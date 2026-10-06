// §8.2: a small `useApi(fetcher, deps)` hook — no React Query, because polling is the
// only cache-like behaviour this portal has (§4.2 rule 8).
//
// Two kinds of fetch, deliberately different (implementation review of R2):
// - **The view changed** (`deps` changed): state goes back to `pending` with no data, so a page
//   never shows another view's numbers while its own are computing (§4.2 rule 1).
// - **The same view refreshed** (`reload`, called by the poll when the ledgers moved): the
//   previous data stays on screen with `refreshing: true` until the new answer arrives. The
//   first version blanked the page on every poll-triggered reload, which during a running
//   stage meant a flow page that flashed empty for seconds every few seconds.
// An error is the §3.3 envelope mapped to `ApiError`, rendered as a named state.
import { useCallback, useEffect, useRef, useState } from "react";

export interface ApiState<T> {
  data: T | null;
  error: Error | null;
  /** No data for this view yet: render `Pending`, never a zero. */
  pending: boolean;
  /** Data on screen is this view's previous answer; a newer one is computing. */
  refreshing: boolean;
  /** Re-runs the fetcher for the same view — the poll's "refetch this view". */
  reload: () => void;
}

type Held<T> = Omit<ApiState<T>, "reload">;

export function useApi<T>(fetcher: () => Promise<T>, deps: readonly unknown[]): ApiState<T> {
  const [state, setState] = useState<Held<T>>({
    data: null, error: null, pending: true, refreshing: false,
  });
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  const viewKey = JSON.stringify(deps);
  const lastView = useRef<string | null>(null);

  useEffect(() => {
    let alive = true;
    const sameView = lastView.current === viewKey;
    lastView.current = viewKey;
    setState((previous) =>
      sameView && previous.data !== null
        ? { ...previous, refreshing: true }
        : { data: null, error: null, pending: true, refreshing: false });
    fetcher()
      .then((data) => {
        if (alive) setState({ data, error: null, pending: false, refreshing: false });
      })
      .catch((cause: unknown) => {
        if (!alive) return;
        const error = cause instanceof Error ? cause : new Error(String(cause));
        // A failed refresh is still a failure: name it, and drop the old numbers rather than
        // keep presenting them as current.
        setState({ data: null, error, pending: false, refreshing: false });
      });
    return () => {
      alive = false;
    };
    // `viewKey` and `tick` are the dependency list by design: the caller names the values the
    // fetch depends on, `reload` bumps `tick`, and `fetcher` is read fresh each run.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewKey, tick]);

  return { ...state, reload };
}
