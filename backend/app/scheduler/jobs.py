from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import StrategyConfig
from app.services.broker_service import get_active_broker
from app.services.monitoring_service import MonitoringService
from app.services.orchestration_service import run_trading_cycle, should_run_poll, sync_portfolio_state


def poll_job(db: Session) -> dict:
    should_run, _ = should_run_poll(db)
    if not should_run:
        return {"status": "skipped"}
    return run_trading_cycle(db, trigger="scheduler")


def startup_sync_job(db: Session) -> dict:
    return sync_portfolio_state(db, trigger="startup")


def monitor_positions_job(db: Session) -> dict:
    strategy = db.scalar(select(StrategyConfig).limit(1))
    if not strategy:
        return {"status": "missing_strategy"}
    adapter, _, _ = get_active_broker(db)
    return MonitoringService(adapter).reconcile_open_positions(db, strategy)


def eod_summary_job(db: Session) -> dict:
    return monitor_positions_job(db)
