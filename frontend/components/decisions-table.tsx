"use client";

import { useMemo, useState } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime, titleCase } from "@/lib/format";
import type { Decision } from "@/types/api";

export function DecisionsTable({ decisions }: { decisions: Decision[] }) {
  const [filter, setFilter] = useState("");
  const filtered = useMemo(
    () =>
      decisions.filter((decision) =>
        `${decision.symbol} ${decision.action}`.toLowerCase().includes(filter.toLowerCase())
      ),
    [decisions, filter]
  );

  return (
    <div className="space-y-4">
      <Input
        placeholder="Filter by symbol or action"
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
        className="max-w-sm"
      />
      <div className="overflow-hidden rounded-2xl border border-border">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Symbol</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>Approval</TableHead>
                <TableHead>Rationale</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((decision) => (
                <TableRow key={decision.id}>
                  <TableCell>{formatDateTime(decision.timestamp)}</TableCell>
                  <TableCell>{decision.symbol}</TableCell>
                  <TableCell>{titleCase(decision.action)}</TableCell>
                  <TableCell>{(decision.confidence * 100).toFixed(0)}%</TableCell>
                  <TableCell>
                    <StatusBadge value={decision.approved} />
                  </TableCell>
                  <TableCell className="max-w-[420px] text-muted-foreground">
                    {decision.rationale_json.join(" • ")}
                    {decision.rejection_reasons_json.length ? (
                      <div className="mt-2 text-rose-600 dark:text-rose-300">
                        {decision.rejection_reasons_json.join(" • ")}
                      </div>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}

