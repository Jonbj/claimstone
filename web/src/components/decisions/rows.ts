// Small readers for control rows the portal renders but does not own: a ledger row's
// fields arrive as `unknown`, and every display value goes through these so a missing
// field renders "—" rather than crashing the card that shows it.
import type { Row } from "@/lib/control";

export function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function has(value: unknown): string {
  return typeof value === "string" && value ? value : "—";
}

export function linksOf(row: Row): Record<string, unknown> {
  const links = row.links;
  return typeof links === "object" && links !== null ? (links as Record<string, unknown>) : {};
}

export type { Row };
