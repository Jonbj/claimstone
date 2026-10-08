// A short date-time in UTC, never the browser's zone and never relative ("6 Oct 2026, 20:41 UTC").
// Only an ISO-8601 timestamp that names its own offset is formatted; anything else (including a
// zone-less string, which the browser would read in local time) is returned as received.
const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})$/;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function isIsoTimestamp(value: unknown): value is string {
  return typeof value === "string" && ISO.test(value) && !Number.isNaN(Date.parse(value));
}

export function formatUtc(value: string): string {
  if (!isIsoTimestamp(value)) return value;
  const d = new Date(value);
  const two = (n: number) => String(n).padStart(2, "0");
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}, ${two(d.getUTCHours())}:${two(d.getUTCMinutes())} UTC`;
}
