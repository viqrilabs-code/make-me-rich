from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.llm import LLMDecisionEngine, fallback_hold
from app.models import DailyPerformance, Order, Position, SchedulerRun, StrategyConfig, TradeDecision, TradingGoal
from app.risk.engine import RiskEngine
from app.risk.models import RiskEvaluationContext
from app.services.audit_service import add_audit_log, add_risk_event
from app.services.broker_service import get_active_broker
from app.services.execution_service import ExecutionService
from app.services.goal_planner import compute_goal_plan
from app.services.market_service import MarketService
from app.services.news_service import NewsService
from app.services.strategy_engine import compute_features, generate_candidate_actions
from app.utils.time import ensure_utc, is_market_open


logger = logging.getLogger(__name__)


def sync_portfolio_state(db: Session, trigger: str = "startup") -> dict:
    strategy = db.scalar(select(StrategyConfig).limit(1))
    if not strategy:
        return {"status": "missing_configuration"}

    adapter, broker_name, using_fallback = get_active_broker(db)
    execution = ExecutionService(adapter)
    account = adapter.get_account()
    snapshot = execution.record_snapshot(db, account, source=f"sync:{trigger}")
    performance = execution.update_daily_performance(db)
    add_audit_log(
        db,
        category="scheduler",
        message="Portfolio state synced.",
        metadata={
            "trigger": trigger,
            "broker": broker_name,
            "using_fallback": using_fallback,
            "snapshot_source": snapshot.source,
        },
    )
    return {
        "status": "synced",
        "broker": broker_name,
        "using_fallback": using_fallback,
        "snapshot_id": snapshot.id,
        "daily_performance_id": performance.id if performance else None,
    }


def should_run_poll(db: Session) -> tuple[bool, datetime | None]:
    strategy = db.scalar(select(StrategyConfig).limit(1))
    if not strategy or strategy.pause_scheduler:
        return False, None
    last_run = db.scalar(
        select(SchedulerRun)
        .where(SchedulerRun.lock_acquired.is_(True))
        .order_by(SchedulerRun.started_at.desc())
        .limit(1)
    )
    if not last_run:
        return True, None
    started_at = ensure_utc(last_run.started_at)
    if started_at is None:
        return True, None
    next_due = started_at + timedelta(minutes=strategy.polling_interval_minutes)
    return datetime.now(timezone.utc) >= next_due, next_due


