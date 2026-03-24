from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class TradeDecisionResponse(ORMModel):
    id: int
    timestamp: datetime
    symbol: str
    action: str
    instrument_type: str
    confidence: float
    rationale_json: list[str]
    llm_response_json: dict
    candidate_actions_json: list[dict]
    approved: bool
    rejection_reasons_json: list[str]
    scheduler_run_id: int | None = None


class LatestDecisionSummary(BaseModel):
    timestamp: datetime | None = None
    symbol: str | None = None
    action: str | None = None
    confidence: float | None = None
    approved: bool | None = None

