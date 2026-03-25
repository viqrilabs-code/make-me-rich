from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AuditLog, StrategyConfig, UserConfig
from app.schemas.market import (
    DailyTopDealItemResponse,
    DailyTopDealsResponse,
    RequestedInstrument,
    TradeCandidateResponse,
    TradeFeatureResponse,
    TradeQuoteResponse,
    TradeSetupResponse,
)
from app.schemas.news import NewsSummaryResponse
from app.services.broker_service import get_active_broker
from app.services.hot_deals_service import build_market_session
from app.services.market_service import MarketService
from app.services.news_service import NewsService
from app.services.strategy_engine import compute_features, generate_candidate_actions
from app.services.trade_setup_service import (
    _align_hold_decision,
    _analysis_note,
    _analysis_strategy,
    _analysis_window,
    _build_chart_points,
    _build_option_contract_plan,
    _ensure_decision_candidate,
    _execution_blockers,
    _filter_candidates,
    _heuristic_decision,
    _make_hold_decision_decisive,
    _mode_note,
    _ranking_score,
    _trade_name,
)


_SCAN_CATEGORY = "daily_top_deals_scan"
_SCAN_INSTRUMENTS: tuple[RequestedInstrument, ...] = ("stock",)
_NSE_QUOTE_SCAN_LIMIT = 240
_NSE_DEEP_SCAN_LIMIT = 80
_NSE_NEWS_SYMBOL_LIMIT = 50


def get_daily_top_deals_snapshot(db: Session) -> DailyTopDealsResponse:
    strategy = db.scalar(select(StrategyConfig).limit(1))
    timezone_name = _effective_timezone(db)
    local_now = datetime.now(ZoneInfo(timezone_name))
    scan_date = local_now.date().isoformat()
    existing = _latest_scan_log(db, scan_date)
    next_trigger_at = _next_trigger_at(local_now, timezone_name)

    if existing:
        response = DailyTopDealsResponse.model_validate(existing.metadata_json or {})
        return response.model_copy(
            update={
                "can_trigger": False,
                "next_trigger_at": next_trigger_at,
            }
        )

    return DailyTopDealsResponse(
        scan_date=scan_date,
        timezone=timezone_name,
        triggered_at=None,
        next_trigger_at=next_trigger_at,
        can_trigger=True,
        universe_label="NSE cash equity universe",
        universe_size=0,
        deep_scan_size=0,
        scan_scope=list(_SCAN_INSTRUMENTS),
        symbols_scanned=[],
        candidate_count=0,
        actionable_count=0,
        message=(
            "Run today's sweep once to scan the full NSE cash-equity universe, then deep-rank the strongest liquid "
            "names and store the top 5 stock-buy ideas for the day."
        ),
        scan_notes=[],
        items=[],
    )


