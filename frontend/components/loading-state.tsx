export function LoadingState({ label = "Loading dashboard..." }: { label?: string }) {
  return (
    <div className="flex min-h-[240px] items-center justify-center rounded-2xl border border-dashed border-border bg-card/60 text-sm text-muted-foreground">
      {label}
    </div>
  );
}

