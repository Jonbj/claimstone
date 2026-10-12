// The grants of one series: a first bounded walk of the index, then cheap refreshes by id (see
// components/scheduler/grants.ts). A refresh never starts while one is running, and leaving the page
// cancels the walk before its next request.
import { useCallback, useEffect, useRef, useState } from "react";
import { findSeriesGrants, refreshGrants } from "@/components/scheduler/grants";
import type { Cancel, SeriesGrants } from "@/components/scheduler/grants";

interface Token extends Cancel { busy: boolean }

export function useSeriesGrants(project: string, id: string) {
  const [state, setState] = useState<{ data: SeriesGrants | null; error: Error | null; pending: boolean }>(
    { data: null, error: null, pending: true });
  const token = useRef<Token>({ cancelled: false, busy: false });
  const known = useRef<SeriesGrants | null>(null);

  const again = useRef<"none" | "refresh" | "full">("none");

  const run = useCallback(async (full = false): Promise<void> => {
    const mine = token.current;
    if (full) known.current = null;     // an id the list does not know yet: walk the index again
    if (mine.busy) {
      // A write happened while a read was running: that read may predate it, so read once more after.
      if (again.current !== "full") again.current = full ? "full" : "refresh";
      return;
    }
    mine.busy = true;
    try {
      const previous = known.current;
      const next = previous ? await refreshGrants(project, id, previous, mine) : await findSeriesGrants(project, id, mine);
      if (mine.cancelled) return;
      known.current = next;
      setState({ data: next, error: null, pending: false });
    } catch (cause) {
      if (mine.cancelled) return;
      known.current = null;
      setState({ data: null, error: cause instanceof Error ? cause : new Error(String(cause)), pending: false });
    } finally {
      mine.busy = false;
      const next = again.current;
      again.current = "none";
      if (next !== "none" && !mine.cancelled) void run(next === "full");
    }
  }, [project, id]);

  useEffect(() => {
    const mine: Token = { cancelled: false, busy: false };
    token.current = mine;
    known.current = null;
    setState({ data: null, error: null, pending: true });
    void run();
    return () => { mine.cancelled = true; };
  }, [run]);

  const refresh = useCallback(() => run(false), [run]);
  /** After a write: read the known ids again, or walk the index again when a grant was just created. */
  const reload = useCallback((full = false) => run(full), [run]);
  return { ...state, refresh, reload };
}
