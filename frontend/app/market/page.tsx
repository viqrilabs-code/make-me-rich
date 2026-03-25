"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { Newspaper, PauseCircle, PlayCircle, Radar, RefreshCw, ShieldCheck, Sparkles, TrendingUp } from "lucide-react";

import { ChartCard } from "@/components/chart-card";
import { ChartContainer } from "@/components/chart-container";
import { ErrorState } from "@/components/error-state";
import { FeatureLaunchStrip } from "@/components/feature-launch-strip";
import { LoadingState } from "@/components/loading-state";
import { NewsPanel } from "@/components/news-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatCurrency, formatDateTime, formatPercent, titleCase } from "@/lib/format";
import { useAppStore } from "@/lib/store";
import type { BrokerHealth, ConfigResponse, NewsSummary, RequestedInstrument, StrategyConfig, TradeSetup } from "@/types/api";

const EMPTY_SUMMARY: NewsSummary = {
  items: [],
  overall_sentiment: 0,
  top_symbols: [],
  feed_status: "empty",
  technical_only: true,
  technical_only_reason: "No fresh headlines are available yet."
};

const INSTRUMENT_OPTIONS: Array<{
  id: RequestedInstrument;
  label: string;
  blurb: string;
}> = [
  { id: "stock", label: "Stocks", blurb: "Directional equity trade from price structure and catalysts." },
  { id: "option", label: "Options", blurb: "Call or put expression from the same underlying setup." },
  { id: "future", label: "Futures", blurb: "Higher-conviction directional exposure with tighter risk discipline." }
];

