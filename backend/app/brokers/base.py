from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.brokers.types import (
    BrokerAccount,
    BrokerHealth,
    BrokerMargin,
    BrokerOrder,
    BrokerPosition,
    Candle,
    OrderRequest,
    Quote,
)


class BrokerAdapter(ABC):
    broker_name: str

    @abstractmethod
    def get_account(self) -> BrokerAccount: ...

    @abstractmethod
    def get_positions(self) -> list[BrokerPosition]: ...

    @abstractmethod
    def get_holdings(self) -> list[BrokerPosition]: ...

    @abstractmethod
    def get_orders(self) -> list[BrokerOrder]: ...

    @abstractmethod
    def get_quotes(self, symbols: list[str]) -> list[Quote]: ...

    @abstractmethod
    def get_candles(self, symbol: str, interval: str, lookback: int) -> list[Candle]: ...

    @abstractmethod
    def place_order(self, order_request: OrderRequest) -> BrokerOrder: ...

    @abstractmethod
    def modify_order(self, order_id: str, payload: dict[str, Any]) -> BrokerOrder: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def get_margin(self) -> BrokerMargin: ...

    @abstractmethod
    def healthcheck(self) -> BrokerHealth: ...

