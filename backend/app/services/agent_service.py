from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from statistics import mean
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.brokers.mock import MockBrokerAdapter
from app.brokers.types import Candle, Quote
from app.db.session import SessionLocal
from app.llm import LLMDecisionEngine
from app.llm.schemas import LLMDecisionResponse, fallback_hold
from app.models import AgentEvent, AgentSession, DailyPerformance, Order, Position, StrategyConfig, TradeDecision, TradingGoal
from app.risk.engine import RiskEngine
from app.risk.models import RiskEvaluationContext
from app.schemas.agent import (
    AgentCommandResponse,
    AgentEventResponse,
    AgentSessionResponse,
    AgentStatusResponse,
)
from app.services.agent_event_bus import agent_event_bus
from app.services.audit_service import add_audit_log, add_risk_event
from app.services.broker_service import get_active_broker
from app.services.execution_service import ExecutionService
from app.services.goal_planner import compute_goal_plan
from app.services.market_service import MarketService
from app.services.news_service import NewsService
from app.services.strategy_engine import FeatureSet, compute_features, generate_candidate_actions
from app.utils.time import is_market_open


logger = logging.getLogger(__name__)

AGENT_LOOP_MIN_SECONDS = 30
AGENT_LOOP_MAX_SECONDS = 120
RECENT_EVENT_LIMIT = 40


def _rounded(value: float | int | None) -> float:
    return round(float(value or 0.0), 2)


@dataclass(frozen=True, slots=True)
class AgentLane:
    key: str
    label: str
    requested_instrument: str
    interval: str
    lookback: int
    holding_minutes: int
    enabled: bool = True
    execution_supported: bool = True
    reason: str | None = None


@dataclass(slots=True)
class LaneEvaluation:
    lane: AgentLane
    quote: Quote | None
    candles: list[Candle]
    features: FeatureSet | None
    news_sentiment: float
    news_technical_only: bool
    candidates: list[dict[str, Any]]
    decision: LLMDecisionResponse
    ranking_score: float
    note: str


