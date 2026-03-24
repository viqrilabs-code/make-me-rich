export type AuthResponse = {
  authenticated: boolean;
  user: { username: string; timezone: string } | null;
  has_user: boolean;
  signup_allowed: boolean;
};

export type StrategyConfig = {
  id: number;
  polling_interval_minutes: number;
  mode: "advisory" | "paper" | "live";
  risk_profile: string;
  allowed_instruments_json: {
    instrument_types: string[];
    symbols: string[];
  };
  watchlist_symbols_json: string[];
  max_risk_per_trade_pct: number;
  max_daily_loss_pct: number;
  max_drawdown_pct: number;
  max_open_positions: number;
  max_capital_per_trade_pct: number;
  leverage_enabled: boolean;
  futures_enabled: boolean;
  options_enabled: boolean;
  shorting_enabled: boolean;
  market_hours_only: boolean;
  kill_switch: boolean;
  cooldown_until: string | null;
  mandatory_stop_loss: boolean;
  cooldown_after_losses: number;
  cooldown_minutes: number;
  selected_broker: string;
  preferred_llm_provider: "openai" | "anthropic" | "gemini";
  live_mode_armed: boolean;
  pause_scheduler: boolean;
};

export type TradingGoal = {
  id: number;
  initial_capital: number;
  target_multiplier: number;
  target_amount: number;
  start_date: string;
  target_date: string;
  status: string;
  plan?: {
    target_amount: number;
    remaining_gap: number;
    days_remaining: number;
    daily_required_pace: number;
    urgency_score: number;
    mode_suggestion: string;
  };
};

export type OverviewResponse = {
  latest_snapshot: {
    id: number;
    timestamp: string;
    total_equity: number;
    cash_balance: number;
    margin_available: number;
    realized_pnl: number;
    unrealized_pnl: number;
    source: string;
  } | null;
  goal_progress_pct: number;
  target_capital: number;
  current_capital: number;
  invested_capital: number;
  todays_pnl: number;
  todays_pnl_pct: number;
  open_positions: Position[];
  latest_decision: {
    timestamp: string | null;
    symbol: string | null;
    action: string | null;
    confidence: number | null;
    approved: boolean | null;
  } | null;
  latest_risk_event: {
    timestamp: string;
    event_type: string;
    severity: string;
    message: string;
  } | null;
  strategy_mode: string;
  active_broker: string;
  using_fallback_broker: boolean;
  watchlist_symbols: string[];
  available_instruments: RequestedInstrument[];
  trade_fetch_ready: boolean;
  missing_trade_credentials: string[];
  market_session: MarketSession;
  hot_deals: HotDeal[];
};

export type MarketSession = {
  label: string;
  note: string;
  local_time: string;
  market_open: boolean;
};

export type HotDeal = {
  symbol: string;
  action: string;
  instrument_type: string;
  side: string;
  score: number;
  conviction: string;
  market_regime: string;
  ltp: number;
  momentum_score: number;
  trend_score: number;
  rsi: number;
  sentiment_score: number;
  opportunity_window: string;
  setup_note: string;
  stop_loss_hint: number | null;
  take_profit_hint: number | null;
};

export type Position = {
  id: number;
  symbol: string;
  instrument_type: string;
  side: string;
  quantity: number;
  avg_price: number;
  current_price: number;
  unrealized_pnl: number;
  realized_pnl: number;
  stop_loss: number | null;
  take_profit: number | null;
  opened_at: string;
  status: string;
  mode: string;
};

export type Decision = {
  id: number;
  timestamp: string;
  symbol: string;
  action: string;
  instrument_type: string;
  confidence: number;
  rationale_json: string[];
  llm_response_json: Record<string, unknown>;
  candidate_actions_json: Array<Record<string, unknown>>;
  approved: boolean;
  rejection_reasons_json: string[];
  scheduler_run_id: number | null;
};

export type Order = {
  id: number;
  broker_order_id: string | null;
  client_order_id: string;
  symbol: string;
  instrument_type: string;
  side: string;
  order_type: string;
  quantity: number;
  price: number | null;
  status: string;
  fill_price: number | null;
  fill_quantity: number | null;
  placed_at: string;
  updated_at: string;
  mode: string;
  raw_payload_json: Record<string, unknown>;
};

export type DailyPerformance = {
  id: number;
  trading_date: string;
  opening_equity: number;
  closing_equity: number;
  realized_pnl: number;
  unrealized_pnl: number;
  drawdown_pct: number;
  trades_count: number;
};

export type NewsItem = {
  title: string;
  description: string | null;
  source: string;
  published_at: string;
  url: string;
  symbols: string[];
  sentiment_score: number;
  relevance_score: number;
};

