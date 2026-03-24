from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import sin

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

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
from app.models import Order, PortfolioSnapshot, Position


class MockBrokerAdapter(BrokerAdapter):
    broker_name = "mock"

    def __init__(self, db_factory: sessionmaker[Session]) -> None:
        self.db_factory = db_factory

    def _base_price(self, symbol: str) -> float:
        seed = sum(ord(char) for char in symbol.upper())
        cycle = int(datetime.now(timezone.utc).timestamp() // 300)
        drift = ((seed % 17) - 8) * 0.22
        wave = sin(cycle / 7) * 0.8
        return round(80 + (seed % 240) + drift + wave, 2)

    def get_account(self) -> BrokerAccount:
        with self.db_factory() as db:
            snapshot = db.scalar(
                select(PortfolioSnapshot).order_by(PortfolioSnapshot.timestamp.desc()).limit(1)
            )
            if snapshot:
                return BrokerAccount(
                    cash_balance=snapshot.cash_balance,
                    total_equity=snapshot.total_equity,
                    margin_available=snapshot.margin_available,
                    realized_pnl=snapshot.realized_pnl,
                    unrealized_pnl=snapshot.unrealized_pnl,
                    source="mock-broker",
                    raw_payload={"snapshot_id": snapshot.id},
                )

            return BrokerAccount(
                cash_balance=100000.0,
                total_equity=100000.0,
                margin_available=100000.0,
                source="mock-broker",
                raw_payload={},
            )

    def get_positions(self) -> list[BrokerPosition]:
        with self.db_factory() as db:
            positions = db.scalars(
                select(Position).where(Position.status == "open").order_by(Position.opened_at.desc())
            ).all()
            return [
                BrokerPosition(
                    symbol=position.symbol,
                    instrument_type=position.instrument_type,
                    side=position.side,
                    quantity=position.quantity,
                    avg_price=position.avg_price,
                    current_price=position.current_price,
                    unrealized_pnl=position.unrealized_pnl,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                    broker_position_id=position.broker_position_id,
                    mode=position.mode,
                    raw_payload=position.raw_payload_json,
                )
                for position in positions
            ]

    def get_holdings(self) -> list[BrokerPosition]:
        return self.get_positions()

    def get_orders(self) -> list[BrokerOrder]:
        with self.db_factory() as db:
            orders = db.scalars(select(Order).order_by(Order.placed_at.desc()).limit(100)).all()
            return [
                BrokerOrder(
                    broker_order_id=order.broker_order_id,
                    client_order_id=order.client_order_id,
                    symbol=order.symbol,
                    instrument_type=order.instrument_type,
                    side=order.side,
                    order_type=order.order_type,
                    quantity=order.quantity,
                    price=order.price,
                    trigger_price=order.trigger_price,
                    status=order.status,
                    fill_price=order.fill_price,
                    fill_quantity=order.fill_quantity,
                    placed_at=order.placed_at,
                    updated_at=order.updated_at,
                    mode=order.mode,
                    raw_payload=order.raw_payload_json,
                )
                for order in orders
            ]

    def get_quotes(self, symbols: list[str]) -> list[Quote]:
        timestamp = datetime.now(timezone.utc)
        quotes: list[Quote] = []
        for symbol in symbols:
            ltp = self._base_price(symbol)
            spread = max(0.05, round(ltp * 0.001, 2))
            quotes.append(
                Quote(
                    symbol=symbol,
                    ltp=ltp,
                    bid=round(ltp - spread, 2),
                    ask=round(ltp + spread, 2),
                    timestamp=timestamp,
                    volume=50000 + (sum(ord(char) for char in symbol) % 50000),
                )
            )
        return quotes

    def get_candles(self, symbol: str, interval: str, lookback: int) -> list[Candle]:
        try:
            step_minutes = int(interval.rstrip("m"))
        except ValueError:
            step_minutes = 5
        now = datetime.now(timezone.utc)
        base = self._base_price(symbol)
        candles: list[Candle] = []
        for index in range(lookback):
            point = lookback - index
            close = round(base * (1 + sin(point / 4) * 0.01 + (index - lookback / 2) * 0.0008), 2)
            open_price = round(close * (1 - 0.0015), 2)
            high = round(max(open_price, close) * 1.0025, 2)
            low = round(min(open_price, close) * 0.9975, 2)
            candles.append(
                Candle(
                    timestamp=now - timedelta(minutes=step_minutes * point),
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=40000 + point * 250,
                )
            )
        return candles

    def place_order(self, order_request: OrderRequest) -> BrokerOrder:
        quote = self.get_quotes([order_request.symbol])[0]
        fill_price = order_request.price or quote.ltp
        now = datetime.now(timezone.utc)
        return BrokerOrder(
            broker_order_id=f"mock_{order_request.client_order_id}",
            client_order_id=order_request.client_order_id,
            symbol=order_request.symbol,
            instrument_type=order_request.instrument_type,
            side=order_request.side,
            order_type=order_request.order_type,
            quantity=order_request.quantity,
            price=order_request.price,
            trigger_price=order_request.trigger_price,
            status="filled",
            fill_price=fill_price,
            fill_quantity=order_request.quantity,
            placed_at=now,
            updated_at=now,
            mode=order_request.mode,
            raw_payload={
                "simulated": True,
                "stop_loss": order_request.stop_loss,
                "take_profit": order_request.take_profit,
            },
        )

    def modify_order(self, order_id: str, payload: dict[str, object]) -> BrokerOrder:
        now = datetime.now(timezone.utc)
        return BrokerOrder(
            broker_order_id=order_id,
            client_order_id=payload.get("client_order_id", order_id),  # type: ignore[arg-type]
            symbol=str(payload.get("symbol", "UNKNOWN")),
            instrument_type=str(payload.get("instrument_type", "STOCK")),
            side=str(payload.get("side", "BUY")),
            order_type=str(payload.get("order_type", "MARKET")),
            quantity=float(payload.get("quantity", 0.0)),
            price=float(payload["price"]) if payload.get("price") is not None else None,
            trigger_price=(
                float(payload["trigger_price"]) if payload.get("trigger_price") is not None else None
            ),
            status="modified",
            fill_price=None,
            fill_quantity=None,
            placed_at=now,
            updated_at=now,
            mode=str(payload.get("mode", "paper")),
            raw_payload={"simulated": True, "payload": payload},
        )

    def cancel_order(self, order_id: str) -> dict[str, object]:
        return {"order_id": order_id, "status": "cancelled", "simulated": True}

    def get_margin(self) -> BrokerMargin:
        account = self.get_account()
        return BrokerMargin(
            available=account.margin_available,
            utilized=max(account.total_equity - account.margin_available, 0),
            leverage_enabled=False,
        )

    def healthcheck(self) -> BrokerHealth:
        return BrokerHealth(
            broker=self.broker_name,
            healthy=True,
            message="Mock broker is ready for advisory and paper trading flows.",
            details={"mode": "simulation"},
        )

