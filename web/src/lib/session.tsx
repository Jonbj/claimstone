// The operator session (spec v2.1 F1). A React context over `control.session / signIn /
// signOut`: `operator` is `{id, name}` or null, and `ready` says whether the first
// `GET /control/v1/session` has answered, so a page never shows "Sign in" for a moment to
// someone who is signed in. A 401 from any control route signs the context out
// (`setUnauthorizedHandler`), and nothing here touches storage: the cookie is HttpOnly and the
// CSRF token lives in control.ts's memory.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { ControlError, control, setUnauthorizedHandler } from "@/lib/control";
import type { Operator } from "@/lib/control";

export interface SessionState {
  operator: Operator | null;
  /** False until the first session probe has answered. */
  ready: boolean;
  /** Set when the probe itself failed for a reason other than "not signed in". */
  error: Error | null;
  signIn: (id: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [operator, setOperator] = useState<Operator | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let alive = true;
    setUnauthorizedHandler(() => setOperator(null));
    control
      .session()
      .then((info) => {
        if (alive) setOperator(info.operator);
      })
      .catch((cause: unknown) => {
        if (!alive) return;
        // 401 is the ordinary "nobody signed in"; anything else is named, never hidden.
        if (!(cause instanceof ControlError && cause.status === 401)) {
          setError(cause instanceof Error ? cause : new Error(String(cause)));
        }
      })
      .finally(() => {
        if (alive) setReady(true);
      });
    return () => {
      alive = false;
      setUnauthorizedHandler(null);
    };
  }, []);

  const signIn = useCallback(async (id: string, password: string) => {
    const info = await control.signIn(id, password);
    setError(null);
    setOperator(info.operator);
  }, []);

  const signOut = useCallback(async () => {
    try {
      await control.signOut();
    } finally {
      // Even if the server could not be told, this tab no longer acts as the operator.
      setOperator(null);
    }
  }, []);

  const value = useMemo(
    () => ({ operator, ready, error, signIn, signOut }),
    [operator, ready, error, signIn, signOut],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession needs a SessionProvider above it");
  return value;
}

/** Where to go after signing in. Only a path that starts with a single `/` is followed: `//evil`
 *  (protocol-relative), `/\evil`, `https://…` and anything else fall back to `/`. */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return "/";
  if (/[\u0000-\u001f]/.test(next)) return "/";
  return next;
}