export type NewsSummary = {
  items: NewsItem[];
  overall_sentiment: number;
  top_symbols: Array<{ symbol: string; articles: number }>;
  feed_status: string;
  technical_only: boolean;
  technical_only_reason: string | null;
};

export type RequestedInstrument = "stock" | "option" | "future";

export type TradeSetup = {
  symbol: string;
  requested_instrument: RequestedInstrument;
  chart_interval: string;
  chart_lookback: number;
  analysis_generated_at: string;
  active_broker: string;
  using_fallback_broker: boolean;
  execution_ready: boolean;
  execution_blockers: string[];
  mode_note: string;
  analysis_note: string;
  market_session: MarketSession;
  quote: {
    symbol: string;
    ltp: number;
    bid: number | null;
    ask: number | null;
    spread_pct: number;
    timestamp: string;
    volume: number | null;
  };
  features: {
    symbol: string;
    momentum_score: number;
    volatility_score: number;
    trend_score: number;
    volume_spike_score: number;
    atr: number;
    moving_average_crossover: number;
    rsi: number;
    market_regime: string;
  };
  candidates: Array<{
    symbol: string;
    action: string;
    instrument_type: string;
    side: string;
    score: number;
    entry_type: string;
  }>;
  decision: {
    decision: string;
    symbol: string;
    instrument_type: string;
    action: string;
    side: string;
    quantity: number;
    entry_type: string;
    entry_price_hint: number | null;
    stop_loss: number | null;
    take_profit: number | null;
    max_holding_minutes: number;
    confidence: number;
    rationale_points: string[];
    invalidation_condition: string;
    risk_level: string;
  };
  news_summary: NewsSummary;
  chart_points: Array<{
    timestamp: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number | null;
    fast_ma: number | null;
    slow_ma: number | null;
  }>;
};

export type BestTradeResponse = {
  symbol: string;
  selected_instrument: RequestedInstrument;
  available_instruments: RequestedInstrument[];
  evaluated_instruments: Array<{
    instrument: RequestedInstrument;
    action: string;
    confidence: number;
    execution_ready: boolean;
    ranking_score: number;
    blocker: string | null;
  }>;
  setup: TradeSetup;
};

export type AuditEntry = {
  id: number;
  timestamp: string;
  category?: string;
  event_type?: string;
  severity?: string;
  message: string;
  metadata_json: Record<string, unknown>;
};

export type SchedulerStatus = {
  running: boolean;
  paused: boolean;
  poll_interval_minutes: number;
  last_run_at: string | null;
  next_due_at: string | null;
  active_jobs: Array<{ id: string; next_run_time: string | null }>;
  lock_state: string;
};

export type ConfigResponse = {
  user: { id: number; admin_username: string; timezone: string };
  goal: TradingGoal | null;
  strategy: StrategyConfig | null;
  broker_credentials: Array<{
    id: number;
    broker_name: string;
    label: string;
    configured: boolean;
    last_validated_at: string | null;
    secret_source: string;
    metadata_json: Record<string, unknown>;
  }>;
  api_credentials: Array<{
    integration: string;
    label: string;
    field_name: string;
    configured: boolean;
    source: string;
    masked_value: string | null;
    required_for_trade_fetch: boolean;
    description: string;
    docs_url: string;
    manage_url: string;
    steps: string[];
  }>;
  secret_status: Record<string, boolean>;
};

export type AgentEvent = {
  id: number;
  agent_session_id: number;
  timestamp: string;
  phase: string;
  event_type: string;
  severity: string;
  message: string;
  metadata_json: Record<string, unknown>;
};

export type AgentSession = {
  id: number;
  symbol: string;
  status: string;
  mode: string;
  selected_broker: string;
  target_multiplier: number;
  start_equity: number;
  current_equity: number;
  target_equity: number;
  auto_execute: boolean;
  launched_from: string;
  allowed_lanes_json: string[];
  heartbeat_at: string | null;
  started_at: string | null;
  stopped_at: string | null;
  last_message: string | null;
  progress_pct: number;
  cash_balance: number;
  margin_available: number;
  realized_pnl: number;
  unrealized_pnl: number;
  today_pnl: number;
  today_pnl_pct: number;
  session_pnl: number;
  session_pnl_pct: number;
  target_gap: number;
  raw_state_json: Record<string, unknown>;
};

export type AgentStatus = {
  active: boolean;
  can_start: boolean;
  suggested_symbol: string | null;
  message: string | null;
  session: AgentSession | null;
  recent_events: AgentEvent[];
};

export type AgentCommandResponse = {
  message: string;
  session: AgentSession | null;
};
