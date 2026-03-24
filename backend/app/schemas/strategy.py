from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class StrategyUpdate(BaseModel):
    polling_interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    mode: str | None = Field(default=None, pattern="^(advisory|paper|live)$")
    risk_profile: str | None = None
    allowed_instruments_json: dict | None = None
    watchlist_symbols_json: list[str] | None = None
    max_risk_per_trade_pct: float | None = Field(default=None, ge=0.1, le=10.0)
    max_daily_loss_pct: float | None = Field(default=None, ge=0.1, le=20.0)
    max_drawdown_pct: float | None = Field(default=None, ge=0.5, le=50.0)
    max_open_positions: int | None = Field(default=None, ge=1, le=20)
    max_capital_per_trade_pct: float | None = Field(default=None, ge=1.0, le=100.0)
    leverage_enabled: bool | None = None
    futures_enabled: bool | None = None
    options_enabled: bool | None = None
    shorting_enabled: bool | None = None
    market_hours_only: bool | None = None
    mandatory_stop_loss: bool | None = None
    selected_broker: str | None = None
    preferred_llm_provider: str | None = Field(default=None, pattern="^(openai|anthropic|gemini)$")
    live_mode_armed: bool | None = None
    pause_scheduler: bool | None = None


class StrategyResponse(ORMModel):
    id: int
    polling_interval_minutes: int
    mode: str
    risk_profile: str
    allowed_instruments_json: dict
    watchlist_symbols_json: list[str]
    max_risk_per_trade_pct: float
    max_daily_loss_pct: float
    max_drawdown_pct: float
    max_open_positions: int
    max_capital_per_trade_pct: float
    leverage_enabled: bool
    futures_enabled: bool
    options_enabled: bool
    shorting_enabled: bool
    market_hours_only: bool
    kill_switch: bool
    cooldown_until: datetime | None
    mandatory_stop_loss: bool
    cooldown_after_losses: int
    cooldown_minutes: int
    selected_broker: str
    preferred_llm_provider: str
    live_mode_armed: bool
    pause_scheduler: bool
    created_at: datetime
    updated_at: datetime