def refresh_daily_top_deals_snapshot(db: Session) -> DailyTopDealsResponse:
    current = get_daily_top_deals_snapshot(db)
    if not current.can_trigger:
        raise ValueError(
            f"Today's top 5 sweep already ran. It unlocks again at {current.next_trigger_at.isoformat()}."
        )

    strategy = db.scalar(select(StrategyConfig).limit(1))
    if not strategy:
        raise ValueError("No strategy configuration available.")
    adapter, active_broker, using_fallback_broker = get_active_broker(db)
    if using_fallback_broker and strategy.selected_broker != "mock":
        raise RuntimeError(
            f"{strategy.selected_broker.upper()} is unavailable right now. "
            "Daily top-deals scan is blocked because falling back to mock prices would be misleading. "
            "Reconnect the live broker in Strategy before running the sweep."
        )
    universe_symbols, quote_scan_symbols = _scan_universe_symbols(strategy, adapter)
    if not universe_symbols:
        raise ValueError("No NSE stock universe is available right now. Check the live broker instruments and try again.")

    market_session = build_market_session()
    chart_interval, chart_lookback = _analysis_window(market_session.market_open)
    market_service = MarketService(adapter)
    quotes_map = market_service.get_quotes_map(quote_scan_symbols)
    deep_scan_symbols = _deep_scan_symbols(quote_scan_symbols, quotes_map, limit=_NSE_DEEP_SCAN_LIMIT)
    if not deep_scan_symbols:
        raise RuntimeError("The NSE quote sweep returned no liquid symbols to deep-scan today.")

    candles_map = market_service.get_candles_map(
        deep_scan_symbols,
        interval=chart_interval,
        lookback=chart_lookback,
    )
    news_symbols = deep_scan_symbols[:_NSE_NEWS_SYMBOL_LIMIT]
    news_summary = NewsService().summarize(news_symbols)

    heuristic_results: list[tuple[float, RequestedInstrument, TradeSetupResponse]] = []
    scan_notes: list[str] = []
    if len(universe_symbols) > len(quote_scan_symbols):
        scan_notes.append(
            f"NSE metadata universe screened: {len(universe_symbols)} symbols. Live quote scan focused on the top {len(quote_scan_symbols)} tradable names first."
        )
    if len(quote_scan_symbols) > len(deep_scan_symbols):
        scan_notes.append(
            f"Deep chart scan focused on the top {len(deep_scan_symbols)} liquid names from that quote-ranked subset."
        )

    for symbol in deep_scan_symbols:
        try:
            symbol_results = _scan_symbol_instruments(
                strategy=strategy,
                symbol=symbol,
                adapter=adapter,
                active_broker=active_broker,
                using_fallback_broker=using_fallback_broker,
                market_session=market_session,
                chart_interval=chart_interval,
                chart_lookback=chart_lookback,
                quote=quotes_map.get(symbol),
                candles=candles_map.get(symbol, []),
                news_summary=_symbol_news_summary(news_summary, symbol),
            )
            heuristic_results.extend(symbol_results)
        except Exception as exc:  # noqa: BLE001
            scan_notes.append(f"{symbol}: {str(exc)}")

    if not heuristic_results:
        raise RuntimeError(
            "No daily top-deals scan could be completed. Check live broker access and Strategy symbols, then try again."
        )

    buy_stock_pool = [
        row for row in heuristic_results if row[1] == "stock" and row[2].decision.action == "BUY_STOCK"
    ]
    shortlisted = sorted(buy_stock_pool, key=lambda row: row[0], reverse=True)[:5]

    items = [
        DailyTopDealItemResponse(
            rank=rank,
            instrument=instrument,
            ranking_score=round(ranking_score, 3),
            actionable=setup.decision.action != "HOLD",
            setup=setup,
        )
        for rank, (ranking_score, instrument, setup) in enumerate(shortlisted, start=1)
    ]

    items.sort(key=lambda item: item.ranking_score, reverse=True)
    items = [
        item.model_copy(update={"rank": index})
        for index, item in enumerate(items, start=1)
    ]

    actionable_count = len(items)
    response = DailyTopDealsResponse(
        scan_date=current.scan_date,
        timezone=current.timezone,
        triggered_at=datetime.now(ZoneInfo(current.timezone)),
        next_trigger_at=current.next_trigger_at,
        can_trigger=False,
        universe_label="NSE cash equity universe",
        universe_size=len(universe_symbols),
        deep_scan_size=len(deep_scan_symbols),
        scan_scope=list(_SCAN_INSTRUMENTS),
        symbols_scanned=deep_scan_symbols,
        candidate_count=len(heuristic_results),
        actionable_count=actionable_count,
        message=(
            "Today's stock-buy sweep is ready. The board scanned the NSE cash-equity universe with a live quote pass, "
            "then ran deeper chart and news analysis on the strongest liquid names."
            if items
            else "Today's sweep found no stock-buy setups strong enough to make the board."
        ),
        scan_notes=scan_notes[:12],
        items=items,
    )

    db.add(
        AuditLog(
            category=_SCAN_CATEGORY,
            message="Daily top 5 deals sweep completed.",
            metadata_json=response.model_dump(mode="json"),
        )
    )
    db.flush()
    return response


def _configured_symbols(strategy: StrategyConfig | None) -> list[str]:
    if strategy is None:
        return []
    values = (
        strategy.watchlist_symbols_json
        or (strategy.allowed_instruments_json or {}).get("symbols")
        or []
    )
    seen: list[str] = []
    for value in values:
        symbol = str(value).strip().upper()
        if symbol and symbol not in seen:
            seen.append(symbol)
    return seen


