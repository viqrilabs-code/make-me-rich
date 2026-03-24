export function formatCurrency(value: number | null | undefined) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2
  }).format(value ?? 0);
}

export function formatSignedCurrency(value: number | null | undefined) {
  const amount = value ?? 0;
  const prefix = amount > 0 ? "+" : "";
  return `${prefix}${formatCurrency(amount)}`;
}

export function formatPercent(value: number | null | undefined) {
  return `${(value ?? 0).toFixed(2)}%`;
}

export function formatSignedPercent(value: number | null | undefined) {
  const amount = value ?? 0;
  const prefix = amount > 0 ? "+" : "";
  return `${prefix}${formatPercent(amount)}`;
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return "--";
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata"
  }).format(new Date(value));
}

export function titleCase(value: string | null | undefined) {
  if (!value) return "--";
  return value
    .toLowerCase()
    .split(/[_\s-]+/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
