// The one table of state words the scheduler pages translate. A known word maps to its catalog
// key; an unknown word maps to null and is shown as the server sent it, never mapped to a default.
const KNOWN = new Set([
  "PLANNED", "AUTHORIZED", "REVOKED", "ENABLED", "DISABLED",
  "ALIVE", "STALE", "STOPPED", "NOT_STARTED", "UNKNOWN", "IDLE", "DRIVING",
  // The dossier's own states (periodic_dossier.preview).
  "INSUFFICIENT_ACQUISITION", "WAITING_FOR_SCHEDULE", "WAITING_FOR_EVIDENCE", "READY_FOR_HUMAN_READING",
]);

export function stateLabelKey(word: string): string | null {
  return KNOWN.has(word) ? `sched.state.${word}` : null;
}
