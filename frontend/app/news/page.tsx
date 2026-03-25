"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";

import { ErrorState } from "@/components/error-state";
import { LoadingState } from "@/components/loading-state";
import { NewsPanel } from "@/components/news-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { NewsSummary, StrategyConfig } from "@/types/api";

const EMPTY_SUMMARY: NewsSummary = {
  items: [],
  overall_sentiment: 0,
  top_symbols: [],
  feed_status: "empty",
  technical_only: true,
  technical_only_reason: "No fresh headlines are available yet."
};

export default function NewsPage() {
  const [strategy, setStrategy] = useState<StrategyConfig | null>(null);
  const [summary, setSummary] = useState<NewsSummary>(EMPTY_SUMMARY);
  const [symbolsInput, setSymbolsInput] = useState("");
  const [isBooting, setIsBooting] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    Promise.allSettled([
      apiFetch<StrategyConfig>("/api/strategy"),
      apiFetch<NewsSummary>("/api/news/summary")
    ]).then((results) => {
      if (!active) return;
      const [strategyResult, summaryResult] = results;

      if (strategyResult.status === "rejected" && summaryResult.status === "rejected") {
        setError("Unable to load the news board.");
        setIsBooting(false);
        return;
      }

      if (strategyResult.status === "fulfilled") {
        setStrategy(strategyResult.value);
        const defaultSymbols = uniqueSymbols(strategyResult.value);
        setSymbolsInput(defaultSymbols.join(", "));
      }

      if (summaryResult.status === "fulfilled") {
        setSummary(summaryResult.value);
      }

      setIsBooting(false);
    });

    return () => {
      active = false;
    };
  }, []);

  const symbolChips = useMemo(() => uniqueSymbols(strategy), [strategy]);

  async function fetchNews(symbols: string[]) {
    setIsRefreshing(true);
    setError(null);
    try {
      const refreshed = await apiFetch<NewsSummary>("/api/news/refresh", {
        method: "POST",
        json: { symbols }
      });
      setSummary(refreshed);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to fetch news right now");
    } finally {
      setIsRefreshing(false);
    }
  }

  function parseSymbols(input: string) {
    return Array.from(
      new Set(
        input
          .split(",")
          .map((value) => value.trim().toUpperCase())
          .filter(Boolean)
      )
    );
  }

  function submitSymbols(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = parseSymbols(symbolsInput);
    if (!parsed.length) {
      setError("Enter at least one stock symbol.");
      return;
    }
    void fetchNews(parsed);
  }

  function useSingleSymbol(symbol: string) {
    setSymbolsInput(symbol);
    void fetchNews([symbol]);
  }

  if (error && isBooting) return <ErrorState message={error} />;
  if (isBooting) return <LoadingState label="Loading news board..." />;

  return (
    <div className="space-y-8">
      <section className="rounded-[32px] border border-border/70 bg-card/85 p-6 shadow-[0_24px_80px_rgba(15,23,42,0.12)] backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <div className="text-xs uppercase tracking-[0.2em] text-primary">News board</div>
            <h1 className="mt-3 font-display text-4xl font-semibold tracking-tight">Fetch news for any stock list</h1>
            <p className="mt-3 text-sm text-muted-foreground">Enter comma-separated stocks and pull a fresh news snapshot on demand.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={summary.technical_only ? "warning" : "success"}>
              {summary.technical_only ? "Technical-only mode" : "Live news assist"}
            </Badge>
            <Badge variant="info">{summary.feed_status.replaceAll("_", " ")}</Badge>
          </div>
        </div>

        <form className="mt-6 grid gap-3 lg:grid-cols-[1fr_auto]" onSubmit={submitSymbols}>
          <Input
            value={symbolsInput}
            onChange={(event) => setSymbolsInput(event.target.value.toUpperCase())}
            placeholder="RELIANCE, INFY, HDFCBANK"
            className="h-12 rounded-2xl bg-background/70"
          />
          <Button type="submit" size="lg" className="gap-2 rounded-2xl" disabled={isRefreshing}>
            <RefreshCw className={cn("h-4 w-4", isRefreshing && "animate-spin")} />
            {isRefreshing ? "Fetching news..." : "Fetch news"}
          </Button>
        </form>

        {symbolChips.length ? (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Tracked stocks</span>
            {symbolChips.map((symbol) => (
              <button
                key={symbol}
                type="button"
                className={cn(
                  "rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] transition-colors",
                  parseSymbols(symbolsInput).includes(symbol)
                    ? "border-primary/40 bg-primary/10 text-foreground"
                    : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"
                )}
                onClick={() => useSingleSymbol(symbol)}
              >
                {symbol}
              </button>
            ))}
          </div>
        ) : null}

        {error ? (
          <div className="mt-4 rounded-2xl border border-rose-500/25 bg-rose-500/8 px-4 py-3 text-sm text-rose-300">
            {error}
          </div>
        ) : null}
      </section>

      <NewsPanel summary={summary} onRefresh={() => void fetchNews(parseSymbols(symbolsInput))} refreshing={isRefreshing} />
    </div>
  );
}

function uniqueSymbols(strategy: StrategyConfig | null) {
  const values = strategy?.watchlist_symbols_json?.length
    ? strategy.watchlist_symbols_json
    : strategy?.allowed_instruments_json?.symbols ?? [];
  return Array.from(new Set(values.map((value) => value.trim().toUpperCase()).filter(Boolean)));
}
