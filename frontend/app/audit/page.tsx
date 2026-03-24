"use client";

import { useEffect, useState } from "react";

import { AuditTable } from "@/components/audit-table";
import { ErrorState } from "@/components/error-state";
import { LoadingState } from "@/components/loading-state";
import { apiFetch } from "@/lib/api";
import type { AuditEntry } from "@/types/api";

type SchedulerRun = {
  id: number;
  started_at: string;
  completed_at: string | null;
  status: string;
  lock_acquired: boolean;
  actions_taken_json: Array<Record<string, unknown>>;
  error_message: string | null;
};

export default function AuditPage() {
  const [logs, setLogs] = useState<AuditEntry[] | null>(null);
  const [risks, setRisks] = useState<AuditEntry[] | null>(null);
  const [runs, setRuns] = useState<SchedulerRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiFetch<AuditEntry[]>("/api/audit/logs"),
      apiFetch<AuditEntry[]>("/api/audit/risk-events"),
      apiFetch<SchedulerRun[]>("/api/audit/scheduler-runs")
    ])
      .then(([logsData, riskData, runsData]) => {
        setLogs(logsData);
        setRisks(riskData);
        setRuns(runsData);
      })
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Unable to load audit data"));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!logs || !risks || !runs) return <LoadingState label="Loading audit trail..." />;

  return (
    <div className="space-y-8">
      <section>
        <div className="text-xs uppercase tracking-[0.2em] text-primary">Audit and logs</div>
        <h1 className="mt-2 font-display text-4xl font-semibold">Readable trail of every meaningful system move</h1>
        <p className="mt-3 max-w-3xl text-muted-foreground">
          Prompt validation, scheduler activity, risk events, and operational notes stay queryable so every decision remains auditable.
        </p>
      </section>
      <section className="space-y-4">
        <h2 className="font-display text-2xl font-semibold">Audit log</h2>
        <AuditTable rows={logs} />
      </section>
      <section className="space-y-4">
        <h2 className="font-display text-2xl font-semibold">Risk events</h2>
        <AuditTable rows={risks} mode="risk" />
      </section>
      <section className="space-y-4">
        <h2 className="font-display text-2xl font-semibold">Scheduler runs</h2>
        <div className="overflow-hidden rounded-2xl border border-border">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-border">
                <tr>
                  <th className="p-3 text-left text-xs uppercase tracking-[0.16em] text-muted-foreground">Run</th>
                  <th className="p-3 text-left text-xs uppercase tracking-[0.16em] text-muted-foreground">Started</th>
                  <th className="p-3 text-left text-xs uppercase tracking-[0.16em] text-muted-foreground">Status</th>
                  <th className="p-3 text-left text-xs uppercase tracking-[0.16em] text-muted-foreground">Actions</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id} className="border-b border-border">
                    <td className="p-3">{run.id}</td>
                    <td className="p-3">{run.started_at}</td>
                    <td className="p-3">{run.status}</td>
                    <td className="p-3 text-muted-foreground">{JSON.stringify(run.actions_taken_json)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}

