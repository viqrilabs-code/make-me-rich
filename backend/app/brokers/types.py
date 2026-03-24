from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


InstrumentType = Literal["STOCK", "CALL", "PUT", "FUTURE"]
OrderSide = Literal["BUY", "SELL"]
EntryType = Literal["MARKET", "LIMIT", "STOP_LIMIT"]


class Quote(BaseModel):
    symbol: str
    ltp: float
    bid: float | None = None
    ask: float | None = None
    timestamp: datetime
    volume: float | None = None

    @property
    def spread_pct(self) -> float:
        if not self.bid or not self.ask or self.ltp <= 0:
            return 0.0
        return (self.ask - self.bid) / self.ltp * 100


class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class BrokerAccount(BaseModel):
    cash_balance: float
    total_equity: float
    margin_available: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    source: str = "broker"
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class BrokerPosition(BaseModel):
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
    mode: str = "paper"
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class BrokerOrder(BaseModel):
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
    mode: str = "paper"
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class BrokerMargin(BaseModel):
    available: float
    utilized: float
    leverage_enabled: bool = False


class OrderRequest(BaseModel):
    client_order_id: str
    idempotency_key: str
    symbol: str
    instrument_type: str
    side: str
    order_type: str = "MARKET"
    quantity: float
    price: float | None = None
    trigger_price: float | None = None
    mode: str = "paper"
    stop_loss: float | None = None
    take_profit: float | None = None


class BrokerHealth(BaseModel):
    broker: str
    healthy: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)

