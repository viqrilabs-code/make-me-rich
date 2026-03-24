from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models import StrategyConfig
from app.schemas.common import MessageResponse
from app.schemas.strategy import StrategyResponse, StrategyUpdate
from app.services.orchestration_service import run_trading_cycle


router = APIRouter(prefix="/api/strategy", tags=["strategy"])


@router.get("", response_model=StrategyResponse)
def get_strategy(_: object = Depends(get_current_user), db: Session = Depends(get_db)) -> StrategyResponse:
    strategy = db.scalar(select(StrategyConfig).limit(1))
    if not strategy:
        raise HTTPException(status_code=404, detail="No strategy config available")
    return StrategyResponse.model_validate(strategy)


@router.put("", response_model=StrategyResponse)
def put_strategy(
    payload: StrategyUpdate,
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategyResponse:
    settings = get_settings()
    strategy = db.scalar(select(StrategyConfig).limit(1))
    if not strategy:
        raise HTTPException(status_code=404, detail="No strategy config available")

    updates = payload.model_dump(exclude_none=True)
    requested_mode = updates.get("mode", strategy.mode)
    if requested_mode == "live" and not settings.live_execution_enabled:
        raise HTTPException(status_code=400, detail="Live execution is not enabled in environment settings")
    if requested_mode == "live" and not updates.get("live_mode_armed", strategy.live_mode_armed):
        raise HTTPException(status_code=400, detail="Live mode requires explicit arming")

    for key, value in updates.items():
        setattr(strategy, key, value)

    db.commit()
    db.refresh(strategy)
    return StrategyResponse.model_validate(strategy)


@router.post("/kill-switch", response_model=MessageResponse)
def enable_kill_switch(_: object = Depends(get_current_user), db: Session = Depends(get_db)) -> MessageResponse:
    strategy = db.scalar(select(StrategyConfig).limit(1))
    if not strategy:
        raise HTTPException(status_code=404, detail="No strategy config available")
    strategy.kill_switch = True
    strategy.mode = "advisory"
    db.commit()
    return MessageResponse(message="Kill switch enabled", timestamp=datetime.now(timezone.utc))


@router.post("/manual-only", response_model=MessageResponse)
def enable_manual_only(_: object = Depends(get_current_user), db: Session = Depends(get_db)) -> MessageResponse:
    strategy = db.scalar(select(StrategyConfig).limit(1))
    if not strategy:
        raise HTTPException(status_code=404, detail="No strategy config available")
    strategy.pause_scheduler = True
    db.commit()
    return MessageResponse(
        message="Scheduler paused. Manual trade search remains available.",
        timestamp=datetime.now(timezone.utc),
    )


@router.post("/resume-scheduler", response_model=MessageResponse)
def resume_scheduler_only(_: object = Depends(get_current_user), db: Session = Depends(get_db)) -> MessageResponse:
    strategy = db.scalar(select(StrategyConfig).limit(1))
    if not strategy:
        raise HTTPException(status_code=404, detail="No strategy config available")
    strategy.pause_scheduler = False
    db.commit()
    return MessageResponse(
        message="Scheduler resumed. Automatic polling is active again.",
        timestamp=datetime.now(timezone.utc),
    )


@router.post("/resume", response_model=MessageResponse)
def resume_strategy(_: object = Depends(get_current_user), db: Session = Depends(get_db)) -> MessageResponse:
    strategy = db.scalar(select(StrategyConfig).limit(1))
    if not strategy:
        raise HTTPException(status_code=404, detail="No strategy config available")
    strategy.kill_switch = False
    strategy.cooldown_until = None
    strategy.pause_scheduler = False
    db.commit()
    return MessageResponse(message="Strategy resumed", timestamp=datetime.now(timezone.utc))


@router.post("/run-once")
def run_once(_: object = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    result = run_trading_cycle(db, trigger="manual")
    db.commit()
    return result
