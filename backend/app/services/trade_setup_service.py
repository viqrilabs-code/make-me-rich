from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from math import ceil, floor
from statistics import mean
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm import LLMDecisionEngine
from app.llm.schemas import LLMDecisionResponse, fallback_hold
from app.models import StrategyConfig, TradingGoal
from app.schemas.market import (
    BestTradeInstrumentScoreResponse,
    OptionContractPlanResponse,
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


_NSE_WEEKLY_EXPIRY_WEEKDAY = 1  # Tuesday
_NSE_DERIVATIVES_TRADING_HOLIDAYS_2026: set[date] = {
    date(2026, 1, 26),
    date(2026, 3, 3),
    date(2026, 3, 26),
    date(2026, 3, 31),
    date(2026, 4, 3),
    date(2026, 4, 14),
    date(2026, 5, 1),
    date(2026, 5, 28),
    date(2026, 6, 26),
    date(2026, 9, 14),
    date(2026, 10, 2),
    date(2026, 10, 20),
    date(2026, 11, 10),
    date(2026, 11, 24),
    date(2026, 12, 25),
}


def build_trade_setup(
    db: Session,
    symbol: str,
    requested_instrument: RequestedInstrument,
    *,
    use_llm: bool = True,
    allow_fallback_broker: bool = True,
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
    if using_fallback_broker and strategy.selected_broker != "mock" and not allow_fallback_broker:
        raise RuntimeError(
            f"{strategy.selected_broker.upper()} is unavailable right now. "
            "Manual trade search is blocked because falling back to mock prices would be misleading. "
            "Reconnect the live broker in Strategy before fetching a trade."
        )
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
    decision = _make_hold_decision_decisive(decision, requested_instrument)
    filtered_candidates = _ensure_decision_candidate(filtered_candidates, decision)
    execution_blockers = _execution_blockers(strategy, requested_instrument, decision.action)
    option_contract = (
        _build_option_contract_plan(adapter, clean_symbol, quote.ltp, features.atr, decision)
        if requested_instrument == "option"
        else None
    )
    trade_name = _trade_name(clean_symbol, requested_instrument, decision, option_contract)

    return TradeSetupResponse(
        symbol=clean_symbol,
        trade_name=trade_name,
        requested_instrument=requested_instrument,
        chart_interval=chart_interval,
        chart_lookback=chart_lookback,
        analysis_generated_at=datetime.now(timezone.utc),
        analysis_engine="llm" if use_llm else "heuristic",
        selected_broker=strategy.selected_broker,
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
        option_contract=option_contract,
    )


def build_best_trade_setup(
    db: Session,
    symbol: str,
    *,
    allow_fallback_broker: bool = True,
) -> BestTradeResponse:
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
            allow_fallback_broker=allow_fallback_broker,
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


def _make_hold_decision_decisive(decision: LLMDecisionResponse, requested_instrument: RequestedInstrument):
    if decision.action != "HOLD":
        return decision

    lane_label = {
        "stock": "stock",
        "option": "options",
        "future": "futures",
    }[requested_instrument]
    rationale = [point.strip().rstrip(".") for point in decision.rationale_points if point and point.strip()]
    primary_reason = rationale[0] if rationale else f"No clear {lane_label} edge is present right now"
    if primary_reason.upper().startswith(("WAIT", "DO NOT", "STAND ASIDE")):
        primary_line = primary_reason
    else:
        primary_line = f"WAIT. Do not enter this {lane_label} trade now."

    reason_line = primary_reason
    if reason_line.upper().startswith(("WAIT", "DO NOT", "STAND ASIDE")):
        reason_line = f"Reason: no clear {lane_label} edge is present right now."
    else:
        reason_line = f"Reason: {reason_line}."

    recheck_line = "Re-check only after a clean breakout, breakdown, or clear volume expansion."
    invalidation = decision.invalidation_condition.strip() if decision.invalidation_condition else ""
    if not invalidation or invalidation == "A stronger risk-adjusted setup appears.":
        invalidation = recheck_line

    return decision.model_copy(
        update={
            "quantity": 0.0,
            "confidence": min(decision.confidence, 0.35),
            "rationale_points": [
                primary_line,
                reason_line,
                recheck_line,
            ],
            "invalidation_condition": invalidation,
            "risk_level": "LOW",
        }
    )


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


def _trade_name(
    symbol: str,
    requested_instrument: RequestedInstrument,
    decision: LLMDecisionResponse,
    option_contract: OptionContractPlanResponse | None,
) -> str:
    if option_contract:
        return option_contract.contract_name
    if requested_instrument == "future":
        return f"{symbol} futures setup"
    if decision.action == "HOLD":
        return f"{symbol} {requested_instrument} setup"
    return f"{symbol} {decision.action.replace('_', ' ').lower()}"


def _build_option_contract_plan(adapter, symbol: str, underlying_ltp: float, atr: float, decision: LLMDecisionResponse) -> OptionContractPlanResponse | None:
    option_side = "CALL" if decision.action == "BUY_CALL" else "PUT" if decision.action == "BUY_PUT" else None
    if not option_side:
        return None

    live_plan = _live_option_contract_plan(adapter, symbol, underlying_ltp, atr, decision, option_side)
    if live_plan:
        return live_plan
    return _synthetic_option_contract_plan(symbol, underlying_ltp, atr, decision, option_side)


def _live_option_contract_plan(
    adapter,
    symbol: str,
    underlying_ltp: float,
    atr: float,
    decision: LLMDecisionResponse,
    option_side: str,
) -> OptionContractPlanResponse | None:
    get_instruments = getattr(adapter, "_get_instruments", None)
    instrument_from_row = getattr(adapter, "_instrument_from_row", None)
    infer_type = getattr(adapter, "_infer_instrument_type_from_row", None)
    if not callable(get_instruments) or not callable(instrument_from_row):
        return None

    try:
        rows = get_instruments("fno")
    except Exception:
        return None

    candidates: list[tuple[datetime, float, dict[str, str]]] = []
    today = datetime.now(timezone.utc).date()
    for row in rows:
        row_type = infer_type(row) if callable(infer_type) else str(row.get("OPTION_TYPE") or "").upper()
        if row_type != option_side:
            continue
        underlying_value = str(
            row.get("UNDERLYING_SYMBOL")
            or row.get("SYMBOL_NAME")
            or row.get("TRADING_SYMBOL")
            or row.get("CUSTOM_SYMBOL")
            or ""
        ).upper()
        if symbol not in underlying_value:
            continue

        expiry = _parse_contract_expiry(row)
        if expiry and expiry.date() < today:
            continue
        strike = _parse_float_from_row(row, "STRIKE_PRICE", "STRIKE", "STRIKEPRC")
        if strike is None:
            continue
        expiry_rank = expiry or datetime.now(timezone.utc) + timedelta(days=365)
        strike_distance = abs(strike - underlying_ltp)
        if option_side == "CALL" and strike < underlying_ltp:
            strike_distance *= 1.15
        if option_side == "PUT" and strike > underlying_ltp:
            strike_distance *= 1.15
        candidates.append((expiry_rank, strike_distance, row))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1]))
    chosen_row = candidates[0][2]
    requested_symbol = (
        chosen_row.get("TRADING_SYMBOL")
        or chosen_row.get("CUSTOM_SYMBOL")
        or chosen_row.get("SYMBOL_NAME")
        or symbol
    )
    try:
        resolved = instrument_from_row(requested_symbol, chosen_row, option_side)
    except Exception:
        return None

    premium_entry = None
    try:
        option_quotes = adapter.get_quotes([resolved.scrip_code])
        premium_entry = option_quotes[0].ltp if option_quotes else None
    except Exception:
        premium_entry = None

    strike = _parse_float_from_row(chosen_row, "STRIKE_PRICE", "STRIKE", "STRIKEPRC")
    lot_size = int(round(_parse_float_from_row(chosen_row, "LOT_SIZE", "LOTSIZE", "MARKET_LOT") or 1))
    expiry = _parse_contract_expiry(chosen_row)
    return _option_plan_from_pricing(
        contract_name=resolved.display_symbol,
        contract_symbol=resolved.scrip_code,
        option_side=option_side,
        expiry_label=expiry.strftime("%d %b %Y") if expiry else None,
        strike_price=strike,
        lot_size=max(lot_size, 1),
        premium_entry=premium_entry,
        underlying_ltp=underlying_ltp,
        atr=atr,
        decision=decision,
        pricing_source="live_contract",
    )


