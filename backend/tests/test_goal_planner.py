from app.services.goal_planner import compute_goal_plan


def test_goal_planner_calculates_gap_and_mode(goal) -> None:
    plan = compute_goal_plan(goal, current_capital=102000.0)
    assert plan.target_amount == 120000.0
    assert plan.remaining_gap == 18000.0
    assert plan.days_remaining >= 0
    assert plan.mode_suggestion in {"defensive", "normal", "aggressive-within-risk"}

