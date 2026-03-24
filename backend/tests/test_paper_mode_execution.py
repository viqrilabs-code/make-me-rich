from __future__ import annotations

from app.brokers.base import BrokerAdapter
from app.brokers.types import BrokerAccount, BrokerHealth, BrokerMargin, BrokerOrder, BrokerPosition, Candle, OrderRequest, Quote
from app.llm.schemas import LLMDecisionResponse
from app.models import Order
from app.risk.models import RiskEvaluationResult
from app.services.execution_service import ExecutionService


class FailingLiveBroker(BrokerAdapter):
    broker_name = "live-stub"

    def get_account(self) -> BrokerAccount:
        raise NotImplementedError

    def get_positions(self) -> list[BrokerPosition]:
        raise NotImplementedError

    def get_holdings(self) -> list[BrokerPosition]:
        raise NotImplementedError

    def get_orders(self) -> list[BrokerOrder]:
        raise NotImplementedError

    def get_quotes(self, symbols: list[str]) -> list[Quote]:
        raise NotImplementedError

    def get_candles(self, symbol: str, interval: str, lookback: int) -> list[Candle]:
        raise NotImplementedError

    def place_order(self, order_request: OrderRequest) -> BrokerOrder:
        raise AssertionError("paper mode should not hit the live broker adapter")

    def modify_order(self, order_id: str, payload: dict[str, object]) -> BrokerOrder:
        raise NotImplementedError

    def cancel_order(self, order_id: str) -> dict[str, object]:
        raise NotImplementedError

    def get_margin(self) -> BrokerMargin:
        raise NotImplementedError

    def healthcheck(self) -> BrokerHealth:
        return BrokerHealth(broker=self.broker_name, healthy=True, message="ok")


def test_paper_mode_executes_via_mock_broker(db_session, strategy) -> None:
    strategy.mode = "paper"
    db_session.commit()

    execution = ExecutionService(FailingLiveBroker())
    decision = LLMDecisionResponse(
        decision="BUY_STOCK",
        symbol="INFY",
        instrument_type="STOCK",
        action="BUY_STOCK",
        side="BUY",
        quantity=1,
        entry_type="MARKET",
        entry_price_hint=1500.0,
        stop_loss=1475.0,
        take_profit=1550.0,
        max_holding_minutes=60,
        confidence=0.8,
        rationale_points=["Paper trade verification."],
        invalidation_condition="Stop loss breached.",
        risk_level="LOW",
    )
    risk_result = RiskEvaluationResult(
        approved=True,
        computed_position_size=1.0,
        final_order_payload={
            "symbol": "INFY",
            "instrument_type": "STOCK",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 1.0,
            "price": 1500.0,
            "stop_loss": 1475.0,
            "take_profit": 1550.0,
        },
    )

    result = execution.execute(
        db_session,
        strategy=strategy,
        decision=decision,
        risk_result=risk_result,
        scheduler_run_id=1,
    )

    saved_order = db_session.query(Order).one()
    assert result["status"] == "filled"
    assert saved_order.raw_payload_json["execution_broker"] == "mock"