def _synthetic_option_contract_plan(
    symbol: str,
    underlying_ltp: float,
    atr: float,
    decision: LLMDecisionResponse,
    option_side: str,
) -> OptionContractPlanResponse:
    strike_step = _strike_step(underlying_ltp)
    if option_side == "CALL":
        strike = _round_up_to_step(underlying_ltp, strike_step)
    else:
        strike = _round_down_to_step(underlying_ltp, strike_step)
    expiry = _next_weekly_expiry()
    suffix = "CE" if option_side == "CALL" else "PE"
    contract_name = f"{symbol} {expiry.strftime('%d %b')} {int(strike)} {suffix}"
    contract_symbol = contract_name.replace(" ", "").upper()
    premium_entry = round(max(underlying_ltp * 0.012, atr * 0.85, 3.0), 2)
    return _option_plan_from_pricing(
        contract_name=contract_name,
        contract_symbol=contract_symbol,
        option_side=option_side,
        expiry_label=expiry.strftime("%d %b %Y"),
        strike_price=float(strike),
        lot_size=1,
        premium_entry=premium_entry,
        underlying_ltp=underlying_ltp,
        atr=atr,
        decision=decision,
        pricing_source="synthetic_contract",
    )


def _option_plan_from_pricing(
    *,
    contract_name: str,
    contract_symbol: str,
    option_side: str,
    expiry_label: str | None,
    strike_price: float | None,
    lot_size: int,
    premium_entry: float | None,
    underlying_ltp: float,
    atr: float,
    decision: LLMDecisionResponse,
    pricing_source: str,
) -> OptionContractPlanResponse:
    base_premium = premium_entry or round(max(underlying_ltp * 0.012, atr * 0.85, 3.0), 2)
    underlying_entry = decision.entry_price_hint or underlying_ltp
    underlying_stop = decision.stop_loss or max(underlying_entry - max(atr, underlying_entry * 0.012), 0.01)
    underlying_target = decision.take_profit or (underlying_entry + max(atr * 1.8, underlying_entry * 0.018))
    risk_pct = max(abs(underlying_entry - underlying_stop) / max(underlying_entry, 0.01), 0.012)
    reward_pct = max(abs(underlying_target - underlying_entry) / max(underlying_entry, 0.01), 0.018)
    premium_risk_pct = min(max(risk_pct * 2.4, 0.18), 0.55)
    premium_reward_pct = min(max(reward_pct * 2.8, 0.28), 1.1)
    premium_stop = round(max(base_premium * (1 - premium_risk_pct), 0.05), 2)
    premium_target = round(base_premium * (1 + premium_reward_pct), 2)
    probable_profit = round(max((premium_target - base_premium) * lot_size, 0.0), 2)
    probable_loss = round(max((base_premium - premium_stop) * lot_size, 0.0), 2)
    return OptionContractPlanResponse(
        contract_name=contract_name,
        contract_symbol=contract_symbol,
        option_side=option_side,
        expiry_label=expiry_label,
        strike_price=round(strike_price, 2) if strike_price is not None else None,
        lot_size=lot_size,
        premium_entry=round(base_premium, 2),
        premium_stop_loss=premium_stop,
        premium_take_profit=premium_target,
        probable_profit=probable_profit,
        probable_loss=probable_loss,
        underlying_entry=round(underlying_entry, 2),
        underlying_stop_loss=round(underlying_stop, 2),
        underlying_take_profit=round(underlying_target, 2),
        pricing_source=pricing_source,
    )


