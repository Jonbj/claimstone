// The scheduler's own refresh. The ledger poll (`usePoll`) does not see worker sidecars or the grant
// and schedule ledgers, so the scheduler pages also read again on a timer, visible tab only. A read
// never starts while the same read is still in flight: the server's status reads can wait on the
// project's writer lock while a mandate pass runs, and requests must not pile up behind it.
import { useEffect, useRef, useState } from "react";

export const REFRESH_MS = 15_000;
export const DOSSIER_MIN_MS = 45_000;

/** Calls `fn` every `ms` while the tab is visible. */
export function useVisibleInterval(fn: () => void, ms: number = REFRESH_MS): void {
  const ref = useRef(fn);
  useEffect(() => { ref.current = fn; });
  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") ref.current();
    }, ms);
    return () => clearInterval(timer);
  }, [ms]);
}

/** A function that calls `reload` unless a read is in flight or the last start was less than
 *  `minGapMs` ago. The first read (on load) counts as the last start. */
export function useIdleReload(reload: () => void, busy: boolean, minGapMs = 0): () => void {
  const busyRef = useRef(busy);
  const reloadRef = useRef(reload);
  const lastRef = useRef<number | null>(null);
  if (lastRef.current === null) lastRef.current = Date.now();
  useEffect(() => { busyRef.current = busy; reloadRef.current = reload; });
  const callRef = useRef(() => {
    if (busyRef.current) return;
    const now = Date.now();
    if (now - (lastRef.current ?? 0) < minGapMs) return;
    lastRef.current = now;
    reloadRef.current();
  });
  return callRef.current;
}

/** The time, moving on every `ms`; for labels that depend on "now". */
export function useNow(ms = 30_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(timer);
  }, [ms]);
  return now;
}

/** When `data` last changed identity, as an ISO time: "as of" for a read the page keeps. */
export function useAsOf(data: unknown): string | null {
  const [at, setAt] = useState<string | null>(null);
  useEffect(() => { if (data) setAt(new Date().toISOString()); }, [data]);
  return at;
}
