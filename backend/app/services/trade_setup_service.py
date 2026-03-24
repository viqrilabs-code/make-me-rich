from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from statistics import mean
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm import LLMDecisionEngine
from app.llm.schemas import LLMDecisionResponse, fallback_hold
from app.models import StrategyConfig, TradingGoal
from app.schemas.market import (
    BestTradeInstrumentScoreResponse,
    BestTradeResponse,
    RequestedInstrument,
    TradeCandidateResponse,
    TradeChartPointResponse,
    TradeFeatureResponse,
    TradeQuoteResponse,
    TradeSetupResponse,
)
from app.services.broker_service import get_active_broker
from app.services.goal_planner import compute_goal_plan
from app.services.hot_deals_service import build_market_session
from app.services.market_service import MarketService
from app.services.news_service import NewsService
from app.services.strategy_engine import compute_features, generate_candidate_actions


def build_trade_setup(
    db: Session,
    symbol: str,
    requested_instrument: RequestedInstrument,
    *,
    use_llm: bool = True,
) -> TradeSetupResponse:
    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
        raise ValueError("Symbol is required.")

    strategy = db.scalar(select(StrategyConfig).limit(1))
    goal = db.scalar(select(TradingGoal).order_by(TradingGoal.updated_at.desc()).limit(1))
    if not strategy:
        raise ValueError("No strategy configuration available.")
    configured_symbols = _configured_symbols(strategy)
    if configured_symbols and clean_symbol not in configured_symbols:
        raise ValueError(
            f"{clean_symbol} is not in Strategy watchlist. Search is limited to: {', '.join(configured_symbols)}."
        )

    adapter, active_broker, using_fallback_broker = get_active_broker(db)
    market_service = MarketService(adapter)
    news_service = NewsService()
    market_session = build_market_session()
    chart_interval, chart_lookback = _analysis_window(market_session.market_open)
    account = adapter.get_account()

    quotes = market_service.get_quotes_map([clean_symbol])
    quote = quotes.get(clean_symbol)
    if not quote:
        raise LookupError(f"No quote available for {clean_symbol}.")

    chart_points_raw = market_service.get_candles_map(
        [clean_symbol],
        interval=chart_interval,
        lookback=chart_lookback,
    ).get(clean_symbol, [])
    if len(chart_points_raw) < 20:
        raise LookupError(f"Not enough historical candles available for {clean_symbol}.")

    news_summary = news_service.summarize([clean_symbol])
    features = compute_features(clean_symbol, chart_points_raw)
    analysis_strategy = _analysis_strategy(strategy, requested_instrument)
    candidates = generate_candidate_actions(
        strategy=analysis_strategy,
        features=features,
        news_sentiment=news_summary.overall_sentiment,
    )
    filtered_candidates = _filter_candidates(candidates, requested_instrument)
    if not filtered_candidates:
        filtered_candidates = candidates[:1]

    goal_plan = (
        compute_goal_plan(goal, current_capital=account.total_equity).to_dict()
        if goal
        else {
            "target_amount": 0.0,
            "remaining_gap": 0.0,
            "days_remaining": 0,
            "daily_required_pace": 0.0,
            "urgency_score": 0.0,
            "mode_suggestion": "defensive",
        }
    )
    if use_llm:
        llm_engine = LLMDecisionEngine()
        llm_context = {
            "default_symbol": clean_symbol,
            "profit_target_note": "Target multiplier is aspirational and not guaranteed.",
            "goal_plan": goal_plan,
            "portfolio": {
                "current_capital": account.total_equity,
                "cash_balance": account.cash_balance,
                "realized_pnl": account.realized_pnl,
                "unrealized_pnl": account.unrealized_pnl,
            },
            "strategy": {
                "mode": strategy.mode,
                "risk_profile": strategy.risk_profile,
                "allowed_instruments": {
                    **(strategy.allowed_instruments_json or {}),
                    "requested_instrument": requested_instrument,
                },
                "selected_broker": active_broker,
                "using_fallback_broker": using_fallback_broker,
            },
            "technical_features": [asdict(features)],
            "candidate_actions": [candidate.to_dict() for candidate in filtered_candidates],
            "quotes": {clean_symbol: quote.model_dump()},
            "news_summary": news_summary.model_dump(),
        }
        decision = llm_engine.request_decision(llm_context, db)
    else:
        decision = _heuristic_decision(
            symbol=clean_symbol,
            requested_instrument=requested_instrument,
            quote=quote,
            features=features,
            candidates=filtered_candidates,
        )
    decision = _align_hold_decision(decision, requested_instrument)
    filtered_candidates = _ensure_decision_candidate(filtered_candidates, decision)
    execution_blockers = _execution_blockers(strategy, requested_instrument, decision.action)

    return TradeSetupResponse(
        symbol=clean_symbol,
        requested_instrument=requested_instrument,
        chart_interval=chart_interval,
        chart_lookback=chart_lookback,
        analysis_generated_at=datetime.now(timezone.utc),
        active_broker=active_broker,
        using_fallback_broker=using_fallback_broker,
        execution_ready=not execution_blockers and decision.action != "HOLD",
        execution_blockers=execution_blockers,
        mode_note=_mode_note(strategy.mode),
        analysis_note=_analysis_note(news_summary),
        market_session=market_session,
        quote=TradeQuoteResponse(
            symbol=quote.symbol,
            ltp=quote.ltp,
            bid=quote.bid,
            ask=quote.ask,
            spread_pct=round(quote.spread_pct, 3),
            timestamp=quote.timestamp,
            volume=quote.volume,
        ),
        features=TradeFeatureResponse(**asdict(features)),
        candidates=[TradeCandidateResponse(**candidate.to_dict()) for candidate in filtered_candidates],
        decision=decision,
        news_summary=news_summary,
        chart_points=_build_chart_points(chart_points_raw),
    )