export default function MarketPage() {
  const router = useRouter();
  const { agentStatus, setAgentLauncherOpen, setSelectedAgentSymbol } = useAppStore();
  const [strategy, setStrategy] = useState<StrategyConfig | null>(null);
  const [marketSummary, setMarketSummary] = useState<NewsSummary>(EMPTY_SUMMARY);
  const [tradeSetup, setTradeSetup] = useState<TradeSetup | null>(null);
  const [brokerHealth, setBrokerHealth] = useState<BrokerHealth | null>(null);
  const [symbolInput, setSymbolInput] = useState("HDFCBANK");
  const [selectedInstrument, setSelectedInstrument] = useState<RequestedInstrument>("stock");
  const [isBooting, setIsBooting] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isRefreshingNews, setIsRefreshingNews] = useState(false);
  const [isSwitchingManualMode, setIsSwitchingManualMode] = useState(false);
  const [tradeGateMessage, setTradeGateMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function boot() {
      setIsBooting(true);
      setError(null);
      const [strategyResult, newsResult, configResult, brokerResult] = await Promise.allSettled([
        apiFetch<StrategyConfig>("/api/strategy"),
        apiFetch<NewsSummary>("/api/news/summary"),
        apiFetch<ConfigResponse>("/api/config"),
        apiFetch<BrokerHealth>("/api/broker/health")
      ]);

      if (!active) return;

      const nextStrategy = strategyResult.status === "fulfilled" ? strategyResult.value : null;
      const trackedSymbols = uniqueSymbols(nextStrategy);
      const defaultSymbol = trackedSymbols[0] ?? "HDFCBANK";

      if (strategyResult.status === "fulfilled") {
        setStrategy(nextStrategy);
      }
      if (newsResult.status === "fulfilled") {
        setMarketSummary(newsResult.value);
      }
      if (configResult.status === "fulfilled") {
        setTradeGateMessage(buildTradeGateMessage(configResult.value));
      }

      setSymbolInput(defaultSymbol);

      if (brokerResult?.status === "fulfilled") {
        setBrokerHealth(brokerResult.value);
      }

      if (configResult.status === "fulfilled" && buildTradeGateMessage(configResult.value)) {
        setIsBooting(false);
        return;
      }

      try {
        const setup = await apiFetch<TradeSetup>(
          `/api/market/trade-setup?symbol=${encodeURIComponent(defaultSymbol)}&instrument=stock`
        );
        if (!active) return;
        setTradeSetup(setup);
      } catch (loadError) {
        if (!active) return;
        setError(loadError instanceof Error ? loadError.message : "Unable to load trade finder");
      } finally {
        if (active) setIsBooting(false);
      }
    }

    boot();

    return () => {
      active = false;
    };
  }, []);

  async function fetchTradeSetup(symbol: string, instrument: RequestedInstrument) {
    if (tradeGateMessage) {
      setError(tradeGateMessage);
      return;
    }
    const cleanSymbol = symbol.trim().toUpperCase();
    const trackedSymbols = uniqueSymbols(strategy);
    if (!cleanSymbol) {
      setError("Choose a strategy symbol to fetch a trade setup.");
      return;
    }
    if (trackedSymbols.length && !trackedSymbols.includes(cleanSymbol)) {
      setError(`Search is limited to your Strategy symbols: ${trackedSymbols.join(", ")}`);
      return;
    }

    setSelectedInstrument(instrument);
    setSymbolInput(cleanSymbol);
    setIsRefreshing(true);
    setError(null);

    try {
      const setup = await apiFetch<TradeSetup>(
        `/api/market/trade-setup?symbol=${encodeURIComponent(cleanSymbol)}&instrument=${instrument}`
      );
      setTradeSetup(setup);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to refresh trade setup");
    } finally {
      setIsRefreshing(false);
      setIsBooting(false);
    }
  }

  function submitSymbol(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void fetchTradeSetup(symbolInput, selectedInstrument);
  }

  async function setManualOnly(paused: boolean) {
    setIsSwitchingManualMode(true);
    setError(null);
    try {
      await apiFetch(paused ? "/api/strategy/manual-only" : "/api/strategy/resume-scheduler", {
        method: "POST"
      });
      const refreshedStrategy = await apiFetch<StrategyConfig>("/api/strategy");
      setStrategy(refreshedStrategy);
      const refreshedHealth = await apiFetch<BrokerHealth>("/api/broker/health");
      setBrokerHealth(refreshedHealth);
    } catch (toggleError) {
      setError(toggleError instanceof Error ? toggleError.message : "Unable to update scheduler mode");
    } finally {
      setIsSwitchingManualMode(false);
    }
  }

  async function refreshNewsManually() {
    const cleanSymbol = symbolInput.trim().toUpperCase();
    if (!cleanSymbol) {
      setError("Pick a strategy stock before refreshing news.");
      return;
    }

    setIsRefreshingNews(true);
    setError(null);
    try {
      const refreshedSummary = await apiFetch<NewsSummary>("/api/news/refresh", {
        method: "POST",
        json: { symbols: [cleanSymbol] }
      });
      setMarketSummary(refreshedSummary);
      await fetchTradeSetup(cleanSymbol, selectedInstrument);
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Unable to refresh news right now");
    } finally {
      setIsRefreshingNews(false);
    }
  }

  if (tradeGateMessage && !tradeSetup && !isBooting) return <ErrorState message={tradeGateMessage} />;
  if (error && !tradeSetup && !isBooting) return <ErrorState message={error} />;
  if (isBooting && !tradeSetup) return <LoadingState label="Loading trade finder..." />;
  if (!tradeSetup) return <ErrorState message="Trade finder did not return a setup." />;

  const highlightedTrade = tradeSetup.decision.action !== "HOLD" && tradeSetup.decision.confidence >= 0.78;
  const watchlist = uniqueSymbols(strategy);
  const directive = buildActionDirective(tradeSetup);
  const chartData = buildTechnicalChartData(tradeSetup);
  const optionPlan = tradeSetup.option_contract;
  const displayedEntry = optionPlan?.premium_entry ?? tradeSetup.decision.entry_price_hint ?? tradeSetup.quote.ltp;
  const displayedStop = optionPlan?.premium_stop_loss ?? tradeSetup.decision.stop_loss;
  const displayedTarget = optionPlan?.premium_take_profit ?? tradeSetup.decision.take_profit;
  const currentSymbol = symbolInput.trim().toUpperCase() || tradeSetup.symbol;

  return (
    <div className="space-y-8">
      <FeatureLaunchStrip
        title="Core actions"
        cards={[
          {
            title: "Top 5 deals",
            status: "Full-NSE sweep board",
            actionLabel: "Open top 5 board",
            onClick: () => router.push("/#daily-top-deals"),
            tone: "amber"
          },
          {
            title: "ReAct agent",
            status: agentStatus?.active ? "Running now" : "Launch from overview",
            actionLabel: agentStatus?.active ? "View live agent" : "Open launch pad",
            onClick: () => {
              setSelectedAgentSymbol(currentSymbol);
              setAgentLauncherOpen(true);
              router.push("/#react-agent");
            },
            tone: "teal"
          }
        ]}
      />

      <section className="space-y-5">
        <div className="text-xs uppercase tracking-[0.2em] text-primary">Trade finder</div>
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-3xl">
            <h1 className="font-display text-4xl font-semibold tracking-tight">Fetch the next stock, option, or futures idea from live charts and technical context</h1>
            <p className="mt-3 text-sm text-muted-foreground">Pick one tracked stock and pull one clear setup.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <Badge variant={tradeSetup.execution_ready ? "success" : "warning"}>
              {tradeSetup.execution_ready ? "Execution-ready candidate" : "Research-first setup"}
            </Badge>
            <Badge variant={tradeSetup.using_fallback_broker ? "warning" : "info"}>
              {tradeSetup.using_fallback_broker
                ? `Fallback broker active (${tradeSetup.active_broker})`
                : `Broker ${tradeSetup.active_broker}`}
            </Badge>
            <Badge variant={tradeSetup.analysis_engine === "llm" ? "success" : "warning"}>
              {tradeSetup.analysis_engine === "llm" ? "LLM-assisted analysis" : "Fast heuristic analysis"}
            </Badge>
            <Badge variant="info">Selected broker {tradeSetup.selected_broker}</Badge>
            <Badge variant={tradeSetup.news_summary.technical_only ? "warning" : "success"}>
              {tradeSetup.news_summary.technical_only ? "Technical-only mode" : "News-assisted mode"}
            </Badge>
          </div>
        </div>

        <div className="rounded-[28px] border border-border/70 bg-card/80 p-5 shadow-[0_18px_60px_rgba(15,23,42,0.12)] backdrop-blur">
          <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
            <div className="space-y-3">
              <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Instrument lane</div>
              <div className="grid gap-3 sm:grid-cols-3">
            {INSTRUMENT_OPTIONS.map((option) => (
              <Button
                key={option.id}
                type="button"
                variant={selectedInstrument === option.id ? "default" : "outline"}
                className={cn(
                  "h-auto w-full flex-col items-start gap-1 rounded-2xl px-4 py-4 text-left text-base",
                  selectedInstrument === option.id &&
                    "shadow-[0_0_0_1px_rgba(34,211,238,0.28),0_14px_28px_rgba(34,211,238,0.12)]"
                )}
                disabled={Boolean(tradeGateMessage)}
                onClick={() => void fetchTradeSetup(symbolInput, option.id)}
              >
                <span>{option.label}</span>
              </Button>
            ))}
              </div>
            </div>

            <div className="rounded-2xl border border-border/70 bg-background/55 p-4">
              <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Scheduler mode</div>
              <div className="mt-2 text-xl font-semibold">
                {strategy?.pause_scheduler ? "Manual search only" : "Auto polling enabled"}
              </div>
              <p className="mt-2 text-sm text-muted-foreground">Pause recurring scans when you want manual-only analysis.</p>
              <div className="mt-4 flex flex-wrap gap-3">
                <Button
                  type="button"
                  variant={strategy?.pause_scheduler ? "secondary" : "default"}
                  className="gap-2 rounded-2xl"
                  disabled={isSwitchingManualMode || Boolean(strategy?.pause_scheduler)}
                  onClick={() => void setManualOnly(true)}
                >
                  <PauseCircle className="h-4 w-4" />
                  Manual-only
                </Button>
                <Button
                  type="button"
                  variant={strategy?.pause_scheduler ? "default" : "outline"}
                  className="gap-2 rounded-2xl"
                  disabled={isSwitchingManualMode || !strategy?.pause_scheduler}
                  onClick={() => void setManualOnly(false)}
                >
                  <PlayCircle className="h-4 w-4" />
                  Resume scheduler
                </Button>
              </div>
            </div>
          </div>

          <form className="mt-5 grid gap-3 lg:grid-cols-[1fr_auto]" onSubmit={submitSymbol}>
            {watchlist.length ? (
              <Select
                value={symbolInput}
                onChange={(event) => setSymbolInput(event.target.value.toUpperCase())}
                className="h-12 rounded-2xl bg-background/70"
              >
                {watchlist.map((symbol) => (
                  <option key={symbol} value={symbol}>
                    {symbol}
                  </option>
                ))}
              </Select>
            ) : (
              <Input
                value={symbolInput}
                onChange={(event) => setSymbolInput(event.target.value.toUpperCase())}
                placeholder="Add comma-separated symbols in Strategy first"
                className="h-12 rounded-2xl bg-background/70"
              />
            )}
            <Button
              type="submit"
              size="lg"
              className="gap-2 rounded-2xl"
              disabled={isRefreshing || Boolean(tradeGateMessage)}
            >
              <RefreshCw className={cn("h-4 w-4", isRefreshing && "animate-spin")} />
              {isRefreshing ? "Refreshing setup..." : "Fetch trade"}
            </Button>
          </form>

          {tradeGateMessage ? (
            <div className="mt-4 rounded-2xl border border-amber-500/25 bg-amber-500/8 px-4 py-3 text-sm text-amber-200">
              {tradeGateMessage}
            </div>
          ) : null}

          {brokerHealth && !brokerHealth.healthy ? (
            <div className="mt-4 rounded-2xl border border-rose-500/25 bg-rose-500/8 px-4 py-3 text-sm text-rose-200">
              <div className="font-semibold">
                {titleCase(brokerHealth.broker)} is unavailable, so manual live trade search is paused.
              </div>
              <div className="mt-1">
                {brokerHealth.message}
                {typeof brokerHealth.details?.error === "string" ? ` ${brokerHealth.details.error}` : ""}
              </div>
              <div className="mt-2 text-rose-100/90">
                Go to Strategy and refresh the broker token, or switch the broker to mock if you want simulation-only
                analysis.
              </div>
            </div>
          ) : null}

          <div className="mt-4 rounded-2xl border border-border/70 bg-background/45 px-4 py-3 text-sm text-muted-foreground">
            Fetch trade uses the live broker path and stops if live pricing is unavailable.
          </div>

          {watchlist.length ? (
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Strategy symbols</span>
              {watchlist.map((symbol) => (
                <button
                  key={symbol}
                  type="button"
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] transition-colors",
                    symbolInput === symbol
                      ? "border-primary/40 bg-primary/10 text-foreground"
                      : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"
                  )}
                  onClick={() => {
                    setSymbolInput(symbol);
                    void fetchTradeSetup(symbol, selectedInstrument);
                  }}
                >
                  {symbol}
                </button>
              ))}
            </div>
          ) : (
            <div className="mt-4 rounded-2xl border border-dashed border-border p-4 text-sm text-muted-foreground">
              Add your comma-separated symbols on the Strategy page first. Manual search stays limited to those names.
            </div>
          )}

          {error ? (
            <div className="mt-4 rounded-2xl border border-rose-500/25 bg-rose-500/8 px-4 py-3 text-sm text-rose-300">
              {error}
            </div>
          ) : null}
        </div>
      </section>

      <section
        className={cn(
          "signal-frame rounded-[34px] p-[1px] shadow-[0_28px_90px_rgba(15,23,42,0.22)]",
          `signal-frame--${directive.theme}`
        )}
      >
        <div className="signal-frame__shell rounded-[33px] border-transparent p-6 text-white">
          <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
            <div className="space-y-5">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={directive.badgeVariant}>{directive.badgeLabel}</Badge>
                <Badge variant="info">If you only read one card, read this one</Badge>
              </div>
              <div>
                <div className={cn("text-xs uppercase tracking-[0.24em]", directive.kickerClass)}>What to do now</div>
                <h2 className="mt-3 max-w-4xl font-display text-4xl font-semibold tracking-tight sm:text-5xl">
                  {directive.title}
                </h2>
                <p className="mt-4 max-w-3xl text-base leading-7 text-slate-300">{directive.subtitle}</p>
              </div>

              <div className="grid gap-3 md:grid-cols-3">
                {directive.steps.map((step, index) => (
                  <div key={step} className={cn("rounded-[24px] border p-4 backdrop-blur", directive.stepClass)}>
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-400">Step {index + 1}</div>
                    <div className="mt-3 text-sm leading-6 text-slate-200">{step}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid gap-4">
              <div className={cn("rounded-[28px] border p-5 backdrop-blur", directive.panelClass)}>
                <div className="text-xs uppercase tracking-[0.16em] text-slate-400">Simple summary</div>
                <div className="mt-3 font-display text-3xl font-semibold">{directive.summaryLabel}</div>
                <div className="mt-2 text-sm leading-6 text-slate-300">{directive.summaryText}</div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className={cn("rounded-[24px] border p-4", directive.metricClass)}>
                  <div className={cn("text-xs uppercase tracking-[0.16em]", directive.metricLabelClass)}>Entry</div>
                  <div className="mt-3 text-2xl font-semibold">{formatCurrency(displayedEntry)}</div>
                </div>
                <div className={cn("rounded-[24px] border p-4", directive.metricClass)}>
                  <div className={cn("text-xs uppercase tracking-[0.16em]", directive.metricLabelClass)}>Confidence</div>
                  <div className="mt-3 text-2xl font-semibold">{formatPercent(tradeSetup.decision.confidence * 100)}</div>
                </div>
                <div className={cn("rounded-[24px] border p-4", directive.metricClass)}>
                  <div className={cn("text-xs uppercase tracking-[0.16em]", directive.metricLabelClass)}>Stop loss</div>
                  <div className="mt-3 text-2xl font-semibold">
                    {displayedStop != null ? formatCurrency(displayedStop) : "--"}
                  </div>
                </div>
                <div className={cn("rounded-[24px] border p-4", directive.metricClass)}>
                  <div className={cn("text-xs uppercase tracking-[0.16em]", directive.metricLabelClass)}>Take profit</div>
                  <div className="mt-3 text-2xl font-semibold">
                    {displayedTarget != null ? formatCurrency(displayedTarget) : "--"}
                  </div>
                </div>
              </div>

              <div className={cn("rounded-[24px] border p-4 text-sm leading-6 text-slate-300", directive.panelClass)}>
                {directive.whyLine}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section
        className={cn(
          "rounded-[32px] border border-border/70 bg-card/80 p-1 shadow-[0_22px_80px_rgba(15,23,42,0.14)]",
          highlightedTrade && "live-wire-border"
        )}
      >
        <div
          className={cn(
            "rounded-[30px] border border-transparent p-6",
            highlightedTrade
              ? "live-wire-shell"
              : "bg-[radial-gradient(circle_at_top_left,_rgba(8,145,178,0.08),_transparent_34%),linear-gradient(180deg,rgba(255,255,255,0.02),transparent)]"
          )}
        >
          <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
            <div className="space-y-5">
              <div className="flex flex-wrap items-center gap-3">
                <Badge variant={tradeSetup.execution_ready ? "success" : "warning"}>
                  {tradeSetup.execution_ready ? "Actionable setup" : "Review-only setup"}
                </Badge>
                <Badge variant="info">{titleCase(tradeSetup.requested_instrument)}</Badge>
                <Badge variant={tradeSetup.decision.action === "HOLD" ? "default" : "success"}>
                  {titleCase(tradeSetup.decision.action)}
                </Badge>
              </div>

              <div>
                <div className="text-xs uppercase tracking-[0.22em] text-primary">Detailed breakdown</div>
                <div className="mt-3 flex flex-wrap items-end gap-4">
                  <h2 className="font-display text-5xl font-semibold tracking-tight">{tradeSetup.trade_name}</h2>
                  <div className="pb-1 text-lg text-muted-foreground">
                    {titleCase(tradeSetup.decision.instrument_type)} | {titleCase(tradeSetup.decision.side)}
                  </div>
                </div>
                <p className="mt-3 max-w-3xl text-muted-foreground">{tradeSetup.analysis_note}</p>
              </div>

              <div className="grid gap-4 md:grid-cols-4">
                <MetricChip label="Entry" value={formatCurrency(displayedEntry)} />
                <MetricChip label="Stop loss" value={displayedStop != null ? formatCurrency(displayedStop) : "--"} />
                <MetricChip label="Take profit" value={displayedTarget != null ? formatCurrency(displayedTarget) : "--"} />
                <MetricChip label="Confidence" value={formatPercent(tradeSetup.decision.confidence * 100)} />
              </div>

              {optionPlan ? (
                <div className="rounded-3xl border border-border/70 bg-background/60 p-4">
                  <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Option trade plan</div>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <Badge variant="success">{optionPlan.option_side}</Badge>
                    {optionPlan.expiry_label ? <Badge variant="info">{optionPlan.expiry_label}</Badge> : null}
                    {optionPlan.strike_price != null ? <Badge variant="default">Strike {formatCurrency(optionPlan.strike_price)}</Badge> : null}
                    <Badge variant="default">Lot size {optionPlan.lot_size}</Badge>
                  </div>
                  <div className="mt-4 font-display text-3xl font-semibold tracking-tight">{optionPlan.contract_name}</div>
                  <div className="mt-2 text-sm text-muted-foreground">
                    Contract symbol {optionPlan.contract_symbol} | Pricing {titleCase(optionPlan.pricing_source.replaceAll("_", " "))}
                  </div>
                  <div className="mt-4 grid gap-4 md:grid-cols-5">
                    <MetricChip label="Premium entry" value={optionPlan.premium_entry != null ? formatCurrency(optionPlan.premium_entry) : "--"} />
                    <MetricChip label="Premium stop" value={optionPlan.premium_stop_loss != null ? formatCurrency(optionPlan.premium_stop_loss) : "--"} />
                    <MetricChip label="Premium exit" value={optionPlan.premium_take_profit != null ? formatCurrency(optionPlan.premium_take_profit) : "--"} />
                    <MetricChip label="Probable profit" value={optionPlan.probable_profit != null ? formatCurrency(optionPlan.probable_profit) : "--"} />
                    <MetricChip label="Probable loss" value={optionPlan.probable_loss != null ? formatCurrency(optionPlan.probable_loss) : "--"} />
                  </div>
                  <div className="mt-4 grid gap-4 md:grid-cols-3">
                    <MetricChip label="Underlying entry" value={optionPlan.underlying_entry != null ? formatCurrency(optionPlan.underlying_entry) : "--"} />
                    <MetricChip label="Underlying stop" value={optionPlan.underlying_stop_loss != null ? formatCurrency(optionPlan.underlying_stop_loss) : "--"} />
                    <MetricChip label="Underlying exit" value={optionPlan.underlying_take_profit != null ? formatCurrency(optionPlan.underlying_take_profit) : "--"} />
                  </div>
                </div>
              ) : null}

              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-3xl border border-border/70 bg-background/60 p-4">
                  <div className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-muted-foreground">
                    <Sparkles className="h-4 w-4" />
                    Rationale
                  </div>
                  <div className="mt-3 space-y-2 text-sm text-foreground/90">
                    {tradeSetup.decision.rationale_points.map((point) => (
                      <div key={point} className="rounded-2xl border border-border/60 bg-card/60 px-3 py-2">
                        {point}
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-3xl border border-border/70 bg-background/60 p-4">
                  <div className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-muted-foreground">
                    <ShieldCheck className="h-4 w-4" />
                    Execution posture
                  </div>
                  <div className="mt-3 text-sm text-muted-foreground">{tradeSetup.mode_note}</div>
                  <div className="mt-4 space-y-2">
                    {tradeSetup.execution_blockers.length ? (
                      tradeSetup.execution_blockers.map((blocker) => (
                        <div key={blocker} className="rounded-2xl border border-amber-500/20 bg-amber-500/8 px-3 py-2 text-sm text-amber-200 dark:text-amber-300">
                          {blocker}
                        </div>
                      ))
                    ) : (
                      <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/8 px-3 py-2 text-sm text-emerald-200 dark:text-emerald-300">
                        No strategy blocker is visible on this setup. Real execution would still need to clear the hard risk engine.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div className="grid gap-4">
              <div className="rounded-3xl border border-border/70 bg-background/55 p-4">
                <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Quote board</div>
                <div className="mt-3 font-display text-4xl font-semibold">{formatCurrency(tradeSetup.quote.ltp)}</div>
                <div className="mt-3 grid gap-3 text-sm text-muted-foreground sm:grid-cols-2">
                  <div>Bid {tradeSetup.quote.bid ? formatCurrency(tradeSetup.quote.bid) : "--"}</div>
                  <div>Ask {tradeSetup.quote.ask ? formatCurrency(tradeSetup.quote.ask) : "--"}</div>
                  <div>Spread {formatPercent(tradeSetup.quote.spread_pct)}</div>
                  <div>Volume {formatCompactNumber(tradeSetup.quote.volume)}</div>
                </div>
                <div className="mt-3 text-xs text-muted-foreground">{formatDateTime(tradeSetup.quote.timestamp)}</div>
              </div>

              <div className="rounded-3xl border border-border/70 bg-background/55 p-4">
                <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Market context</div>
                <div className="mt-3 text-2xl font-semibold">{tradeSetup.market_session.label}</div>
                <div className="mt-2 text-sm text-muted-foreground">{tradeSetup.market_session.note}</div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Badge variant="info">{titleCase(tradeSetup.features.market_regime)}</Badge>
                  <Badge variant={tradeSetup.news_summary.overall_sentiment >= 0 ? "success" : "danger"}>
                    Sentiment {tradeSetup.news_summary.overall_sentiment.toFixed(2)}
                  </Badge>
                  <Badge variant={tradeSetup.news_summary.technical_only ? "warning" : "success"}>
                    {tradeSetup.news_summary.technical_only ? "Technical-only" : "Live news"}
                  </Badge>
                  <Badge variant="default">
                    {tradeSetup.chart_interval} x {tradeSetup.chart_lookback}
                  </Badge>
                </div>
                {tradeSetup.news_summary.technical_only ? (
                  <div className="mt-4 rounded-2xl border border-amber-500/20 bg-amber-500/8 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
                    {tradeSetup.news_summary.technical_only_reason}
                  </div>
                ) : null}
              </div>

              <div className="rounded-3xl border border-border/70 bg-background/55 p-4">
                <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                  <Radar className="h-4 w-4" />
                  Signal stack
                </div>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <SignalTile label="Momentum" value={tradeSetup.features.momentum_score} />
                  <SignalTile label="Trend" value={tradeSetup.features.trend_score} />
                  <SignalTile label="RSI" value={tradeSetup.features.rsi} />
                  <SignalTile label="ATR" value={tradeSetup.features.atr} />
                  <SignalTile label="Vol spike" value={tradeSetup.features.volume_spike_score} />
                  <SignalTile label="Volatility" value={tradeSetup.features.volatility_score} />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4">
        <div>
          <div className="text-xs uppercase tracking-[0.18em] text-primary">Chart guide</div>
          <h2 className="mt-2 font-display text-2xl font-semibold tracking-tight">How to read the charts below</h2>
          <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
            You do not need to be a market expert here. When news is unavailable, this board leans on the same kind of historical price and momentum studies many systematic traders watch first.
          </p>
        </div>
        {tradeSetup.news_summary.technical_only ? (
          <div className="rounded-3xl border border-amber-500/20 bg-amber-500/8 p-5 text-sm text-amber-700 dark:text-amber-300">
            {tradeSetup.news_summary.technical_only_reason} The setup is now being ranked from historical candles, moving averages, Bollinger bands, RSI, MACD, ATR, and volume participation.
          </div>
        ) : null}
        <div className="grid gap-4 lg:grid-cols-4">
          <ChartGuideCard
            title="Price envelope"
            whatYouSee="Price line sits inside Bollinger bands with fast and slow trend guides."
            whatItMeans="Price pressing the upper band with rising trend lines suggests strength. Rejection from the band can mean exhaustion."
            whatToDo="Use this chart to judge whether the move is expanding cleanly or stretching too far too fast."
          />
          <ChartGuideCard
            title="Volume chart"
            whatYouSee="Taller bars mean more people are trading that symbol at that moment."
            whatItMeans="A move with strong volume is more believable. A move with very weak volume can fade quickly."
            whatToDo="If price jumps but volume stays tiny, be cautious. If both rise together, the move has better backing."
          />
          <ChartGuideCard
            title="RSI rhythm"
            whatYouSee="RSI oscillates between 0 and 100 with 30 and 70 acting as common stress zones."
            whatItMeans="Above 70 can mean strong momentum or short-term overheating. Below 30 can mean panic or oversold pressure."
            whatToDo="Use RSI as a momentum thermometer, not a standalone buy or sell button."
          />
          <ChartGuideCard
            title="MACD pulse"
            whatYouSee="Two momentum lines and a histogram that flips above or below zero."
            whatItMeans="When MACD stays above the signal line and the histogram improves, momentum is strengthening. The opposite warns of fade."
            whatToDo="Look for the action card, price structure, and MACD to point the same way before trusting a setup."
          />
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <ChartCard
          title="Historical price structure"
          description={`Price, Bollinger envelope, and moving averages across the ${tradeSetup.chart_interval} window.`}
        >
          <ChartContainer className="h-[320px]">
            {({ width, height }) => (
              <LineChart width={width} height={height} data={chartData}>
                <CartesianGrid strokeDasharray="4 4" opacity={0.18} />
                <XAxis dataKey="label" tickLine={false} axisLine={false} minTickGap={24} />
                <YAxis tickLine={false} axisLine={false} domain={["auto", "auto"]} />
                <Tooltip />
                <Line type="monotone" dataKey="bollinger_upper" stroke="#94a3b8" strokeWidth={1.5} dot={false} strokeDasharray="6 6" />
                <Line type="monotone" dataKey="bollinger_mid" stroke="#f97316" strokeWidth={1.8} dot={false} />
                <Line type="monotone" dataKey="bollinger_lower" stroke="#94a3b8" strokeWidth={1.5} dot={false} strokeDasharray="6 6" />
                <Line type="monotone" dataKey="close" stroke="#22d3ee" strokeWidth={2.6} dot={false} />
                <Line type="monotone" dataKey="fast_ma" stroke="#f97316" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="slow_ma" stroke="#a78bfa" strokeWidth={2} dot={false} />
              </LineChart>
            )}
          </ChartContainer>
        </ChartCard>

        <ChartCard title="Volume pulse" description="Taller bars mean more participation. Big moves with stronger volume are usually more trustworthy.">
          <div className="space-y-4">
            <div className="rounded-2xl border border-border/70 bg-background/50 p-4 text-sm text-muted-foreground">
              Read this chart like a confidence meter: rising price with rising bars is healthier than rising price with weak bars.
            </div>
            <ChartContainer className="h-[272px]">
              {({ width, height }) => (
                <BarChart width={width} height={height} data={chartData}>
                <CartesianGrid strokeDasharray="4 4" opacity={0.18} />
                <XAxis dataKey="label" tickLine={false} axisLine={false} minTickGap={24} />
                <YAxis tickLine={false} axisLine={false} />
                <Tooltip />
                <Bar dataKey="volume" fill="#14b8a6" radius={[8, 8, 0, 0]} />
              </BarChart>
              )}
            </ChartContainer>
          </div>
        </ChartCard>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <ChartCard title="RSI oscillator" description="Momentum oscillator with 30 and 70 reference levels used by many discretionary and systematic traders.">
          <ChartContainer className="h-[280px]">
            {({ width, height }) => (
              <LineChart width={width} height={height} data={chartData}>
                <CartesianGrid strokeDasharray="4 4" opacity={0.18} />
                <XAxis dataKey="label" tickLine={false} axisLine={false} minTickGap={24} />
                <YAxis tickLine={false} axisLine={false} domain={[0, 100]} />
                <Tooltip />
                <ReferenceLine y={70} stroke="#fb7185" strokeDasharray="4 4" />
                <ReferenceLine y={30} stroke="#22c55e" strokeDasharray="4 4" />
                <ReferenceLine y={50} stroke="#64748b" strokeDasharray="4 4" />
                <Line type="monotone" dataKey="rsi_line" stroke="#22d3ee" strokeWidth={2.4} dot={false} />
              </LineChart>
            )}
          </ChartContainer>
        </ChartCard>

        <ChartCard title="MACD pulse" description="Histogram plus MACD and signal lines to judge whether directional momentum is accelerating or fading.">
          <ChartContainer className="h-[280px]">
            {({ width, height }) => (
              <ComposedChart width={width} height={height} data={chartData}>
                <CartesianGrid strokeDasharray="4 4" opacity={0.18} />
                <XAxis dataKey="label" tickLine={false} axisLine={false} minTickGap={24} />
                <YAxis tickLine={false} axisLine={false} />
                <Tooltip />
                <ReferenceLine y={0} stroke="#64748b" strokeDasharray="4 4" />
                <Bar dataKey="macd_histogram" fill="#14b8a6" radius={[4, 4, 0, 0]} />
                <Line type="monotone" dataKey="macd_line" stroke="#22d3ee" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="macd_signal" stroke="#f97316" strokeWidth={2} dot={false} />
              </ComposedChart>
            )}
          </ChartContainer>
        </ChartCard>
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <ChartCard title="Candidate ladder" description="The board ranks candidates before the final decision is shaped.">
          <div className="space-y-3">
            {tradeSetup.candidates.map((candidate) => (
              <div key={`${candidate.symbol}-${candidate.action}-${candidate.instrument_type}`} className="rounded-2xl border border-border/70 bg-background/55 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="font-semibold">
                      {candidate.symbol} | {titleCase(candidate.action)}
                    </div>
                    <div className="mt-1 text-sm text-muted-foreground">
                      {titleCase(candidate.instrument_type)} | {titleCase(candidate.side)} | {candidate.entry_type}
                    </div>
                  </div>
                  <Badge variant={candidate.score >= 0.7 ? "success" : candidate.score >= 0.45 ? "info" : "warning"}>
                    Score {candidate.score.toFixed(2)}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </ChartCard>

        <ChartCard
          title="Symbol-specific catalysts"
          description={
            tradeSetup.news_summary.technical_only
              ? "No usable live headlines are steering the setup, so this panel explains why the board switched to technical-only mode."
              : "Latest relevant headlines that influenced the setup scoring."
          }
        >
          <div className="space-y-3">
            {tradeSetup.news_summary.items.length ? (
              tradeSetup.news_summary.items.slice(0, 5).map((item) => (
                <a
                  key={item.url}
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block rounded-2xl border border-border/70 bg-background/55 p-4 transition-colors hover:border-primary/35 hover:bg-muted/30"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    {item.symbols.map((symbol) => (
                      <Badge key={symbol} variant="info">
                        {symbol}
                      </Badge>
                    ))}
                    <Badge variant={item.sentiment_score >= 0 ? "success" : "danger"}>
                      Sentiment {item.sentiment_score.toFixed(2)}
                    </Badge>
                  </div>
                  <div className="mt-3 font-medium">{item.title}</div>
                  <div className="mt-2 text-sm text-muted-foreground">{item.description}</div>
                  <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
                    <Newspaper className="h-3.5 w-3.5" />
                    <span>
                      {item.source} | {formatDateTime(item.published_at)}
                    </span>
                  </div>
                </a>
              ))
            ) : (
              <div className="rounded-2xl border border-dashed border-border p-5 text-sm text-muted-foreground">
                {tradeSetup.news_summary.technical_only_reason ??
                  "No recent relevant headlines were returned for this symbol, so the setup is leaning primarily on price structure and regime analysis."}
              </div>
            )}
          </div>
        </ChartCard>
      </section>

      <section className="space-y-4">
        <div>
          <div className="text-xs uppercase tracking-[0.18em] text-primary">Broader tape</div>
          <h2 className="mt-2 font-display text-2xl font-semibold tracking-tight">Watchlist-level market context</h2>
        </div>
        <NewsPanel summary={marketSummary} onRefresh={() => void refreshNewsManually()} refreshing={isRefreshingNews} />
      </section>
    </div>
  );
}

function buildActionDirective(tradeSetup: TradeSetup) {
  const action = tradeSetup.decision.action;
  const symbol = tradeSetup.symbol;
  const requestedLane = titleCase(tradeSetup.requested_instrument).toLowerCase();
  const optionPlan = tradeSetup.option_contract;
  const tradeName = optionPlan?.contract_name ?? tradeSetup.trade_name ?? symbol;
  const entry = formatCurrency(optionPlan?.premium_entry ?? tradeSetup.decision.entry_price_hint ?? tradeSetup.quote.ltp);
  const stop = optionPlan?.premium_stop_loss != null
    ? formatCurrency(optionPlan.premium_stop_loss)
    : tradeSetup.decision.stop_loss != null
      ? formatCurrency(tradeSetup.decision.stop_loss)
      : "not set";
  const target = optionPlan?.premium_take_profit != null
    ? formatCurrency(optionPlan.premium_take_profit)
    : tradeSetup.decision.take_profit != null
      ? formatCurrency(tradeSetup.decision.take_profit)
      : "not set";
  const analysisFlavor = tradeSetup.news_summary.technical_only
    ? "This call is being made from price history and technical indicators because live news is unavailable."
    : "This call blends technical structure with live headline context.";
  const firstBlocker = tradeSetup.execution_blockers[0];
  const firstReason =
    tradeSetup.decision.rationale_points[0] ??
    firstBlocker ??
    "The board does not see enough evidence yet.";
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
      badgeLabel: "WAIT",
      badgeVariant: "warning" as const,
      title: `WAIT. Do not trade ${symbol} ${requestedLane} right now.`,
      subtitle:
        `Stand aside. This setup does not clear the entry threshold. ${analysisFlavor}`,
      steps: [
        `Do nothing in ${symbol} right now.`,
        "Keep capital free for a cleaner setup.",
        "Re-check only after a clean breakout, breakdown, or clear volume expansion."
      ],
      summaryLabel: "WAIT",
      summaryText:
        "No entry. No chase. Preserve capital until the edge becomes clear.",
      whyLine: `Stand-aside reason: ${firstBlocker ?? firstReason}`,
      kickerClass: "text-amber-200/90",
      stepClass: "border-amber-300/15 bg-amber-300/6",
      panelClass: "border-amber-300/15 bg-amber-300/6",
      metricClass: "border-amber-300/15 bg-amber-300/8",
      metricLabelClass: "text-amber-200"
    };
  }

  if (!tradeSetup.execution_ready && firstBlocker) {
    return {
      ...directionalTheme,
      badgeLabel: "Watch only",
      badgeVariant: "info" as const,
      title: `This ${requestedLane} setup looks interesting, but do not place it yet.`,
      subtitle:
        `The analysis sees an opportunity, but your current settings or safeguards still block execution. Treat this as research, not an order. ${analysisFlavor}`,
      steps: [
        optionPlan ? `Watch ${tradeName} near premium ${entry} instead of placing it immediately.` : `Watch ${symbol} near ${entry} instead of placing the trade immediately.`,
        `If you decide to allow it later, keep the stop near ${stop}.`,
        `If price reaches ${target}, that is the planned profit zone for this idea.`
      ],
      summaryLabel: optionPlan ? tradeName : titleCase(action),
      summaryText: "Potential setup found, but the app is still telling you to hold off on acting.",
      whyLine: `Why the app is holding you back: ${firstBlocker}`
    };
  }

  return {
    ...directionalTheme,
    badgeLabel: "Action",
    badgeVariant: "success" as const,
    title: buildActionTitle(action, symbol, requestedLane, entry, tradeName),
    subtitle:
      `This is the clearest idea on the board right now. The trade is still not guaranteed to work, but this is the action the app wants you to focus on first. ${analysisFlavor}`,
    steps: [
      optionPlan ? `Enter ${tradeName} near premium ${entry}.` : `Enter near ${entry}.`,
      `Keep the stop loss near ${stop}.`,
      `Start taking profit near ${target}.`
    ],
    summaryLabel: optionPlan ? tradeName : titleCase(action),
    summaryText: optionPlan
      ? `This is the current best ${optionPlan.option_side.toLowerCase()} expression for ${symbol}.`
      : `This is the current best move for ${symbol} in the ${requestedLane} lane.`,
    whyLine: `Why the app likes this trade: ${firstReason}`
  };
}

function buildActionTitle(action: string, symbol: string, requestedLane: string, entry: string, tradeName: string) {
  switch (action) {
    case "BUY_STOCK":
      return `Buy ${symbol} stock near ${entry}.`;
    case "SELL_STOCK":
      return `Consider a short stock trade in ${symbol} near ${entry}.`;
    case "BUY_CALL":
      return `Buy ${tradeName} near ${entry}.`;
    case "BUY_PUT":
      return `Buy ${tradeName} near ${entry}.`;
    case "BUY_FUTURE":
      return `Consider a futures buy on ${symbol} near ${entry}.`;
    case "SELL_FUTURE":
      return `Consider a futures sell on ${symbol} near ${entry}.`;
    case "EXIT":
      return `Exit ${symbol} now to protect capital.`;
    case "REDUCE":
      return `Reduce your ${symbol} position now.`;
    default:
      return `Focus on the ${requestedLane} setup in ${symbol} near ${entry}.`;
  }
}

function uniqueSymbols(strategy: StrategyConfig | null) {
  const values = strategy?.watchlist_symbols_json?.length
    ? strategy.watchlist_symbols_json
    : strategy?.allowed_instruments_json?.symbols ?? [];
  return Array.from(new Set(values.map((value) => value.trim().toUpperCase()).filter(Boolean)));
}

function MetricChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-border/70 bg-background/55 p-4">
      <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{label}</div>
      <div className="mt-2 text-xl font-semibold">{value}</div>
    </div>
  );
}

function ChartGuideCard({
  title,
  whatYouSee,
  whatItMeans,
  whatToDo
}: {
  title: string;
  whatYouSee: string;
  whatItMeans: string;
  whatToDo: string;
}) {
  return (
    <div className="rounded-3xl border border-border/70 bg-card/75 p-5 shadow-[0_16px_50px_rgba(15,23,42,0.08)]">
      <div className="text-xs uppercase tracking-[0.16em] text-primary">{title}</div>
      <div className="mt-4 space-y-3 text-sm leading-6 text-muted-foreground">
        <div>
          <span className="font-semibold text-foreground">What you see: </span>
          {whatYouSee}
        </div>
        <div>
          <span className="font-semibold text-foreground">What it means: </span>
          {whatItMeans}
        </div>
        <div>
          <span className="font-semibold text-foreground">What to do: </span>
          {whatToDo}
        </div>
      </div>
    </div>
  );
}

function SignalTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-border/70 bg-card/70 p-3">
      <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{label}</div>
      <div className="mt-2 flex items-center gap-2 text-lg font-semibold">
        <TrendingUp className="h-4 w-4 text-primary" />
        {value.toFixed(2)}
      </div>
    </div>
  );
}

