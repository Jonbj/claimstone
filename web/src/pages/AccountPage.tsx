import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { cardClass, inputClass, primaryClass, quietClass } from "@/components/wizard/stepTypes";
import { useApi } from "@/hooks/useApi";
import { ControlError, control } from "@/lib/control";
import { formatUtc } from "@/lib/datetime";
import { useLocale } from "@/lib/i18n";
import { useSession } from "@/lib/session";

// My account: who I am, change my password, and my sessions. The only client-side password rule
// is that the two new values match; the server owns every other rule and its sentence is shown
// as given. A password is never kept in state after a request has been sent.
function asError(cause: unknown): Error {
  return cause instanceof Error ? cause : new Error(String(cause));
}

function PasswordSection({ onChanged }: { onChanged: () => void }) {
  const { t } = useLocale();
  const session = useSession();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [mismatch, setMismatch] = useState(false);
  const [reauth, setReauth] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault(); // the CSP has form-action 'none'
    setDone(false);
    setError(null);
    setReauth(false);
    if (next !== again) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    setBusy(true);
    try {
      await control.changePassword(current, next);
      setCurrent("");
      setNext("");
      setAgain("");
      setDone(true);
      await session.recheck(); // a forced change clears here
      onChanged();
    } catch (cause) {
      setCurrent("");
      if (cause instanceof ControlError && cause.status === 403 && cause.code === "REAUTH") {
        setReauth(true); // the typed new value stays: only the current password is fixed
      } else {
        setError(asError(cause));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={`${cardClass} flex flex-col gap-4`} aria-labelledby="account-password">
      <h2 id="account-password" className="text-base font-semibold">{t("auth.account.passwordTitle")}</h2>
      <form onSubmit={submit} className="flex max-w-md flex-col gap-4">
        <div className="flex flex-col gap-1">
        <label className="flex flex-col gap-1 text-sm font-medium">
          {t("auth.account.current")}
          <input
            type="password" name="current" value={current} autoComplete="current-password" required
            onChange={(e) => setCurrent(e.target.value)}
            aria-invalid={reauth ? true : undefined}
            aria-describedby={reauth ? "account-reauth" : undefined}
            className={inputClass}
          />
        </label>
          {reauth ? (
            <span id="account-reauth" role="alert" className="text-[13px] text-red-700 dark:text-red-400">
              {t("auth.account.reauth")}
            </span>
          ) : null}
        </div>
        <label className="flex flex-col gap-1 text-sm font-medium">
          {t("auth.account.new")}
          <input
            type="password" name="new" value={next} autoComplete="new-password" required
            onChange={(e) => setNext(e.target.value)} className={inputClass}
          />
        </label>
        <div className="flex flex-col gap-1">
        <label className="flex flex-col gap-1 text-sm font-medium">
          {t("auth.account.again")}
          <input
            type="password" name="again" value={again} autoComplete="new-password" required
            onChange={(e) => setAgain(e.target.value)}
            aria-invalid={mismatch ? true : undefined}
            aria-describedby={mismatch ? "account-mismatch" : undefined}
            className={inputClass}
          />
        </label>
          {mismatch ? (
            <span id="account-mismatch" role="alert" className="text-[13px] text-red-700 dark:text-red-400">
              {t("auth.account.mismatch")}
            </span>
          ) : null}
        </div>
        <button type="submit" disabled={busy || !current || !next || !again} className={primaryClass}>
          {busy ? t("auth.account.changing") : t("auth.account.change")}
        </button>
      </form>
      <p role="status" className="text-sm">{done ? t("auth.account.changed") : ""}</p>
      {error ? <ErrorState error={error} context="password" /> : null}
    </section>
  );
}

function SessionsSection({ changes }: { changes: number }) {
  const { t } = useLocale();
  const list = useApi(() => control.accountSessions(), []);
  // A password change ends the other sessions: fetch the list again (same view, data stays).
  const seen = useRef(changes);
  useEffect(() => {
    if (changes !== seen.current) {
      seen.current = changes;
      list.reload();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [changes]);
  const [busy, setBusy] = useState(false);
  const [ended, setEnded] = useState<number | null>(null);
  const [error, setError] = useState<Error | null>(null);

  async function endOthers() {
    setBusy(true);
    setError(null);
    try {
      const result = await control.endOtherSessions();
      setEnded(result.ended);
      list.reload();
    } catch (cause) {
      setError(asError(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={`${cardClass} flex flex-col gap-4`} aria-labelledby="account-sessions">
      <h2 id="account-sessions" className="text-base font-semibold">{t("auth.account.sessionsTitle")}</h2>
      {list.error ? <ErrorState error={list.error} context="sessions" /> : null}
      {list.pending ? <Pending label={t("auth.account.loading")} /> : null}
      {list.data ? (
        list.data.sessions.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("auth.account.sessionsNone")}</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {list.data.sessions.map((row) => (
              <li key={row.session_id} className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1 rounded-lg border border-border px-3 py-2 text-sm">
                <span>{t("auth.account.sessionStarted", { when: formatUtc(row.created_at) })}</span>
                <span className="text-muted-foreground">
                  {t("auth.account.sessionSeen", { when: formatUtc(row.last_seen) })}
                </span>
                {row.current ? <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium">{t("auth.account.sessionThis")}</span> : null}
              </li>
            ))}
          </ul>
        )
      ) : null}
      <div>
        <button type="button" onClick={() => void endOthers()} disabled={busy} className={quietClass}>
          {t("auth.account.endOthers")}
        </button>
      </div>
      <p role="status" className="text-sm">{ended !== null ? t("auth.account.endedOthers", { n: ended }) : ""}</p>
      {error ? <ErrorState error={error} context="sessions" /> : null}
    </section>
  );
}

export default function AccountPage() {
  const session = useSession();
  // Nothing is fetched before the session is known, nor while signed out (the shell offers Sign in).
  if (!session.ready || !session.operator) return null;
  return <Account id={session.operator.id} forced={session.operator.must_change_password} />;
}

function Account({ id, forced }: { id: string; forced: boolean }) {
  const { t } = useLocale();
  const account = useApi(() => control.account(), [id]);
  const [changes, setChanges] = useState(0);
  const me = account.data?.operator ?? null;

  return (
    <div className="flex min-w-0 max-w-2xl flex-col gap-6">
      <h1 className="text-[40px] leading-tight">{t("auth.account.title")}</h1>
      {forced ? (
        <p role="alert" className="rounded-lg border border-amber-400 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:bg-amber-950/40 dark:text-amber-100">
          {t("auth.account.mustChange")}
        </p>
      ) : null}
      <section className={`${cardClass} flex flex-col gap-3`} aria-labelledby="account-who">
        <h2 id="account-who" className="text-base font-semibold">{t("auth.account.who")}</h2>
        {account.error ? <ErrorState error={account.error} context="account" /> : null}
        {account.pending ? <Pending label={t("auth.account.loading")} /> : null}
        {me ? (
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
            <dt className="text-muted-foreground">{t("auth.account.name")}</dt>
            <dd className="break-words">{me.name}</dd>
            <dt className="text-muted-foreground">{t("auth.account.id")}</dt>
            <dd className="break-all font-mono">{me.id}</dd>
            <dt className="text-muted-foreground">{t("auth.account.role")}</dt>
            <dd>{me.role === "admin" ? t("auth.account.roleAdmin") : t("auth.account.roleOperator")}</dd>
            <dt className="text-muted-foreground">{t("auth.account.email")}</dt>
            <dd className="break-all">{me.email ?? t("auth.account.emailNone")}</dd>
          </dl>
        ) : null}
      </section>
      <PasswordSection onChanged={() => setChanges((n) => n + 1)} />
      {forced ? (
        <p className="text-sm text-muted-foreground">{t("auth.account.sessionsAfterChange")}</p>
      ) : (
        <SessionsSection changes={changes} />
      )}
    </div>
  );
}
