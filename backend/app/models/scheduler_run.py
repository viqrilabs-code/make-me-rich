from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SchedulerRun(Base):
    __tablename__ = "scheduler_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    lock_acquired: Mapped[bool] = mapped_column(Boolean, default=False)
    actions_taken_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    error_message: Mapped[str | None] = mapped_column(String(512))

    decisions: Mapped[list["TradeDecision"]] = relationship(back_populates="scheduler_run")

