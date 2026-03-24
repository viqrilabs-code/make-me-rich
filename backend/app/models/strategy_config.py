from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class StrategyConfig(TimestampMixin, Base):
    __tablename__ = "strategy_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    polling_interval_minutes: Mapped[int] = mapped_column(Integer, default=5)
    mode: Mapped[str] = mapped_column(String(16), default="advisory")
    risk_profile: Mapped[str] = mapped_column(String(32), default="balanced")
    allowed_instruments_json: Mapped[dict] = mapped_column(JSON, default=dict)
    watchlist_symbols_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    max_risk_per_trade_pct: Mapped[float] = mapped_column(Float, default=1.0)
    max_daily_loss_pct: Mapped[float] = mapped_column(Float, default=2.0)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, default=8.0)
    max_open_positions: Mapped[int] = mapped_column(Integer, default=2)
    max_capital_per_trade_pct: Mapped[float] = mapped_column(Float, default=20.0)
    leverage_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    futures_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    options_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    shorting_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    market_hours_only: Mapped[bool] = mapped_column(Boolean, default=True)
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mandatory_stop_loss: Mapped[bool] = mapped_column(Boolean, default=True)
    cooldown_after_losses: Mapped[int] = mapped_column(Integer, default=2)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=60)
    selected_broker: Mapped[str] = mapped_column(String(32), default="mock")
    preferred_llm_provider: Mapped[str] = mapped_column(String(32), default="openai")
    live_mode_armed: Mapped[bool] = mapped_column(Boolean, default=False)
    pause_scheduler: Mapped[bool] = mapped_column(Boolean, default=False)