def build_best_trade_setup(db: Session, symbol: str) -> BestTradeResponse:
    strategy = db.scalar(select(StrategyConfig).limit(1))
    if not strategy:
        raise ValueError("No strategy configuration available.")

    available_instruments = _available_instruments(strategy)
    evaluated_setups: list[TradeSetupResponse] = []
    evaluation_rows: list[BestTradeInstrumentScoreResponse] = []

    for instrument in available_instruments:
        setup = build_trade_setup(
            db,
            symbol=symbol,
            requested_instrument=instrument,
            use_llm=False,
        )
        ranking_score = _ranking_score(setup)
        evaluated_setups.append(setup)
        evaluation_rows.append(
            BestTradeInstrumentScoreResponse(
                instrument=instrument,
                action=setup.decision.action,
                confidence=setup.decision.confidence,
                execution_ready=setup.execution_ready,
                ranking_score=round(ranking_score, 3),
                blocker=setup.execution_blockers[0] if setup.execution_blockers else None,
            )
        )

    if not evaluated_setups:
        raise LookupError(f"No trade setup could be built for {symbol.strip().upper()}.")

    best_setup = max(evaluated_setups, key=_ranking_score)
    return BestTradeResponse(
        symbol=best_setup.symbol,
        selected_instrument=best_setup.requested_instrument,
        available_instruments=available_instruments,
        evaluated_instruments=sorted(
            evaluation_rows,
            key=lambda row: row.ranking_score,
            reverse=True,
        ),
        setup=best_setup,
    )


def _analysis_window(market_open: bool) -> tuple[str, int]:
    if market_open:
        return "15m", 96
    return "1d", 90


def _configured_symbols(strategy: StrategyConfig) -> list[str]:
    values = (
        strategy.watchlist_symbols_json
        or (strategy.allowed_instruments_json or {}).get("symbols")
        or []
    )
    seen: list[str] = []
    for value in values:
        symbol = str(value).strip().upper()
        if symbol and symbol not in seen:
            seen.append(symbol)
    return seen


def _available_instruments(strategy: StrategyConfig) -> list[RequestedInstrument]:
    instruments: list[RequestedInstrument] = ["stock"]
    if strategy.options_enabled:
        instruments.append("option")
    if strategy.futures_enabled:
        instruments.append("future")
    return instruments


def _analysis_strategy(strategy: StrategyConfig, requested_instrument: RequestedInstrument) -> SimpleNamespace:
    return SimpleNamespace(
        options_enabled=strategy.options_enabled or requested_instrument == "option",
        futures_enabled=strategy.futures_enabled or requested_instrument == "future",
        shorting_enabled=strategy.shorting_enabled,
    )


def _filter_candidates(candidates: list, requested_instrument: RequestedInstrument) -> list:
    allowed_types = {
        "stock": {"STOCK"},
        "option": {"CALL", "PUT"},
        "future": {"FUTURE"},
    }[requested_instrument]
    return [
        candidate
        for candidate in candidates
        if candidate.action == "HOLD" or candidate.instrument_type in allowed_types
    ]


def _execution_blockers(
    strategy: StrategyConfig,
    requested_instrument: RequestedInstrument,
    action: str,
) -> list[str]:
    blockers: list[str] = []
    if requested_instrument == "option" and not strategy.options_enabled:
        blockers.append("Options execution is disabled in Strategy settings. This is research-only until options are enabled.")
    if requested_instrument == "future" and not strategy.futures_enabled:
        blockers.append("Futures execution is disabled in Strategy settings. This is research-only until futures are enabled.")
    if strategy.kill_switch:
        blockers.append("Kill switch is active. New trades stay blocked until strategy is resumed.")
    if action == "HOLD":
        blockers.append("No high-conviction setup is present for the requested instrument right now.")
    return blockers


def _align_hold_decision(decision, requested_instrument: RequestedInstrument):
    if decision.action != "HOLD":
        return decision
    family = {
        "stock": "STOCK",
        "option": "OPTION",
        "future": "FUTURE",
    }[requested_instrument]
    return decision.model_copy(update={"instrument_type": family})


