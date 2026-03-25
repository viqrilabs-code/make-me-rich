from __future__ import annotations

from app.brokers.base import BrokerAdapter
from app.brokers.types import Candle, Quote


class MarketService:
    def __init__(self, broker: BrokerAdapter) -> None:
        self.broker = broker

    def get_quotes_map(self, symbols: list[str]) -> dict[str, Quote]:
        batch_getter = getattr(self.broker, "get_quotes_batch", None)
        if callable(batch_getter):
            return batch_getter(symbols)

        quotes: dict[str, Quote] = {}
        for symbol in list(dict.fromkeys(symbols)):
            try:
                rows = self.broker.get_quotes([symbol])
            except Exception:
                continue
            for quote in rows:
                quotes[quote.symbol] = quote
        return quotes

    def get_candles_map(
        self, symbols: list[str], interval: str = "5m", lookback: int = 50
    ) -> dict[str, list[Candle]]:
        batch_getter = getattr(self.broker, "get_candles_batch", None)
        if callable(batch_getter):
            return batch_getter(symbols, interval=interval, lookback=lookback)
        return {
            symbol: self.broker.get_candles(symbol, interval=interval, lookback=lookback)
            for symbol in symbols
        }
