"use client";

import { RefreshCw, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { formatCurrency, formatDateTime, formatPercent, titleCase } from "@/lib/format";
import type { DailyTopDealsResponse } from "@/types/api";

function actionTone(action: string) {
  if (action.startsWith("BUY")) return "emerald";
  if (action.startsWith("SELL") || action === "EXIT" || action === "REDUCE") return "rose";
  return "amber";
}

function tradeLabel(item: DailyTopDealsResponse["items"][number]) {
  if (item.instrument === "option" && item.setup.option_contract) {
    return item.setup.option_contract.contract_name;
  }
  return item.setup.trade_name;
}

export function DailyTopDealsPanel({
  data,
  loading,
  error,
  onTrigger,
  disabled,
  gateMessage,
}: {
  data: DailyTopDealsResponse | null;
  loading: boolean;
  error: string | null;
  onTrigger: () => void;
  disabled: boolean;
  gateMessage: string | null;
}) {
  const hasItems = Boolean(data?.items.length);

  return (
    <section className="rounded-[32px] border border-border/70 bg-card/85 p-6 shadow-[0_24px_80px_rgba(15,23,42,0.12)] backdrop-blur">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <div className="text-xs uppercase tracking-[0.24em] text-primary">Top 5 deals today</div>
          <h2 className="mt-3 font-display text-4xl font-semibold tracking-tight">
            One sweep, five strongest stocks to buy today
          </h2>
          <p className="mt-3 text-sm text-muted-foreground">Full-NSE sweep. Stored once for the day.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {data?.scan_scope.map((scope) => (
            <Badge key={scope} variant="info">
              {titleCase(scope)}
            </Badge>
          ))}
          <Badge variant={data?.can_trigger ? "warning" : "success"}>
            {data?.can_trigger ? "Not run yet today" : "Locked for today"}
          </Badge>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Button
          type="button"
          size="lg"
          className="gap-2 rounded-2xl"
          disabled={disabled || loading || !data?.can_trigger}
          onClick={onTrigger}
        >
          {loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {loading ? "Scanning today's top 5..." : "Run today's top 5 sweep"}
        </Button>
        <div className="text-sm text-muted-foreground">
          {data?.triggered_at
            ? `Last sweep: ${formatDateTime(data.triggered_at)}`
            : `Locked after one run until ${data ? formatDateTime(data.next_trigger_at) : "tomorrow"}.`}
        </div>
      </div>

      {gateMessage ? (
        <div className="mt-4 rounded-2xl border border-amber-500/25 bg-amber-500/8 px-4 py-3 text-sm text-amber-200">
          {gateMessage}
        </div>
      ) : null}

      {error ? (
        <div className="mt-4 rounded-2xl border border-rose-500/25 bg-rose-500/8 px-4 py-3 text-sm text-rose-300">
          {error}
        </div>
      ) : null}

      <div className="mt-4 rounded-2xl border border-border/70 bg-background/45 px-4 py-3 text-sm text-muted-foreground">
        {data?.message}
        {data?.items.length ? ` ${data.actionable_count} stock buys made the board.` : ""}
      </div>

      {data ? (
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <Metric label="Universe" value={data.universe_label} />
          <Metric label="Universe size" value={String(data.universe_size)} />
          <Metric label="Deep scan size" value={String(data.deep_scan_size)} />
        </div>
      ) : null}

      {hasItems ? (
        <div className="mt-6 grid gap-4 xl:grid-cols-2">
          {data!.items.map((item) => {
            const tone = actionTone(item.setup.decision.action);
            const isOption = item.instrument === "option" && item.setup.option_contract;
            const entry = isOption ? item.setup.option_contract?.premium_entry : item.setup.decision.entry_price_hint ?? item.setup.quote.ltp;
            const stop = isOption ? item.setup.option_contract?.premium_stop_loss : item.setup.decision.stop_loss;
            const target = isOption ? item.setup.option_contract?.premium_take_profit : item.setup.decision.take_profit;
            return (
              <article
                key={`${item.rank}-${item.instrument}-${item.setup.symbol}`}
                className={cn(
                  "rounded-[28px] border p-5",
                  tone === "emerald" && "border-emerald-500/25 bg-emerald-500/5",
                  tone === "rose" && "border-rose-500/25 bg-rose-500/5",
                  tone === "amber" && "border-amber-500/25 bg-amber-500/5"
                )}
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="info">#{item.rank}</Badge>
                    <Badge variant={item.actionable ? "success" : "warning"}>{titleCase(item.setup.decision.action)}</Badge>
                    <Badge variant="info">{titleCase(item.instrument)}</Badge>
                  </div>
                  <div className="text-sm text-muted-foreground">Score {item.ranking_score.toFixed(2)}</div>
                </div>

                <div className="mt-4">
                  <div className="font-display text-2xl font-semibold">{tradeLabel(item)}</div>
                  <div className="mt-1 text-sm text-muted-foreground">{item.setup.symbol}</div>
                </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-3">
                  <Metric label="Entry" value={entry != null ? formatCurrency(entry) : "--"} />
                  <Metric label="Stop" value={stop != null ? formatCurrency(stop) : "--"} />
                  <Metric label="Target" value={target != null ? formatCurrency(target) : "--"} />
                </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <Metric label="Confidence" value={formatPercent(item.setup.decision.confidence * 100)} />
                  <Metric
                    label="Quote"
                    value={formatCurrency(item.setup.quote.ltp)}
                  />
                </div>

                {isOption ? (
                  <div className="mt-4 rounded-2xl border border-border/70 bg-background/50 px-4 py-3 text-sm text-muted-foreground">
                    {item.setup.option_contract?.option_side} | Strike {item.setup.option_contract?.strike_price ?? "--"} | Expiry{" "}
                    {item.setup.option_contract?.expiry_label ?? "--"}
                  </div>
                ) : null}

                <div className="mt-4 text-sm leading-6 text-muted-foreground">
                  {item.setup.decision.rationale_points[0] ?? item.setup.analysis_note}
                </div>

                {item.setup.execution_blockers.length ? (
                  <div className="mt-4 rounded-2xl border border-border/70 bg-background/50 px-4 py-3 text-sm text-muted-foreground">
                    {item.setup.execution_blockers[0]}
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : (
        <div className="mt-6 rounded-3xl border border-dashed border-border p-5 text-sm text-muted-foreground">
          Run the once-a-day sweep to store today&apos;s stock-buy board.
        </div>
      )}

      {data?.scan_notes.length ? (
        <div className="mt-6 rounded-3xl border border-border/70 bg-background/40 p-4">
          <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Scan notes</div>
          <div className="mt-3 grid gap-2 text-sm text-muted-foreground">
            {data.scan_notes.slice(0, 5).map((note) => (
              <div key={note}>{note}</div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-border/70 bg-background/45 px-4 py-3">
      <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{label}</div>
      <div className="mt-2 text-lg font-semibold text-foreground">{value}</div>
    </div>
  );
}