function formatCompactNumber(value: number | null | undefined) {
  if (value == null) return "--";
  return new Intl.NumberFormat("en-IN", {
    notation: "compact",
    maximumFractionDigits: 1
  }).format(value);
}

function buildTradeGateMessage(config: ConfigResponse) {
  const missing = config.api_credentials
    .filter((credential) => credential.required_for_trade_fetch && !credential.configured)
    .map((credential) => credential.label);
  if (!missing.length) return null;
  return `Before fetching trades, add these keys in Strategy -> API keys: ${missing.join(", ")}.`;
}

function buildTechnicalChartData(tradeSetup: TradeSetup) {
  const closes = tradeSetup.chart_points.map((point) => point.close);
  const labels = tradeSetup.chart_points.map((point) =>
    tradeSetup.chart_interval === "1d"
      ? new Intl.DateTimeFormat("en-IN", { month: "short", day: "numeric", timeZone: "Asia/Kolkata" }).format(
          new Date(point.timestamp)
        )
      : new Intl.DateTimeFormat("en-IN", {
          hour: "numeric",
          minute: "2-digit",
          timeZone: "Asia/Kolkata"
        }).format(new Date(point.timestamp))
  );
  const bollinger = closes.map((_, index) => computeBollinger(closes.slice(0, index + 1)));
  const rsiSeries = computeRsiSeries(closes, 14);
  const macdSeries = computeMacdSeries(closes);

  return tradeSetup.chart_points.map((point, index) => ({
    ...point,
    label: labels[index],
    bollinger_upper: roundOrNull(bollinger[index].upper),
    bollinger_mid: roundOrNull(bollinger[index].middle),
    bollinger_lower: roundOrNull(bollinger[index].lower),
    rsi_line: roundOrNull(rsiSeries[index]),
    macd_line: roundOrNull(macdSeries[index].macd),
    macd_signal: roundOrNull(macdSeries[index].signal),
    macd_histogram: roundOrNull(macdSeries[index].histogram)
  }));
}

