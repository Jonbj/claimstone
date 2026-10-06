// §8.2: a small `useApi(fetcher, deps)` hook — no React Query, because polling is the
// only cache-like behaviour this portal has (§4.2 rule 8). While a fetch is in flight
// the state is `pending` so pages render `Pending`, never a zero (§4.2 rule 1); an
// error is the §3.3 envelope mapped to `ApiError`, rendered as a named state.
import { useCallback, useEffect, useState } from "react";

export interface ApiState<T> {
  data: T | null;
  error: Error | null;
  pending: boolean;
  /** Re-runs the fetcher without changing `deps` — the poll's "refetch this view". */
  reload: () => void;
}

export function useApi<T>(fetcher: () => Promise<T>, deps: readonly unknown[]): ApiState<T> {
  const [state, setState] = useState<Omit<ApiState<T>, "reload">>({
    data: null,
    error: null,
    pending: true,
  });
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let alive = true;
    // New fetch: back to Pending — a stale number is worse than "computing…" (§4.2 rule 1).
    setState({ data: null, error: null, pending: true });
    fetcher()
      .then((data) => {
        if (alive) setState({ data, error: null, pending: false });
      })
      .catch((cause: unknown) => {
        if (!alive) return;
        const error = cause instanceof Error ? cause : new Error(String(cause));
        setState({ data: null, error, pending: false });
      });
    return () => {
      alive = false;
    };
    // `deps` and `tick` are the dependency list by design: the caller names the values
    // the fetch depends on, `reload` bumps `tick`, and `fetcher` is read fresh each run.
  }, [...deps, tick]);

  return { ...state, reload };
}
