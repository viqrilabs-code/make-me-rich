from __future__ import annotations

from datetime import datetime, timezone

from app.llm.schemas import LLMDecisionResponse
from app.models import StrategyConfig
from app.schemas.market import (
    TradeCandidateResponse,
    TradeChartPointResponse,
    TradeFeatureResponse,
    TradeQuoteResponse,
    TradeSetupResponse,
)
from app.schemas.news import NewsSummaryResponse
from app.schemas.portfolio import MarketSessionResponse
from app.services.trade_setup_service import build_best_trade_setup


def _setup(symbol: str, instrument: str, action: str, confidence: float, execution_ready: bool) -> TradeSetupResponse:
    instrument_type = {
        "stock": "STOCK",
        "option": "OPTION",
        "future": "FUTURE",
    }[instrument]
    return TradeSetupResponse(
        symbol=symbol,
        trade_name=f"{symbol} {instrument} setup",
        requested_instrument=instrument,  # type: ignore[arg-type]
        chart_interval="15m",
        chart_lookback=96,
        analysis_generated_at=datetime.now(timezone.utc),
        analysis_engine="llm",
        selected_broker="indmoney",
        active_broker="indmoney",
        using_fallback_broker=False,
        execution_ready=execution_ready,
        execution_blockers=[] if execution_ready else ["Blocked"],
        mode_note="Advisory",
        analysis_note="Live trade setup",
        market_session=MarketSessionResponse(
            label="Open",
            note="Market open",
            local_time=datetime.now(timezone.utc),
            market_open=True,
        ),
        quote=TradeQuoteResponse(
            symbol=symbol,
            ltp=100.0,
            bid=99.8,
            ask=100.2,
            spread_pct=0.4,
            timestamp=datetime.now(timezone.utc),
            volume=1000,
        ),
        features=TradeFeatureResponse(
            symbol=symbol,
            momentum_score=0.7,
            volatility_score=0.3,
            trend_score=0.8,
            volume_spike_score=0.5,
            atr=2.1,
            moving_average_crossover=0.4,
            rsi=58.0,
            market_regime="bullish",
        ),
        candidates=[
            TradeCandidateResponse(
                symbol=symbol,
                action=action,
                instrument_type=instrument_type,
                side="BUY",
                score=confidence,
                entry_type="MARKET",
            )
        ],
        decision=LLMDecisionResponse(
            decision=action,
            symbol=symbol,
            instrument_type=instrument_type,
            action=action,
            side="BUY",
            quantity=1,
            entry_type="MARKET",
            entry_price_hint=100.0,
            stop_loss=96.0,
            take_profit=108.0,
            max_holding_minutes=120,
            confidence=confidence,
            rationale_points=["Strong setup"],
            invalidation_condition="Trend breaks",
            risk_level="MEDIUM",
        ),
        news_summary=NewsSummaryResponse(
            items=[],
            overall_sentiment=0.2,
            top_symbols=[],
        ),
        chart_points=[
            TradeChartPointResponse(
                timestamp=datetime.now(timezone.utc),
                open=99.0,
                high=101.0,
                low=98.5,
                close=100.0,
                volume=1000,
                fast_ma=99.5,
                slow_ma=98.8,
            )
        ],
        option_contract=None,
    )


def test_build_best_trade_setup_prefers_best_enabled_lane(db_session, monkeypatch) -> None:
    strategy = db_session.query(StrategyConfig).first()
    assert strategy is not None
    strategy.options_enabled = True
    strategy.futures_enabled = True
    db_session.commit()

    setups = {
        "stock": _setup("INFY", "stock", "HOLD", 0.2, False),
        "option": _setup("INFY", "option", "BUY_CALL", 0.82, True),
        "future": _setup("INFY", "future", "BUY_FUTURE", 0.64, True),
    }

    def fake_build_trade_setup(
        db,
        symbol: str,
        requested_instrument: str,
        *,
        use_llm: bool = True,
        allow_fallback_broker: bool = True,
    ):
        if use_llm:
            return _setup("INFY", requested_instrument, "BUY_CALL", 0.82, True)
        return setups[requested_instrument]

    monkeypatch.setattr(
        "app.services.trade_setup_service.build_trade_setup",
        fake_build_trade_setup,
    )

    best = build_best_trade_setup(db_session, "INFY")

    assert best.selected_instrument == "option"
    assert best.setup.decision.action == "BUY_CALL"
    assert [row.instrument for row in best.evaluated_instruments] == ["option", "future", "stock"]
