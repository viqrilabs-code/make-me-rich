from __future__ import annotations

from typing import Any

import httpx

from app.brokers.base import BrokerAdapter
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
from app.core.config import Settings


class GrowwAdapter(BrokerAdapter):
    broker_name = "groww"

    ENDPOINTS: dict[str, str | None] = {
        "account": None,
        "positions": None,
        "holdings": None,
        "orders": None,
        "quotes": None,
        "candles": None,
        "place_order": None,
        "modify_order": None,
        "cancel_order": None,
        "margin": None,
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.Client(
            base_url=settings.groww_base_url,
            timeout=15.0,
            headers={
                "Authorization": f"Bearer {settings.groww_api_key or ''}",
                "X-Client-Id": settings.groww_client_id or "",
            },
        )

    def _not_ready(self, operation: str) -> RuntimeError:
        return RuntimeError(
            f"GrowwAdapter {operation} is intentionally isolated until verified broker endpoints are configured. "
            "Update GrowwAdapter.ENDPOINTS with the real endpoint paths and auth contract."
        )

    def get_account(self) -> BrokerAccount:
        raise self._not_ready("get_account")

    def get_positions(self) -> list[BrokerPosition]:
        raise self._not_ready("get_positions")

    def get_holdings(self) -> list[BrokerPosition]:
        raise self._not_ready("get_holdings")

    def get_orders(self) -> list[BrokerOrder]:
        raise self._not_ready("get_orders")

    def get_quotes(self, symbols: list[str]) -> list[Quote]:
        raise self._not_ready("get_quotes")

    def get_candles(self, symbol: str, interval: str, lookback: int) -> list[Candle]:
        raise self._not_ready("get_candles")

    def place_order(self, order_request: OrderRequest) -> BrokerOrder:
        raise self._not_ready("place_order")

    def modify_order(self, order_id: str, payload: dict[str, Any]) -> BrokerOrder:
        raise self._not_ready("modify_order")

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        raise self._not_ready("cancel_order")

    def get_margin(self) -> BrokerMargin:
        raise self._not_ready("get_margin")

    def healthcheck(self) -> BrokerHealth:
        configured = bool(self.settings.groww_client_id and self.settings.groww_api_key)
        return BrokerHealth(
            broker=self.broker_name,
            healthy=configured and all(self.ENDPOINTS.values()),
            message="Groww scaffold loaded. Configure verified endpoints before live usage.",
            details={"configured": configured, "missing_endpoints": [k for k, v in self.ENDPOINTS.items() if not v]},
        )

