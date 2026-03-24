from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker

from app.brokers.mock import MockBrokerAdapter
from app.llm.schemas import LLMDecisionResponse
from app.risk.models import RiskEvaluationResult
from app.services.execution_service import ExecutionService


def test_duplicate_execution_prevented(db_session, strategy) -> None:
    adapter = MockBrokerAdapter(sessionmaker(bind=db_session.get_bind()))
    service = ExecutionService(adapter)
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
    risk = RiskEvaluationResult(
        approved=True,
        rejection_reasons=[],
        computed_position_size=1.0,
        final_order_payload={
            "symbol": "INFY",
            "instrument_type": "STOCK",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 1.0,
            "price": 1500.0,
            "stop_loss": 1485.0,
            "take_profit": 1530.0,
        },
    )
    first = service.execute(db_session, strategy, decision, risk, scheduler_run_id=1)
    second = service.execute(db_session, strategy, decision, risk, scheduler_run_id=1)
    assert first["status"] == "filled"
    assert second["status"] == "duplicate"
