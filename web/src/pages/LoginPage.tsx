import { useState } from "react";
import type { FormEvent } from "react";
import { Navigate, useSearchParams } from "react-router";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useSession, safeNext } from "@/lib/session";

// F1: operators are declared on the CLI (`claimstone operator add`), so this page only signs
// in. The server's sentence is shown as given — including the RATE_LIMITED one — and an
// unknown id and a wrong password look the same because the server says the same thing.
// After signing in the operator returns to `?next=`, accepted only as a path that starts
// with a single `/` (`safeNext`).
export default function LoginPage() {
  const session = useSession();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const [id, setId] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  if (session.operator) return <Navigate to={next} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault(); // the CSP has form-action 'none': a native submit is never wanted
    setBusy(true);
    setError(null);
    try {
      await session.signIn(id.trim(), password);
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mx-auto flex w-full max-w-sm flex-col gap-4 pt-8">
      <h1 className="text-[40px] leading-tight">Sign in</h1>
      <p className="text-sm text-muted-foreground">
        Reading needs no session. Signing, deciding and exporting do.
      </p>
      {!session.ready ? <Pending label="checking the session…" /> : null}
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm font-medium">
          Operator id
          <input
            name="id"
            value={id}
            onChange={(e) => setId(e.target.value)}
            autoComplete="username"
            required
            className="min-h-11 rounded-lg border border-border bg-card px-3 font-mono text-sm font-normal"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">
          Password
          <input
            name="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
            className="min-h-11 rounded-lg border border-border bg-card px-3 text-sm font-normal"
          />
        </label>
        <button
          type="submit"
          disabled={busy || !id.trim() || !password}
          className="min-h-11 rounded-lg bg-rail px-4 text-sm font-semibold text-rail-foreground disabled:opacity-50"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
      {error ? <ErrorState error={error} context="sign-in" /> : null}
    </section>
  );
}
