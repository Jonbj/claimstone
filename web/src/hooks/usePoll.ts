// §4.2 rule 8: poll `/projects/{p}/poll` every 3 s on project-scoped pages. When the
// ledgers signature changes and the tab is visible, call `onChange` — the page refetches
// its own view's data, never a full reload. No SSE, no WebSocket. A failing poll is
// retried silently: the poll is a liveness probe, not data the page renders.
import { useEffect, useRef } from "react";
import { api } from "@/lib/api";
import type { Poll } from "@/lib/api-types";

export const POLL_INTERVAL_MS = 3000;

export function usePoll(project: string | null, onChange: () => void): void {
  // Keep the latest callback without re-arming the timer on every render.
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  });

  useEffect(() => {
    if (project === null) return;
    let signature: string | null = null;
    let stopped = false;
    const timer = setInterval(async () => {
      if (stopped || document.visibilityState !== "visible") return;
      try {
        const state: Poll = await api.poll(project);
        const next = JSON.stringify(state.ledgers);
        // The first answer is the baseline; only a *change* in the signature triggers.
        if (signature !== null && next !== signature) onChangeRef.current();
        signature = next;
      } catch {
        // A dead API is the page's own error state; the poll just keeps trying.
      }
    }, POLL_INTERVAL_MS);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [project]);
}
