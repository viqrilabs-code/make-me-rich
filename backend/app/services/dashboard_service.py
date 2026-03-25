from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from threading import Lock

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.brokers.types import BrokerAccount, BrokerPosition
from app.core.config import get_settings
from app.models import DailyPerformance, PortfolioSnapshot, Position, RiskEvent, StrategyConfig, TradeDecision, TradingGoal
from app.schemas.decision import LatestDecisionSummary
from app.schemas.portfolio import OverviewResponse, PortfolioSnapshotResponse, PositionResponse
from app.services.broker_service import get_active_broker
from app.services.credential_service import is_trade_fetch_ready, missing_trade_credentials
from app.services.execution_service import ExecutionService
from app.services.hot_deals_service import build_market_session


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _BrokerPortfolioCacheEntry:
    selected_broker: str
    broker_name: str
    using_fallback: bool
    broker_account: BrokerAccount | None
    broker_positions: list[BrokerPosition]
    fetched_at: datetime


_BROKER_PORTFOLIO_CACHE: _BrokerPortfolioCacheEntry | None = None
_BROKER_PORTFOLIO_CACHE_LOCK = Lock()
_BROKER_PORTFOLIO_CACHE_TTL = timedelta(seconds=45)
_BROKER_PORTFOLIO_CACHE_STALE_TTL = timedelta(minutes=5)


def _get_broker_cache(
    selected_broker: str,
    *,
    max_age: timedelta,
) -> _BrokerPortfolioCacheEntry | None:
    entry = _BROKER_PORTFOLIO_CACHE
    if entry is None or entry.selected_broker != selected_broker:
        return None
    if datetime.now(timezone.utc) - entry.fetched_at > max_age:
        return None
    return entry


def _set_broker_cache(
    selected_broker: str,
    broker_name: str,
    using_fallback: bool,
    broker_account: BrokerAccount | None,
    broker_positions: list[BrokerPosition],
) -> None:
    global _BROKER_PORTFOLIO_CACHE
    _BROKER_PORTFOLIO_CACHE = _BrokerPortfolioCacheEntry(
        selected_broker=selected_broker,
        broker_name=broker_name,
        using_fallback=using_fallback,
        broker_account=broker_account,
        broker_positions=list(broker_positions),
        fetched_at=datetime.now(timezone.utc),
    )


def _cache_result(
    latest_snapshot: PortfolioSnapshot | None,
    latest_daily_performance: DailyPerformance | None,
    cache_entry: _BrokerPortfolioCacheEntry,
) -> tuple[
    PortfolioSnapshot | None,
    DailyPerformance | None,
    BrokerAccount | None,
    list[BrokerPosition],
    str,
    bool,
]:
    return (
        latest_snapshot,
        latest_daily_performance,
        cache_entry.broker_account,
        list(cache_entry.broker_positions),
        cache_entry.broker_name,
        cache_entry.using_fallback,
    )


def _build_snapshot_response(
    latest_snapshot: PortfolioSnapshot | None,
    account: BrokerAccount | None,
    broker_name: str | None,
) -> PortfolioSnapshotResponse | None:
    if account is None:
        return PortfolioSnapshotResponse.model_validate(latest_snapshot) if latest_snapshot else None

    return PortfolioSnapshotResponse(
        id=latest_snapshot.id if latest_snapshot else 0,
        timestamp=datetime.now(timezone.utc),
        cash_balance=account.cash_balance,
        total_equity=account.total_equity,
        margin_available=account.margin_available,
        realized_pnl=account.realized_pnl,
        unrealized_pnl=account.unrealized_pnl,
        source=f"live:{broker_name or account.source}",
        raw_payload_json=account.raw_payload,
    )


