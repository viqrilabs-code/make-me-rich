from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from app.brokers.mock import MockBrokerAdapter
from app.llm.schemas import LLMDecisionResponse
from app.schemas.news import NewsSummaryResponse
from app.services import trade_setup_service


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
