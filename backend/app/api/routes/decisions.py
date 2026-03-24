from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import TradeDecision
from app.schemas.decision import TradeDecisionResponse


router = APIRouter(prefix="/api/decisions", tags=["decisions"])


@router.get("", response_model=list[TradeDecisionResponse])
def list_decisions(
    limit: int = Query(default=50, ge=1, le=500),
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TradeDecisionResponse]:
    decisions = db.scalars(
        select(TradeDecision).order_by(TradeDecision.timestamp.desc()).limit(limit)
    ).all()
    return [TradeDecisionResponse.model_validate(decision) for decision in decisions]


@router.get("/{decision_id}", response_model=TradeDecisionResponse)
def get_decision(
    decision_id: int,
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TradeDecisionResponse:
    decision = db.get(TradeDecision, decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    return TradeDecisionResponse.model_validate(decision)

