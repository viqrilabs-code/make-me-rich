from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AgentStartRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    launched_from: str = Field(default="overview", max_length=32)


class AgentEventResponse(BaseModel):
    id: int
    agent_session_id: int
    timestamp: datetime
    phase: str
    event_type: str
    severity: str
    message: str
    metadata_json: dict


class AgentSessionResponse(BaseModel):
    id: int
    symbol: str
    status: str
    mode: str
    selected_broker: str
    target_multiplier: float
    start_equity: float
    current_equity: float
    target_equity: float
    auto_execute: bool
    launched_from: str
    allowed_lanes_json: list[str]
    heartbeat_at: datetime | None = None
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    last_message: str | None = None
    progress_pct: float
    cash_balance: float = 0.0
    margin_available: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    today_pnl: float = 0.0
    today_pnl_pct: float = 0.0
    session_pnl: float = 0.0
    session_pnl_pct: float = 0.0
    target_gap: float = 0.0
    raw_state_json: dict


class AgentStatusResponse(BaseModel):
    active: bool
    can_start: bool
    suggested_symbol: str | None = None
    message: str | None = None
    session: AgentSessionResponse | None = None
    recent_events: list[AgentEventResponse]


class AgentCommandResponse(BaseModel):
    message: str
    session: AgentSessionResponse | None = None