def _parse_contract_expiry(row: dict[str, str]) -> datetime | None:
    for key in ("EXPIRY_DATE", "EXPIRY", "EXPIRY_DT"):
        value = str(row.get(key) or "").strip()
        if not value:
            continue
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d-%b-%y", "%d %b %Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _parse_float_from_row(row: dict[str, str], *keys: str) -> float | None:
    for key in keys:
        raw = str(row.get(key) or "").strip().replace(",", "")
        if not raw:
            continue
        try:
            return float(raw)
        except ValueError:
            continue
    return None


def _strike_step(price: float) -> int:
    if price >= 5000:
        return 100
    if price >= 1000:
        return 50
    if price >= 250:
        return 20
    return 10


def _round_up_to_step(value: float, step: int) -> int:
    return int(ceil(value / step) * step)


def _round_down_to_step(value: float, step: int) -> int:
    return int(floor(value / step) * step)


def _next_weekly_expiry(reference: datetime | None = None) -> datetime:
    now = reference or datetime.now(timezone.utc)
    days_until_expiry = (_NSE_WEEKLY_EXPIRY_WEEKDAY - now.weekday()) % 7
    if days_until_expiry == 0:
        days_until_expiry = 7
    candidate = (now + timedelta(days=days_until_expiry)).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    while candidate.weekday() >= 5 or candidate.date() in _nse_derivatives_holidays(candidate.year):
        candidate -= timedelta(days=1)
    return candidate


def _nse_derivatives_holidays(year: int) -> set[date]:
    if year == 2026:
        return _NSE_DERIVATIVES_TRADING_HOLIDAYS_2026
    return set()


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
