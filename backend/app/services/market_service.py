from __future__ import annotations

from app.brokers.base import BrokerAdapter
from app.brokers.types import Candle, Quote


class MarketService:
    def __init__(self, broker: BrokerAdapter) -> None:
        self.broker = broker

    def get_quotes_map(self, symbols: list[str]) -> dict[str, Quote]:
        quotes = self.broker.get_quotes(symbols)
        return {quote.symbol: quote for quote in quotes}

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
