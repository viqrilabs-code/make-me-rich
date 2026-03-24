"use client";

import { useEffect, useState } from "react";

import { DecisionsTable } from "@/components/decisions-table";
import { ErrorState } from "@/components/error-state";
import { LoadingState } from "@/components/loading-state";
import { apiFetch } from "@/lib/api";
import type { Decision } from "@/types/api";

export default function DecisionsPage() {
  const [decisions, setDecisions] = useState<Decision[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<Decision[]>("/api/decisions")
      .then(setDecisions)
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Unable to load decisions"));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!decisions) return <LoadingState label="Loading decision log..." />;

  return (
    <div className="space-y-8">
      <section>
        <div className="text-xs uppercase tracking-[0.2em] text-primary">Decision log</div>
        <h1 className="mt-2 font-display text-4xl font-semibold">AI outputs with audit-friendly rationale</h1>
        <p className="mt-3 max-w-3xl text-muted-foreground">
          Every decision captures candidates, chosen action, confidence, and whether the hard risk engine approved or rejected it.
        </p>
      </section>
      <DecisionsTable decisions={decisions} />
    </div>
  );
}

