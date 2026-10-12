// The one table of state words the scheduler pages translate. A known word maps to its catalog
// key; an unknown word maps to null and is shown as the server sent it, never mapped to a default.
const KNOWN = new Set([
  "PLANNED", "AUTHORIZED", "REVOKED", "ENABLED", "DISABLED",
  "ALIVE", "STALE", "STOPPED", "NOT_STARTED", "UNKNOWN", "IDLE", "DRIVING",
]);

export function stateLabelKey(word: string): string | null {
  return KNOWN.has(word) ? `sched.state.${word}` : null;
}
