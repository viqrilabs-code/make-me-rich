from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import SchedulerRun, StrategyConfig
from app.scheduler.engine import scheduler_manager
from app.schemas.scheduler import SchedulerStatusResponse
from app.utils.time import ensure_utc


router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


@router.get("/status", response_model=SchedulerStatusResponse)
def scheduler_status(_: object = Depends(get_current_user), db: Session = Depends(get_db)) -> SchedulerStatusResponse:
    strategy = db.scalar(select(StrategyConfig).limit(1))
    latest_run = db.scalar(select(SchedulerRun).order_by(SchedulerRun.started_at.desc()).limit(1))
    status_payload = scheduler_manager.status()
    return SchedulerStatusResponse(
        running=status_payload["running"],
        paused=bool(strategy.pause_scheduler) if strategy else False,
        poll_interval_minutes=strategy.polling_interval_minutes if strategy else 5,
        last_run_at=ensure_utc(latest_run.started_at) if latest_run else None,
        next_due_at=ensure_utc(status_payload["next_due_at"]),
        active_jobs=status_payload["active_jobs"],
        lock_state=status_payload["lock_state"],
    )
