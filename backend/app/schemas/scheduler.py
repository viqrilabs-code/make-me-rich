from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SchedulerStatusResponse(BaseModel):
    running: bool
    paused: bool
    poll_interval_minutes: int
    last_run_at: datetime | None = None
    next_due_at: datetime | None = None
    active_jobs: list[dict]
    lock_state: str