def _effective_timezone(db: Session) -> str:
    user = db.scalar(select(UserConfig).limit(1))
    return (user.timezone if user else get_settings().timezone) or "Asia/Kolkata"


def _scan_universe_symbols(strategy: StrategyConfig, adapter) -> tuple[list[str], list[str]]:
    universe, quote_scan_symbols = _nse_cash_symbols_from_adapter(adapter)
    if universe:
        return universe, quote_scan_symbols
    if adapter.__class__.__name__.lower().startswith("mock"):
        configured = _configured_symbols(strategy)
        return configured, configured
    raise LookupError(
        "The selected live broker did not return the NSE cash-equity universe. "
        "Reconnect the broker and try the daily sweep again."
    )


def _nse_cash_symbols_from_adapter(adapter) -> tuple[list[str], list[str]]:
    getter = getattr(adapter, "_get_instruments", None)
    if not callable(getter):
        return [], []
    try:
        rows = getter()
    except TypeError:
        rows = getter("equity")
    except Exception:
        return [], []

    scored_symbols: list[tuple[float, str]] = []
    universe_symbols: list[str] = []
    for row in rows:
        exchange = str(row.get("EXCHANGE") or row.get("exchange") or "").upper()
        segment = str(row.get("SEGMENT") or row.get("segment") or "").upper()
        trading_symbol = str(
            row.get("TRADING_SYMBOL")
            or row.get("trading_symbol")
            or row.get("SYMBOL")
            or row.get("symbol")
            or ""
        ).strip().upper()
        if exchange != "NSE" or segment not in {"CASH", "EQ", "EQUITY"}:
            continue
        if not trading_symbol or trading_symbol in universe_symbols:
            continue
        universe_symbols.append(trading_symbol)

        series = str(row.get("SERIES") or row.get("series") or "").upper()
        intraday = str(row.get("IS_INTRADAY") or row.get("is_intraday") or "").strip()
        buy_allowed = str(row.get("BUY_ALLOWED") or row.get("buy_allowed") or "").strip()
        sell_allowed = str(row.get("SELL_ALLOWED") or row.get("sell_allowed") or "").strip()
        freeze_qty_raw = str(row.get("FREEZE_QUANTITY") or row.get("freeze_quantity") or "0").replace(",", "").strip()
        try:
            freeze_quantity = float(freeze_qty_raw or "0")
        except ValueError:
            freeze_quantity = 0.0

        score = freeze_quantity
        if series == "EQ":
            score += 50_000
        if intraday == "1":
            score += 25_000
        if buy_allowed == "1":
            score += 10_000
        if sell_allowed == "1":
            score += 5_000
        scored_symbols.append((score, trading_symbol))

    scored_symbols.sort(key=lambda item: item[0], reverse=True)
    quote_scan_symbols = [symbol for _, symbol in scored_symbols[:_NSE_QUOTE_SCAN_LIMIT]]
    return universe_symbols, quote_scan_symbols


def _deep_scan_symbols(
    universe_symbols: list[str],
    quotes_map,
    *,
    limit: int,
) -> list[str]:
    scored: list[tuple[float, str]] = []
    for symbol in universe_symbols:
        quote = quotes_map.get(symbol)
        if quote is None or quote.ltp <= 0:
            continue
        volume = float(quote.volume or 0.0)
        spread_penalty = max(quote.spread_pct, 0.05)
        liquidity_score = (volume + 1.0) / spread_penalty
        scored.append((liquidity_score, symbol))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [symbol for _, symbol in scored[:limit]]


def _symbol_news_summary(news_summary: NewsSummaryResponse, symbol: str) -> NewsSummaryResponse:
    symbol_items = [item for item in news_summary.items if symbol in item.symbols]
    if symbol_items:
        overall = round(sum(item.sentiment_score for item in symbol_items) / len(symbol_items), 2)
        top_symbols = [{"symbol": symbol, "articles": len(symbol_items)}]
        technical_only = False
        technical_only_reason = None
    else:
        overall = news_summary.overall_sentiment
        top_symbols = []
        technical_only = news_summary.technical_only
        technical_only_reason = news_summary.technical_only_reason

    return NewsSummaryResponse(
        items=symbol_items,
        overall_sentiment=overall,
        top_symbols=top_symbols,
        feed_status=news_summary.feed_status,
        technical_only=technical_only,
        technical_only_reason=technical_only_reason,
    )


