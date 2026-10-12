// Small formatters shared by the scheduler pages. Times are UTC and explicit, never the browser's
// zone; a value that is not an ISO timestamp with an offset is returned as received.
import { formatUtc } from "@/lib/datetime";
import type { Identity } from "@/lib/scheduler";

export function utcRange(from: string, to: string): string {
  return `${formatUtc(from)} → ${formatUtc(to)}`;
}

/** "10 × 3 = 30": candidates times requests each is the ceiling in requests. */
export function requestsLine(each: number, count: number, total: number): string {
  return `${count} × ${each} = ${total}`;
}

/** "3 / 8": the denominator stays visible; an unknown part is a dash, never a zero. */
export function ratio(part: number | null | undefined, whole: number | null | undefined): string {
  const show = (n: number | null | undefined) => (typeof n === "number" ? String(n) : "—");
  return `${show(part)} / ${show(whole)}`;
}

/** Who an identity is: the name, the operator id, the CLI login, "uid N", else a dash. Never nothing. */
export function identityName(identity: Identity | null | undefined): string {
  return identity?.name || identity?.operator || identity?.login
    || (typeof identity?.uid === "number" ? `uid ${identity.uid}` : "—");
}

/** A rate as a percentage with one decimal; anything that is not a number is a dash, never NaN. */
export function percent(rate: unknown): string {
  return typeof rate === "number" && Number.isFinite(rate) ? `${(rate * 100).toFixed(1)}%` : "—";
}
