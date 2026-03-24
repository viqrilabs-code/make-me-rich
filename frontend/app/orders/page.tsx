"use client";

import { useEffect, useState } from "react";

import { ErrorState } from "@/components/error-state";
import { LoadingState } from "@/components/loading-state";
import { OrdersTable } from "@/components/orders-table";
import { PositionsTable } from "@/components/positions-table";
import { apiFetch } from "@/lib/api";
import type { Order, OverviewResponse, Position } from "@/types/api";

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [positions, setPositions] = useState<Position[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([apiFetch<Order[]>("/api/orders"), apiFetch<OverviewResponse>("/api/portfolio/overview")])
      .then(([orderRows, overview]) => {
        setOrders(orderRows);
        setPositions(overview.open_positions);
      })
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Unable to load orders"));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!orders || !positions) return <LoadingState label="Loading orders and positions..." />;

  return (
    <div className="space-y-8">
      <section>
        <div className="text-xs uppercase tracking-[0.2em] text-primary">Orders and positions</div>
        <h1 className="mt-2 font-display text-4xl font-semibold">Execution trail and live exposure</h1>
        <p className="mt-3 max-w-3xl text-muted-foreground">
          Paper fills, live orders, current exposure, and bracket-style stop/target tracking all stay visible here.
        </p>
      </section>
      <section className="space-y-4">
        <h2 className="font-display text-2xl font-semibold">Open positions</h2>
        <PositionsTable positions={positions} />
      </section>
      <section className="space-y-4">
        <h2 className="font-display text-2xl font-semibold">Order history</h2>
        <OrdersTable orders={orders} />
      </section>
    </div>
  );
}
