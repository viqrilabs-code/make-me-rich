from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from app.brokers.mock import MockBrokerAdapter
from app.llm.schemas import LLMDecisionResponse
from app.schemas.news import NewsSummaryResponse
from app.services import trade_setup_service
from app.services.strategy_engine import FeatureSet, generate_candidate_actions


def test_trade_setup_builds_option_analysis_with_chart_and_blocker(db_session, monkeypatch) -> None:
    testing_factory = sessionmaker(
        bind=db_session.get_bind(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    monkeypatch.setattr(
        trade_setup_service,
        "get_active_broker",
        lambda db: (MockBrokerAdapter(testing_factory), "mock", False),
    )
    monkeypatch.setattr(
        trade_setup_service.NewsService,
        "summarize",
        lambda self, symbols: NewsSummaryResponse(
            items=[],
            overall_sentiment=0.0,
            top_symbols=[],
            feed_status="error",
            technical_only=True,
            technical_only_reason="Live news fetch failed, so the board switched to technical-only analysis.",
        ),
    )
    monkeypatch.setattr(
        trade_setup_service.LLMDecisionEngine,
        "request_decision",
        lambda self, context, db: LLMDecisionResponse(
            decision="BUY_CALL",
            symbol="INFY",
            instrument_type="CALL",
            action="BUY_CALL",
            side="BUY",
            quantity=1,
            entry_type="MARKET",
            entry_price_hint=1500.0,
            stop_loss=1480.0,
            take_profit=1530.0,
            max_holding_minutes=240,
            confidence=0.82,
            rationale_points=["Momentum and sentiment align for an options upside expression."],
            invalidation_condition="Momentum weakens materially.",
            risk_level="MEDIUM",
        ),
    )

    response = trade_setup_service.build_trade_setup(db_session, symbol="INFY", requested_instrument="option")

    assert response.symbol == "INFY"
    assert response.requested_instrument == "option"
    assert response.decision.action == "BUY_CALL"
    assert any(candidate.instrument_type == "CALL" for candidate in response.candidates)
    assert len(response.chart_points) >= 20
    assert any("Options execution is disabled" in blocker for blocker in response.execution_blockers)
    assert "technical-only mode" in response.analysis_note


def test_trade_setup_rejects_symbol_outside_strategy_watchlist(db_session) -> None:
    with pytest.raises(ValueError, match="Strategy watchlist"):
        trade_setup_service.build_trade_setup(db_session, symbol="SBIN", requested_instrument="stock")


def test_trade_setup_makes_hold_decision_concise_and_decisive(db_session, monkeypatch) -> None:
    testing_factory = sessionmaker(
        bind=db_session.get_bind(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    monkeypatch.setattr(
        trade_setup_service,
        "get_active_broker",
        lambda db: (MockBrokerAdapter(testing_factory), "mock", False),
    )
    monkeypatch.setattr(
        trade_setup_service.NewsService,
        "summarize",
        lambda self, symbols: NewsSummaryResponse(
            items=[],
            overall_sentiment=0.0,
            top_symbols=[],
            feed_status="empty",
            technical_only=True,
            technical_only_reason="No fresh headlines were returned.",
        ),
    )
    monkeypatch.setattr(
        trade_setup_service.LLMDecisionEngine,
        "request_decision",
        lambda self, context, db: LLMDecisionResponse(
            decision="HOLD",
            symbol="INFY",
            instrument_type="STOCK",
            action="HOLD",
            side="BUY",
            quantity=0,
            entry_type="MARKET",
            entry_price_hint=None,
            stop_loss=None,
            take_profit=None,
            max_holding_minutes=0,
            confidence=0.61,
            rationale_points=["The setup is not strong enough yet and price might need more confirmation."],
            invalidation_condition="A stronger risk-adjusted setup appears.",
            risk_level="MEDIUM",
        ),
    )

    response = trade_setup_service.build_trade_setup(
        db_session,
        symbol="INFY",
        requested_instrument="stock",
        use_llm=True,
    )

    assert response.decision.action == "HOLD"
    assert response.decision.confidence == 0.35
    assert response.decision.rationale_points[0] == "WAIT. Do not enter this stock trade now."
    assert response.decision.rationale_points[1].startswith("Reason:")
    assert response.decision.invalidation_condition == "Re-check only after a clean breakout, breakdown, or clear volume expansion."


def test_option_setup_includes_option_contract_plan(db_session, monkeypatch) -> None:
    testing_factory = sessionmaker(
        bind=db_session.get_bind(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    monkeypatch.setattr(
        trade_setup_service,
        "get_active_broker",
        lambda db: (MockBrokerAdapter(testing_factory), "mock", False),
    )
    monkeypatch.setattr(
        trade_setup_service.NewsService,
        "summarize",
        lambda self, symbols: NewsSummaryResponse(
            items=[],
            overall_sentiment=0.15,
            top_symbols=[],
            feed_status="empty",
            technical_only=True,
            technical_only_reason="No fresh headlines were returned.",
        ),
    )
    monkeypatch.setattr(
        trade_setup_service.LLMDecisionEngine,
        "request_decision",
        lambda self, context, db: LLMDecisionResponse(
            decision="BUY_CALL",
            symbol="INFY",
            instrument_type="CALL",
            action="BUY_CALL",
            side="BUY",
            quantity=1,
            entry_type="MARKET",
            entry_price_hint=1500.0,
            stop_loss=1480.0,
            take_profit=1530.0,
            max_holding_minutes=240,
            confidence=0.78,
            rationale_points=["Trend and momentum support a call option expression."],
            invalidation_condition="Momentum weakens materially.",
            risk_level="MEDIUM",
        ),
    )

    response = trade_setup_service.build_trade_setup(db_session, symbol="INFY", requested_instrument="option")

    assert response.option_contract is not None
    assert response.option_contract.option_side == "CALL"
    assert response.option_contract.premium_entry is not None
    assert response.option_contract.probable_profit is not None
    assert response.option_contract.probable_loss is not None
    assert response.trade_name == response.option_contract.contract_name


def test_next_weekly_expiry_uses_tuesday_and_rolls_back_for_nse_holiday() -> None:
    expiry = trade_setup_service._next_weekly_expiry(datetime(2026, 3, 25, 9, 0, tzinfo=timezone.utc))

    assert expiry.date().isoformat() == "2026-03-30"


def test_trade_setup_blocks_silent_mock_fallback_for_manual_live_search(db_session, monkeypatch, strategy) -> None:
    testing_factory = sessionmaker(
        bind=db_session.get_bind(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    strategy.selected_broker = "indmoney"

    monkeypatch.setattr(
        trade_setup_service,
        "get_active_broker",
        lambda db: (MockBrokerAdapter(testing_factory), "mock", True),
    )

    with pytest.raises(RuntimeError, match="falling back to mock prices would be misleading"):
        trade_setup_service.build_trade_setup(
            db_session,
            symbol="INFY",
            requested_instrument="stock",
            use_llm=False,
            allow_fallback_broker=False,
        )


def test_generate_candidate_actions_can_surface_non_hold_signal_for_moderate_bullish_setup(strategy) -> None:
    strategy.options_enabled = True
    features = FeatureSet(
        symbol="INFY",
        momentum_score=1.3,
        volatility_score=0.8,
        trend_score=0.9,
        volume_spike_score=1.18,
        atr=18.0,
        moving_average_crossover=0.7,
        rsi=59.0,
        market_regime="bullish",
    )

    actions = generate_candidate_actions(strategy, features, news_sentiment=0.08)

    assert any(action.action == "BUY_STOCK" for action in actions)
