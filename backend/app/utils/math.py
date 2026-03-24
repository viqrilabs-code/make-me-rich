from __future__ import annotations


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    if denominator == 0:
        return default
    return numerator / denominator


def pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return (current - previous) / previous