def _ensure_decision_candidate(candidates: list, decision: LLMDecisionResponse) -> list:
    if any(
        candidate.action == decision.action
        and candidate.instrument_type == decision.instrument_type
        and candidate.side == decision.side
        for candidate in candidates
    ):
        return candidates

    return [
        *candidates,
        SimpleNamespace(
            symbol=decision.symbol,
            action=decision.action,
            instrument_type=decision.instrument_type,
            side=decision.side,
            score=decision.confidence,
            entry_type=decision.entry_type,
            to_dict=lambda: {
                "symbol": decision.symbol,
                "action": decision.action,
                "instrument_type": decision.instrument_type,
                "side": decision.side,
                "score": decision.confidence,
                "entry_type": decision.entry_type,
            },
        ),
    ]


def _mode_note(mode: str) -> str:
    if mode == "live":
        return "Strategy is in live mode, but this screen is still advisory until a trade passes hard risk checks."
    if mode == "paper":
        return "Strategy is in paper mode, so this setup can be simulated end to end without touching live capital."
    return "Strategy is in advisory mode, so this setup is for review-first decision making."


def _analysis_note(news_summary) -> str:
    if getattr(news_summary, "technical_only", False):
        reason = news_summary.technical_only_reason or "No fresh headlines are available."
        return (
            "This setup is running in technical-only mode using broker-backed historical candles, price structure, "
            f"volume, volatility, and indicator signals. {reason} Any real execution still goes through the risk engine before an order can be placed."
        )
    return (
        "This setup blends broker-backed historical candles, the latest quote, and recent Marketaux headlines. "
        "Any real execution still goes through the risk engine before an order can be placed."
    )


def _ranking_score(setup: TradeSetupResponse) -> float:
    score = setup.decision.confidence
    if setup.execution_ready:
        score += 0.1
    if setup.decision.action == "HOLD":
        score -= 0.35
    if setup.decision.action in {"EXIT", "REDUCE"}:
        score += 0.03
    score -= min(len(setup.execution_blockers), 3) * 0.05
    return score


def _heuristic_decision(symbol: str, requested_instrument: RequestedInstrument, quote, features, candidates: list) -> LLMDecisionResponse:
    top_candidate = next((candidate for candidate in candidates if candidate.action != "HOLD"), None)
    if top_candidate is None:
        return fallback_hold(
            symbol=symbol,
            rationale="No high-conviction setup is present for the requested instrument right now.",
        )

    stop_loss, take_profit = _protective_levels(top_candidate.side, quote.ltp, features.atr)
    risk_level = "MEDIUM" if top_candidate.score >= 0.7 else "LOW"
    return LLMDecisionResponse(
        decision=top_candidate.action,
        symbol=symbol,
        instrument_type=top_candidate.instrument_type,
        action=top_candidate.action,
        side=top_candidate.side,
        quantity=1.0,
        entry_type=top_candidate.entry_type,
        entry_price_hint=quote.ltp,
        stop_loss=stop_loss,
        take_profit=take_profit,
        max_holding_minutes=120 if requested_instrument == "stock" else 90,
        confidence=min(max(top_candidate.score, 0.2), 0.95),
        rationale_points=[
            f"Heuristic pre-ranking favours {top_candidate.action.replace('_', ' ').lower()} for {symbol}.",
            f"Momentum {features.momentum_score:.2f}, trend {features.trend_score:.2f}, RSI {features.rsi:.2f}.",
        ],
        invalidation_condition=(
            f"Exit if price falls below {stop_loss:.2f}."
            if top_candidate.side == "BUY"
            else f"Exit if price rises above {stop_loss:.2f}."
        ),
        risk_level=risk_level,
    )


def _protective_levels(side: str, ltp: float, atr: float) -> tuple[float, float]:
    buffer = max(atr, ltp * 0.01)
    target_buffer = max(buffer * 1.8, ltp * 0.015)
    if side.upper() == "SELL":
        return round(ltp + buffer, 2), round(max(ltp - target_buffer, 0.01), 2)
    return round(max(ltp - buffer, 0.01), 2), round(ltp + target_buffer, 2)


def _build_chart_points(candles: list) -> list[TradeChartPointResponse]:
    closes = [candle.close for candle in candles]
    chart_points: list[TradeChartPointResponse] = []
    for index, candle in enumerate(candles):
        fast_ma = _moving_average(closes[: index + 1], 5)
        slow_ma = _moving_average(closes[: index + 1], 20)
        chart_points.append(
            TradeChartPointResponse(
                timestamp=candle.timestamp,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                fast_ma=round(fast_ma, 2) if fast_ma else None,
                slow_ma=round(slow_ma, 2) if slow_ma else None,
            )
        )
    return chart_points


def _moving_average(values: list[float], window: int) -> float:
    if not values:
        return 0.0
    segment = values[-window:] if len(values) >= window else values
    return mean(segment)
