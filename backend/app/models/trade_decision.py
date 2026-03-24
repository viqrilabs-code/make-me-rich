from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TradeDecision(Base):
    __tablename__ = "trade_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[str] = mapped_column(String(32))
    instrument_type: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    rationale_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    llm_response_json: Mapped[dict] = mapped_column(JSON, default=dict)
    candidate_actions_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    rejection_reasons_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    scheduler_run_id: Mapped[int | None] = mapped_column(ForeignKey("scheduler_runs.id"))

    scheduler_run: Mapped["SchedulerRun | None"] = relationship(back_populates="decisions")

