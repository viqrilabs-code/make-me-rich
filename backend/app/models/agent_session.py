from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AgentSession(TimestampMixin, Base):
    __tablename__ = "agent_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="idle")
    mode: Mapped[str] = mapped_column(String(16), default="advisory")
    selected_broker: Mapped[str] = mapped_column(String(32), default="mock")
    target_multiplier: Mapped[float] = mapped_column(Float, default=1.2)
    start_equity: Mapped[float] = mapped_column(Float, default=0.0)
    current_equity: Mapped[float] = mapped_column(Float, default=0.0)
    target_equity: Mapped[float] = mapped_column(Float, default=0.0)
    auto_execute: Mapped[bool] = mapped_column(Boolean, default=False)
    launched_from: Mapped[str] = mapped_column(String(32), default="overview")
    allowed_lanes_json: Mapped[list] = mapped_column(JSON, default=list)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message: Mapped[str | None] = mapped_column(String(255))
    raw_state_json: Mapped[dict] = mapped_column(JSON, default=dict)
