import { useState } from "react";
import type { FormEvent } from "react";
import { Navigate, useSearchParams } from "react-router";
import ErrorState from "@/components/ErrorState";
import LogoMark from "@/components/LogoMark";
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
    <div className="grid min-h-screen bg-background text-foreground min-[900px]:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
      <aside className="login-brand relative flex flex-col justify-between gap-10 overflow-hidden bg-rail px-8 py-8 text-rail-foreground min-[900px]:px-14 min-[900px]:py-12">
        <div className="login-grid pointer-events-none absolute inset-0" aria-hidden="true" />
        <div className="relative flex items-center gap-2.5 text-lg font-semibold tracking-tight">
          <LogoMark size={30} stone="#3d4853" />
          <span>Claimstone</span>
        </div>
        <div className="relative flex flex-col gap-8">
          <svg viewBox="0 0 64 64" role="img" aria-label="Claimstone" className="login-stone h-40 w-40 min-[900px]:h-64 min-[900px]:w-64">
            <path d="M11 26 L37 11 L56 22 L53 47 L19 54 L8 41 Z" fill="#3d4853" stroke="#3d4853" strokeWidth="7" strokeLinejoin="round" />
            <path className="login-streak" d="M16 43 L47 25" stroke="#f5a524" strokeWidth="8" strokeLinecap="round" fill="none" pathLength="1" />
            <path className="login-streak-soft" d="M25 49 L38 41.5" stroke="#f5a524" strokeOpacity=".55" strokeWidth="3" strokeLinecap="round" fill="none" pathLength="1" />
          </svg>
          <p className="max-w-md text-2xl font-semibold leading-snug tracking-tight min-[900px]:text-[32px]">
            {t("auth.login.tagline")}
          </p>
        </div>
        <ul className="relative flex flex-col gap-2.5 text-sm text-rail-muted">
          {(["p1", "p2", "p3"] as const).map((key) => (
            <li key={key} className="flex items-start gap-2.5">
              <span aria-hidden="true" className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
              {t(`auth.login.${key}`)}
            </li>
          ))}
        </ul>
      </aside>
      <section className="flex items-center justify-center px-4 py-10 min-[900px]:px-12">
        <div className="flex w-full max-w-sm flex-col gap-5">
          <div>
            <h1 className="text-[32px] leading-tight">{t("auth.login.title")}</h1>
            <p className="mt-1.5 text-sm text-muted-foreground">{t("auth.login.lede")}</p>
          </div>
          {!session.ready ? <Pending label={t("auth.login.checking")} /> : null}
          <form onSubmit={submit} className="flex flex-col gap-4">
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              {t("auth.login.id")}
              <input
                name="id"
                value={id}
                onChange={(e) => setId(e.target.value)}
                autoComplete="username"
                required
                className="min-h-12 rounded-lg border border-border bg-card px-3 font-mono text-sm font-normal"
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
                className="min-h-12 rounded-lg border border-border bg-card px-3 text-sm font-normal"
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
      </section>
    </div>
  );
}
