from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


ALLOWED_ACTIONS = {
    "HOLD",
    "EXIT",
    "REDUCE",
    "BUY_STOCK",
    "SELL_STOCK",
    "BUY_CALL",
    "BUY_PUT",
    "BUY_FUTURE",
    "SELL_FUTURE",
}


class LLMDecisionResponse(BaseModel):
    decision: str
    symbol: str
    instrument_type: str
    action: str
    side: str
    quantity: float = Field(ge=0)
    entry_type: str
    entry_price_hint: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    max_holding_minutes: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale_points: list[str]
    invalidation_condition: str
    risk_level: str

    @field_validator("action")
    @classmethod
    def normalize_action(cls, value: str) -> str:
        normalized = value.upper().strip()
        if normalized not in ALLOWED_ACTIONS:
            raise ValueError(f"Unsupported action: {value}")
        return normalized

    @field_validator("decision", "symbol", "instrument_type", "side", "entry_type", "risk_level")
    @classmethod
    def normalize_strings(cls, value: str) -> str:
        return value.strip().upper() if isinstance(value, str) else value


def fallback_hold(symbol: str = "CASH", rationale: str = "Evidence weak or unavailable") -> LLMDecisionResponse:
    return LLMDecisionResponse(
        decision="HOLD",
        symbol=symbol,
        instrument_type="STOCK",
        action="HOLD",
        side="BUY",
        quantity=0,
        entry_type="MARKET",
        entry_price_hint=None,
        stop_loss=None,
        take_profit=None,
        max_holding_minutes=0,
        confidence=0.2,
        rationale_points=[rationale],
        invalidation_condition="A stronger risk-adjusted setup appears.",
        risk_level="LOW",
    )