def _dedupe_broker_positions(positions: list[BrokerPosition]) -> list[BrokerPosition]:
    deduped: list[BrokerPosition] = []
    seen: set[tuple[str, str, str, str]] = set()
    for position in positions:
        key = (
            position.broker_position_id or "",
            position.symbol,
            position.instrument_type,
            position.side,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(position)
    return deduped


def _build_broker_position_rows(
    broker_positions: list[BrokerPosition],
    synced_at: datetime,
) -> list[PositionResponse]:
    return [
        PositionResponse(
            id=-(index + 1),
            symbol=position.symbol,
            instrument_type=position.instrument_type,
            side=position.side,
            quantity=position.quantity,
            avg_price=position.avg_price,
            current_price=position.current_price,
            unrealized_pnl=position.unrealized_pnl,
            realized_pnl=0.0,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            opened_at=synced_at,
            closed_at=None,
            status="open",
            broker_position_id=position.broker_position_id,
            mode=position.mode,
            raw_payload_json={**position.raw_payload, "synced_from_broker": True},
        )
        for index, position in enumerate(broker_positions)
    ]


def _should_refresh_snapshot(
    latest_snapshot: PortfolioSnapshot | None,
    account: BrokerAccount,
) -> bool:
    if latest_snapshot is None:
        return True

    snapshot_age = datetime.now(timezone.utc) - latest_snapshot.timestamp.replace(tzinfo=timezone.utc)
    materially_changed = any(
        abs(current - previous) >= 0.01
        for current, previous in [
            (account.cash_balance, latest_snapshot.cash_balance),
            (account.total_equity, latest_snapshot.total_equity),
            (account.margin_available, latest_snapshot.margin_available),
            (account.realized_pnl, latest_snapshot.realized_pnl),
            (account.unrealized_pnl, latest_snapshot.unrealized_pnl),
        ]
    )
    return snapshot_age >= timedelta(minutes=2) or materially_changed


def refresh_live_portfolio_cache(
    db: Session,
) -> tuple[
    PortfolioSnapshot | None,
    DailyPerformance | None,
    BrokerAccount | None,
    list[BrokerPosition],
    str,
    bool,
]:
    strategy = db.scalar(select(StrategyConfig).limit(1))
    latest_snapshot = db.scalar(
        select(PortfolioSnapshot).order_by(PortfolioSnapshot.timestamp.desc()).limit(1)
    )
    latest_daily_performance = db.scalar(
        select(DailyPerformance).order_by(DailyPerformance.trading_date.desc()).limit(1)
    )
    if not strategy:
        return latest_snapshot, latest_daily_performance, None, [], "mock", False

    selected_broker = strategy.selected_broker
    cached = _get_broker_cache(selected_broker, max_age=_BROKER_PORTFOLIO_CACHE_TTL)
    if cached:
        return _cache_result(latest_snapshot, latest_daily_performance, cached)

    with _BROKER_PORTFOLIO_CACHE_LOCK:
        cached = _get_broker_cache(selected_broker, max_age=_BROKER_PORTFOLIO_CACHE_TTL)
        if cached:
            return _cache_result(latest_snapshot, latest_daily_performance, cached)

        adapter, broker_name, using_fallback = get_active_broker(db)
        if using_fallback and selected_broker != "mock":
            _set_broker_cache(
                selected_broker=selected_broker,
                broker_name=selected_broker,
                using_fallback=True,
                broker_account=None,
                broker_positions=[],
            )
            return latest_snapshot, latest_daily_performance, None, [], selected_broker, True

        broker_account: BrokerAccount | None = None
        broker_positions: list[BrokerPosition] = []

        try:
            broker_account = adapter.get_account()
            broker_positions = adapter.get_positions()
            try:
                broker_positions.extend(adapter.get_holdings())
            except Exception as exc:  # noqa: BLE001
                logger.warning("Live holdings unavailable", extra={"error": str(exc)})
            broker_positions = _dedupe_broker_positions(broker_positions)

            if broker_account and _should_refresh_snapshot(latest_snapshot, broker_account):
                execution = ExecutionService(adapter)
                latest_snapshot = execution.record_snapshot(
                    db,
                    broker_account,
                    source=f"view:{broker_name}",
                )
                db.flush()
                execution.update_daily_performance(db)
                latest_daily_performance = db.scalar(
                    select(DailyPerformance).order_by(DailyPerformance.trading_date.desc()).limit(1)
                )

            _set_broker_cache(
                selected_broker=selected_broker,
                broker_name=broker_name,
                using_fallback=using_fallback,
                broker_account=broker_account,
                broker_positions=broker_positions,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Live broker refresh unavailable", extra={"error": str(exc)})
            stale_cache = _get_broker_cache(selected_broker, max_age=_BROKER_PORTFOLIO_CACHE_STALE_TTL)
            if stale_cache:
                return _cache_result(latest_snapshot, latest_daily_performance, stale_cache)

    return (
        latest_snapshot,
        latest_daily_performance,
        broker_account,
        broker_positions,
        broker_name,
        using_fallback,
    )


def build_latest_snapshot(db: Session) -> PortfolioSnapshotResponse | None:
    latest_snapshot, _, broker_account, _, broker_name, _ = refresh_live_portfolio_cache(db)
    return _build_snapshot_response(latest_snapshot, broker_account, broker_name)


def build_overview(db: Session) -> OverviewResponse:
    settings = get_settings()
    goal = db.scalar(select(TradingGoal).order_by(TradingGoal.updated_at.desc()).limit(1))
    strategy = db.scalar(select(StrategyConfig).limit(1))
    open_positions = db.scalars(
        select(Position).where(Position.status == "open").order_by(Position.opened_at.desc())
    ).all()
    latest_decision = db.scalar(
        select(TradeDecision).order_by(TradeDecision.timestamp.desc()).limit(1)
    )
    latest_risk_event = db.scalar(
        select(RiskEvent).order_by(RiskEvent.timestamp.desc()).limit(1)
    )

    (
        latest_snapshot,
        latest_daily_performance,
        broker_account,
        broker_positions,
        broker_name,
        using_fallback_broker,
    ) = refresh_live_portfolio_cache(db)

    snapshot_response = _build_snapshot_response(latest_snapshot, broker_account, broker_name)
    target_capital = goal.target_amount if goal else 0.0
    current_capital = (
        broker_account.total_equity
        if broker_account
        else latest_snapshot.total_equity
        if latest_snapshot
        else 0.0
    )
    progress = 0.0 if target_capital == 0 else min((current_capital / target_capital) * 100, 100.0)

    invested_capital = round(sum(abs(position.quantity) * position.avg_price for position in open_positions), 2)
    if broker_positions:
        invested_capital = round(
            sum(abs(position.quantity) * (position.current_price or position.avg_price) for position in broker_positions),
            2,
        )

    position_rows = [PositionResponse.model_validate(position) for position in open_positions]
    if broker_positions:
        synced_at = snapshot_response.timestamp if snapshot_response else datetime.now(timezone.utc)
        position_rows = _build_broker_position_rows(broker_positions, synced_at)

    todays_pnl = 0.0
    todays_pnl_pct = 0.0
    if latest_daily_performance and latest_daily_performance.opening_equity > 0:
        todays_pnl = round(current_capital - latest_daily_performance.opening_equity, 2)
        todays_pnl_pct = round(
            (todays_pnl / latest_daily_performance.opening_equity) * 100,
            2,
        )
    elif broker_account:
        todays_pnl = round(broker_account.realized_pnl + broker_account.unrealized_pnl, 2)
    elif latest_snapshot:
        todays_pnl = round(latest_snapshot.realized_pnl + latest_snapshot.unrealized_pnl, 2)

    market_session = build_market_session()
    hot_deals = []
    watchlist_symbols = (
        strategy.watchlist_symbols_json
        if strategy and strategy.watchlist_symbols_json
        else settings.default_watchlist_symbols
    )
    available_instruments = ["stock"]
    if strategy and strategy.options_enabled:
        available_instruments.append("option")
    if strategy and strategy.futures_enabled:
        available_instruments.append("future")

    selected_broker = strategy.selected_broker if strategy else broker_name
    trade_ready = is_trade_fetch_ready(db, selected_broker)
    missing_credentials = missing_trade_credentials(db, selected_broker)

    return OverviewResponse(
        latest_snapshot=snapshot_response,
        goal_progress_pct=round(progress, 2),
        target_capital=target_capital,
        current_capital=current_capital,
        invested_capital=invested_capital,
        todays_pnl=todays_pnl,
        todays_pnl_pct=todays_pnl_pct,
        open_positions=position_rows,
        latest_decision=(
            LatestDecisionSummary(
                timestamp=latest_decision.timestamp,
                symbol=latest_decision.symbol,
                action=latest_decision.action,
                confidence=latest_decision.confidence,
                approved=latest_decision.approved,
            )
            if latest_decision
            else None
        ),
        latest_risk_event=(
            {
                "timestamp": latest_risk_event.timestamp,
                "event_type": latest_risk_event.event_type,
                "severity": latest_risk_event.severity,
                "message": latest_risk_event.message,
            }
            if latest_risk_event
            else None
        ),
        strategy_mode=strategy.mode if strategy else "advisory",
        active_broker=broker_name,
        using_fallback_broker=using_fallback_broker,
        watchlist_symbols=watchlist_symbols,
        available_instruments=available_instruments,
        trade_fetch_ready=trade_ready,
        missing_trade_credentials=missing_credentials,
        market_session=market_session,
        hot_deals=hot_deals,
    )
