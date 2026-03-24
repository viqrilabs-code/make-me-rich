from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from app.models import TradingGoal
from app.utils.math import clamp


@dataclass(slots=True)
class GoalPlan:
    target_amount: float
    remaining_gap: float
    days_remaining: int
    daily_required_pace: float
    urgency_score: float
    mode_suggestion: str

    def to_dict(self) -> dict[str, float | int | str]:
        return asdict(self)


def compute_goal_plan(goal: TradingGoal, current_capital: float) -> GoalPlan:
    target_amount = goal.initial_capital * goal.target_multiplier
    remaining_gap = max(target_amount - current_capital, 0.0)
    days_remaining = max((goal.target_date - date.today()).days, 0)
    daily_required_pace = remaining_gap / max(days_remaining, 1)
    progress_ratio = 0.0 if target_amount <= 0 else current_capital / target_amount
    urgency_score = clamp((1 - progress_ratio) * 100 / max(days_remaining, 1) * 5, 0, 100)

    if urgency_score >= 55:
        mode_suggestion = "aggressive-within-risk"
    elif urgency_score >= 25:
        mode_suggestion = "normal"
    else:
        mode_suggestion = "defensive"

    return GoalPlan(
        target_amount=round(target_amount, 2),
        remaining_gap=round(remaining_gap, 2),
        days_remaining=days_remaining,
        daily_required_pace=round(daily_required_pace, 2),
        urgency_score=round(urgency_score, 2),
        mode_suggestion=mode_suggestion,
    )
