import type { Figures } from "@/lib/control";

export const DASH = "—";

/** A figure for the page: an unknown is a dash, never 0 (a known zero stays "0"). */
export function show(value: unknown): string {
  if (value === null || value === undefined) return DASH;
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : DASH;
  if (typeof value === "string") return value || DASH;
  return DASH;
}

/** The placeholders of the explanation copy, from whatever figures the server has given so far. */
export function explainParams(figures: Figures, extra: Record<string, string> = {}): Record<string, string> {
  const floor = typeof figures.acquisition_floor === "number" ? figures.acquisition_floor.toFixed(2) : DASH;
  const classes = Array.isArray(figures.classes) ? String(figures.classes.length) : DASH;
  return {
    topics: show(figures.topics),
    terms: show(figures.terms),
    searches: show(figures.searches_per_index),
    searchesAll: show(figures.searches_all_indexes),
    total: show(figures.questions_total),
    literature: show(figures.questions_literature),
    operational: show(figures.questions_operational),
    floor,
    classes,
    added: show(figures.excluded_hosts_added),
    supplied: show(figures.supplied_copies),
    ...extra,
  };
}
