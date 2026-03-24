from __future__ import annotations

from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import StrategyConfig
from app.scheduler.lock import scheduler_lock
from app.services.broker_service import get_active_broker
from app.services.monitoring_service import MonitoringService
from app.services.orchestration_service import run_trading_cycle, should_run_poll, sync_portfolio_state
from app.utils.time import ensure_utc


class SchedulerManager:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.scheduler = BackgroundScheduler(timezone="UTC")
        self.started = False

    def start(self) -> None:
        if self.started:
            return
        self.scheduler.add_job(
            self._poll_wrapper,
            IntervalTrigger(minutes=1),
            id="trading-poll",
            replace_existing=True,
            max_instances=1,
        )
        self.scheduler.add_job(
            self._monitor_wrapper,
            IntervalTrigger(minutes=self.settings.scheduler_monitor_minutes),
            id="open-position-monitor",
            replace_existing=True,
            max_instances=1,
        )
        self.scheduler.add_job(
            self._eod_wrapper,
            CronTrigger(hour=10, minute=30),
            id="end-of-day-summary",
            replace_existing=True,
            max_instances=1,
        )
        self.scheduler.start()
        self.started = True
        with SessionLocal() as db:
            sync_portfolio_state(db, trigger="startup")
            db.commit()

    def shutdown(self) -> None:
        if self.started:
            self.scheduler.shutdown(wait=False)
            self.started = False

    def _poll_wrapper(self) -> None:
        if not scheduler_lock.acquire():
            return
        try:
            with SessionLocal() as db:
                should_run, _ = should_run_poll(db)
                if should_run:
                    run_trading_cycle(db, trigger="scheduler")
                    db.commit()
        finally:
            scheduler_lock.release()

    def _monitor_wrapper(self) -> None:
        if not scheduler_lock.acquire():
            return
        try:
            with SessionLocal() as db:
                strategy = db.scalar(select(StrategyConfig).limit(1))
                if not strategy:
                    return
                adapter, _, _ = get_active_broker(db)
                MonitoringService(adapter).reconcile_open_positions(db, strategy)
                db.commit()
        finally:
            scheduler_lock.release()

    def _eod_wrapper(self) -> None:
        if not scheduler_lock.acquire():
            return
        try:
            with SessionLocal() as db:
                strategy = db.scalar(select(StrategyConfig).limit(1))
                if not strategy:
                    return
                adapter, _, _ = get_active_broker(db)
                MonitoringService(adapter).reconcile_open_positions(db, strategy)
                db.commit()
        finally:
            scheduler_lock.release()

    def status(self) -> dict:
        with SessionLocal() as db:
            strategy = db.scalar(select(StrategyConfig).limit(1))
            _, next_due = should_run_poll(db)
        return {
            "running": self.started,
            "paused": bool(strategy.pause_scheduler) if strategy else False,
            "poll_interval_minutes": strategy.polling_interval_minutes if strategy else self.settings.scheduler_poll_fallback_minutes,
            "last_checked_at": datetime.now(timezone.utc),
            "next_due_at": ensure_utc(next_due),
            "active_jobs": [
                {"id": job.id, "next_run_time": ensure_utc(job.next_run_time)}
                for job in self.scheduler.get_jobs()
            ],
            "lock_state": scheduler_lock.state(),
        }


scheduler_manager = SchedulerManager()
