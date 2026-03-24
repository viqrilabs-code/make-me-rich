import { Badge } from "@/components/ui/badge";

export function StatusBadge({ value }: { value: string | boolean | null | undefined }) {
  if (value === true) return <Badge variant="success">Approved</Badge>;
  if (value === false) return <Badge variant="danger">Rejected</Badge>;
  const normalized = String(value ?? "unknown").toLowerCase();
  if (["filled", "open", "running", "healthy", "active", "completed"].includes(normalized)) {
    return <Badge variant="success">{normalized}</Badge>;
  }
  if (["warning", "paused", "advisory"].includes(normalized)) {
    return <Badge variant="warning">{normalized}</Badge>;
  }
  if (["failed", "error", "live", "unhealthy"].includes(normalized)) {
    return <Badge variant="danger">{normalized}</Badge>;
  }
  return <Badge variant="default">{normalized}</Badge>;
}

