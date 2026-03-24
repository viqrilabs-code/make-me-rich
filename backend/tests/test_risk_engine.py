from datetime import datetime, timezone

from app.brokers.types import Quote
from app.llm.schemas import LLMDecisionResponse
from app.risk.engine import RiskEngine
from app.risk.models import RiskEvaluationContext


def test_risk_engine_approves_valid_trade(strategy) -> None:
    engine = RiskEngine()
    decision = LLMDecisionResponse(
        decision="BUY_STOCK",
        symbol="INFY",
        instrument_type="STOCK",
        action="BUY_STOCK",
        side="BUY",
        quantity=1,
        entry_type="MARKET",
        entry_price_hint=1500.0,
        stop_loss=1485.0,
        take_profit=1530.0,
        max_holding_minutes=120,
        confidence=0.8,
        rationale_points=["Momentum strong"],
        invalidation_condition="Breaks support",
        risk_level="MEDIUM",
    )
    result = engine.evaluate(
        RiskEvaluationContext(
            strategy=strategy,
            decision=decision,
            account_equity=100000.0,
            daily_loss_pct=0.0,
            drawdown_pct=1.0,
            open_positions=[],
            existing_position=None,
            quote=Quote(symbol="INFY", ltp=1500.0, bid=1499.0, ask=1501.0, timestamp=datetime.now(timezone.utc)),
            duplicate_keys=set(),
            now=datetime.now(timezone.utc),
            market_open=True,
            stale_after_minutes=15,
        )
    )
    assert result.approved is True
    assert result.computed_position_size >= 1


def test_risk_engine_rejects_when_kill_switch_enabled(strategy) -> None:
    strategy.kill_switch = True
    engine = RiskEngine()
    decision = LLMDecisionResponse(
        decision="BUY_STOCK",
        symbol="INFY",
        instrument_type="STOCK",
        action="BUY_STOCK",
        side="BUY",
        quantity=1,
        entry_type="MARKET",
        entry_price_hint=1500.0,
        stop_loss=1485.0,
        take_profit=1530.0,
        max_holding_minutes=120,
        confidence=0.8,
        rationale_points=["Momentum strong"],
        invalidation_condition="Breaks support",
        risk_level="MEDIUM",
    )
    result = engine.evaluate(
        RiskEvaluationContext(
            strategy=strategy,
            decision=decision,
            account_equity=100000.0,
            daily_loss_pct=0.0,
            drawdown_pct=1.0,
            open_positions=[],
            existing_position=None,
            quote=Quote(symbol="INFY", ltp=1500.0, bid=1499.0, ask=1501.0, timestamp=datetime.now(timezone.utc)),
            duplicate_keys=set(),
            now=datetime.now(timezone.utc),
            market_open=True,
            stale_after_minutes=15,
        )
    )
    assert result.approved is False
    assert "Kill switch is enabled." in result.rejection_reasons

