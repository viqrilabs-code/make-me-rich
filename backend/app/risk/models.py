from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.brokers.types import Quote
from app.llm.schemas import LLMDecisionResponse
from app.models import Position, StrategyConfig


@dataclass(slots=True)
class RiskEvaluationContext:
    strategy: StrategyConfig
    decision: LLMDecisionResponse
    account_equity: float
    daily_loss_pct: float
    drawdown_pct: float
    open_positions: list[Position]
    existing_position: Position | None
    quote: Quote | None
    duplicate_keys: set[str]
    now: datetime
    market_open: bool
    stale_after_minutes: int


@dataclass(slots=True)
class RiskEvaluationResult:
    approved: bool
    rejection_reasons: list[str] = field(default_factory=list)
    computed_position_size: float = 0.0
    final_order_payload: dict | None = None

