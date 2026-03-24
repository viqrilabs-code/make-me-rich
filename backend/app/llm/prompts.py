from __future__ import annotations

import json
from typing import Any


PROMPT_VERSION = "decision-v2"


def build_decision_prompt(context: dict[str, Any]) -> dict[str, str]:
    system_prompt = (
        "You are an algorithmic trading decision assistant for a single-user personal system. "
        "Profit targets are not guaranteed. Optimize for risk-adjusted decision quality, not excitement. "
        "Prioritize capital preservation after drawdown. Only choose from the supplied candidates. "
        "Never invent broker, account, market, or news data. Prefer HOLD if evidence is weak. "
        "Return JSON only and exactly match the required schema. "
        "Return one JSON object only, with no markdown fences, no commentary, and no wrapper keys. "
        "Required keys: decision, symbol, instrument_type, action, side, quantity, entry_type, "
        "entry_price_hint, stop_loss, take_profit, max_holding_minutes, confidence, rationale_points, "
        "invalidation_condition, risk_level. "
        "Use one of these actions only: HOLD, EXIT, REDUCE, BUY_STOCK, SELL_STOCK, BUY_CALL, BUY_PUT, BUY_FUTURE, SELL_FUTURE. "
        "rationale_points must be an array of short strings. "
        "If the best choice is to stay out, return HOLD with quantity 0."
    )
    user_prompt = json.dumps(context, default=str, separators=(",", ":"), indent=2)
    return {
        "version": PROMPT_VERSION,
        "system": system_prompt,
        "user": user_prompt,
    }
