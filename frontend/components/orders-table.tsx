"use client";

import { useMemo, useState } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatCurrency, formatDateTime } from "@/lib/format";
import type { Order } from "@/types/api";

export function OrdersTable({ orders }: { orders: Order[] }) {
  const [filter, setFilter] = useState("");
  const filtered = useMemo(
    () =>
      orders.filter((order) =>
        `${order.symbol} ${order.status} ${order.side}`.toLowerCase().includes(filter.toLowerCase())
      ),
    [orders, filter]
  );

  return (
    <div className="space-y-4">
      <Input placeholder="Filter orders" value={filter} onChange={(event) => setFilter(event.target.value)} className="max-w-sm" />
      <div className="overflow-hidden rounded-2xl border border-border">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Placed</TableHead>
                <TableHead>Symbol</TableHead>
                <TableHead>Side</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Qty</TableHead>
                <TableHead>Fill</TableHead>
                <TableHead>Mode</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((order) => (
                <TableRow key={order.id}>
                  <TableCell>{formatDateTime(order.placed_at)}</TableCell>
                  <TableCell>{order.symbol}</TableCell>
                  <TableCell>{order.side}</TableCell>
                  <TableCell>
                    <StatusBadge value={order.status} />
                  </TableCell>
                  <TableCell>{order.quantity}</TableCell>
                  <TableCell>{order.fill_price ? formatCurrency(order.fill_price) : "—"}</TableCell>
                  <TableCell>{order.mode}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}

