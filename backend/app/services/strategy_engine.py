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
    bias = _directional_bias(features, news_sentiment)
    defensive_bias = abs(min(bias, 0.0)) + max(features.volatility_score - 1.6, 0.0)
    long_signal = bias
    short_signal = -bias

    if long_signal >= 1.35:
        actions.append(
            CandidateAction(
                symbol=features.symbol,
                action="BUY_STOCK",
                instrument_type="STOCK",
                side="BUY",
                score=clamp(0.45 + (long_signal / 6), 0.18, 0.99),
            )
        )
        if strategy.options_enabled and long_signal >= 1.65:
            actions.append(
                CandidateAction(
                    symbol=features.symbol,
                    action="BUY_CALL",
                    instrument_type="CALL",
                    side="BUY",
                    score=clamp(0.42 + (long_signal / 6.5), 0.16, 0.95),
                )
            )
    if short_signal >= 1.25:
        actions.append(
            CandidateAction(
                symbol=features.symbol,
                action="REDUCE",
                instrument_type="STOCK",
                side="SELL",
                score=clamp(0.4 + (short_signal / 6.5), 0.16, 0.95),
            )
        )
        actions.append(
            CandidateAction(
                symbol=features.symbol,
                action="EXIT",
                instrument_type="STOCK",
                side="SELL",
                score=clamp(0.46 + ((short_signal + defensive_bias) / 7.2), 0.18, 0.99),
            )
        )
        if strategy.options_enabled and short_signal >= 1.6:
            actions.append(
                CandidateAction(
                    symbol=features.symbol,
                    action="BUY_PUT",
                    instrument_type="PUT",
                    side="BUY",
                    score=clamp(0.42 + (short_signal / 6.2), 0.16, 0.92),
                )
            )

    if strategy.futures_enabled and long_signal >= 2.0:
        actions.append(
            CandidateAction(
                symbol=features.symbol,
                action="BUY_FUTURE",
                instrument_type="FUTURE",
                side="BUY",
                score=clamp(0.48 + (long_signal / 6.5), 0.18, 0.94),
            )
        )

    if strategy.futures_enabled and strategy.shorting_enabled and short_signal >= 2.0:
        actions.append(
            CandidateAction(
                symbol=features.symbol,
                action="SELL_FUTURE",
                instrument_type="FUTURE",
                side="SELL",
                score=clamp(0.48 + (short_signal / 6.5), 0.18, 0.9),
            )
        )

    if strategy.shorting_enabled and short_signal >= 2.3:
        actions.append(
            CandidateAction(
                symbol=features.symbol,
                action="SELL_STOCK",
                instrument_type="STOCK",
                side="SELL",
                score=clamp(0.45 + (short_signal / 6.8), 0.18, 0.9),
            )
        )

    return sorted(actions, key=lambda item: item.score, reverse=True)


def _directional_bias(features: FeatureSet, news_sentiment: float) -> float:
    bias = (
        features.momentum_score * 0.55
        + features.trend_score * 1.35
        + features.moving_average_crossover * 1.15
        + ((features.rsi - 50) / 7.0)
        + ((features.volume_spike_score - 1.0) * 1.25)
        + (news_sentiment * 2.5)
    )

    if features.market_regime == "bullish":
        bias += 0.45
    elif features.market_regime == "bearish":
        bias -= 0.45
    elif features.market_regime == "sideways":
        bias *= 0.8
    elif features.market_regime == "volatile":
        bias *= 0.88

    if features.volatility_score > 2.8:
        bias *= 0.82

    return round(bias, 3)
