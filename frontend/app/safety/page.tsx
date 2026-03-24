"use client";

import { useCallback, useEffect, useState } from "react";

import { ErrorState } from "@/components/error-state";
import { LoadingState } from "@/components/loading-state";
import { SafetyControls } from "@/components/safety-controls";
import { apiFetch } from "@/lib/api";
import type { SchedulerStatus, StrategyConfig } from "@/types/api";

export default function SafetyPage() {
  const [strategy, setStrategy] = useState<StrategyConfig | null>(null);
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [strategyData, schedulerData] = await Promise.all([
        apiFetch<StrategyConfig>("/api/strategy"),
        apiFetch<SchedulerStatus>("/api/scheduler/status")
      ]);
      setStrategy(strategyData);
      setScheduler(schedulerData);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load safety controls");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <ErrorState message={error} />;
  if (!strategy || !scheduler) return <LoadingState label="Loading safety controls..." />;

  return (
    <div className="space-y-8">
      <section>
        <div className="text-xs uppercase tracking-[0.2em] text-primary">Safety controls</div>
        <h1 className="mt-2 font-display text-4xl font-semibold">Kill switch, pause, cooldown, and manual intervention</h1>
        <p className="mt-3 max-w-3xl text-muted-foreground">
          These controls are designed to be blunt on purpose. The risk engine always has veto power, and this page adds fast operational overrides on top.
        </p>
      </section>
      <SafetyControls strategy={strategy} scheduler={scheduler} onRefresh={load} />
    </div>
  );
}
