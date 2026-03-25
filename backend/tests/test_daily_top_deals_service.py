from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.llm.schemas import LLMDecisionResponse
from app.schemas.market import (
    TradeCandidateResponse,
    TradeChartPointResponse,
    TradeFeatureResponse,
    TradeQuoteResponse,
    TradeSetupResponse,
)
from app.schemas.news import NewsSummaryResponse
from app.schemas.portfolio import MarketSessionResponse
from app.services.daily_top_deals_service import get_daily_top_deals_snapshot, refresh_daily_top_deals_snapshot


def _setup(symbol: str, instrument: str, action: str, confidence: float, execution_ready: bool) -> TradeSetupResponse:
    instrument_type = {
        "stock": "STOCK",
        "option": "CALL",
    }[instrument]
    return TradeSetupResponse(
        symbol=symbol,
        trade_name=f"{symbol} {instrument} setup",
        requested_instrument=instrument,  # type: ignore[arg-type]
        chart_interval="15m",
        chart_lookback=96,
        analysis_generated_at=datetime.now(timezone.utc),
        analysis_engine="llm",
        selected_broker="groww",
        active_broker="groww",
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
            quantity=1 if action != "HOLD" else 0,
            entry_type="MARKET",
            entry_price_hint=100.0 if action != "HOLD" else None,
            stop_loss=96.0 if action != "HOLD" else None,
            take_profit=108.0 if action != "HOLD" else None,
            max_holding_minutes=120,
            confidence=confidence,
            rationale_points=["Strong setup"] if action != "HOLD" else ["WAIT. Do not enter this stock trade now."],
            invalidation_condition="Trend breaks",
            risk_level="MEDIUM",
        ),
        news_summary=NewsSummaryResponse(
            items=[],
            overall_sentiment=0.2,
            top_symbols=[],
            feed_status="ok",
            technical_only=False,
            technical_only_reason=None,
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


def test_daily_top_deals_scan_runs_once_per_day_and_persists_snapshot(db_session, monkeypatch, strategy) -> None:
    strategy.watchlist_symbols_json = ["INFY", "TCS", "RELIANCE"]
    strategy.allowed_instruments_json = {"instrument_types": ["STOCK", "OPTION"], "symbols": ["INFY", "TCS", "RELIANCE"]}
    db_session.commit()

    setups = {
        ("INFY", "stock"): _setup("INFY", "stock", "BUY_STOCK", 0.91, True),
        ("INFY", "option"): _setup("INFY", "option", "BUY_CALL", 0.88, False),
        ("TCS", "stock"): _setup("TCS", "stock", "HOLD", 0.22, False),
        ("TCS", "option"): _setup("TCS", "option", "BUY_CALL", 0.79, False),
        ("RELIANCE", "stock"): _setup("RELIANCE", "stock", "BUY_STOCK", 0.83, True),
        ("RELIANCE", "option"): _setup("RELIANCE", "option", "HOLD", 0.2, False),
    }

    def fake_scan_symbol_instruments(*, symbol: str, **kwargs):
        results = []
        for requested_instrument in ("stock", "option"):
            setup = setups[(symbol, requested_instrument)]
            results.append((setup.decision.confidence, requested_instrument, setup))
        return results

    monkeypatch.setattr(
        "app.services.daily_top_deals_service._scan_symbol_instruments",
        fake_scan_symbol_instruments,
    )

    first = get_daily_top_deals_snapshot(db_session)
    assert first.can_trigger is True
    assert first.items == []

    refreshed = refresh_daily_top_deals_snapshot(db_session)
    db_session.commit()

    assert refreshed.can_trigger is False
    assert len(refreshed.items) == 2
    assert refreshed.items[0].setup.symbol == "INFY"
    assert refreshed.items[0].setup.decision.action == "BUY_STOCK"
    assert all(item.instrument == "stock" for item in refreshed.items)
    assert all(item.setup.decision.action == "BUY_STOCK" for item in refreshed.items)

    snapshot = get_daily_top_deals_snapshot(db_session)
    assert snapshot.can_trigger is False
    assert len(snapshot.items) == 2

    with pytest.raises(ValueError, match="already ran"):
        refresh_daily_top_deals_snapshot(db_session)


def test_daily_top_deals_uses_nse_universe_not_strategy_watchlist(db_session, monkeypatch, strategy) -> None:
    strategy.watchlist_symbols_json = ["ONLYWATCHLIST"]
    strategy.allowed_instruments_json = {"instrument_types": ["STOCK", "OPTION"], "symbols": ["ONLYWATCHLIST"]}
    strategy.selected_broker = "groww"
    db_session.commit()

    seen_symbols: list[str] = []

    class FakeAdapter:
        pass

    def fake_get_active_broker(db):
        return FakeAdapter(), "groww", False

    def fake_scan_universe_symbols(current_strategy, adapter):
        assert current_strategy.watchlist_symbols_json == ["ONLYWATCHLIST"]
        return ["AAA", "BBB", "CCC"], ["AAA", "BBB", "CCC"]

    def fake_quotes_map(self, symbols):
        now = datetime.now(timezone.utc)
        return {
            symbol: TradeQuoteResponse(
                symbol=symbol,
                ltp=100.0 + index,
                bid=99.8 + index,
                ask=100.2 + index,
                spread_pct=0.25,
                timestamp=now,
                volume=10_000 - index * 100,
            )
            for index, symbol in enumerate(symbols)
        }

    def fake_candles_map(self, symbols, *, interval, lookback):
        return {symbol: [{"close": 100 + idx}] * 30 for idx, symbol in enumerate(symbols)}

    def fake_news_summary(symbols):
        return NewsSummaryResponse(
            items=[],
            overall_sentiment=0.1,
            top_symbols=[{"symbol": symbol, "articles": 0} for symbol in symbols[:3]],
            feed_status="ok",
            technical_only=False,
            technical_only_reason=None,
        )

    def fake_scan_symbol_instruments(*, symbol: str, **kwargs):
        seen_symbols.append(symbol)
        return [
            (_setup(symbol, "stock", "BUY_STOCK", 0.9, True).decision.confidence, "stock", _setup(symbol, "stock", "BUY_STOCK", 0.9, True)),
            (_setup(symbol, "option", "BUY_CALL", 0.8, False).decision.confidence, "option", _setup(symbol, "option", "BUY_CALL", 0.8, False)),
        ]

    monkeypatch.setattr("app.services.daily_top_deals_service.get_active_broker", fake_get_active_broker)
    monkeypatch.setattr("app.services.daily_top_deals_service._scan_universe_symbols", fake_scan_universe_symbols)
    monkeypatch.setattr("app.services.daily_top_deals_service._deep_scan_symbols", lambda universe_symbols, quotes_map, *, limit: universe_symbols[:limit])
    monkeypatch.setattr("app.services.market_service.MarketService.get_quotes_map", fake_quotes_map)
    monkeypatch.setattr("app.services.market_service.MarketService.get_candles_map", fake_candles_map)
    monkeypatch.setattr("app.services.daily_top_deals_service.NewsService.summarize", lambda self, symbols: fake_news_summary(symbols))
    monkeypatch.setattr("app.services.daily_top_deals_service._scan_symbol_instruments", fake_scan_symbol_instruments)

    refreshed = refresh_daily_top_deals_snapshot(db_session)
    db_session.commit()

    assert seen_symbols == ["AAA", "BBB", "CCC"]
    assert refreshed.universe_label == "NSE cash equity universe"
    assert refreshed.universe_size == 3
    assert refreshed.deep_scan_size == 3
    assert refreshed.symbols_scanned == ["AAA", "BBB", "CCC"]
    assert all(item.setup.symbol in {"AAA", "BBB", "CCC"} for item in refreshed.items)
    assert all(item.instrument == "stock" for item in refreshed.items)
    assert all(item.setup.decision.action == "BUY_STOCK" for item in refreshed.items)
