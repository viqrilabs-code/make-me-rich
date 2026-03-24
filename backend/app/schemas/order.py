from __future__ import annotations

from datetime import datetime

from app.schemas.common import ORMModel


class OrderResponse(ORMModel):
    id: int
    broker_order_id: str | None = None
    client_order_id: str
    symbol: str
    instrument_type: str
    side: str
    order_type: str
    quantity: float
    price: float | None = None
    trigger_price: float | None = None
    status: str
    fill_price: float | None = None
    fill_quantity: float | None = None
    placed_at: datetime
    updated_at: datetime
    mode: str
    raw_payload_json: dict

