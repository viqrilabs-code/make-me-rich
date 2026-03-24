from __future__ import annotations

import logging
from datetime import datetime, time

from app.brokers.base import BrokerAdapter
from app.models import StrategyConfig
from app.schemas.portfolio import HotDealResponse, MarketSessionResponse
from app.services.market_service import MarketService
from app.services.news_service import NewsService
from app.services.strategy_engine import compute_features, generate_candidate_actions
from app.utils.math import clamp
from app.utils.time import is_market_open, to_ist, utc_now


logger = logging.getLogger(__name__)


def _feature_window(session_label: str) -> tuple[str, int]:
    if session_label in {"Pre-market prep", "Opening drive"}:
        return "1d", 90
    return "5m", 50


def build_market_session(now: datetime | None = None) -> MarketSessionResponse:
    now = now or utc_now()
    local = to_ist(now)
    clock = local.time()
    market_open = is_market_open(now)

    if clock < time(9, 15):
        label = "Pre-market prep"
        note = "Build the watchlist, review overnight news, and wait for the first candles before fresh entries."
    elif clock < time(10, 15):
        label = "Opening drive"
        note = "Favor only the strongest breakouts or defensive exits; early volatility can punish oversized trades."
    elif clock < time(12, 45):
        label = "Trend continuation"
        note = "This is the cleanest intraday window for confirmed momentum if price, trend, and news still agree."
    elif clock < time(14, 30):
        label = "Midday patience"
        note = "Liquidity often softens here. Prefer selective follow-through setups rather than chasing weak moves."
    elif clock <= time(15, 30):
        label = "Closing setup"
        note = "Late-session ideas should be smaller and disciplined, with stops already defined before the close."
    else:
        label = "Post-close review"
        note = "Use the board for tomorrow's setup planning rather than new live entries."

    return MarketSessionResponse(
        label=label,
        note=note,
        local_time=local,
        market_open=market_open,
    )


def build_hot_deals(
    strategy: StrategyConfig,
    broker: BrokerAdapter,
    symbols: list[str],
    limit: int = 4,
) -> tuple[MarketSessionResponse, list[HotDealResponse]]:
    session = build_market_session()
    clean_symbols = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
    if not clean_symbols:
        return session, []

    market_service = MarketService(broker)
    news_summary = NewsService().summarize(clean_symbols)
    feature_interval, feature_lookback = _feature_window(session.label)

    try:
        quotes = market_service.get_quotes_map(clean_symbols)
        candles_map = market_service.get_candles_map(
            clean_symbols,
            interval=feature_interval,
            lookback=feature_lookback,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Hot deals market fetch failed", extra={"error": str(exc)})
        return session, []

    ideas: list[HotDealResponse] = []
    for symbol in clean_symbols:
        quote = quotes.get(symbol)
        if not quote:
            continue
        candles = candles_map.get(symbol, [])
        if len(candles) < 10:
            continue

        symbol_news = [item for item in news_summary.items if symbol in item.symbols]
        symbol_sentiment = (
            sum(item.sentiment_score for item in symbol_news) / len(symbol_news)
            if symbol_news
            else news_summary.overall_sentiment
        )
        features = compute_features(symbol, candles)
        candidates = generate_candidate_actions(strategy, features, symbol_sentiment)
        candidate = next((item for item in candidates if item.action != "HOLD"), None)
        if not candidate:
            continue

        timing_boost = _timing_boost(session.label, candidate.action, features.market_regime)
        final_score = clamp(candidate.score * timing_boost, 0.1, 0.99)
        stop_loss_hint, take_profit_hint = _trade_levels(candidate.side, quote.ltp, features.atr)
        ideas.append(
            HotDealResponse(
                symbol=symbol,
                action=candidate.action,
                instrument_type=candidate.instrument_type,
                side=candidate.side,
                score=round(final_score, 2),
                conviction=_conviction_label(final_score),
                market_regime=features.market_regime,
                ltp=quote.ltp,
                momentum_score=features.momentum_score,
                trend_score=features.trend_score,
                rsi=features.rsi,
                sentiment_score=round(symbol_sentiment, 2),
                opportunity_window=session.label,
                setup_note=_build_setup_note(session.label, candidate.action, features.market_regime),
                stop_loss_hint=stop_loss_hint,
                take_profit_hint=take_profit_hint,
            )
        )

    ideas.sort(key=lambda item: item.score, reverse=True)
    return session, ideas[:limit]


def _timing_boost(session_label: str, action: str, regime: str) -> float:
    if session_label == "Opening drive" and action.startswith("BUY") and regime in {"bullish", "event-driven"}:
        return 1.08
    if session_label == "Trend continuation" and regime in {"bullish", "bearish"}:
        return 1.05
    if session_label == "Midday patience":
        return 0.93
    if session_label == "Closing setup" and action in {"EXIT", "REDUCE"}:
        return 1.04
    if session_label in {"Pre-market prep", "Post-close review"}:
        return 0.9
    return 1.0


def _trade_levels(side: str, ltp: float, atr: float) -> tuple[float, float]:
    buffer = max(atr, ltp * 0.01)
    target_buffer = max(buffer * 1.8, ltp * 0.015)
    if side.upper() == "SELL":
        return round(ltp + buffer, 2), round(max(ltp - target_buffer, 0.01), 2)
    return round(max(ltp - buffer, 0.01), 2), round(ltp + target_buffer, 2)


def _conviction_label(score: float) -> str:
    if score >= 0.8:
        return "High"
    if score >= 0.62:
        return "Medium"
    return "Watch"


def _build_setup_note(session_label: str, action: str, regime: str) -> str:
    if session_label == "Opening drive":
        return f"{action.replace('_', ' ')} looks strongest into the open. Treat {regime} conditions as fast-moving and size carefully."
    if session_label == "Trend continuation":
        return f"This setup fits a continuation window. Keep only {regime} names where momentum has already held through the morning."
    if session_label == "Midday patience":
        return f"Keep this on a tighter leash during midday drift. Only take it if the {regime} structure stays clean."
    if session_label == "Closing setup":
        return f"This is more suitable as a late-session or next-session handoff idea while the {regime} backdrop remains intact."
    return f"Use this as a prepared setup rather than an immediate live trade while the market is in {session_label.lower()}."
