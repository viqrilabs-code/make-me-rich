from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BrokerHealthResponse(BaseModel):
    broker: str
    healthy: bool
    message: str
    active_broker: str | None = None
    using_fallback: bool = False
    details: dict


class BrokerAccountResponse(BaseModel):
    cash_balance: float
    total_equity: float
    margin_available: float
    realized_pnl: float
    unrealized_pnl: float
    source: str
    raw_payload: dict


class BrokerPositionResponse(BaseModel):
    symbol: str
    instrument_type: str
    side: str
    quantity: float
    avg_price: float
    current_price: float
    unrealized_pnl: float
    stop_loss: float | None = None
    take_profit: float | None = None
    broker_position_id: str | None = None
    mode: str
    raw_payload: dict


class BrokerOrderResponse(BaseModel):
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
    raw_payload: dict

