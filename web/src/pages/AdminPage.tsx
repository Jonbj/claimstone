import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { CHECK_TARGETS, control } from "@/lib/control";
import type { AdminCheckRow, CheckTarget, ControlAdmin } from "@/lib/control";
import { useSession } from "@/lib/session";

// Administration (spec v2.1 F6). Two sources, kept apart:
// - the read API's admin (credential PRESENCE as booleans, configured and available backends,
//   instrument versions), which works with no session;
// - the control API's admin (signed in): the last recorded check per target, a Check button for
//   each, and the credential form.
// Opening this page contacts no service: every check is a button. A credential value is typed
// into a password field, sent once, and the field is cleared after every submit, success or
// failure; it is never rendered back and never kept in storage. The password is asked again.
const card = "rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800";
const primary = "min-h-11 rounded-md bg-teal-600 px-4 text-sm font-medium text-white disabled:opacity-50";
const input = "min-h-11 w-full rounded-md border border-border bg-background px-3 text-sm";

/** The server's own 501 sentence for the paid test call (control.py `_admin_paid_test`). */
export const PAID_TEST_REASON =
  "a paid test call needs the model-call boundary and a cost reservation; it belongs to the " +
  "scheduler's authorized operations, not to a button here";

function CheckLine({ row }: { row: AdminCheckRow | undefined }) {
  if (!row) return <span className="text-muted-foreground">never checked from here</span>;
  return (
    <span>
      {row.ok ? "reachable" : "not reachable"} · {row.recorded_at}
      {row.status !== null ? ` · HTTP ${row.status}` : ""}
      {row.latency_ms !== null ? ` · ${row.latency_ms} ms` : ""}
      {row.detail ? ` · ${row.detail}` : ""}
      <span className="text-muted-foreground"> · by {row.actor}</span>
    </span>
  );
}

