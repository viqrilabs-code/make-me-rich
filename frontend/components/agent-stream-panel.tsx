"use client";

import { Bot, CircleDot, Radio, ShieldCheck, TriangleAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/cn";
import { formatCurrency, formatDateTime, formatSignedCurrency, formatSignedPercent, titleCase } from "@/lib/format";
import type { AgentEvent, AgentSession } from "@/types/api";

type AgentSnapshot = {
  current_equity?: number;
  progress_pct?: number;
  realized_pnl?: number;
  unrealized_pnl?: number;
  today_pnl?: number;
  today_pnl_pct?: number;
  session_pnl?: number;
  session_pnl_pct?: number;
  target_gap?: number;
};

type Props = {
  session: AgentSession | null;
  events: AgentEvent[];
  streamingConnected: boolean;
  selectedSymbol: string;
  onOpenLauncher: () => void;
  onStop: () => void;
  disabled?: boolean;
  busy?: boolean;
};

export function AgentStreamPanel({
  session,
  events,
  streamingConnected,
  selectedSymbol,
  onOpenLauncher,
  onStop,
  disabled = false,
  busy = false
}: Props) {
  const active = Boolean(session && (session.status === "starting" || session.status === "running"));

  return (
    <section className="overflow-hidden rounded-[32px] border border-border/70 bg-card/90 p-6 shadow-[0_18px_64px_rgba(15,23,42,0.14)]">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <div className="text-xs uppercase tracking-[0.24em] text-primary">Autonomous ReAct Agent</div>
          <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight">
            Let the agent work the enabled lanes for {selectedSymbol || session?.symbol || "your chosen stock"}
          </h2>
          <p className="mt-3 text-sm text-muted-foreground">Live stream, live P&L, same hard risk engine.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={active ? "success" : "info"}>{active ? "Agent active" : "Agent idle"}</Badge>
          <Badge variant={streamingConnected ? "success" : "warning"}>
            {streamingConnected ? "Live stream connected" : "Live stream reconnecting"}
          </Badge>
        </div>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <div className="space-y-4 rounded-[28px] border border-border/70 bg-background/60 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Control room</div>
              <div className="mt-2 text-2xl font-semibold">
                {active ? `${session?.symbol} agent is running` : "Ready to activate"}
              </div>
            </div>
            <div className="flex items-center gap-2">
              {active ? (
                <Button variant="outline" onClick={onStop} disabled={busy} className="gap-2 rounded-full">
                  <TriangleAlert className="h-4 w-4" />
                  Stop agent
                </Button>
              ) : (
                <Button onClick={onOpenLauncher} disabled={disabled || busy} className="gap-2 rounded-full">
                  <Bot className="h-4 w-4" />
                  Start with launch pad
                </Button>
              )}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <InfoCard label="Target path" value={session ? `${session.target_multiplier.toFixed(2)}x` : "1.20x"} />
            <InfoCard label="Execution mode" value={session ? titleCase(session.mode) : "Advisory"} />
            <InfoCard label="Start equity" value={session ? formatCurrency(session.start_equity) : "--"} />
            <InfoCard label="Current equity" value={session ? formatCurrency(session.current_equity) : "--"} />
            <InfoCard
              label="Session PnL"
              value={session ? formatSignedCurrency(session.session_pnl) : "--"}
              accent={session ? (session.session_pnl >= 0 ? "positive" : "negative") : "neutral"}
              hint={session ? formatSignedPercent(session.session_pnl_pct) : undefined}
            />
            <InfoCard
              label="Target gap"
              value={session ? formatCurrency(session.target_gap) : "--"}
              hint={session ? "Remaining distance to 1.20x" : undefined}
            />
            <InfoCard
              label="Realized PnL"
              value={session ? formatSignedCurrency(session.realized_pnl) : "--"}
              accent={session ? (session.realized_pnl >= 0 ? "positive" : "negative") : "neutral"}
            />
            <InfoCard
              label="Unrealized PnL"
              value={session ? formatSignedCurrency(session.unrealized_pnl) : "--"}
              accent={session ? (session.unrealized_pnl >= 0 ? "positive" : "negative") : "neutral"}
            />
          </div>

          <div className="rounded-[24px] border border-border/70 bg-background/60 p-4">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Progress to session target</span>
              <span>{session ? `${session.progress_pct.toFixed(2)}%` : "0.00%"}</span>
            </div>
            <Progress value={session?.progress_pct ?? 0} className="mt-3" />
            <div className="mt-3 text-sm text-muted-foreground">
              {session?.last_message ?? "Open the launch pad first, pick the stock, review the workflow, and then start the live autonomous run."}
            </div>
          </div>

          <div className="rounded-[24px] border border-border/70 bg-background/60 p-4">
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-muted-foreground">
              <ShieldCheck className="h-4 w-4" />
              Safety frame
            </div>
            <div className="mt-3 text-sm text-muted-foreground">
              Target is aspirational. Risk checks still have veto power.
            </div>
          </div>
        </div>

        <div className="rounded-[28px] border border-border/70 bg-background/60 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Live activity</div>
              <div className="mt-2 text-2xl font-semibold">Stream of specialist decisions and trade actions</div>
            </div>
            <Badge variant={events.some((event) => event.event_type === "trade_executed") ? "success" : "info"}>
              {events.some((event) => event.event_type === "trade_executed") ? "Trade executed" : "Watching"}
            </Badge>
          </div>

          <div className="mt-4 space-y-3">
            {events.length ? (
              events.slice(-10).reverse().map((event) => (
                <div
                  key={event.id}
                  className={cn(
                    "rounded-[22px] border px-4 py-3",
                    event.event_type === "trade_executed" || event.event_type === "trade_simulated"
                      ? "border-emerald-500/30 bg-emerald-500/8"
                      : event.event_type === "risk_checked" && event.severity !== "success"
                        ? "border-amber-500/30 bg-amber-500/8"
                        : "border-border/70 bg-background/60"
                  )}
                >
                  {(() => {
                    const snapshot = readSnapshot(event);
                    return (
                      <>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      {event.event_type === "trade_executed" || event.event_type === "trade_simulated" ? (
                        <CircleDot className="h-4 w-4 text-emerald-400" />
                      ) : (
                        <Radio className="h-4 w-4 text-primary" />
                      )}
                      <span className="text-sm font-semibold">{event.message}</span>
                    </div>
                    <span className="text-xs text-muted-foreground">{formatDateTime(event.timestamp)}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <Badge variant="info">{titleCase(event.phase)}</Badge>
                    <Badge variant={event.severity === "success" ? "success" : event.severity === "warning" ? "warning" : "info"}>
                      {titleCase(event.event_type.replaceAll("_", " "))}
                    </Badge>
                  </div>
                  {snapshot ? (
                    <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2 xl:grid-cols-4">
                      <div>Equity {formatCurrency(snapshot.current_equity ?? 0)}</div>
                      <div>Session {formatSignedCurrency(snapshot.session_pnl ?? 0)}</div>
                      <div>Realized {formatSignedCurrency(snapshot.realized_pnl ?? 0)}</div>
                      <div>Unrealized {formatSignedCurrency(snapshot.unrealized_pnl ?? 0)}</div>
                    </div>
                  ) : null}
                      </>
                    );
                  })()}
                </div>
              ))
            ) : (
              <div className="rounded-[22px] border border-dashed border-border px-4 py-6 text-sm text-muted-foreground">
                The live stream will appear here after the agent starts.
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function InfoCard({
  label,
  value,
  hint,
  accent = "neutral"
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: "positive" | "negative" | "neutral";
}) {
  return (
    <div className="rounded-[22px] border border-border/70 bg-background/60 p-4">
      <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{label}</div>
      <div
        className={cn(
          "mt-3 text-2xl font-semibold",
          accent === "positive" ? "text-emerald-300" : accent === "negative" ? "text-rose-300" : ""
        )}
      >
        {value}
      </div>
      {hint ? <div className="mt-2 text-xs text-muted-foreground">{hint}</div> : null}
    </div>
  );
}

function readSnapshot(event: AgentEvent): AgentSnapshot | null {
  const snapshot = event.metadata_json?.snapshot;
  if (!snapshot || typeof snapshot !== "object") {
    return null;
  }
  return snapshot as AgentSnapshot;
}
