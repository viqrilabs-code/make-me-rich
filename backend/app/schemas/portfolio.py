from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel
from app.schemas.decision import LatestDecisionSummary


class PositionResponse(ORMModel):
    id: int
    symbol: str
    instrument_type: str
    side: str
    quantity: float
    avg_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    stop_loss: float | None = None
    take_profit: float | None = None
    opened_at: datetime
    closed_at: datetime | None = None
    status: str
    broker_position_id: str | None = None
    mode: str
    raw_payload_json: dict


class PortfolioSnapshotResponse(ORMModel):
    id: int
    timestamp: datetime
    cash_balance: float
    total_equity: float
    margin_available: float
    realized_pnl: float
    unrealized_pnl: float
    source: str
    raw_payload_json: dict


class DailyPerformanceResponse(ORMModel):
    id: int
    trading_date: date
    opening_equity: float
    closing_equity: float
    realized_pnl: float
    unrealized_pnl: float
    drawdown_pct: float
    trades_count: int


class MarketSessionResponse(BaseModel):
    label: str
    note: str
    local_time: datetime
    market_open: bool


class HotDealResponse(BaseModel):
    symbol: str
    action: str
    instrument_type: str
    side: str
    score: float
    conviction: str
    market_regime: str
    ltp: float
    momentum_score: float
    trend_score: float
    rsi: float
    sentiment_score: float
    opportunity_window: str
    setup_note: str
    stop_loss_hint: float | None = None
    take_profit_hint: float | None = None


class OverviewResponse(BaseModel):
    latest_snapshot: PortfolioSnapshotResponse | None
    goal_progress_pct: float
    target_capital: float
    current_capital: float
    invested_capital: float
    todays_pnl: float
    todays_pnl_pct: float
    open_positions: list[PositionResponse]
    latest_decision: LatestDecisionSummary | None
    latest_risk_event: dict | None
    strategy_mode: str
    active_broker: str
    using_fallback_broker: bool
    watchlist_symbols: list[str]
    available_instruments: list[str]
    trade_fetch_ready: bool
    missing_trade_credentials: list[str]
    market_session: MarketSessionResponse
    hot_deals: list[HotDealResponse]
