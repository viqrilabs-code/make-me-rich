import { StatusBadge } from "@/components/status-badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime } from "@/lib/format";
import type { AuditEntry } from "@/types/api";

export function AuditTable({ rows, mode = "audit" }: { rows: AuditEntry[]; mode?: "audit" | "risk" }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-border">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead>
              <TableHead>{mode === "risk" ? "Event" : "Category"}</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Message</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id}>
                <TableCell>{formatDateTime(row.timestamp)}</TableCell>
                <TableCell>{row.event_type ?? row.category ?? "—"}</TableCell>
                <TableCell>
                  <StatusBadge value={row.severity ?? row.category ?? "info"} />
                </TableCell>
                <TableCell className="text-muted-foreground">{row.message}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
