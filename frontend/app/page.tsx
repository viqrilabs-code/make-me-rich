"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { Clock3, RefreshCw, ShieldAlert, Sparkles, WandSparkles, Wallet } from "lucide-react";

import { AgentStreamPanel } from "@/components/agent-stream-panel";
import { ChartCard } from "@/components/chart-card";
import { ChartContainer } from "@/components/chart-container";
import { ErrorState } from "@/components/error-state";
import { FeaturedSignalCard } from "@/components/featured-signal-card";
import { HotDealsPanel } from "@/components/hot-deals-panel";
import { LoadingState } from "@/components/loading-state";
import { MetricCard } from "@/components/metric-card";
import { ModeBadge } from "@/components/mode-badge";
import { NewsPanel } from "@/components/news-panel";
import { PositionsTable } from "@/components/positions-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/cn";
import {
  formatCurrency,
  formatDateTime,
  formatPercent,
  formatSignedCurrency,
  formatSignedPercent,
  titleCase
} from "@/lib/format";
import { useAppStore } from "@/lib/store";
import type {
  AgentCommandResponse,
  AgentStatus,
  BestTradeResponse,
  DailyPerformance,
  NewsSummary,
  OverviewResponse,
  SchedulerStatus,
  TradeSetup
} from "@/types/api";

const EMPTY_NEWS: NewsSummary = {
  items: [],
  overall_sentiment: 0,
  top_symbols: [],
  feed_status: "empty",
  technical_only: true,
  technical_only_reason: "No fresh headlines are available yet."
};

