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

  const run = useCallback(async () => {
    const mine = token.current;
    if (mine.busy) return;
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

  return { ...state, refresh: run };
}
