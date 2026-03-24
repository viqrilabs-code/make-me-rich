import { ArrowDownRight, ArrowUpRight } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/cn";

export function MetricCard({
  label,
  value,
  hint,
  tone = "neutral"
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "neutral" | "positive" | "negative";
}) {
  return (
    <Card className="overflow-hidden border-border/60 bg-[linear-gradient(180deg,rgba(255,255,255,0.04),transparent)]">
      <CardContent className="space-y-3 p-5">
        <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
        <div className="font-display text-[2rem] font-semibold tracking-tight">{value}</div>
        {hint ? (
          <div
            className={cn(
              "flex items-center gap-2 text-sm",
              tone === "positive" && "text-emerald-600 dark:text-emerald-300",
              tone === "negative" && "text-rose-600 dark:text-rose-300",
              tone === "neutral" && "text-muted-foreground"
            )}
          >
            {tone === "positive" ? <ArrowUpRight className="h-4 w-4" /> : null}
            {tone === "negative" ? <ArrowDownRight className="h-4 w-4" /> : null}
            <span>{hint}</span>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
