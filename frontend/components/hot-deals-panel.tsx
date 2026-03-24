"use client";

import { Flame, Radar } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency, formatPercent, titleCase } from "@/lib/format";
import type { HotDeal, MarketSession } from "@/types/api";

function actionVariant(action: string) {
  if (action.startsWith("BUY")) return "success" as const;
  if (action.startsWith("SELL") || action === "EXIT" || action === "REDUCE") return "danger" as const;
  return "warning" as const;
}

export function HotDealsPanel({
  deals,
  session,
  featuredShown = false
}: {
  deals: HotDeal[];
  session: MarketSession;
  featuredShown?: boolean;
}) {
  return (
    <section className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="text-xs uppercase tracking-[0.22em] text-primary">Today&apos;s hot deals</div>
          <h2 className="mt-2 font-display text-2xl font-semibold">Best setups for the current India market window</h2>
          <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
            Ranked from live broker data, technical posture, and current news tone when available. If news drops out, the board falls back to technical-only ranking instead of fake headlines.
          </p>
        </div>
        <div className="rounded-2xl border border-border/70 bg-card/70 px-4 py-3 text-sm text-muted-foreground">
          <div className="font-medium text-foreground">{session.label}</div>
          <div className="mt-1 max-w-md">{session.note}</div>
        </div>
      </div>

      {deals.length ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {deals.map((deal) => (
            <Card key={`${deal.symbol}-${deal.action}`} className="overflow-hidden border-border/70 bg-card/90">
              <CardHeader className="space-y-4 pb-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">{deal.opportunity_window}</div>
                    <CardTitle className="mt-2 flex items-center gap-3 text-2xl">
                      <span>{deal.symbol}</span>
                      <Badge variant={actionVariant(deal.action)}>{titleCase(deal.action)}</Badge>
                    </CardTitle>
                  </div>
                  <div className="text-right">
                    <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Conviction</div>
                    <div className="mt-2 flex items-center justify-end gap-2 text-lg font-semibold">
                      <Flame className="h-4 w-4 text-primary" />
                      {deal.conviction}
                    </div>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="info">{titleCase(deal.market_regime)}</Badge>
                  <Badge variant="default">{titleCase(deal.instrument_type)}</Badge>
                  <Badge variant="default">{deal.side}</Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="rounded-2xl bg-muted/40 p-4">
                    <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Last traded price</div>
                    <div className="mt-2 font-display text-3xl font-semibold">{formatCurrency(deal.ltp)}</div>
                    <div className="mt-2 text-sm text-muted-foreground">Score {formatPercent(deal.score * 100)}</div>
                  </div>
                  <div className="rounded-2xl border border-border/70 p-4">
                    <div className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-muted-foreground">
                      <Radar className="h-4 w-4" />
                      Setup notes
                    </div>
                    <p className="mt-2 text-sm text-muted-foreground">{deal.setup_note}</p>
                  </div>
                </div>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  <div className="rounded-xl border border-border/70 p-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Momentum</div>
                    <div className="mt-2 font-semibold">{formatPercent(deal.momentum_score)}</div>
                  </div>
                  <div className="rounded-xl border border-border/70 p-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Trend</div>
                    <div className="mt-2 font-semibold">{formatPercent(deal.trend_score)}</div>
                  </div>
                  <div className="rounded-xl border border-border/70 p-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">RSI / sentiment</div>
                    <div className="mt-2 font-semibold">
                      {deal.rsi.toFixed(1)} / {deal.sentiment_score.toFixed(2)}
                    </div>
                  </div>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-emerald-700 dark:text-emerald-300">Stop hint</div>
                    <div className="mt-2 font-semibold">{formatCurrency(deal.stop_loss_hint)}</div>
                  </div>
                  <div className="rounded-xl border border-sky-500/20 bg-sky-500/5 p-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-sky-700 dark:text-sky-300">Target hint</div>
                    <div className="mt-2 font-semibold">{formatCurrency(deal.take_profit_hint)}</div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            {featuredShown
              ? "No secondary setups are close to the lead signal right now. That usually means focus should stay on the strongest board idea."
              : "No strong setups cleared the current filter. That usually means the app prefers patience over forcing a trade right now."}
          </CardContent>
        </Card>
      )}
    </section>
  );
}
