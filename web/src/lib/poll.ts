// §4.2 rule 8: poll `/projects/{p}/poll` every 3 s on project-scoped pages. When the
// ledgers signature changes and the tab is visible, call `onChange` — the page refetches
// its own view's data, never a full reload. No SSE, no WebSocket.
import type { Poll } from "./api-types";

export const POLL_INTERVAL_MS = 3000;

/**
 * Polls `poller` every 3 s while the returned stop function is not called. The first
 * answer is the baseline; only a *change* in the ledgers signature, seen by a visible
 * tab, triggers `onChange`. A failing poll is retried silently — the poll is a
 * liveness probe, not data the page renders.
 */
export function startPolling(
  poller: () => Promise<Poll>,
  onChange: () => void,
  intervalMs: number = POLL_INTERVAL_MS,
): () => void {
  let signature: string | null = null;
  let stopped = false;
  const timer = setInterval(async () => {
    if (stopped || document.visibilityState !== "visible") return;
    try {
      const state = await poller();
      const next = JSON.stringify(state.ledgers);
      if (signature !== null && next !== signature) onChange();
      signature = next;
    } catch {
      // A dead API is the page's own error state; the poll just keeps trying.
    }
  }, intervalMs);
  return () => {
    stopped = true;
    clearInterval(timer);
  };
}