export default function OverviewPage() {
  const {
    agentStatus,
    agentEvents,
    agentStreamConnected,
    setAgentStatus,
    selectedAgentSymbol,
    setSelectedAgentSymbol,
    agentLauncherOpen,
    setAgentLauncherOpen
  } = useAppStore();
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [performance, setPerformance] = useState<DailyPerformance[]>([]);
  const [news, setNews] = useState<NewsSummary>(EMPTY_NEWS);
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [bestTrade, setBestTrade] = useState<BestTradeResponse | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [isFetchingBestTrade, setIsFetchingBestTrade] = useState(false);
  const [isAgentSubmitting, setIsAgentSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tradeError, setTradeError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    Promise.allSettled([
      apiFetch<OverviewResponse>("/api/portfolio/overview"),
      apiFetch<DailyPerformance[]>("/api/portfolio/performance"),
      apiFetch<NewsSummary>("/api/news/summary"),
      apiFetch<SchedulerStatus>("/api/scheduler/status")
    ]).then((results) => {
      if (cancelled) return;
      const [overviewResult, performanceResult, newsResult, schedulerResult] = results;

      if (overviewResult.status === "rejected") {
        setError(overviewResult.reason instanceof Error ? overviewResult.reason.message : "Unable to load overview");
        return;
      }

      setOverview(overviewResult.value);
      const initialSymbol = selectedAgentSymbol || overviewResult.value.watchlist_symbols[0] || "";
      setSelectedSymbol(initialSymbol);
      setSelectedAgentSymbol(initialSymbol);
      if (performanceResult.status === "fulfilled") setPerformance(performanceResult.value);
      if (newsResult.status === "fulfilled") setNews(newsResult.value);
      if (schedulerResult.status === "fulfilled") setScheduler(schedulerResult.value);
    });

    return () => {
      cancelled = true;
    };
  }, [selectedAgentSymbol, setSelectedAgentSymbol]);

  async function fetchBestTrade(symbol: string) {
    if (!overview?.trade_fetch_ready) {
      setTradeError(
        `Before fetching trades, provide these keys in Strategy -> API keys: ${overview?.missing_trade_credentials.join(" ")}`
      );
      return;
    }
    const cleanSymbol = symbol.trim().toUpperCase();
    if (!cleanSymbol) {
      setTradeError("Pick a stock from your Strategy watchlist first.");
      return;
    }
    if (overview?.watchlist_symbols.length && !overview.watchlist_symbols.includes(cleanSymbol)) {
      setTradeError(`Search stays limited to your Strategy stocks: ${overview.watchlist_symbols.join(", ")}`);
      return;
    }

    setIsFetchingBestTrade(true);
    setTradeError(null);
    try {
      const response = await apiFetch<BestTradeResponse>(`/api/market/best-trade?symbol=${encodeURIComponent(cleanSymbol)}`);
      setBestTrade(response);
      setSelectedSymbol(cleanSymbol);
      setSelectedAgentSymbol(cleanSymbol);
    } catch (loadError) {
      setTradeError(loadError instanceof Error ? loadError.message : "Unable to pick the best trade");
    } finally {
      setIsFetchingBestTrade(false);
    }
  }

  function submitTradeSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void fetchBestTrade(selectedSymbol);
  }

  async function handleStartAgent() {
    const symbol = selectedSymbol.trim().toUpperCase();
    if (!symbol) {
      setTradeError("Pick a stock first. The agent only runs on the stock you selected.");
      return;
    }
    setIsAgentSubmitting(true);
    setTradeError(null);
    try {
      await apiFetch<AgentCommandResponse>("/api/agent/start", {
        method: "POST",
        json: { symbol, launched_from: "overview" }
      });
      const refreshedStatus = await apiFetch<AgentStatus>("/api/agent/status");
      setAgentStatus(refreshedStatus);
      setAgentLauncherOpen(false);
    } catch (agentError) {
      setTradeError(agentError instanceof Error ? agentError.message : "Unable to start the autonomous agent");
    } finally {
      setIsAgentSubmitting(false);
    }
  }

  async function handleStopAgent() {
    setIsAgentSubmitting(true);
    try {
      await apiFetch<AgentCommandResponse>("/api/agent/stop", { method: "POST" });
      const refreshedStatus = await apiFetch<AgentStatus>("/api/agent/status");
      setAgentStatus(refreshedStatus);
      setAgentLauncherOpen(false);
    } catch (agentError) {
      setTradeError(agentError instanceof Error ? agentError.message : "Unable to stop the autonomous agent");
    } finally {
      setIsAgentSubmitting(false);
    }
  }

  const chartData = useMemo(() => {
    if (performance.length) {
      return performance.map((row) => ({
        date: row.trading_date,
        equity: row.closing_equity,
        realized: row.realized_pnl,
        unrealized: row.unrealized_pnl
      }));
    }

    if (!overview?.latest_snapshot) return [];
    return [
      {
        date: new Date(overview.latest_snapshot.timestamp).toISOString().slice(0, 10),
        equity: overview.latest_snapshot.total_equity,
        realized: overview.latest_snapshot.realized_pnl,
        unrealized: overview.latest_snapshot.unrealized_pnl
      }
    ];
  }, [overview, performance]);

  if (error) return <ErrorState message={error} />;
  if (!overview) return <LoadingState label="Loading overview..." />;

  const liveAgentSession = agentStatus?.active ? agentStatus.session : null;
  const liveCurrentCapital = liveAgentSession?.current_equity ?? overview.current_capital;
  const liveTargetCapital = liveAgentSession?.target_equity ?? overview.target_capital;
  const liveGoalProgress = liveAgentSession?.progress_pct ?? overview.goal_progress_pct;
  const liveGoalGap = liveAgentSession?.target_gap ?? Math.max(liveTargetCapital - liveCurrentCapital, 0);
  const liveTodayPnl = liveAgentSession?.today_pnl ?? overview.todays_pnl;
  const liveTodayPnlPct = liveAgentSession?.today_pnl_pct ?? overview.todays_pnl_pct;
  const liveRealizedPnl = liveAgentSession?.realized_pnl ?? overview.latest_snapshot?.realized_pnl ?? 0;
  const liveUnrealizedPnl = liveAgentSession?.unrealized_pnl ?? overview.latest_snapshot?.unrealized_pnl ?? 0;
  const liveCashBalance = liveAgentSession?.cash_balance ?? overview.latest_snapshot?.cash_balance ?? 0;
  const liveMarginAvailable = liveAgentSession?.margin_available ?? overview.latest_snapshot?.margin_available ?? 0;
  const liveSyncedAt =
    typeof liveAgentSession?.raw_state_json?.last_synced_at === "string"
      ? liveAgentSession.raw_state_json.last_synced_at
      : overview.latest_snapshot?.timestamp;
  const featuredDeal = overview.hot_deals[0] ?? null;
  const secondaryDeals = overview.hot_deals.slice(featuredDeal ? 1 : 0);
  const actionCard = bestTrade?.setup ? buildOverviewActionCard(bestTrade.setup) : null;
  const liveSourceLabel =
    overview.latest_snapshot?.source?.startsWith("live:")
      ? `Live ${titleCase(overview.active_broker)} account`
      : `Last synced from ${titleCase(overview.active_broker)}`;

  return (
    <div className="space-y-8">
      <FeaturedSignalCard
        deal={featuredDeal}
        session={overview.market_session}
        source={overview.latest_snapshot?.source}
      />

      <section className="rounded-[32px] border border-border/70 bg-card/85 p-6 shadow-[0_24px_80px_rgba(15,23,42,0.12)] backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <div className="text-xs uppercase tracking-[0.24em] text-primary">Today&apos;s trade finder</div>
            <h2 className="mt-3 font-display text-4xl font-semibold tracking-tight">Pick the clearest trade from your Strategy stocks</h2>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              Search only within the comma-separated stocks saved on the Strategy page. The button checks the available instrument lanes for that stock and brings the strongest advisory setup to the top.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={overview.using_fallback_broker ? "warning" : "success"}>
              {overview.using_fallback_broker ? "Fallback broker active" : `Broker ${titleCase(overview.active_broker)}`}
            </Badge>
            {overview.available_instruments.map((instrument) => (
              <Badge key={instrument} variant="info">
                {titleCase(instrument)}
              </Badge>
            ))}
          </div>
        </div>

        <form className="mt-5 grid gap-3 lg:grid-cols-[1fr_auto]" onSubmit={submitTradeSearch}>
          <div className="space-y-2">
            <Input
              list="overview-watchlist"
              value={selectedSymbol}
              onChange={(event) => {
                const symbol = event.target.value.toUpperCase();
                setSelectedSymbol(symbol);
                setSelectedAgentSymbol(symbol);
              }}
              placeholder="Search a Strategy stock like INFY or HDFCBANK"
              className="h-12 rounded-2xl bg-background/70"
            />
            <datalist id="overview-watchlist">
              {overview.watchlist_symbols.map((symbol) => (
                <option key={symbol} value={symbol} />
              ))}
            </datalist>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Tracked stocks</span>
              {overview.watchlist_symbols.map((symbol) => (
                <button
                  key={symbol}
                  type="button"
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] transition-colors",
                    selectedSymbol === symbol
                      ? "border-primary/40 bg-primary/10 text-foreground"
                      : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"
                  )}
                  onClick={() => {
                    setSelectedSymbol(symbol);
                    setSelectedAgentSymbol(symbol);
                  }}
                >
                  {symbol}
                </button>
              ))}
            </div>
          </div>
          <Button
            type="submit"
            size="lg"
            className="gap-2 rounded-2xl"
            disabled={isFetchingBestTrade || !overview.trade_fetch_ready}
          >
            {isFetchingBestTrade ? <RefreshCw className="h-4 w-4 animate-spin" /> : <WandSparkles className="h-4 w-4" />}
            {isFetchingBestTrade ? "Finding today's best trade..." : "Pick today's best trade"}
          </Button>
        </form>

        {!overview.trade_fetch_ready ? (
          <div className="mt-4 rounded-2xl border border-amber-500/25 bg-amber-500/8 px-4 py-3 text-sm text-amber-200">
            Before fetching trades, provide these keys in Strategy -&gt; API keys:{" "}
            {overview.missing_trade_credentials.join(" ")}
          </div>
        ) : null}

        {tradeError ? (
          <div className="mt-4 rounded-2xl border border-rose-500/25 bg-rose-500/8 px-4 py-3 text-sm text-rose-300">
            {tradeError}
          </div>
        ) : null}

        {bestTrade && actionCard ? (
          <div className="mt-6 space-y-4">
            <section
              className={cn(
                "signal-frame rounded-[34px] p-[1px] shadow-[0_28px_90px_rgba(15,23,42,0.16)]",
                `signal-frame--${actionCard.theme}`
              )}
            >
              <div className="signal-frame__shell rounded-[33px] border-transparent p-6 text-white">
                <div className="grid gap-6 xl:grid-cols-[1.08fr_0.92fr]">
                  <div className="space-y-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={actionCard.badgeVariant}>{actionCard.badgeLabel}</Badge>
                      <Badge variant="info">{titleCase(bestTrade.selected_instrument)}</Badge>
                      <Badge variant={bestTrade.setup.execution_ready ? "success" : "warning"}>
                        {bestTrade.setup.execution_ready ? "Ready to review" : "Research only"}
                      </Badge>
                    </div>
                    <div>
                      <div className={cn("text-xs uppercase tracking-[0.24em]", actionCard.kickerClass)}>What to do today</div>
                      <h2 className="mt-3 max-w-4xl font-display text-4xl font-semibold tracking-tight sm:text-5xl">
                        {actionCard.title}
                      </h2>
                      <p className="mt-4 max-w-3xl text-base leading-7 text-slate-300">{actionCard.subtitle}</p>
                    </div>
                    <div className="grid gap-3 md:grid-cols-3">
                      {actionCard.steps.map((step, index) => (
                        <div key={step} className={cn("rounded-[24px] border p-4 backdrop-blur", actionCard.stepClass)}>
                          <div className="text-xs uppercase tracking-[0.16em] text-slate-400">Step {index + 1}</div>
                          <div className="mt-3 text-sm leading-6 text-slate-200">{step}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="grid gap-4">
                    <div className={cn("rounded-[28px] border p-5 backdrop-blur", actionCard.panelClass)}>
                      <div className="text-xs uppercase tracking-[0.16em] text-slate-400">Why this lane won</div>
                      <div className="mt-3 font-display text-3xl font-semibold">{bestTrade.symbol}</div>
                      <div className="mt-2 text-sm leading-6 text-slate-300">{actionCard.whyLine}</div>
                    </div>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <ActionMetricCard label="Entry" value={formatCurrency(bestTrade.setup.decision.entry_price_hint ?? bestTrade.setup.quote.ltp)} className={actionCard.metricClass} labelClass={actionCard.metricLabelClass} />
                      <ActionMetricCard label="Confidence" value={formatPercent(bestTrade.setup.decision.confidence * 100)} className={actionCard.metricClass} labelClass={actionCard.metricLabelClass} />
                      <ActionMetricCard label="Stop loss" value={bestTrade.setup.decision.stop_loss != null ? formatCurrency(bestTrade.setup.decision.stop_loss) : "--"} className={actionCard.metricClass} labelClass={actionCard.metricLabelClass} />
                      <ActionMetricCard label="Take profit" value={bestTrade.setup.decision.take_profit != null ? formatCurrency(bestTrade.setup.decision.take_profit) : "--"} className={actionCard.metricClass} labelClass={actionCard.metricLabelClass} />
                    </div>
                    <div className={cn("rounded-[24px] border p-4", actionCard.panelClass)}>
                      <div className="text-xs uppercase tracking-[0.16em] text-slate-400">Lane scorecard</div>
                      <div className="mt-3 grid gap-2">
                        {bestTrade.evaluated_instruments.map((lane) => (
                          <div key={lane.instrument} className="flex items-center justify-between rounded-2xl border border-white/10 px-3 py-3 text-sm text-slate-200">
                            <span>
                              {titleCase(lane.instrument)} | {titleCase(lane.action)}
                            </span>
                            <span>{formatPercent(lane.confidence * 100)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </div>
        ) : (
          <div className="mt-6 rounded-3xl border border-dashed border-border p-5 text-sm text-muted-foreground">
            Pick a tracked stock and the board will bring its clearest stock, options, or futures idea here.
          </div>
        )}
      </section>

      <AgentStreamPanel
        session={agentStatus?.session ?? null}
        events={agentEvents}
        streamingConnected={agentStreamConnected}
        selectedSymbol={selectedSymbol}
        onOpenLauncher={() => setAgentLauncherOpen(true)}
        onStop={() => void handleStopAgent()}
        disabled={!selectedSymbol}
        busy={isAgentSubmitting}
      />

      {agentLauncherOpen && !(agentStatus?.active) ? (
        <section className="rounded-[32px] border border-primary/20 bg-[radial-gradient(circle_at_top_left,_rgba(8,145,178,0.12),_transparent_40%),linear-gradient(160deg,rgba(15,23,42,0.92),rgba(15,23,42,0.78))] p-6 text-white shadow-[0_24px_90px_rgba(15,23,42,0.22)]">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="max-w-3xl">
              <div className="text-xs uppercase tracking-[0.24em] text-cyan-200/90">AI Agent Launch Pad</div>
              <h2 className="mt-3 font-display text-4xl font-semibold tracking-tight">
                Tell the agent which stock should carry the X to 1.2X attempt
              </h2>
              <p className="mt-3 text-sm leading-6 text-slate-300">
                Nothing starts on the first click anymore. This launch pad asks for the stock, explains the workflow, and only then lets you begin the autonomous run.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Target path 1.20x</Badge>
              <Badge variant="success">{titleCase(overview.strategy_mode)} mode</Badge>
            </div>
          </div>

          <div className="mt-6 grid gap-6 xl:grid-cols-[0.96fr_1.04fr]">
            <div className="space-y-4 rounded-[28px] border border-white/10 bg-white/5 p-5 backdrop-blur">
              <div>
                <div className="text-xs uppercase tracking-[0.16em] text-slate-400">Selected stock</div>
                <Input
                  list="agent-watchlist"
                  value={selectedSymbol}
                  onChange={(event) => {
                    const symbol = event.target.value.toUpperCase();
                    setSelectedSymbol(symbol);
                    setSelectedAgentSymbol(symbol);
                  }}
                  placeholder="Pick the stock the agent should focus on"
                  className="mt-3 h-12 rounded-2xl border-white/10 bg-slate-950/40 text-white placeholder:text-slate-500"
                />
                <datalist id="agent-watchlist">
                  {overview.watchlist_symbols.map((symbol) => (
                    <option key={symbol} value={symbol} />
                  ))}
                </datalist>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {overview.watchlist_symbols.map((symbol) => (
                  <button
                    key={symbol}
                    type="button"
                    className={cn(
                      "rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] transition-colors",
                      selectedSymbol === symbol
                        ? "border-cyan-300/40 bg-cyan-300/12 text-white"
                        : "border-white/10 text-slate-300 hover:border-cyan-300/30 hover:text-white"
                    )}
                    onClick={() => {
                      setSelectedSymbol(symbol);
                      setSelectedAgentSymbol(symbol);
                    }}
                  >
                    {symbol}
                  </button>
                ))}
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <LaunchMetric label="Current capital" value={formatCurrency(liveCurrentCapital)} />
                <LaunchMetric label="Target capital" value={formatCurrency(liveTargetCapital)} />
                <LaunchMetric label="Available instruments" value={overview.available_instruments.map(titleCase).join(", ")} />
                <LaunchMetric label="Broker path" value={titleCase(overview.active_broker)} />
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <Button
                  onClick={() => void handleStartAgent()}
                  disabled={!selectedSymbol || isAgentSubmitting}
                  className="gap-2 rounded-full"
                >
                  {isAgentSubmitting ? <RefreshCw className="h-4 w-4 animate-spin" /> : <WandSparkles className="h-4 w-4" />}
                  {isAgentSubmitting ? "Starting autonomous run..." : `Start AI agent for ${selectedSymbol || "selected stock"}`}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setAgentLauncherOpen(false)}
                  className="rounded-full border-white/15 bg-transparent text-white hover:bg-white/5"
                >
                  Cancel
                </Button>
              </div>
            </div>

            <div className="space-y-4 rounded-[28px] border border-white/10 bg-white/5 p-5 backdrop-blur">
              <div>
                <div className="text-xs uppercase tracking-[0.16em] text-slate-400">How the agent works</div>
                <h3 className="mt-3 font-display text-3xl font-semibold tracking-tight">Five plain-English stages before any trade happens</h3>
              </div>

              {[
                "1. Observe: it pulls fresh price, candle, position, and portfolio state for the stock you picked.",
                "2. Specialist lanes: it checks stock intraday, swing, options, futures, and the forex scout lane for that same stock context.",
                "3. Coordinator: it compares the lane outputs and picks the strongest risk-adjusted idea instead of firing blindly.",
                "4. Risk gate: your hard limits still have veto power, including kill switch, cooldown, drawdown, and mandatory stop loss.",
                "5. Action and stream: it records the recommendation or execution attempt and pushes the event into the live activity feed immediately."
              ].map((step) => (
                <div key={step} className="rounded-[22px] border border-white/10 bg-slate-950/30 px-4 py-4 text-sm leading-6 text-slate-200">
                  {step}
                </div>
              ))}

              <div className="rounded-[22px] border border-amber-400/20 bg-amber-400/8 px-4 py-4 text-sm leading-6 text-amber-100">
                The 1.2X target is an aspiration, not a promise. The agent is autonomous in workflow, but not above the risk engine.
              </div>
            </div>
          </div>
        </section>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="overflow-hidden rounded-[32px] border border-border/70 bg-[radial-gradient(circle_at_top_left,_rgba(8,145,178,0.2),_transparent_38%),linear-gradient(145deg,rgba(15,23,42,0.86),rgba(15,23,42,0.58))] p-6 text-white shadow-[0_24px_80px_rgba(15,23,42,0.28)]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-xs uppercase tracking-[0.24em] text-cyan-200/90">Capital board</div>
              <h1 className="mt-3 font-display text-4xl font-semibold tracking-tight">Live capital posture from your broker account</h1>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <ModeBadge mode={overview.strategy_mode} />
              <Badge variant={overview.using_fallback_broker ? "warning" : "success"}>
                {overview.using_fallback_broker ? "Using mock fallback" : liveSourceLabel}
              </Badge>
            </div>
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="space-y-6">
              <div>
                <div className="text-sm uppercase tracking-[0.2em] text-slate-300">Current capital</div>
                <div className="mt-2 font-display text-5xl font-semibold">{formatCurrency(liveCurrentCapital)}</div>
                <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-slate-300">
                  <span>Target {formatCurrency(liveTargetCapital)}</span>
                  <span className="h-1 w-1 rounded-full bg-slate-400" />
                  <span>Gap {formatCurrency(liveGoalGap)}</span>
                  <span className="h-1 w-1 rounded-full bg-slate-400" />
                  <span>Synced {liveSyncedAt ? formatDateTime(liveSyncedAt) : "Waiting for broker sync"}</span>
                  {liveAgentSession ? (
                    <>
                      <span className="h-1 w-1 rounded-full bg-emerald-300" />
                      <span className="text-emerald-200">Agent session streaming live</span>
                    </>
                  ) : null}
                </div>
              </div>

              <div className="space-y-3 rounded-3xl border border-white/10 bg-white/5 p-4 backdrop-blur">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-300">Progress to goal</span>
                  <span className="font-medium text-white">{formatPercent(liveGoalProgress)}</span>
                </div>
                <Progress value={liveGoalProgress} />
                <p className="text-sm text-slate-300">
                  {liveAgentSession
                    ? "The autonomous agent is now driving this goal bar with live session equity, progress, and remaining gap values."
                    : "The dashboard now reads from the connected account path first. Goals help frame urgency, but they never override capital preservation or hard risk rules."}
                </p>
              </div>
            </div>

            <div className="grid gap-3">
              <div className="rounded-3xl border border-white/10 bg-white/5 p-4 backdrop-blur">
                <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-slate-300">
                  <Clock3 className="h-4 w-4" />
                  Market window
                </div>
                <div className="mt-3 text-2xl font-semibold">{overview.market_session.label}</div>
                <div className="mt-2 text-sm text-slate-300">{overview.market_session.note}</div>
                <div className="mt-3 text-xs text-slate-400">{formatDateTime(overview.market_session.local_time)}</div>
              </div>

              <div className="rounded-3xl border border-white/10 bg-white/5 p-4 backdrop-blur">
                <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-slate-300">
                  <Sparkles className="h-4 w-4" />
                  Latest AI pulse
                </div>
                <div className="mt-3 text-2xl font-semibold">
                  {overview.latest_decision?.symbol ?? "--"}
                  {overview.latest_decision?.action ? ` | ${titleCase(overview.latest_decision.action)}` : ""}
                </div>
                <div className="mt-2 text-sm text-slate-300">
                  Confidence {overview.latest_decision?.confidence ? `${Math.round(overview.latest_decision.confidence * 100)}%` : "--"}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="grid gap-4">
          <MetricCard
            label="Invested capital"
            value={formatCurrency(overview.invested_capital)}
            hint={`${overview.open_positions.length} live positions`}
          />
          <MetricCard
            label="Today's PnL"
            value={formatSignedCurrency(liveTodayPnl)}
            hint={formatSignedPercent(liveTodayPnlPct)}
            tone={liveTodayPnl >= 0 ? "positive" : "negative"}
          />
          <MetricCard
            label="Unrealized PnL"
            value={formatSignedCurrency(liveUnrealizedPnl)}
            hint={`Realized ${formatSignedCurrency(liveRealizedPnl)}`}
            tone={liveUnrealizedPnl >= 0 ? "positive" : "negative"}
          />
          <MetricCard
            label="Available cash"
            value={formatCurrency(liveCashBalance)}
            hint={`Margin ${formatCurrency(liveMarginAvailable)}`}
            tone="neutral"
          />
          {liveAgentSession ? (
            <MetricCard
              label="Agent session PnL"
              value={formatSignedCurrency(liveAgentSession.session_pnl)}
              hint={formatSignedPercent(liveAgentSession.session_pnl_pct)}
              tone={liveAgentSession.session_pnl >= 0 ? "positive" : "negative"}
            />
          ) : null}
          <MetricCard
            label="Scheduler"
            value={scheduler?.running ? "Running" : "Idle"}
            hint={
              scheduler?.next_due_at
                ? `Next due ${formatDateTime(scheduler.next_due_at)}`
                : "Use Manual-only mode on Market when you want quiet scanning."
            }
            tone={scheduler?.running ? "positive" : "neutral"}
          />
        </div>
      </section>

      <HotDealsPanel deals={secondaryDeals} session={overview.market_session} featuredShown={Boolean(featuredDeal)} />

      <section className="grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
        <ChartCard title="Progress to goal" description="The target remains aspirational. The live account balance is what matters.">
          <div className="space-y-4">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Progress</span>
              <span>{formatPercent(liveGoalProgress)}</span>
            </div>
            <Progress value={liveGoalProgress} />
            <div className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-3">
              <div>Cash balance: {formatCurrency(liveCashBalance)}</div>
              <div>Margin available: {formatCurrency(liveMarginAvailable)}</div>
              <div>Active broker: {titleCase(overview.active_broker)}</div>
            </div>
          </div>
        </ChartCard>

        <ChartCard title="Latest safety signal" description="The most recent system message that deserves a human glance.">
          <div className="space-y-3">
            <div className="rounded-2xl border border-border p-4">
              <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Latest AI decision</div>
              <div className="mt-2 text-lg font-semibold">
                {overview.latest_decision?.symbol ?? "--"}
                {overview.latest_decision?.action ? ` | ${overview.latest_decision.action}` : " No decision"}
              </div>
              <div className="mt-2 text-sm text-muted-foreground">
                Confidence {overview.latest_decision?.confidence ? `${Math.round(overview.latest_decision.confidence * 100)}%` : "--"}
              </div>
            </div>
            <div className="rounded-2xl border border-border p-4">
              <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Latest risk event</div>
              <div className="mt-2 text-lg font-semibold">{overview.latest_risk_event?.event_type ?? "No recent risk events"}</div>
              <div className="mt-2 text-sm text-muted-foreground">{overview.latest_risk_event?.message ?? "System is quiet right now."}</div>
            </div>
          </div>
        </ChartCard>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <ChartCard title="Equity curve" description="Broker-backed daily closing snapshots accumulated by the app.">
          {chartData.length ? (
            <ChartContainer className="h-[280px]">
              {({ width, height }) => (
                <AreaChart width={width} height={height} data={chartData}>
                  <defs>
                    <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#0891b2" stopOpacity={0.55} />
                      <stop offset="95%" stopColor="#0891b2" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="4 4" opacity={0.18} />
                  <XAxis dataKey="date" tickLine={false} axisLine={false} />
                  <YAxis tickLine={false} axisLine={false} />
                  <Tooltip />
                  <Area type="monotone" dataKey="equity" stroke="#0891b2" fill="url(#equityFill)" strokeWidth={2.5} />
                </AreaChart>
              )}
            </ChartContainer>
          ) : (
            <div className="rounded-2xl border border-dashed border-border p-5 text-sm text-muted-foreground">
              Waiting for the first live portfolio snapshots before drawing the equity curve.
            </div>
          )}
        </ChartCard>

        <ChartCard title="PnL mix" description="Realized and unrealized components from the same broker-backed snapshot history.">
          {chartData.length ? (
            <ChartContainer className="h-[280px]">
              {({ width, height }) => (
                <LineChart width={width} height={height} data={chartData}>
                  <CartesianGrid strokeDasharray="4 4" opacity={0.18} />
                  <XAxis dataKey="date" tickLine={false} axisLine={false} />
                  <YAxis tickLine={false} axisLine={false} />
                  <Tooltip />
                  <Line type="monotone" dataKey="realized" stroke="#ea580c" strokeWidth={2.5} dot={false} />
                  <Line type="monotone" dataKey="unrealized" stroke="#14b8a6" strokeWidth={2.5} dot={false} />
                </LineChart>
              )}
            </ChartContainer>
          ) : (
            <div className="rounded-2xl border border-dashed border-border p-5 text-sm text-muted-foreground">
              PnL history will appear here after the app captures live snapshots through broker sync or scheduler runs.
            </div>
          )}
        </ChartCard>
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.75fr_1.25fr]">
        <ChartCard title="Execution posture" description="The controls that matter before any order leaves the system.">
          <div className="space-y-4">
            <div className="rounded-2xl border border-border p-4">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-muted-foreground">
                <ShieldAlert className="h-4 w-4" />
                Risk status
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Badge variant={overview.market_session.market_open ? "success" : "warning"}>
                  {overview.market_session.market_open ? "Market open" : "Market closed"}
                </Badge>
                <Badge variant={overview.latest_decision?.approved ? "success" : "warning"}>
                  {overview.latest_decision?.approved ? "Latest decision approved" : "Awaiting approval"}
                </Badge>
              </div>
            </div>

            <div className="rounded-2xl border border-border p-4">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-muted-foreground">
                <Wallet className="h-4 w-4" />
                Broker posture
              </div>
              <div className="mt-3 text-lg font-semibold">{titleCase(overview.active_broker)}</div>
              <div className="mt-2 text-sm text-muted-foreground">
                {overview.using_fallback_broker
                  ? "The live broker path is unavailable, so the app has dropped to its mock fallback."
                  : "Overview metrics are being refreshed from the connected broker account path."}
              </div>
            </div>
          </div>
        </ChartCard>

        <ChartCard title="News pulse" description="Live headlines and sentiment still help rank opportunities, but they never override risk controls.">
          <NewsPanel summary={news} />
        </ChartCard>
      </section>

      <section className="space-y-4">
        <div>
          <h2 className="font-display text-2xl font-semibold tracking-tight">Open positions</h2>
          <p className="text-sm text-muted-foreground">
            This table prefers the latest live broker exposure. If the broker is temporarily unavailable, the app falls back to its last synced local records.
          </p>
        </div>
        <PositionsTable positions={overview.open_positions} />
      </section>
    </div>
  );
}

function ActionMetricCard({
  label,
  value,
  className,
  labelClass
}: {
  label: string;
  value: string;
  className: string;
  labelClass: string;
}) {
  return (
    <div className={cn("rounded-[24px] border p-4", className)}>
      <div className={cn("text-xs uppercase tracking-[0.16em]", labelClass)}>{label}</div>
      <div className="mt-3 text-2xl font-semibold">{value}</div>
    </div>
  );
}

function LaunchMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[22px] border border-white/10 bg-slate-950/30 p-4">
      <div className="text-xs uppercase tracking-[0.16em] text-slate-400">{label}</div>
      <div className="mt-3 text-lg font-semibold text-white">{value}</div>
    </div>
  );
}

function buildOverviewActionCard(setup: TradeSetup) {
  const action = setup.decision.action;
  const symbol = setup.symbol;
  const lane = titleCase(setup.requested_instrument).toLowerCase();
  const entry = formatCurrency(setup.decision.entry_price_hint ?? setup.quote.ltp);
  const stop = setup.decision.stop_loss != null ? formatCurrency(setup.decision.stop_loss) : "not set";
  const target = setup.decision.take_profit != null ? formatCurrency(setup.decision.take_profit) : "not set";
  const topReason = setup.decision.rationale_points[0] ?? setup.execution_blockers[0] ?? "The board does not see enough evidence yet.";
  const directionalTheme =
    action.startsWith("SELL") || action === "EXIT" || action === "REDUCE"
      ? {
          theme: "sell",
          kickerClass: "text-rose-200/90",
          stepClass: "border-rose-300/15 bg-rose-300/6",
          panelClass: "border-rose-300/15 bg-rose-300/6",
          metricClass: "border-rose-300/15 bg-rose-300/8",
          metricLabelClass: "text-rose-200"
        }
      : {
          theme: "buy",
          kickerClass: "text-emerald-200/90",
          stepClass: "border-emerald-300/15 bg-emerald-300/6",
          panelClass: "border-emerald-300/15 bg-emerald-300/6",
          metricClass: "border-emerald-300/15 bg-emerald-300/8",
          metricLabelClass: "text-emerald-200"
        };

  if (action === "HOLD") {
    return {
      theme: "wait",
      badgeLabel: "Wait",
      badgeVariant: "warning" as const,
      title: `Do not take a ${lane} trade in ${symbol} right now.`,
      subtitle:
        "The app checked the available instrument lanes for this stock and still thinks waiting is the safest move today.",
      steps: [
        `Do not open a new ${lane} trade in ${symbol} yet.`,
        "Keep this stock on the watchlist and check again after stronger confirmation.",
        "Treat patience as capital protection, not as missing out."
      ],
      whyLine: topReason,
      kickerClass: "text-amber-200/90",
      stepClass: "border-amber-300/15 bg-amber-300/6",
      panelClass: "border-amber-300/15 bg-amber-300/6",
      metricClass: "border-amber-300/15 bg-amber-300/8",
      metricLabelClass: "text-amber-200"
    };
  }

  if (!setup.execution_ready && setup.execution_blockers.length) {
    return {
      ...directionalTheme,
      badgeLabel: "Watch only",
      badgeVariant: "info" as const,
      title: `This ${lane} setup in ${symbol} is interesting, but do not place it yet.`,
      subtitle:
        "The analysis likes the idea, but one of your current safety settings is still blocking execution. Treat this as research, not an order.",
      steps: [
        `Watch ${symbol} near ${entry}.`,
        `If you revisit it later, keep the stop near ${stop}.`,
        `The first profit zone is around ${target}.`
      ],
      whyLine: setup.execution_blockers[0]
    };
  }

  return {
    ...directionalTheme,
    badgeLabel: "Action",
    badgeVariant: "success" as const,
    title: buildOverviewActionTitle(action, symbol, lane, entry),
    subtitle:
      "This is the best setup the app found today for the stock you selected across the currently available instrument lanes.",
    steps: [
      `Plan the entry near ${entry}.`,
      `Protect the downside near ${stop}.`,
      `Start taking profit near ${target}.`
    ],
    whyLine: topReason
  };
}

function buildOverviewActionTitle(action: string, symbol: string, lane: string, entry: string) {
  switch (action) {
    case "BUY_STOCK":
      return `Buy ${symbol} stock near ${entry}.`;
    case "SELL_STOCK":
      return `Sell or short ${symbol} stock near ${entry}.`;
    case "BUY_CALL":
      return `Look at a call option setup on ${symbol} near ${entry}.`;
    case "BUY_PUT":
      return `Look at a put option setup on ${symbol} near ${entry}.`;
    case "BUY_FUTURE":
      return `Look at a futures buy in ${symbol} near ${entry}.`;
    case "SELL_FUTURE":
      return `Look at a futures sell in ${symbol} near ${entry}.`;
    case "EXIT":
      return `Exit ${symbol} now to protect capital.`;
    case "REDUCE":
      return `Reduce your ${symbol} exposure now.`;
    default:
      return `Focus on the ${lane} setup in ${symbol} near ${entry}.`;
  }
}
