import { RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDateTime, titleCase } from "@/lib/format";
import type { NewsSummary } from "@/types/api";

export function NewsPanel({
  summary,
  onRefresh,
  refreshing = false
}: {
  summary: NewsSummary;
  onRefresh?: () => void;
  refreshing?: boolean;
}) {
  return (
    <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle>Relevant Headlines</CardTitle>
              <Badge variant={summary.technical_only ? "warning" : "info"}>
                {summary.technical_only ? "Technical-only mode" : "Live news assist"}
              </Badge>
            </div>
            {onRefresh ? (
              <Button type="button" variant="outline" className="gap-2 rounded-full" onClick={onRefresh} disabled={refreshing}>
                {refreshing ? <RefreshCw className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                {refreshing ? "Refreshing news..." : "Refresh news manually"}
              </Button>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {summary.items.length ? (
            summary.items.map((item) => (
              <a
                key={item.url}
                href={item.url}
                target="_blank"
                rel="noreferrer"
                className="block rounded-2xl border border-border p-4 transition-colors hover:bg-muted/40"
              >
                <div className="flex flex-wrap items-center gap-2">
                  {item.symbols.map((symbol) => (
                    <Badge key={symbol} variant="info">
                      {symbol}
                    </Badge>
                  ))}
                </div>
                <div className="mt-3 font-medium">{item.title}</div>
                <div className="mt-2 text-sm text-muted-foreground">{item.description}</div>
                <div className="mt-3 text-xs text-muted-foreground">
                  {item.source} | {formatDateTime(item.published_at)}
                </div>
              </a>
            ))
          ) : (
            <div className="rounded-2xl border border-dashed border-border p-5 text-sm text-muted-foreground">
              {summary.technical_only_reason ??
                "No fresh headlines matched the current watchlist in the recent fetch window. The trading board will continue ranking setups from price action and technical context."}
            </div>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle>Sentiment Snapshot</CardTitle>
            <Badge variant="default">{titleCase(summary.feed_status.replace("_", " "))}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-2xl bg-muted/50 p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Overall sentiment</div>
            <div className="mt-2 font-display text-3xl font-semibold">{summary.overall_sentiment.toFixed(2)}</div>
          </div>
          {summary.technical_only ? (
            <div className="rounded-xl border border-amber-500/20 bg-amber-500/8 p-3 text-sm text-amber-700 dark:text-amber-300">
              News is not steering this analysis right now. The board is leaning on historical price, volume, RSI, MACD, volatility, and trend structure instead.
            </div>
          ) : null}
          <div className="space-y-3">
            {summary.top_symbols.length ? (
              summary.top_symbols.map((entry) => (
                <div key={entry.symbol} className="flex items-center justify-between rounded-xl border border-border p-3">
                  <span className="font-medium">{entry.symbol}</span>
                  <Badge variant="default">{entry.articles} articles</Badge>
                </div>
              ))
            ) : (
              <div className="rounded-xl border border-dashed border-border p-3 text-sm text-muted-foreground">
                Sentiment will populate here once the news feed sees enough relevant stories.
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
