"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { apiFetch } from "@/lib/api";
import type { SchedulerStatus, StrategyConfig } from "@/types/api";

export function SafetyControls({
  strategy,
  scheduler,
  onRefresh
}: {
  strategy: StrategyConfig;
  scheduler: SchedulerStatus;
  onRefresh: () => Promise<void>;
}) {
  const [busy, setBusy] = useState<string | null>(null);

  async function run(action: string, request: () => Promise<unknown>) {
    setBusy(action);
    try {
      await request();
      await onRefresh();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Immediate controls</CardTitle>
          <CardDescription>Hard stops and operational toggles.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between rounded-2xl border border-border p-4">
            <div>
              <div className="font-medium">Scheduler paused</div>
              <div className="text-sm text-muted-foreground">Pause recurring polling without flipping the kill switch.</div>
            </div>
            <Switch
              checked={strategy.pause_scheduler}
              onCheckedChange={(checked) =>
                run("pause", () =>
                  apiFetch("/api/strategy", { method: "PUT", json: { pause_scheduler: checked } })
                )
              }
            />
          </div>
          <div className="flex flex-wrap gap-3">
            <Button variant="outline" onClick={() => run("kill", () => apiFetch("/api/strategy/kill-switch", { method: "POST" }))} disabled={busy !== null}>
              Enable kill switch
            </Button>
            <Button variant="outline" onClick={() => run("resume", () => apiFetch("/api/strategy/resume", { method: "POST" }))} disabled={busy !== null}>
              Resume strategy
            </Button>
            <Button onClick={() => run("run_once", () => apiFetch("/api/strategy/run-once", { method: "POST" }))} disabled={busy !== null}>
              Run one cycle
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Current safety posture</CardTitle>
          <CardDescription>Operational state pulled from the backend.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <div className="flex items-center justify-between rounded-xl border border-border p-3">
            <span>Kill switch</span>
            <span>{String(strategy.kill_switch)}</span>
          </div>
          <div className="flex items-center justify-between rounded-xl border border-border p-3">
            <span>Cooldown until</span>
            <span>{strategy.cooldown_until ?? "Not active"}</span>
          </div>
          <div className="flex items-center justify-between rounded-xl border border-border p-3">
            <span>Scheduler lock</span>
            <span>{scheduler.lock_state}</span>
          </div>
          <div className="flex items-center justify-between rounded-xl border border-border p-3">
            <span>Scheduler running</span>
            <span>{String(scheduler.running)}</span>
          </div>
          <div className="flex items-center justify-between rounded-xl border border-border p-3">
            <span>Next due</span>
            <span>{scheduler.next_due_at ?? "Waiting for next interval"}</span>
          </div>
          <Button
            variant="secondary"
            onClick={() =>
              run("advisory", () => apiFetch("/api/strategy", { method: "PUT", json: { mode: "advisory", live_mode_armed: false } }))
            }
            disabled={busy !== null}
            className="w-full"
          >
            Force advisory mode
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
