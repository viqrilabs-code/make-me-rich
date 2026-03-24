from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean, pstdev

from app.brokers.types import Candle
from app.models import StrategyConfig
from app.utils.math import clamp, pct_change, safe_div


@dataclass(slots=True)
class FeatureSet:
    symbol: str
    momentum_score: float
    volatility_score: float
    trend_score: float
    volume_spike_score: float
    atr: float
    moving_average_crossover: float
    rsi: float
    market_regime: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class CandidateAction:
    symbol: str
    action: str
    instrument_type: str
    side: str
    score: float
    entry_type: str = "MARKET"

    def to_dict(self) -> dict:
        return asdict(self)


def _moving_average(values: list[float], window: int) -> float:
    if not values:
        return 0.0
    data = values[-window:] if len(values) >= window else values
    return mean(data)


def _compute_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) <= period:
        return 50.0
    gains = []
    losses = []
    for index in range(1, len(closes)):
        delta = closes[index] - closes[index - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = mean(gains[-period:]) if gains[-period:] else 0.0
    avg_loss = mean(losses[-period:]) if losses[-period:] else 0.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_features(symbol: str, candles: list[Candle]) -> FeatureSet:
    closes = [candle.close for candle in candles]
    volumes = [candle.volume or 0.0 for candle in candles]
    highs = [candle.high for candle in candles]
    lows = [candle.low for candle in candles]

    momentum = pct_change(closes[-1], closes[max(len(closes) - 10, 0)]) * 100 if len(closes) > 10 else 0.0
    returns = [
        safe_div(closes[index] - closes[index - 1], closes[index - 1])
        for index in range(1, len(closes))
        if closes[index - 1] != 0
    ]
    volatility = pstdev(returns) * 100 if len(returns) > 1 else 0.0
    short_ma = _moving_average(closes, 5)
    long_ma = _moving_average(closes, 20)
    trend = pct_change(short_ma, long_ma) * 100 if long_ma else 0.0
    volume_spike = safe_div(volumes[-1], mean(volumes[-10:-1] or [1]))
    true_ranges = []
    for index, candle in enumerate(candles[1:], start=1):
        prev_close = candles[index - 1].close
        true_ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - prev_close),
                abs(candle.low - prev_close),
            )
        )
    atr = mean(true_ranges[-14:]) if true_ranges else 0.0
    ma_cross = pct_change(short_ma, long_ma) * 100 if long_ma else 0.0
    rsi = _compute_rsi(closes)

    if volatility > 2.5:
        regime = "volatile"
    elif abs(momentum) < 1.0 and abs(trend) < 0.5:
        regime = "sideways"
    elif momentum > 2 and rsi > 55:
        regime = "bullish"
    elif momentum < -2 and rsi < 45:
        regime = "bearish"
    else:
        regime = "event-driven"

    return FeatureSet(
        symbol=symbol,
        momentum_score=round(momentum, 2),
        volatility_score=round(volatility, 2),
        trend_score=round(trend, 2),
        volume_spike_score=round(volume_spike, 2),
        atr=round(atr, 2),
        moving_average_crossover=round(ma_cross, 2),
        rsi=round(rsi, 2),
        market_regime=regime,
    )


def generate_candidate_actions(
    strategy: StrategyConfig,
    features: FeatureSet,
    news_sentiment: float,
) -> list[CandidateAction]:
    actions: list[CandidateAction] = [
        CandidateAction(
            symbol=features.symbol,
            action="HOLD",
            instrument_type="STOCK",
            side="BUY",
            score=0.1,
        )
    ]
    bias = features.momentum_score + features.trend_score + news_sentiment * 5
    defensive_bias = features.volatility_score - features.momentum_score

    if bias > 3:
        actions.append(
            CandidateAction(
                symbol=features.symbol,
                action="BUY_STOCK",
                instrument_type="STOCK",
                side="BUY",
                score=clamp(bias / 10, 0.1, 0.99),
            )
        )
        if strategy.options_enabled:
            actions.append(
                CandidateAction(
                    symbol=features.symbol,
                    action="BUY_CALL",
                    instrument_type="CALL",
                    side="BUY",
                    score=clamp((bias + features.rsi) / 120, 0.1, 0.95),
                )
            )
    if bias < -3:
        actions.append(
            CandidateAction(
                symbol=features.symbol,
                action="REDUCE",
                instrument_type="STOCK",
                side="SELL",
                score=clamp(abs(bias) / 10, 0.1, 0.95),
            )
        )
        actions.append(
            CandidateAction(
                symbol=features.symbol,
                action="EXIT",
                instrument_type="STOCK",
                side="SELL",
                score=clamp((abs(bias) + defensive_bias) / 15, 0.1, 0.99),
            )
        )
        if strategy.options_enabled:
            actions.append(
                CandidateAction(
                    symbol=features.symbol,
                    action="BUY_PUT",
                    instrument_type="PUT",
                    side="BUY",
                    score=clamp(abs(bias) / 9, 0.1, 0.9),
                )
            )

    if strategy.futures_enabled and bias > 4:
        actions.append(
            CandidateAction(
                symbol=features.symbol,
                action="BUY_FUTURE",
                instrument_type="FUTURE",
                side="BUY",
                score=clamp((bias + 2) / 12, 0.1, 0.9),
            )
        )

    if strategy.futures_enabled and strategy.shorting_enabled and bias < -4:
        actions.append(
            CandidateAction(
                symbol=features.symbol,
                action="SELL_FUTURE",
                instrument_type="FUTURE",
                side="SELL",
                score=clamp(abs(bias) / 12, 0.1, 0.85),
            )
        )

    if strategy.shorting_enabled and bias < -5:
        actions.append(
            CandidateAction(
                symbol=features.symbol,
                action="SELL_STOCK",
                instrument_type="STOCK",
                side="SELL",
                score=clamp(abs(bias) / 11, 0.1, 0.85),
            )
        )

    return sorted(actions, key=lambda item: item.score, reverse=True)
