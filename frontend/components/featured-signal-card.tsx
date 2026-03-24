"use client";

import { ActivitySquare, ArrowRight, Orbit, Radar, Sparkles, Target } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";
import { formatCurrency, formatDateTime, formatPercent, titleCase } from "@/lib/format";
import type { HotDeal, MarketSession } from "@/types/api";

function actionVariant(action: string) {
  if (action.startsWith("BUY")) return "success" as const;
  if (action.startsWith("SELL") || action === "EXIT" || action === "REDUCE") return "danger" as const;
  return "warning" as const;
}

function computeRiskReward(deal: HotDeal) {
  if (!deal.stop_loss_hint || !deal.take_profit_hint) return null;
  const risk = Math.abs(deal.ltp - deal.stop_loss_hint);
  const reward = Math.abs(deal.take_profit_hint - deal.ltp);
  if (risk <= 0) return null;
  return reward / risk;
}

function sourceLabel(source?: string) {
  if (!source) return "Synced portfolio";
  if (source.startsWith("live:indmoney")) return "Live INDstocks feed";
  if (source.startsWith("live:groww")) return "Live Groww feed";
  if (source.startsWith("live:")) return "Live broker feed";
  return titleCase(source.replace(":", " "));
}

export function FeaturedSignalCard({
  deal,
  session,
  source
}: {
  deal: HotDeal | null;
  session: MarketSession;
  source?: string;
}) {
  if (!deal) {
    return (
      <section className="rounded-[32px] border border-border/70 bg-card/80 p-6 shadow-card backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <div className="text-xs uppercase tracking-[0.24em] text-primary">Featured setup</div>
            <h1 className="mt-3 font-display text-4xl font-semibold tracking-tight">No standout signal yet</h1>
            <p className="mt-3 max-w-2xl text-sm text-muted-foreground">
              The board is live, but nothing has earned a high-conviction slot at the top. That is a valid state. Preserving capital
              beats forcing a trade.
            </p>
          </div>
          <div className="rounded-3xl border border-border/70 bg-background/70 px-4 py-3 text-sm text-muted-foreground">
            <div className="font-medium text-foreground">{session.label}</div>
            <div className="mt-1">{session.note}</div>
          </div>
        </div>
      </section>
    );
  }

  const liveWire = deal.score >= 0.78 && deal.conviction === "High";
  const riskReward = computeRiskReward(deal);

  return (
    <section className={cn("rounded-[34px] p-[1px] shadow-[0_28px_90px_rgba(15,23,42,0.22)]", liveWire && "live-wire-border")}>
      <div
        className={cn(
          "rounded-[33px] border border-border/60 bg-[radial-gradient(circle_at_top_left,_rgba(8,145,178,0.12),_transparent_34%),linear-gradient(145deg,rgba(15,23,42,0.9),rgba(15,23,42,0.74))] p-6 text-white",
          liveWire && "live-wire-shell border-transparent"
        )}
      >
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="max-w-3xl">
            <div className="flex flex-wrap items-center gap-2">
              <div className="text-xs uppercase tracking-[0.28em] text-cyan-200/90">Featured setup</div>
              <Badge variant={liveWire ? "success" : "info"}>{liveWire ? "Live wire" : "On radar"}</Badge>
              <Badge variant={actionVariant(deal.action)}>{titleCase(deal.action)}</Badge>
            </div>
            <h1 className="mt-4 font-display text-4xl font-semibold tracking-tight sm:text-5xl">
              {deal.symbol} <span className="text-cyan-200">{titleCase(deal.instrument_type)}</span>
            </h1>
            <p className="mt-4 max-w-2xl text-sm leading-6 text-slate-300">
              This is the strongest setup on the board right now because price structure, momentum, and live news tone are aligned. It is
              highlighted for conviction, not because profit is guaranteed.
            </p>
          </div>

          <div className="rounded-[28px] border border-white/10 bg-white/5 px-4 py-4 text-sm text-slate-300 backdrop-blur">
            <div className="text-xs uppercase tracking-[0.18em] text-slate-400">Signal source</div>
            <div className="mt-2 font-medium text-white">{sourceLabel(source)}</div>
            <div className="mt-3 text-xs uppercase tracking-[0.18em] text-slate-400">Market window</div>
            <div className="mt-2 font-medium text-white">{session.label}</div>
            <div className="mt-1 text-slate-400">{formatDateTime(session.local_time)}</div>
          </div>
        </div>

        <div className="mt-8 grid gap-5 xl:grid-cols-[1.05fr_0.95fr]">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-[28px] border border-white/10 bg-white/5 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.18em] text-slate-400">Spotlight price</div>
              <div className="mt-3 font-display text-4xl font-semibold">{formatCurrency(deal.ltp)}</div>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-slate-300">
                <Badge variant="info">{titleCase(deal.market_regime)}</Badge>
                <span>{titleCase(deal.side)}</span>
              </div>
            </div>

            <div className="rounded-[28px] border border-white/10 bg-white/5 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.18em] text-slate-400">Conviction stack</div>
              <div className="mt-3 flex items-center gap-2 text-3xl font-semibold">
                <Sparkles className="h-5 w-5 text-cyan-300" />
                {deal.conviction}
              </div>
              <div className="mt-3 text-sm text-slate-300">Signal score {formatPercent(deal.score * 100)}</div>
              <div className="mt-2 text-sm text-slate-400">
                {riskReward ? `Reward to risk ${riskReward.toFixed(2)}x` : "Protective levels are mapped below."}
              </div>
            </div>

            <div className="rounded-[24px] border border-cyan-400/20 bg-cyan-400/5 p-4">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-cyan-200">
                <Radar className="h-4 w-4" />
                Momentum
              </div>
              <div className="mt-3 text-2xl font-semibold">{formatPercent(deal.momentum_score)}</div>
            </div>

            <div className="rounded-[24px] border border-emerald-400/20 bg-emerald-400/5 p-4">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-emerald-200">
                <ActivitySquare className="h-4 w-4" />
                Trend
              </div>
              <div className="mt-3 text-2xl font-semibold">{formatPercent(deal.trend_score)}</div>
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-[28px] border border-white/10 bg-white/5 p-5 backdrop-blur">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-slate-400">
                <Orbit className="h-4 w-4" />
                Why it is on top
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-300">{deal.setup_note}</p>
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <div className="rounded-2xl border border-white/10 px-3 py-3">
                  <div className="text-xs uppercase tracking-[0.16em] text-slate-400">RSI</div>
                  <div className="mt-2 font-semibold text-white">{deal.rsi.toFixed(1)}</div>
                </div>
                <div className="rounded-2xl border border-white/10 px-3 py-3">
                  <div className="text-xs uppercase tracking-[0.16em] text-slate-400">Sentiment</div>
                  <div className="mt-2 font-semibold text-white">{deal.sentiment_score.toFixed(2)}</div>
                </div>
                <div className="rounded-2xl border border-white/10 px-3 py-3">
                  <div className="text-xs uppercase tracking-[0.16em] text-slate-400">Window</div>
                  <div className="mt-2 font-semibold text-white">{deal.opportunity_window}</div>
                </div>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-[24px] border border-rose-400/20 bg-rose-400/5 p-4">
                <div className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-rose-200">
                  <Target className="h-4 w-4" />
                  Stop hint
                </div>
                <div className="mt-3 text-2xl font-semibold">{formatCurrency(deal.stop_loss_hint)}</div>
              </div>
              <div className="rounded-[24px] border border-sky-400/20 bg-sky-400/5 p-4">
                <div className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-sky-200">
                  <ArrowRight className="h-4 w-4" />
                  Target hint
                </div>
                <div className="mt-3 text-2xl font-semibold">{formatCurrency(deal.take_profit_hint)}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
