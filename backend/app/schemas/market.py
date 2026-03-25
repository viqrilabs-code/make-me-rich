from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.llm.schemas import LLMDecisionResponse
from app.schemas.news import NewsSummaryResponse
from app.schemas.portfolio import MarketSessionResponse


RequestedInstrument = Literal["stock", "option", "future"]


class TradeQuoteResponse(BaseModel):
    symbol: str
    ltp: float
    bid: float | None = None
    ask: float | None = None
    spread_pct: float
    timestamp: datetime
    volume: float | None = None


class TradeFeatureResponse(BaseModel):
    symbol: str
    momentum_score: float
    volatility_score: float
    trend_score: float
    volume_spike_score: float
    atr: float
    moving_average_crossover: float
    rsi: float
    market_regime: str


class TradeCandidateResponse(BaseModel):
    symbol: str
    action: str
    instrument_type: str
    side: str
    score: float
    entry_type: str


class TradeChartPointResponse(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    fast_ma: float | None = None
    slow_ma: float | None = None


class OptionContractPlanResponse(BaseModel):
    contract_name: str
    contract_symbol: str
    option_side: str
    expiry_label: str | None = None
    strike_price: float | None = None
    lot_size: int = 1
    premium_entry: float | None = None
    premium_stop_loss: float | None = None
    premium_take_profit: float | None = None
    probable_profit: float | None = None
    probable_loss: float | None = None
    underlying_entry: float | None = None
    underlying_stop_loss: float | None = None
    underlying_take_profit: float | None = None
    pricing_source: str = "synthetic"


class TradeSetupResponse(BaseModel):
    symbol: str
    trade_name: str
    requested_instrument: RequestedInstrument
    chart_interval: str
    chart_lookback: int
    analysis_generated_at: datetime
    analysis_engine: str
    selected_broker: str
    active_broker: str
    using_fallback_broker: bool
    execution_ready: bool
    execution_blockers: list[str]
    mode_note: str
    analysis_note: str
    market_session: MarketSessionResponse
    quote: TradeQuoteResponse
    features: TradeFeatureResponse
    candidates: list[TradeCandidateResponse]
    decision: LLMDecisionResponse
    news_summary: NewsSummaryResponse
    chart_points: list[TradeChartPointResponse]
    option_contract: OptionContractPlanResponse | None = None


class BestTradeInstrumentScoreResponse(BaseModel):
    instrument: RequestedInstrument
    action: str
    confidence: float
    execution_ready: bool
    ranking_score: float
    blocker: str | None = None


class BestTradeResponse(BaseModel):
    symbol: str
    selected_instrument: RequestedInstrument
    available_instruments: list[RequestedInstrument]
    evaluated_instruments: list[BestTradeInstrumentScoreResponse]
    setup: TradeSetupResponse


class DailyTopDealItemResponse(BaseModel):
    rank: int
    instrument: RequestedInstrument
    ranking_score: float
    actionable: bool
    setup: TradeSetupResponse


class DailyTopDealsResponse(BaseModel):
    scan_date: str
    timezone: str
    triggered_at: datetime | None = None
    next_trigger_at: datetime
    can_trigger: bool
    universe_label: str = "NSE cash equity universe"
    universe_size: int = 0
    deep_scan_size: int = 0
    scan_scope: list[RequestedInstrument]
    symbols_scanned: list[str]
    candidate_count: int
    actionable_count: int
    message: str
    scan_notes: list[str]
    items: list[DailyTopDealItemResponse]
