import { useState } from "react";
import type { FormEvent } from "react";
import { Navigate, useSearchParams } from "react-router";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useLocale } from "@/lib/i18n";
import { useSession, safeNext } from "@/lib/session";

// F1: operators are declared on the CLI (`claimstone operator add`), so this page only signs
// in. The server's sentence is shown as given — including the RATE_LIMITED one — and an
// unknown id and a wrong password look the same because the server says the same thing.
// After signing in the operator returns to `?next=`, accepted only as a path that starts
// with a single `/` (`safeNext`).
export default function LoginPage() {
  const { t } = useLocale();
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
    <div className="login-brand relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-rail px-4 py-12 text-rail-foreground">
      <div className="login-grid pointer-events-none absolute inset-0" aria-hidden="true" />
      <div className="relative flex w-full max-w-sm flex-col items-center gap-8">
        <div className="flex flex-col items-center gap-5 text-center">
          <svg viewBox="0 0 64 64" role="img" aria-label="Claimstone" className="login-stone h-40 w-40 min-[900px]:h-56 min-[900px]:w-56">
            <path d="M11 26 L37 11 L56 22 L53 47 L19 54 L8 41 Z" fill="#3d4853" stroke="#3d4853" strokeWidth="7" strokeLinejoin="round" />
            <path className="login-streak" d="M16 43 L47 25" stroke="#f5a524" strokeWidth="8" strokeLinecap="round" fill="none" pathLength="1" />
            <path className="login-streak-soft" d="M25 49 L38 41.5" stroke="#f5a524" strokeOpacity=".55" strokeWidth="3" strokeLinecap="round" fill="none" pathLength="1" />
          </svg>
          <span className="text-3xl font-semibold tracking-tight">Claimstone</span>
          <p className="max-w-xs text-sm leading-relaxed text-rail-muted">{t("auth.login.tagline")}</p>
        </div>
        <div className="w-full rounded-2xl border border-rail-border bg-card p-6 text-card-foreground shadow-2xl">
          <h1 className="text-2xl leading-tight">{t("auth.login.title")}</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">{t("auth.login.lede")}</p>
          {!session.ready ? <Pending label={t("auth.login.checking")} /> : null}
          <form onSubmit={submit} className="mt-5 flex flex-col gap-4">
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              {t("auth.login.id")}
              <input
                name="id"
                value={id}
                onChange={(e) => setId(e.target.value)}
                autoComplete="username"
                required
                className="min-h-12 rounded-lg border border-border bg-background px-3 font-mono text-sm font-normal"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              {t("auth.login.password")}
              <input
                name="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                className="min-h-12 rounded-lg border border-border bg-background px-3 text-sm font-normal"
              />
            </label>
            <button
              type="submit"
              disabled={busy || !id.trim() || !password}
              className="mt-1 min-h-12 rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground hover:brightness-95 disabled:opacity-50"
            >
              {busy ? t("auth.login.busy") : t("auth.login.submit")}
            </button>
          </form>
          {error ? <ErrorState error={error} context="sign-in" /> : null}
        </div>
        <ul className="flex flex-col items-center gap-1.5 text-center text-xs text-rail-muted">
          {(["p1", "p2", "p3"] as const).map((key) => (
            <li key={key}>{t(`auth.login.${key}`)}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