function ControlAdminBlock({ data, reload }: { data: ControlAdmin; reload: () => void }) {
  const [checking, setChecking] = useState<CheckTarget | null>(null);
  const [checkError, setCheckError] = useState<Error | null>(null);
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<Error | null>(null);
  const [saved, setSaved] = useState<{ name: string; note: string } | null>(null);

  const targets = CHECK_TARGETS.filter((t) => t in data.check_targets || t in data.checks);

  async function check(target: CheckTarget) {
    if (checking !== null) return;
    setChecking(target);
    setCheckError(null);
    try {
      await control.checkTarget(target);
      reload();
    } catch (cause) {
      setCheckError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setChecking(null);
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (saving || name === "") return;
    setSaving(true);
    setSaveError(null);
    setSaved(null);
    const body = { name, value, password };
    try {
      const answer = await control.setCredential(body);
      setSaved({ name: answer.credential.name, note: answer.credential.note });
      reload();
    } catch (cause) {
      setSaveError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      // Success or failure, the secret and the password do not stay in the page.
      setValue("");
      setPassword("");
      setSaving(false);
    }
  }

  return (
    <>
      <section className={card}>
        <h2 className="text-base font-semibold">Reachability checks</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Each check is one unpaid request, sent only when you press its button.
        </p>
        <ul className="mt-2 divide-y divide-border">
          {targets.map((target) => (
            <li key={target} className="flex flex-wrap items-center gap-3 py-2 text-sm">
              <span className="w-28 font-mono text-xs">{target}</span>
              <span className="flex-1"><CheckLine row={data.checks[target]} /></span>
              <button type="button" disabled={checking !== null} onClick={() => void check(target)}
                      className="min-h-11 rounded-md px-4 text-sm ring-1 ring-gray-300 disabled:opacity-50">
                {checking === target ? "Checking…" : `Check ${target}`}
              </button>
            </li>
          ))}
        </ul>
        {checkError ? <div className="mt-2"><ErrorState error={checkError} context="check" /></div> : null}
        <div className="mt-3">
          <button type="button" disabled title={PAID_TEST_REASON}
                  className="min-h-11 rounded-md px-4 text-sm ring-1 ring-gray-300 opacity-50">
            Paid test call
          </button>
          <p className="mt-1 text-xs text-muted-foreground">Not available: {PAID_TEST_REASON}.</p>
        </div>
      </section>

      <section className={card}>
        <h2 className="text-base font-semibold">Replace a credential</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          The value is written to the host's environment file and never read back. Your password is
          asked again.
        </p>
        <form onSubmit={(e) => void save(e)} className="mt-3 flex max-w-md flex-col gap-3" autoComplete="off">
          <label className="text-sm">
            Credential name
            <select value={name} onChange={(e) => setName(e.target.value)} disabled={saving} className={input}>
              <option value="">Choose a name…</option>
              {Object.keys(data.credentials).map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <label className="text-sm">
            Value
            <input type="password" value={value} autoComplete="off" disabled={saving}
                   onChange={(e) => setValue(e.target.value)} className={input} />
          </label>
          <label className="text-sm">
            Your password
            <input type="password" value={password} autoComplete="current-password" disabled={saving}
                   onChange={(e) => setPassword(e.target.value)} className={input} />
          </label>
          <button type="submit" disabled={saving || name === "" || value === "" || password === ""}
                  className={primary}>
            {saving ? "Saving…" : "Save credential"}
          </button>
        </form>
        {saveError ? <div className="mt-2"><ErrorState error={saveError} context="credential" /></div> : null}
        {saved ? (
          <p className="mt-2 text-sm" role="status">
            <span className="font-mono text-xs">{saved.name}</span> was written. {saved.note}
          </p>
        ) : null}
      </section>
    </>
  );
}

export default function AdminPage() {
  const admin = useApi(() => api.admin(), []);
  const session = useSession();
  const signedIn = session.operator !== null;
  const control_ = useApi<ControlAdmin | null>(
    () => (signedIn ? control.admin() : Promise.resolve(null)), [signedIn]);

  const title = <h1 className="text-[26px]">Administration</h1>;
  const intro = (
    <p className="mt-0.5 text-sm text-muted-foreground">
      What this installation can use. Opening this page sends no request to any service; every check
      is a button.
    </p>
  );
  if (admin.pending) {
    return <section>{title}<Pending label="loading admin…" /></section>;
  }
  if (admin.error) {
    return <section>{title}<ErrorState error={admin.error} context="admin" /></section>;
  }
  const data = admin.data;
  if (!data) return null;
  const instruments = Object.entries(data.instruments).sort(([a], [b]) => a.localeCompare(b));
  const credentials = Object.entries(data.credentials);

  return (
    <section className="flex flex-col gap-5">
      <header>{title}{intro}</header>

      <section className={card}>
        <h2 className="text-base font-semibold">Credentials — presence only</h2>
        {credentials.length === 0 ? (
          <p className="mt-1 text-sm text-muted-foreground">The API lists no credential names.</p>
        ) : credentials.map(([name, present]) => (
          <p key={name} className="mt-1 text-sm">
            <span className="font-mono text-xs">{name}</span>: {present ? "set" : "not set"}
          </p>
        ))}
        <p className="mt-2 text-xs text-muted-foreground">{data.key_rotation_note}</p>
      </section>

      <section className={card}>
        <h2 className="text-base font-semibold">Model backends</h2>
        <p className="mt-1 text-sm">
          configured: {data.backends.configured.length > 0 ? data.backends.configured.join(", ") : "none"}
        </p>
        <p className="mt-1 text-sm">
          available: {data.backends.available.length > 0 ? data.backends.available.join(", ") : "none"}
        </p>
        <p className="mt-2 text-xs text-muted-foreground">{data.backends_note}</p>
      </section>

      {!session.ready ? <Pending label="checking the session…" /> : !signedIn ? (
        <section className={card}>
          <h2 className="text-base font-semibold">Checks and credentials</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Sign in to run a reachability check or replace a credential.{" "}
            <Link to="/login?next=%2Fadmin" className="text-blue-600 hover:underline dark:text-blue-400">
              Sign in
            </Link>
          </p>
        </section>
      ) : control_.error ? (
        <ErrorState error={control_.error} context="control admin" />
      ) : control_.pending || !control_.data ? (
        <Pending label="loading checks…" />
      ) : (
        <ControlAdminBlock data={control_.data} reload={() => { control_.reload(); admin.reload(); }} />
      )}

      <section className={card}>
        <h2 className="text-base font-semibold">Instrument versions</h2>
        {instruments.length === 0 ? (
          <p className="mt-1 text-sm text-muted-foreground">No instrument version is reported.</p>
        ) : instruments.map(([name, version]) => (
          <p key={name} className="mt-1 font-mono text-xs">{name} {version}</p>
        ))}
        <p className="mt-2 text-xs text-muted-foreground">
          Every version the design record must acknowledge; the integrity panel reports whether it does.
        </p>
      </section>
    </section>
  );
}