def run_trading_cycle(db: Session, trigger: str = "scheduler") -> dict:
    settings = get_settings()
    strategy = db.scalar(select(StrategyConfig).limit(1))
    goal = db.scalar(select(TradingGoal).order_by(TradingGoal.updated_at.desc()).limit(1))
    if not strategy or not goal:
        return {"status": "missing_configuration"}

    scheduler_run = SchedulerRun(
        started_at=datetime.now(timezone.utc),
        completed_at=None,
        status="running",
        lock_acquired=True,
        actions_taken_json=[],
        error_message=None,
    )
    db.add(scheduler_run)
    db.flush()

    adapter, broker_name, using_fallback = get_active_broker(db)
    execution = ExecutionService(adapter)
    news_service = NewsService()
    llm_engine = LLMDecisionEngine()
    risk_engine = RiskEngine()

    try:
        open_positions = db.scalars(select(Position).where(Position.status == "open")).all()
        symbols = sorted(
            set(strategy.watchlist_symbols_json or settings.default_watchlist_symbols)
            | {position.symbol for position in open_positions}
        )
        if not symbols:
            symbols = settings.default_watchlist_symbols

        account = adapter.get_account()
        execution.record_snapshot(db, account, source=f"cycle:{trigger}")

        market_service = MarketService(adapter)
        quotes = market_service.get_quotes_map(symbols)
        candles = market_service.get_candles_map(symbols)
        news_summary = news_service.summarize(symbols)

        feature_rows = []
        candidate_actions = []
        sentiment_by_symbol = {
            item["symbol"]: news_summary.overall_sentiment
            for item in news_summary.top_symbols
        }
        for symbol in symbols:
            feature = compute_features(symbol, candles[symbol])
            feature_rows.append(feature.to_dict())
            candidate_actions.extend(
                candidate.to_dict()
                for candidate in generate_candidate_actions(
                    strategy=strategy,
                    features=feature,
                    news_sentiment=sentiment_by_symbol.get(symbol, news_summary.overall_sentiment),
                )[:3]
            )

        candidate_actions = sorted(candidate_actions, key=lambda item: item["score"], reverse=True)[:12]
        current_capital = account.total_equity
        goal_plan = compute_goal_plan(goal, current_capital=current_capital)

        latest_performance = db.scalar(
            select(DailyPerformance).order_by(DailyPerformance.trading_date.desc()).limit(1)
        )
        daily_loss_pct = 0.0
        drawdown_pct = latest_performance.drawdown_pct if latest_performance else 0.0
        if latest_performance and latest_performance.opening_equity > 0:
            daily_loss_pct = max(
                ((latest_performance.opening_equity - current_capital) / latest_performance.opening_equity) * 100,
                0.0,
            )

        llm_context = {
            "default_symbol": symbols[0] if symbols else "CASH",
            "profit_target_note": "Target multiplier is aspirational and not guaranteed.",
            "goal_plan": asdict(goal_plan),
            "portfolio": {
                "current_capital": current_capital,
                "cash_balance": account.cash_balance,
                "realized_pnl": account.realized_pnl,
                "unrealized_pnl": account.unrealized_pnl,
            },
            "strategy": {
                "mode": strategy.mode,
                "risk_profile": strategy.risk_profile,
                "allowed_instruments": strategy.allowed_instruments_json,
                "selected_broker": broker_name,
                "using_fallback_broker": using_fallback,
            },
            "technical_features": feature_rows,
            "candidate_actions": candidate_actions,
            "quotes": {symbol: quote.model_dump() for symbol, quote in quotes.items()},
            "news_summary": news_summary.model_dump(),
        }

        decision = llm_engine.request_decision(llm_context, db)
        if not candidate_actions:
            decision = fallback_hold(rationale="No candidates available.")

        existing_position = next((position for position in open_positions if position.symbol == decision.symbol), None)
        recent_orders = db.scalars(
            select(Order).where(Order.placed_at >= datetime.now(timezone.utc) - timedelta(hours=24))
        ).all()
        risk_result = risk_engine.evaluate(
            RiskEvaluationContext(
                strategy=strategy,
                decision=decision,
                account_equity=current_capital,
                daily_loss_pct=daily_loss_pct,
                drawdown_pct=drawdown_pct,
                open_positions=open_positions,
                existing_position=existing_position,
                quote=quotes.get(decision.symbol),
                duplicate_keys={
                    f"{order.symbol}:{order.raw_payload_json.get('decision_action')}:{order.side}"
                    for order in recent_orders
                },
                now=datetime.now(timezone.utc),
                market_open=is_market_open(),
                stale_after_minutes=settings.market_stale_after_minutes,
            )
        )

        decision_row = TradeDecision(
            timestamp=datetime.now(timezone.utc),
            symbol=decision.symbol,
            action=decision.action,
            instrument_type=decision.instrument_type,
            confidence=decision.confidence,
            rationale_json=decision.rationale_points,
            llm_response_json=decision.model_dump(),
            candidate_actions_json=candidate_actions,
            approved=risk_result.approved,
            rejection_reasons_json=risk_result.rejection_reasons,
            scheduler_run_id=scheduler_run.id,
        )
        db.add(decision_row)
        db.flush()

        if not risk_result.approved:
            add_risk_event(
                db,
                event_type="risk_rejection",
                severity="warning",
                message="Trade rejected by risk engine.",
                metadata={"symbol": decision.symbol, "reasons": risk_result.rejection_reasons},
            )

        execution_result = execution.execute(
            db,
            strategy=strategy,
            decision=decision,
            risk_result=risk_result,
            scheduler_run_id=scheduler_run.id,
        )
        execution.update_daily_performance(db)

        scheduler_run.completed_at = datetime.now(timezone.utc)
        scheduler_run.status = "completed"
        scheduler_run.actions_taken_json = [
            {
                "decision_id": decision_row.id,
                "decision": decision.action,
                "approved": risk_result.approved,
                "execution": execution_result,
            }
        ]
        add_audit_log(
            db,
            category="scheduler",
            message="Trading cycle completed.",
            metadata={"trigger": trigger, "run_id": scheduler_run.id},
        )
        return {
            "status": "completed",
            "run_id": scheduler_run.id,
            "decision_id": decision_row.id,
            "approved": risk_result.approved,
            "execution": execution_result,
        }
    except Exception as exc:  # noqa: BLE001
        scheduler_run.completed_at = datetime.now(timezone.utc)
        scheduler_run.status = "failed"
        scheduler_run.error_message = str(exc)
        add_audit_log(
            db,
            category="scheduler",
            message="Trading cycle failed.",
            metadata={"error": str(exc), "trigger": trigger},
        )
        logger.exception("Trading cycle failed")
        return {"status": "failed", "error": str(exc)}