def _scan_symbol_instruments(
    *,
    strategy: StrategyConfig,
    symbol: str,
    adapter,
    active_broker: str,
    using_fallback_broker: bool,
    market_session,
    chart_interval: str,
    chart_lookback: int,
    quote,
    candles,
    news_summary: NewsSummaryResponse,
) -> list[tuple[float, RequestedInstrument, TradeSetupResponse]]:
    if quote is None:
        raise LookupError(f"No quote available for {symbol}.")
    if len(candles) < 20:
        raise LookupError(f"Not enough historical candles available for {symbol}.")

    features = compute_features(symbol, candles)
    results: list[tuple[float, RequestedInstrument, TradeSetupResponse]] = []

    for instrument in _SCAN_INSTRUMENTS:
        analysis_strategy = _analysis_strategy(strategy, instrument)
        candidates = generate_candidate_actions(
            strategy=analysis_strategy,
            features=features,
            news_sentiment=news_summary.overall_sentiment,
        )
        filtered_candidates = _filter_candidates(candidates, instrument)
        if not filtered_candidates:
            filtered_candidates = candidates[:1]

        decision = _heuristic_decision(
            symbol=symbol,
            requested_instrument=instrument,
            quote=quote,
            features=features,
            candidates=filtered_candidates,
        )
        decision = _align_hold_decision(decision, instrument)
        decision = _make_hold_decision_decisive(decision, instrument)
        filtered_candidates = _ensure_decision_candidate(filtered_candidates, decision)
        execution_blockers = _execution_blockers(strategy, instrument, decision.action)
        option_contract = (
            _build_option_contract_plan(adapter, symbol, quote.ltp, features.atr, decision)
            if instrument == "option"
            else None
        )
        trade_name = _trade_name(symbol, instrument, decision, option_contract)
        setup = TradeSetupResponse(
            symbol=symbol,
            trade_name=trade_name,
            requested_instrument=instrument,
            chart_interval=chart_interval,
            chart_lookback=chart_lookback,
            analysis_generated_at=datetime.now(ZoneInfo("UTC")),
            analysis_engine="heuristic",
            selected_broker=strategy.selected_broker,
            active_broker=active_broker,
            using_fallback_broker=using_fallback_broker,
            execution_ready=not execution_blockers and decision.action != "HOLD",
            execution_blockers=execution_blockers,
            mode_note=_mode_note(strategy.mode),
            analysis_note=_analysis_note(news_summary),
            market_session=market_session,
            quote=TradeQuoteResponse(
                symbol=quote.symbol,
                ltp=quote.ltp,
                bid=quote.bid,
                ask=quote.ask,
                spread_pct=round(quote.spread_pct, 3),
                timestamp=quote.timestamp,
                volume=quote.volume,
            ),
            features=TradeFeatureResponse(**asdict(features)),
            candidates=[TradeCandidateResponse(**candidate.to_dict()) for candidate in filtered_candidates],
            decision=decision,
            news_summary=news_summary,
            chart_points=_build_chart_points(candles),
            option_contract=option_contract,
        )
        results.append((_ranking_score(setup), instrument, setup))

    return results


def _latest_scan_log(db: Session, scan_date: str) -> AuditLog | None:
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.category == _SCAN_CATEGORY)
        .order_by(AuditLog.timestamp.desc())
        .limit(25)
    ).all()
    for row in rows:
        metadata = row.metadata_json or {}
        if str(metadata.get("scan_date") or "") == scan_date:
            return row
    return None


def _next_trigger_at(local_now: datetime, timezone_name: str) -> datetime:
    tomorrow = (local_now + timedelta(days=1)).date()
    return datetime.combine(tomorrow, datetime.min.time(), tzinfo=ZoneInfo(timezone_name))
