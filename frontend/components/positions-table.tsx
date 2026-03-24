import { StatusBadge } from "@/components/status-badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatCurrency, formatDateTime } from "@/lib/format";
import type { Position } from "@/types/api";

export function PositionsTable({ positions }: { positions: Position[] }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-border">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Opened / synced</TableHead>
              <TableHead>Symbol</TableHead>
              <TableHead>Side</TableHead>
              <TableHead>Qty</TableHead>
              <TableHead>Avg</TableHead>
              <TableHead>Current</TableHead>
              <TableHead>Unrealized</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {positions.map((position) => (
              <TableRow key={position.id}>
                <TableCell>{formatDateTime(position.opened_at)}</TableCell>
                <TableCell>{position.symbol}</TableCell>
                <TableCell>{position.side}</TableCell>
                <TableCell>{position.quantity}</TableCell>
                <TableCell>{formatCurrency(position.avg_price)}</TableCell>
                <TableCell>{formatCurrency(position.current_price)}</TableCell>
                <TableCell>{formatCurrency(position.unrealized_pnl)}</TableCell>
                <TableCell>
                  <StatusBadge value={position.status} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
