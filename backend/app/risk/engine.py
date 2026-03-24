from __future__ import annotations

from datetime import timedelta
from math import floor

from app.risk.models import RiskEvaluationContext, RiskEvaluationResult


OPENING_ACTIONS = {"BUY_STOCK", "SELL_STOCK", "BUY_CALL", "BUY_PUT", "BUY_FUTURE", "SELL_FUTURE"}


class RiskEngine:
    def evaluate(self, context: RiskEvaluationContext) -> RiskEvaluationResult:
        strategy = context.strategy
        decision = context.decision
        reasons: list[str] = []
        duplicate_key = f"{decision.symbol}:{decision.action}:{decision.side}"
        is_opening = decision.action in OPENING_ACTIONS

        if strategy.kill_switch:
            reasons.append("Kill switch is enabled.")
        if strategy.cooldown_until and strategy.cooldown_until > context.now:
            reasons.append("Cooldown is active.")
        if context.daily_loss_pct >= strategy.max_daily_loss_pct:
            reasons.append("Daily loss limit reached.")
        if context.drawdown_pct >= strategy.max_drawdown_pct:
            reasons.append("Max drawdown breached.")
        if duplicate_key in context.duplicate_keys:
            reasons.append("Duplicate order intent in same cycle.")
        if strategy.market_hours_only and is_opening and not context.market_open:
            reasons.append("Market hours restriction active.")
        if is_opening and len(context.open_positions) >= strategy.max_open_positions:
            reasons.append("Max open positions reached.")
        if decision.instrument_type == "FUTURE" and not strategy.futures_enabled:
            reasons.append("Futures trading disabled.")
        if decision.instrument_type in {"CALL", "PUT"} and not strategy.options_enabled:
            reasons.append("Options trading disabled.")
        if decision.side == "SELL" and decision.action in {"SELL_STOCK", "SELL_FUTURE"} and not strategy.shorting_enabled:
            reasons.append("Shorting disabled.")
        if context.quote:
            age = context.now - context.quote.timestamp
            if age > timedelta(minutes=context.stale_after_minutes):
                reasons.append("Market data is stale.")
            if context.quote.spread_pct > 1.0:
                reasons.append("Spread too wide.")
        elif is_opening:
            reasons.append("Missing market quote.")

        if decision.action in {"EXIT", "REDUCE"} and not context.existing_position:
            reasons.append("No existing position to reduce or exit.")

        if is_opening and strategy.mandatory_stop_loss and decision.stop_loss is None:
            reasons.append("Mandatory stop loss missing.")

        if decision.action == "HOLD":
            return RiskEvaluationResult(
                approved=True,
                rejection_reasons=[],
                computed_position_size=0.0,
                final_order_payload=None,
            )

        if reasons:
            return RiskEvaluationResult(approved=False, rejection_reasons=reasons)

        if decision.action == "EXIT":
            quantity = context.existing_position.quantity if context.existing_position else 0
        elif decision.action == "REDUCE":
            quantity = max(floor((context.existing_position.quantity if context.existing_position else 0) / 2), 1)
        else:
            entry = decision.entry_price_hint or (context.quote.ltp if context.quote else 0)
            if entry <= 0:
                return RiskEvaluationResult(approved=False, rejection_reasons=["Invalid entry price."])
            risk_per_unit = abs(entry - (decision.stop_loss or entry))
            if risk_per_unit <= 0:
                return RiskEvaluationResult(approved=False, rejection_reasons=["Stop loss distance must be positive."])
            max_risk_capital = context.account_equity * strategy.max_risk_per_trade_pct / 100
            max_capital = context.account_equity * strategy.max_capital_per_trade_pct / 100
            qty_by_risk = floor(max_risk_capital / risk_per_unit)
            qty_by_capital = floor(max_capital / entry)
            quantity = min(qty_by_risk, qty_by_capital)
            if not strategy.leverage_enabled and quantity * entry > context.account_equity:
                reasons.append("Trade would exceed available capital without leverage.")
            if quantity < 1:
                reasons.append("Position size below minimum tradable quantity.")
            if reasons:
                return RiskEvaluationResult(approved=False, rejection_reasons=reasons)

        final_price = decision.entry_price_hint or (context.quote.ltp if context.quote else None)
        final_side = decision.side
        if decision.action in {"EXIT", "REDUCE"} and context.existing_position:
            final_side = "SELL" if context.existing_position.side == "BUY" else "BUY"

        return RiskEvaluationResult(
            approved=True,
            rejection_reasons=[],
            computed_position_size=float(quantity),
            final_order_payload={
                "symbol": decision.symbol,
                "instrument_type": decision.instrument_type,
                "side": final_side,
                "order_type": decision.entry_type,
                "quantity": float(quantity),
                "price": final_price,
                "stop_loss": decision.stop_loss,
                "take_profit": decision.take_profit,
            },
        )

