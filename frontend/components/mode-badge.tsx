import { Badge } from "@/components/ui/badge";

export function ModeBadge({ mode }: { mode: string }) {
  const normalized = mode.toLowerCase();
  if (normalized === "live") return <Badge variant="danger">Live</Badge>;
  if (normalized === "paper") return <Badge variant="info">Paper</Badge>;
  return <Badge variant="warning">Advisory</Badge>;
}