function computeBollinger(values: number[], window = 20) {
  const segment = values.slice(-window);
  if (!segment.length) return { upper: null, middle: null, lower: null };
  const middle = average(segment);
  const variance = segment.reduce((total, value) => total + (value - middle) ** 2, 0) / segment.length;
  const stdDev = Math.sqrt(variance);
  return {
    upper: middle + stdDev * 2,
    middle,
    lower: middle - stdDev * 2
  };
}

function computeRsiSeries(values: number[], period: number) {
  return values.map((_, index) => {
    if (index < 1) return 50;
    const segment = values.slice(0, index + 1);
    if (segment.length <= period) return 50;
    const gains: number[] = [];
    const losses: number[] = [];
    for (let cursor = 1; cursor < segment.length; cursor += 1) {
      const delta = segment[cursor] - segment[cursor - 1];
      gains.push(Math.max(delta, 0));
      losses.push(Math.max(-delta, 0));
    }
    const avgGain = average(gains.slice(-period));
    const avgLoss = average(losses.slice(-period));
    if (avgLoss === 0) return 100;
    const rs = avgGain / avgLoss;
    return 100 - 100 / (1 + rs);
  });
}

function computeMacdSeries(values: number[]) {
  const ema12 = computeEma(values, 12);
  const ema26 = computeEma(values, 26);
  const macdLine = values.map((_, index) => ema12[index] - ema26[index]);
  const signalLine = computeEma(macdLine, 9);

  return macdLine.map((macd, index) => ({
    macd,
    signal: signalLine[index],
    histogram: macd - signalLine[index]
  }));
}

function computeEma(values: number[], period: number) {
  if (!values.length) return [];
  const multiplier = 2 / (period + 1);
  const ema: number[] = [values[0]];
  for (let index = 1; index < values.length; index += 1) {
    ema.push(values[index] * multiplier + ema[index - 1] * (1 - multiplier));
  }
  return ema;
}

function average(values: number[]) {
  if (!values.length) return 0;
  return values.reduce((total, value) => total + value, 0) / values.length;
}

function roundOrNull(value: number | null) {
  if (value == null || Number.isNaN(value)) return null;
  return Number(value.toFixed(2));
}