class AutonomousTradingAgent:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._active_session_id: int | None = None

    def prepare_startup(self) -> None:
        with SessionLocal() as db:
            running_sessions = db.scalars(
                select(AgentSession).where(AgentSession.status.in_(["running", "starting"]))
            ).all()
            for session in running_sessions:
                session.status = "stopped"
                session.stopped_at = datetime.now(timezone.utc)
                session.last_message = "Stopped during startup recovery."
            if running_sessions:
                db.commit()

    def start(self, symbol: str, launched_from: str = "overview") -> AgentCommandResponse:
        clean_symbol = symbol.strip().upper()
        if not clean_symbol:
            raise ValueError("A stock symbol is required to start the AI agent.")

        with self._lock:
            if self._thread and self._thread.is_alive():
                raise ValueError("The autonomous agent is already active.")

            with SessionLocal() as db:
                strategy = db.scalar(select(StrategyConfig).limit(1))
                goal = db.scalar(select(TradingGoal).order_by(TradingGoal.updated_at.desc()).limit(1))
                if not strategy:
                    raise ValueError("No strategy configuration is available yet.")

                configured_symbols = [value.strip().upper() for value in (strategy.watchlist_symbols_json or []) if value]
                if configured_symbols and clean_symbol not in configured_symbols:
                    raise ValueError(
                        f"{clean_symbol} is not in your Strategy watchlist. Pick one of: {', '.join(configured_symbols)}."
                    )

                adapter, broker_name, using_fallback = get_active_broker(db)
                account = adapter.get_account()
                target_multiplier = goal.target_multiplier if goal else 1.2
                target_equity = round(account.total_equity * target_multiplier, 2)
                lanes = self._build_lanes(strategy)
                auto_execute = strategy.mode in {"paper", "live"} and not strategy.kill_switch
                scheduler_was_paused = bool(strategy.pause_scheduler)
                strategy.pause_scheduler = True

                session = AgentSession(
                    symbol=clean_symbol,
                    status="starting",
                    mode=strategy.mode,
                    selected_broker=broker_name,
                    target_multiplier=target_multiplier,
                    start_equity=account.total_equity,
                    current_equity=account.total_equity,
                    target_equity=target_equity,
                    auto_execute=auto_execute,
                    launched_from=launched_from,
                    allowed_lanes_json=[lane.key for lane in lanes],
                    heartbeat_at=datetime.now(timezone.utc),
                    started_at=datetime.now(timezone.utc),
                    stopped_at=None,
                    last_message="Preparing the specialist lanes.",
                    raw_state_json={
                        "selected_symbol": clean_symbol,
                        "goal_note": "Target multipliers are aspirational and never guaranteed.",
                        "broker": broker_name,
                        "scheduler_was_paused": scheduler_was_paused,
                    },
                )
                db.add(session)
                db.flush()
                self._refresh_session_financials(
                    db,
                    session,
                    account=account,
                    broker_name=broker_name,
                    using_fallback=using_fallback,
                )

                self._persist_event(
                    db=db,
                    session=session,
                    phase="observe",
                    event_type="session_started",
                    severity="info",
                    message=f"Autonomous agent activated for {clean_symbol}.",
                    metadata={
                        "symbol": clean_symbol,
                        "mode": strategy.mode,
                        "broker": broker_name,
                        "target_multiplier": target_multiplier,
                        "lanes": [lane.key for lane in lanes],
                    },
                )
                db.commit()
                db.refresh(session)
                session_response = self._serialize_session(session)
                self._active_session_id = session.id
                self._publish_status()

            self._stop_event = threading.Event()
            self._thread = threading.Thread(
                target=self._run_loop,
                args=(session_response.id,),
                name="autonomous-trading-agent",
                daemon=True,
            )
            self._thread.start()
            return AgentCommandResponse(
                message=f"AI agent started for {clean_symbol}.",
                session=session_response,
            )

    def stop(self, reason: str = "Stopped by user") -> AgentCommandResponse:
        with self._lock:
            self._stop_event.set()
            thread = self._thread
            active_session_id = self._active_session_id

        if thread and thread.is_alive():
            thread.join(timeout=3)

        session_response = None
        if active_session_id:
            with SessionLocal() as db:
                session = db.get(AgentSession, active_session_id)
                if session and session.status not in {"stopped", "completed", "failed"}:
                    strategy = db.scalar(select(StrategyConfig).limit(1))
                    if strategy and not bool((session.raw_state_json or {}).get("scheduler_was_paused")):
                        strategy.pause_scheduler = False
                    session.status = "stopped"
                    session.stopped_at = datetime.now(timezone.utc)
                    session.last_message = reason
                    self._persist_event(
                        db=db,
                        session=session,
                        phase="reflect",
                        event_type="session_stopped",
                        severity="warning",
                        message=reason,
                        metadata={"reason": reason},
                    )
                    db.commit()
                    db.refresh(session)
                    session_response = self._serialize_session(session)
                    self._publish_status()
                elif session:
                    session_response = self._serialize_session(session)

        with self._lock:
            self._thread = None
            self._active_session_id = None

        return AgentCommandResponse(message=reason, session=session_response)

    def status(self) -> AgentStatusResponse:
        with SessionLocal() as db:
            try:
                session = db.scalar(
                    select(AgentSession).order_by(AgentSession.started_at.desc(), AgentSession.id.desc()).limit(1)
                )
                recent_events = db.scalars(
                    select(AgentEvent).order_by(AgentEvent.timestamp.desc(), AgentEvent.id.desc()).limit(RECENT_EVENT_LIMIT)
                ).all()
                strategy = db.scalar(select(StrategyConfig).limit(1))
            except OperationalError:
                session = None
                recent_events = []
                strategy = None

            suggested_symbol = None
            if strategy and strategy.watchlist_symbols_json:
                suggested_symbol = strategy.watchlist_symbols_json[0]

            return AgentStatusResponse(
                active=bool(session and session.status in {"starting", "running"}),
                can_start=not bool(session and session.status in {"starting", "running"}),
                suggested_symbol=suggested_symbol,
                message=session.last_message if session else "Autonomous agent is idle.",
                session=self._serialize_session(session) if session else None,
                recent_events=[self._serialize_event(event) for event in reversed(recent_events)],
            )

    def _run_loop(self, session_id: int) -> None:
        try:
            while not self._stop_event.is_set():
                with SessionLocal() as db:
                    session = db.get(AgentSession, session_id)
                    if session is None:
                        return
                    strategy = db.scalar(select(StrategyConfig).limit(1))
                    goal = db.scalar(select(TradingGoal).order_by(TradingGoal.updated_at.desc()).limit(1))
                    if not strategy:
                        self._fail_session(db, session, "Strategy configuration disappeared during agent run.")
                        return

                    adapter, broker_name, using_fallback = get_active_broker(db)
                    market_service = MarketService(adapter)
                    news_service = NewsService()
                    risk_engine = RiskEngine()
                    execution = ExecutionService(adapter)
                    llm_engine = LLMDecisionEngine()
                    account = adapter.get_account()

                    session.status = "running"
                    session.selected_broker = broker_name
                    session.last_message = "Scanning the specialist lanes."
                    self._refresh_session_financials(
                        db,
                        session,
                        account=account,
                        broker_name=broker_name,
                        using_fallback=using_fallback,
                    )

                    if session.target_equity > 0 and account.total_equity >= session.target_equity:
                        self._persist_event(
                            db=db,
                            session=session,
                            phase="reflect",
                            event_type="target_reached",
                            severity="success",
                            message="Target equity reached. The autonomous agent is standing down.",
                            metadata={
                                "current_equity": account.total_equity,
                                "target_equity": session.target_equity,
                            },
                        )
                        session.status = "completed"
                        session.stopped_at = datetime.now(timezone.utc)
                        session.last_message = "Target equity reached."
                        self._restore_scheduler_state(db, session)
                        db.commit()
                        self._publish_status()
                        return

                    self._persist_event(
                        db=db,
                        session=session,
                        phase="observe",
                        event_type="cycle_started",
                        severity="info",
                        message=f"Scanning {session.symbol} across the enabled specialist lanes.",
                        metadata={
                            "symbol": session.symbol,
                            "mode": strategy.mode,
                            "equity": account.total_equity,
                        },
                    )

                    news_summary = news_service.summarize([session.symbol])
                    evaluations = self._evaluate_lanes(
                        db=db,
                        session=session,
                        strategy=strategy,
                        symbol=session.symbol,
                        market_service=market_service,
                        llm_engine=llm_engine,
                        news_summary=news_summary,
                    )
                    if not evaluations:
                        session.last_message = "No tradable specialist lane produced a usable setup."
                        self._persist_event(
                            db=db,
                            session=session,
                            phase="think",
                            event_type="no_lane_signal",
                            severity="warning",
                            message="No tradable specialist lane produced a usable setup.",
                            metadata={"symbol": session.symbol},
                        )
                        db.commit()
                        self._publish_status()
                    else:
                        best = max(evaluations, key=lambda item: item.ranking_score)
                        coordinator_decision = self._coordinator_pick(
                            db=db,
                            session=session,
                            strategy=strategy,
                            goal=goal,
                            account_equity=account.total_equity,
                            broker_name=broker_name,
                            using_fallback=using_fallback,
                            llm_engine=llm_engine,
                            evaluations=evaluations,
                        )
                        decision = coordinator_decision or best.decision
                        chosen_lane = next(
                            (
                                evaluation
                                for evaluation in evaluations
                                if evaluation.decision.action == decision.action
                                and evaluation.decision.instrument_type == decision.instrument_type
                                and evaluation.decision.side == decision.side
                            ),
                            best,
                        )

                        self._persist_event(
                            db=db,
                            session=session,
                            phase="think",
                            event_type="coordinator_selected",
                            severity="info",
                            message=f"Coordinator selected {decision.action} on the {chosen_lane.lane.label} lane.",
                            metadata={
                                "symbol": decision.symbol,
                                "action": decision.action,
                                "instrument_type": decision.instrument_type,
                                "confidence": decision.confidence,
                                "lane": chosen_lane.lane.key,
                            },
                        )

                        open_positions = db.scalars(select(Position).where(Position.status == "open")).all()
                        existing_position = next(
                            (position for position in open_positions if position.symbol == decision.symbol),
                            None,
                        )
                        recent_orders = db.scalars(
                            select(Order).where(Order.placed_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0))
                        ).all()

                        risk_result = risk_engine.evaluate(
                            RiskEvaluationContext(
                                strategy=strategy,
                                decision=decision,
                                account_equity=account.total_equity,
                                daily_loss_pct=self._daily_loss_pct(db, account.total_equity),
                                drawdown_pct=self._drawdown_pct(db),
                                open_positions=open_positions,
                                existing_position=existing_position,
                                quote=chosen_lane.quote,
                                duplicate_keys={
                                    f"{order.symbol}:{order.raw_payload_json.get('decision_action')}:{order.side}"
                                    for order in recent_orders
                                },
                                now=datetime.now(timezone.utc),
                                market_open=is_market_open(),
                                stale_after_minutes=15,
                            )
                        )

                        self._persist_event(
                            db=db,
                            session=session,
                            phase="act",
                            event_type="risk_checked",
                            severity="success" if risk_result.approved else "warning",
                            message=(
                                "Risk engine approved the trade."
                                if risk_result.approved
                                else "Risk engine rejected the trade."
                            ),
                            metadata={
                                "approved": risk_result.approved,
                                "rejection_reasons": risk_result.rejection_reasons,
                                "computed_position_size": risk_result.computed_position_size,
                                "final_order_payload": risk_result.final_order_payload,
                            },
                        )

                        decision_row = TradeDecision(
                            timestamp=datetime.now(timezone.utc),
                            symbol=decision.symbol,
                            action=decision.action,
                            instrument_type=decision.instrument_type,
                            confidence=decision.confidence,
                            rationale_json=decision.rationale_points,
                            llm_response_json={
                                **decision.model_dump(),
                                "agent_mode": True,
                                "lane": chosen_lane.lane.key,
                            },
                            candidate_actions_json=[
                                {
                                    "lane": evaluation.lane.key,
                                    "note": evaluation.note,
                                    "ranking_score": evaluation.ranking_score,
                                    "decision": evaluation.decision.model_dump(),
                                }
                                for evaluation in evaluations
                            ],
                            approved=risk_result.approved,
                            rejection_reasons_json=risk_result.rejection_reasons,
                            scheduler_run_id=None,
                        )
                        db.add(decision_row)
                        db.flush()

                        execution_result = execution.execute(
                            db=db,
                            strategy=strategy,
                            decision=decision,
                            risk_result=risk_result,
                            scheduler_run_id=None,
                        )
                        post_execution_account = (
                            MockBrokerAdapter(SessionLocal).get_account()
                            if strategy.mode == "paper"
                            else adapter.get_account()
                        )
                        self._refresh_session_financials(
                            db,
                            session,
                            account=post_execution_account,
                            broker_name=broker_name,
                            using_fallback=using_fallback,
                        )
                        execution.record_snapshot(db, post_execution_account, source=f"agent:{session.symbol}")
                        execution.update_daily_performance(db)

                        message = self._execution_message(decision, execution_result)
                        self._persist_event(
                            db=db,
                            session=session,
                            phase="act",
                            event_type=self._execution_event_type(execution_result),
                            severity="success" if risk_result.approved else "warning",
                            message=message,
                            metadata={
                                "decision_id": decision_row.id,
                                "decision": decision.model_dump(),
                                "execution": execution_result,
                                "lane": chosen_lane.lane.key,
                            },
                        )

                        session.last_message = message
                        db.commit()
                        self._publish_status()

                sleep_seconds = self._loop_sleep_seconds(strategy.polling_interval_minutes if strategy else 1)
                elapsed = 0
                while elapsed < sleep_seconds and not self._stop_event.is_set():
                    time.sleep(1)
                    elapsed += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Autonomous agent failed")
            with SessionLocal() as db:
                session = db.get(AgentSession, session_id)
                if session:
                    self._fail_session(db, session, str(exc))
        finally:
            with self._lock:
                self._thread = None
                self._active_session_id = None

    def _evaluate_lanes(
        self,
        *,
        db,
        session: AgentSession,
        strategy: StrategyConfig,
        symbol: str,
        market_service: MarketService,
        llm_engine: LLMDecisionEngine,
        news_summary,
    ) -> list[LaneEvaluation]:
        evaluations: list[LaneEvaluation] = []
        lanes = self._build_lanes(strategy)
        for lane in lanes:
            if not lane.enabled:
                continue
            if not lane.execution_supported:
                self._persist_event(
                    db=db,
                    session=session,
                    phase="observe",
                    event_type="specialist_skipped",
                    severity="warning",
                    message=f"{lane.label} skipped.",
                    metadata={"lane": lane.key, "reason": lane.reason},
                )
                continue

            quote = market_service.get_quotes_map([symbol]).get(symbol)
            candles = market_service.get_candles_map([symbol], interval=lane.interval, lookback=lane.lookback).get(symbol, [])
            if not quote or len(candles) < 20:
                self._persist_event(
                    db=db,
                    session=session,
                    phase="observe",
                    event_type="specialist_skipped",
                    severity="warning",
                    message=f"{lane.label} could not get enough market data.",
                    metadata={
                        "lane": lane.key,
                        "quote_available": bool(quote),
                        "candles": len(candles),
                    },
                )
                continue

            features = compute_features(symbol, candles)
            specialist_strategy = self._specialist_strategy(strategy, lane.requested_instrument)
            candidates = generate_candidate_actions(
                strategy=specialist_strategy,
                features=features,
                news_sentiment=news_summary.overall_sentiment,
            )
            filtered_candidates = self._lane_candidates(candidates, lane.requested_instrument)
            decision = self._specialist_decision(
                symbol=symbol,
                lane=lane,
                quote=quote,
                features=features,
                candidates=filtered_candidates,
                llm_engine=llm_engine,
            )
            note = (
                decision.rationale_points[0]
                if decision.rationale_points
                else f"{lane.label} specialist completed its pass."
            )
            ranking_score = self._ranking_score(decision, lane)
            evaluation = LaneEvaluation(
                lane=lane,
                quote=quote,
                candles=candles,
                features=features,
                news_sentiment=news_summary.overall_sentiment,
                news_technical_only=bool(getattr(news_summary, "technical_only", False)),
                candidates=[candidate.to_dict() for candidate in filtered_candidates],
                decision=decision,
                ranking_score=ranking_score,
                note=note,
            )
            evaluations.append(evaluation)
            self._persist_event(
                db=db,
                session=session,
                phase="observe",
                event_type="specialist_observe",
                severity="info",
                message=f"{lane.label} observed {symbol} and produced {decision.action}.",
                metadata={
                    "lane": lane.key,
                    "instrument": lane.requested_instrument,
                    "interval": lane.interval,
                    "lookback": lane.lookback,
                    "decision": decision.model_dump(),
                    "features": asdict(features),
                    "technical_only": evaluation.news_technical_only,
                },
            )
        return evaluations

    def _coordinator_pick(
        self,
        *,
        db,
        session: AgentSession,
        strategy: StrategyConfig,
        goal: TradingGoal | None,
        account_equity: float,
        broker_name: str,
        using_fallback: bool,
        llm_engine: LLMDecisionEngine,
        evaluations: list[LaneEvaluation],
    ) -> LLMDecisionResponse | None:
        if not evaluations:
            return None

        candidate_actions: list[dict[str, Any]] = []
        quotes: dict[str, Any] = {}
        technical_features: list[dict[str, Any]] = []
        for evaluation in evaluations:
            candidate_actions.append(
                {
                    "symbol": evaluation.decision.symbol,
                    "action": evaluation.decision.action,
                    "instrument_type": evaluation.decision.instrument_type,
                    "side": evaluation.decision.side,
                    "score": evaluation.ranking_score,
                    "entry_type": evaluation.decision.entry_type,
                    "lane": evaluation.lane.key,
                }
            )
            if evaluation.quote:
                quotes[evaluation.decision.symbol] = evaluation.quote.model_dump()
            if evaluation.features:
                technical_features.append({**asdict(evaluation.features), "lane": evaluation.lane.key})

        goal_plan = (
            compute_goal_plan(goal, current_capital=account_equity).to_dict()
            if goal
            else {
                "target_amount": round(account_equity * session.target_multiplier, 2),
                "remaining_gap": max(session.target_equity - account_equity, 0),
                "days_remaining": 0,
                "daily_required_pace": 0.0,
                "urgency_score": 0.0,
                "mode_suggestion": "defensive",
            }
        )
        try:
            return llm_engine.request_decision(
                {
                    "default_symbol": session.symbol,
                    "profit_target_note": "Turning X into 1.2X is aspirational and never guaranteed.",
                    "goal_plan": goal_plan,
                    "portfolio": {"current_capital": account_equity},
                    "strategy": {
                        "mode": strategy.mode,
                        "risk_profile": strategy.risk_profile,
                        "selected_broker": broker_name,
                        "using_fallback_broker": using_fallback,
                        "agent_mode": "react-multi-specialist",
                    },
                    "technical_features": technical_features,
                    "candidate_actions": candidate_actions,
                    "quotes": quotes,
                    "news_summary": {
                        "overall_sentiment": mean([evaluation.news_sentiment for evaluation in evaluations]) if evaluations else 0.0,
                        "top_symbols": [{"symbol": session.symbol, "articles": 0}],
                    },
                },
                db,
            )
        except Exception as exc:  # noqa: BLE001
            self._persist_event(
                db=db,
                session=session,
                phase="think",
                event_type="coordinator_fallback",
                severity="warning",
                message="Coordinator LLM fell back to heuristic ranking.",
                metadata={"error": str(exc)},
            )
            return None

    def _specialist_decision(
        self,
        *,
        symbol: str,
        lane: AgentLane,
        quote: Quote,
        features: FeatureSet,
        candidates: list,
        llm_engine: LLMDecisionEngine,
    ) -> LLMDecisionResponse:
        del llm_engine
        top_candidate = next((candidate for candidate in candidates if candidate.action != "HOLD"), None)
        if top_candidate is None:
            return fallback_hold(
                symbol=symbol,
                rationale=f"{lane.label} did not find enough evidence to act.",
            )

        stop_loss, take_profit = self._protective_levels(top_candidate.side, quote.ltp, features.atr)
        confidence = min(max(top_candidate.score, 0.2), 0.95)
        risk_level = "HIGH" if lane.requested_instrument in {"option", "future"} else "MEDIUM"

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
            max_holding_minutes=lane.holding_minutes,
            confidence=confidence,
            rationale_points=[
                f"{lane.label} sees the strongest edge in {top_candidate.action.replace('_', ' ').lower()}.",
                f"Momentum {features.momentum_score:.2f}, trend {features.trend_score:.2f}, RSI {features.rsi:.2f}.",
            ],
            invalidation_condition=(
                f"Exit if price falls below {stop_loss:.2f}."
                if top_candidate.side == "BUY"
                else f"Exit if price rises above {stop_loss:.2f}."
            ),
            risk_level=risk_level,
        )

    def _build_lanes(self, strategy: StrategyConfig) -> list[AgentLane]:
        return [
            AgentLane(
                key="stock_intraday",
                label="Stock intraday specialist",
                requested_instrument="stock",
                interval="15m",
                lookback=96,
                holding_minutes=240,
            ),
            AgentLane(
                key="stock_swing",
                label="Stock swing specialist",
                requested_instrument="stock",
                interval="1d",
                lookback=120,
                holding_minutes=4320,
            ),
            AgentLane(
                key="option_intraday",
                label="Options specialist",
                requested_instrument="option",
                interval="5m",
                lookback=120,
                holding_minutes=180,
                enabled=bool(strategy.options_enabled),
                execution_supported=bool(strategy.options_enabled),
                reason="Options are disabled in Strategy settings." if not strategy.options_enabled else None,
            ),
            AgentLane(
                key="future_intraday",
                label="Futures specialist",
                requested_instrument="future",
                interval="5m",
                lookback=120,
                holding_minutes=240,
                enabled=bool(strategy.futures_enabled),
                execution_supported=bool(strategy.futures_enabled),
                reason="Futures are disabled in Strategy settings." if not strategy.futures_enabled else None,
            ),
            AgentLane(
                key="forex_scout",
                label="Forex scout",
                requested_instrument="forex",
                interval="1h",
                lookback=120,
                holding_minutes=480,
                enabled=True,
                execution_supported=False,
                reason="The current broker stack does not support live forex execution yet, so this lane is scout-only.",
            ),
        ]

    def _specialist_strategy(self, strategy: StrategyConfig, requested_instrument: str):
        return SimpleNamespace(
            options_enabled=strategy.options_enabled or requested_instrument == "option",
            futures_enabled=strategy.futures_enabled or requested_instrument == "future",
            shorting_enabled=strategy.shorting_enabled,
        )

    def _lane_candidates(self, candidates: list, requested_instrument: str) -> list:
        allowed_types = {
            "stock": {"STOCK"},
            "option": {"CALL", "PUT"},
            "future": {"FUTURE"},
            "forex": set(),
        }[requested_instrument]
        return [
            candidate
            for candidate in candidates
            if candidate.action == "HOLD" or candidate.instrument_type in allowed_types
        ]

    def _ranking_score(self, decision: LLMDecisionResponse, lane: AgentLane) -> float:
        score = decision.confidence
        if decision.action == "HOLD":
            score -= 0.35
        if decision.action in {"EXIT", "REDUCE"}:
            score += 0.05
        if lane.requested_instrument == "future":
            score += 0.03
        if lane.key == "stock_swing":
            score -= 0.02
        return round(score, 3)

    def _protective_levels(self, side: str, ltp: float, atr: float) -> tuple[float, float]:
        buffer = max(atr, ltp * 0.01)
        target_buffer = max(buffer * 1.8, ltp * 0.015)
        if side.upper() == "SELL":
            return round(ltp + buffer, 2), round(max(ltp - target_buffer, 0.01), 2)
        return round(max(ltp - buffer, 0.01), 2), round(ltp + target_buffer, 2)

    def _execution_event_type(self, execution_result: dict[str, Any]) -> str:
        status = str(execution_result.get("status", "unknown")).lower()
        if status in {"filled", "success"}:
            return "trade_executed"
        if status == "paper":
            return "trade_simulated"
        if status == "advisory":
            return "trade_recommended"
        if status == "rejected":
            return "trade_blocked"
        return "trade_recorded"

    def _execution_message(self, decision: LLMDecisionResponse, execution_result: dict[str, Any]) -> str:
        status = str(execution_result.get("status", "recorded")).replace("_", " ")
        return f"{decision.action} on {decision.symbol} finished with {status}."

    def _loop_sleep_seconds(self, polling_interval_minutes: int) -> int:
        requested = max(polling_interval_minutes * 60, AGENT_LOOP_MIN_SECONDS)
        return max(AGENT_LOOP_MIN_SECONDS, min(requested, AGENT_LOOP_MAX_SECONDS))

    def _daily_loss_pct(self, db, current_equity: float) -> float:
        latest_session = db.scalar(select(AgentSession).order_by(AgentSession.started_at.desc()).limit(1))
        if latest_session and latest_session.start_equity > 0 and current_equity < latest_session.start_equity:
            return ((latest_session.start_equity - current_equity) / latest_session.start_equity) * 100
        return 0.0

    def _drawdown_pct(self, db) -> float:
        sessions = db.scalars(select(AgentSession).order_by(AgentSession.started_at.asc())).all()
        if not sessions:
            return 0.0
        peak = max([session.current_equity or session.start_equity for session in sessions] or [0.0])
        current = sessions[-1].current_equity or sessions[-1].start_equity
        if peak <= 0:
            return 0.0
        return max(((peak - current) / peak) * 100, 0.0)

    def _compute_progress_pct(self, start_equity: float, current_equity: float, target_equity: float) -> float:
        if start_equity <= 0 or target_equity <= start_equity:
            return 0.0
        progress = ((current_equity - start_equity) / (target_equity - start_equity)) * 100
        return round(max(progress, 0.0), 2)

    def _today_pnl_metrics(self, db, account_equity: float, realized_pnl: float, unrealized_pnl: float) -> tuple[float, float]:
        latest_daily_performance = db.scalar(
            select(DailyPerformance).order_by(DailyPerformance.trading_date.desc()).limit(1)
        )
        today_pnl = _rounded(realized_pnl + unrealized_pnl)
        today_pnl_pct = 0.0

        if latest_daily_performance and latest_daily_performance.opening_equity > 0:
            opening_equity = latest_daily_performance.opening_equity
            today_pnl = _rounded(account_equity - opening_equity)
            today_pnl_pct = round((today_pnl / opening_equity) * 100, 2)
            return today_pnl, today_pnl_pct

        implied_opening = account_equity - today_pnl
        if implied_opening > 0:
            today_pnl_pct = round((today_pnl / implied_opening) * 100, 2)
        return today_pnl, today_pnl_pct

    def _refresh_session_financials(
        self,
        db,
        session: AgentSession,
        *,
        account,
        broker_name: str | None = None,
        using_fallback: bool | None = None,
    ) -> None:
        current_equity = _rounded(account.total_equity)
        session_pnl = _rounded(current_equity - session.start_equity)
        session_pnl_pct = round((session_pnl / session.start_equity) * 100, 2) if session.start_equity > 0 else 0.0
        realized_pnl = _rounded(account.realized_pnl)
        unrealized_pnl = _rounded(account.unrealized_pnl)
        today_pnl, today_pnl_pct = self._today_pnl_metrics(db, current_equity, realized_pnl, unrealized_pnl)
        progress_pct = self._compute_progress_pct(session.start_equity, current_equity, session.target_equity)
        target_gap = _rounded(max(session.target_equity - current_equity, 0.0))
        now = datetime.now(timezone.utc)

        session.current_equity = current_equity
        session.heartbeat_at = now
        session.raw_state_json = {
            **(session.raw_state_json or {}),
            "broker": broker_name or (session.raw_state_json or {}).get("broker"),
            "using_fallback": (
                using_fallback
                if using_fallback is not None
                else bool((session.raw_state_json or {}).get("using_fallback"))
            ),
            "cash_balance": _rounded(account.cash_balance),
            "margin_available": _rounded(account.margin_available),
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "today_pnl": today_pnl,
            "today_pnl_pct": today_pnl_pct,
            "session_pnl": session_pnl,
            "session_pnl_pct": session_pnl_pct,
            "target_gap": target_gap,
            "progress_pct": progress_pct,
            "last_equity": current_equity,
            "last_synced_at": now.isoformat(),
            "account_source": account.source,
        }

    def _session_snapshot(self, session: AgentSession) -> dict[str, float | str | bool | None]:
        state = dict(session.raw_state_json or {})
        return {
            "current_equity": _rounded(session.current_equity),
            "target_equity": _rounded(session.target_equity),
            "progress_pct": self._compute_progress_pct(session.start_equity, session.current_equity, session.target_equity),
            "cash_balance": _rounded(state.get("cash_balance")),
            "margin_available": _rounded(state.get("margin_available")),
            "realized_pnl": _rounded(state.get("realized_pnl")),
            "unrealized_pnl": _rounded(state.get("unrealized_pnl")),
            "today_pnl": _rounded(state.get("today_pnl")),
            "today_pnl_pct": _rounded(state.get("today_pnl_pct")),
            "session_pnl": _rounded(state.get("session_pnl")),
            "session_pnl_pct": _rounded(state.get("session_pnl_pct")),
            "target_gap": _rounded(state.get("target_gap")),
            "last_synced_at": state.get("last_synced_at"),
            "using_fallback": bool(state.get("using_fallback", False)),
        }

    def _publish_status(self) -> None:
        payload = self.status().model_dump(mode="json")
        agent_event_bus.publish({"stream": "status", "payload": payload})

    def _fail_session(self, db, session: AgentSession, reason: str) -> None:
        self._restore_scheduler_state(db, session)
        session.status = "failed"
        session.stopped_at = datetime.now(timezone.utc)
        session.last_message = reason
        add_risk_event(
            db,
            event_type="agent_failure",
            severity="error",
            message="Autonomous trading agent failed.",
            metadata={"session_id": session.id, "reason": reason},
        )
        self._persist_event(
            db=db,
            session=session,
            phase="reflect",
            event_type="session_failed",
            severity="error",
            message=reason,
            metadata={"reason": reason},
        )
        db.commit()
        self._publish_status()

    def _serialize_session(self, session: AgentSession) -> AgentSessionResponse:
        state = dict(session.raw_state_json or {})
        progress_pct = self._compute_progress_pct(session.start_equity, session.current_equity, session.target_equity)
        return AgentSessionResponse(
            id=session.id,
            symbol=session.symbol,
            status=session.status,
            mode=session.mode,
            selected_broker=session.selected_broker,
            target_multiplier=session.target_multiplier,
            start_equity=session.start_equity,
            current_equity=session.current_equity,
            target_equity=session.target_equity,
            auto_execute=session.auto_execute,
            launched_from=session.launched_from,
            allowed_lanes_json=list(session.allowed_lanes_json or []),
            heartbeat_at=session.heartbeat_at,
            started_at=session.started_at,
            stopped_at=session.stopped_at,
            last_message=session.last_message,
            progress_pct=progress_pct,
            cash_balance=_rounded(state.get("cash_balance")),
            margin_available=_rounded(state.get("margin_available")),
            realized_pnl=_rounded(state.get("realized_pnl")),
            unrealized_pnl=_rounded(state.get("unrealized_pnl")),
            today_pnl=_rounded(state.get("today_pnl")),
            today_pnl_pct=_rounded(state.get("today_pnl_pct")),
            session_pnl=_rounded(state.get("session_pnl")),
            session_pnl_pct=_rounded(state.get("session_pnl_pct")),
            target_gap=_rounded(state.get("target_gap")),
            raw_state_json=state,
        )

    def _serialize_event(self, event: AgentEvent) -> AgentEventResponse:
        return AgentEventResponse(
            id=event.id,
            agent_session_id=event.agent_session_id,
            timestamp=event.timestamp,
            phase=event.phase,
            event_type=event.event_type,
            severity=event.severity,
            message=event.message,
            metadata_json=dict(event.metadata_json or {}),
        )

    def _persist_event(
        self,
        *,
        db,
        session: AgentSession,
        phase: str,
        event_type: str,
        severity: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentEvent:
        event = AgentEvent(
            agent_session_id=session.id,
            timestamp=datetime.now(timezone.utc),
            phase=phase,
            event_type=event_type,
            severity=severity,
            message=message[:255],
            metadata_json={
                **(metadata or {}),
                "snapshot": self._session_snapshot(session),
            },
        )
        db.add(event)
        db.flush()
        payload = self._serialize_event(event).model_dump(mode="json")
        agent_event_bus.publish({"stream": "agent_event", "payload": payload})
        add_audit_log(
            db,
            category="agent",
            message=message,
            metadata={
                "session_id": session.id,
                "phase": phase,
                "event_type": event_type,
                "severity": severity,
                "metadata": metadata or {},
            },
        )
        return event

    def _restore_scheduler_state(self, db, session: AgentSession) -> None:
        strategy = db.scalar(select(StrategyConfig).limit(1))
        if not strategy:
            return
        scheduler_was_paused = bool((session.raw_state_json or {}).get("scheduler_was_paused"))
        strategy.pause_scheduler = scheduler_was_paused


autonomous_agent = AutonomousTradingAgent()
