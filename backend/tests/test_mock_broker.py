from sqlalchemy.orm import sessionmaker

from app.brokers.mock import MockBrokerAdapter
from app.brokers.types import OrderRequest
from app.utils.ids import generate_client_order_id, generate_idempotency_key


def test_mock_broker_places_filled_order(db_session) -> None:
    adapter = MockBrokerAdapter(sessionmaker(bind=db_session.get_bind()))
    request = OrderRequest(
        client_order_id=generate_client_order_id(),
        idempotency_key=generate_idempotency_key("INFY", "BUY"),
        symbol="INFY",
        instrument_type="STOCK",
        side="BUY",
        quantity=1,
        mode="paper",
        stop_loss=1450.0,
        take_profit=1550.0,
    )
    order = adapter.place_order(request)
    assert order.status == "filled"
    assert order.fill_quantity == 1

