from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import PortfolioSnapshot, TradingGoal
from app.schemas.goal import GoalCreate, GoalPlanResponse, GoalResponse, GoalUpdate
from app.services.goal_planner import compute_goal_plan


router = APIRouter(prefix="/api/goals", tags=["goals"])


def _serialize_goal(db: Session, goal: TradingGoal) -> GoalResponse:
    snapshot = db.scalar(select(PortfolioSnapshot).order_by(PortfolioSnapshot.timestamp.desc()).limit(1))
    current_capital = snapshot.total_equity if snapshot else goal.initial_capital
    plan = compute_goal_plan(goal, current_capital=current_capital)
    return GoalResponse(
        **GoalResponse.model_validate(goal).model_dump(exclude={"plan"}),
        plan=GoalPlanResponse(**asdict(plan)),
    )


@router.get("/current", response_model=GoalResponse)
def get_current_goal(_: object = Depends(get_current_user), db: Session = Depends(get_db)) -> GoalResponse:
    goal = db.scalar(select(TradingGoal).order_by(TradingGoal.updated_at.desc()).limit(1))
    if not goal:
        raise HTTPException(status_code=404, detail="No trading goal configured")
    return _serialize_goal(db, goal)


@router.post("", response_model=GoalResponse)
def create_goal(
    payload: GoalCreate,
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GoalResponse:
    goal = TradingGoal(
        initial_capital=payload.initial_capital,
        target_multiplier=payload.target_multiplier,
        target_amount=payload.initial_capital * payload.target_multiplier,
        start_date=payload.start_date,
        target_date=payload.target_date,
        status=payload.status,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return _serialize_goal(db, goal)


@router.put("/current", response_model=GoalResponse)
def update_goal(
    payload: GoalUpdate,
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GoalResponse:
    goal = db.scalar(select(TradingGoal).order_by(TradingGoal.updated_at.desc()).limit(1))
    if not goal:
        raise HTTPException(status_code=404, detail="No trading goal configured")

    updates = payload.model_dump(exclude_none=True)
    if "target_days" in updates and "target_date" not in updates:
        start_date = updates.get("start_date", goal.start_date)
        updates["target_date"] = start_date.fromordinal(start_date.toordinal() + updates.pop("target_days"))
    for key, value in updates.items():
        setattr(goal, key, value)
    if payload.initial_capital is not None or payload.target_multiplier is not None:
        goal.target_amount = goal.initial_capital * goal.target_multiplier
    db.commit()
    db.refresh(goal)
    return _serialize_goal(db, goal)
