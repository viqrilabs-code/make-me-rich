"use client";

import { useEffect, useState } from "react";

import { ErrorState } from "@/components/error-state";
import { LoadingState } from "@/components/loading-state";
import { StrategyForm } from "@/components/strategy-form";
import { apiFetch } from "@/lib/api";
import type { ConfigResponse } from "@/types/api";

export default function StrategyPage() {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<ConfigResponse>("/api/config")
      .then(setConfig)
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Unable to load config"));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!config) return <LoadingState label="Loading strategy settings..." />;

  return (
    <div className="space-y-8">
      <section>
        <div className="text-xs uppercase tracking-[0.2em] text-primary">Strategy settings</div>
        <h1 className="mt-2 font-display text-4xl font-semibold">Tune goal, risk, instruments, and execution mode</h1>
        <p className="mt-3 max-w-3xl text-muted-foreground">
          This is now the control room for both strategy rules and the required API keys. Add the INDstocks,
          ChatGPT/OpenAI, Claude, Gemini, and Marketaux keys here before you ask the app to fetch any trade idea.
        </p>
      </section>
      <StrategyForm config={config} onSaved={setConfig} />
    </div>
  );
}
