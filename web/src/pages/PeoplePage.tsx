import { useState } from "react";
import type { FormEvent, InputHTMLAttributes, ReactNode } from "react";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { cardClass, inputClass, primaryClass, quietClass } from "@/components/wizard/stepTypes";
import { useApi } from "@/hooks/useApi";
import { ControlError, control } from "@/lib/control";
import type { Person, PersonAction } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import { useSession } from "@/lib/session";

// People (admins). The server checks the role in the ledger on every request; this page only
// spares a non-admin the 403. Every action asks for the acting admin's own password, and no
// password is kept in state after a submit, whether it worked or not. The server's sentence for
// a refusal (the last active admin cannot be disabled or demoted) is shown as given.
const GRID = "min-[900px]:grid min-[900px]:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,.8fr)_minmax(0,1.4fr)_minmax(0,.7fr)] min-[900px]:gap-x-4";

function asError(cause: unknown): Error {
  return cause instanceof Error ? cause : new Error(String(cause));
}

function isReauth(error: Error | null): boolean {
  return error instanceof ControlError && error.status === 403 && error.code === "REAUTH";
}

function Failure({ error }: { error: Error }) {
  const { t } = useLocale();
  if (isReauth(error)) {
    return <p role="alert" className="text-sm text-red-700 dark:text-red-400">{t("auth.people.reauth")}</p>;
  }
  return <ErrorState error={error} context="people" />;
}

function PasswordInput({ label, value, onChange, autoComplete }: {
  label: string; value: string; onChange: (v: string) => void; autoComplete: string;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-sm font-medium">
      {label}
      <input
        type="password" value={value} required autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)} className={inputClass}
      />
    </label>
  );
}

function ActionForm({ person, action, label, onDone, onCancel }: {
  person: Person; action: PersonAction; label: string; onDone: () => void; onCancel: () => void;
}) {
  const { t } = useLocale();
  const [password, setPassword] = useState("");
  const [extra, setExtra] = useState(action === "email" ? (person.email ?? "") : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const body: Record<string, string> = { password };
    if (action === "password") body.new_password = extra;
    if (action === "email") body.email = extra;
    if (action === "role") body.role = person.role === "admin" ? "operator" : "admin";
    try {
      await control.personAct(person.id, action, body);
      onDone();
    } catch (cause) {
      setError(asError(cause));
    } finally {
      setPassword("");
      if (action === "password") setExtra("");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} aria-label={label} className="mt-3 flex max-w-xl min-w-0 flex-col gap-3 rounded-lg border border-border p-3">
      <p className="text-sm font-medium">{label}</p>
      {action === "password" ? (
        <PasswordInput label={t("auth.people.newTemp")} value={extra} onChange={setExtra} autoComplete="new-password" />
      ) : null}
      {action === "email" ? (
        <label className="flex min-w-0 flex-col gap-1 text-sm font-medium">
          {t("auth.people.newEmail")}
          <input type="email" value={extra} onChange={(e) => setExtra(e.target.value)} autoComplete="off" className={inputClass} />
        </label>
      ) : null}
      <PasswordInput label={t("auth.people.yourPassword")} value={password} onChange={setPassword} autoComplete="current-password" />
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={busy || !password || (action === "password" && !extra)} className={primaryClass}>
          {busy ? t("auth.people.working") : t("auth.people.confirm")}
        </button>
        <button type="button" onClick={onCancel} className={quietClass}>{t("auth.people.cancel")}</button>
      </div>
      {error ? <Failure error={error} /> : null}
    </form>
  );
}

function AddForm({ onAdded }: { onAdded: () => void }) {
  const { t } = useLocale();
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("operator");
  const [temporary, setTemporary] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [created, setCreated] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setCreated(false);
    try {
      await control.createPerson({
        password, id: id.trim(), name: name.trim(), email: email.trim(), role, temporary_password: temporary,
      });
      setId("");
      setName("");
      setEmail("");
      setRole("operator");
      setCreated(true);
      onAdded();
    } catch (cause) {
      setError(asError(cause));
    } finally {
      setPassword("");
      setTemporary("");
      setBusy(false);
    }
  }

  const text = (label: string, value: string, set: (v: string) => void, extra: InputHTMLAttributes<HTMLInputElement> = {}) => (
    <label className="flex min-w-0 flex-col gap-1 text-sm font-medium">
      {label}
      <input value={value} onChange={(e) => set(e.target.value)} className={inputClass} {...extra} />
    </label>
  );

  return (
    <section className={`${cardClass} flex flex-col gap-4`} aria-labelledby="people-add">
      <h2 id="people-add" className="text-base font-semibold">{t("auth.people.add")}</h2>
      <form onSubmit={submit} aria-labelledby="people-add" className="grid max-w-xl min-w-0 gap-4">
        <div className="flex min-w-0 flex-col gap-1">
          {text(t("auth.people.newId"), id, setId, {
            required: true, autoComplete: "off", maxLength: 64, "aria-describedby": "people-id-hint",
          })}
          <p id="people-id-hint" className="text-[13px] text-muted-foreground">{t("auth.people.idHint")}</p>
        </div>
        {text(t("auth.people.newName"), name, setName, { required: true, autoComplete: "off" })}
        {text(t("auth.people.newEmailField"), email, setEmail, { type: "email", autoComplete: "off" })}
        <label className="flex min-w-0 flex-col gap-1 text-sm font-medium">
          {t("auth.people.newRole")}
          <select value={role} onChange={(e) => setRole(e.target.value)} className={inputClass}>
            <option value="operator">{t("auth.people.roleOperator")}</option>
            <option value="admin">{t("auth.people.roleAdmin")}</option>
          </select>
        </label>
        <PasswordInput label={t("auth.people.newTemporary")} value={temporary} onChange={setTemporary} autoComplete="new-password" />
        <PasswordInput label={t("auth.people.yourPassword")} value={password} onChange={setPassword} autoComplete="current-password" />
        <div>
          <button type="submit" disabled={busy || !id.trim() || !name.trim() || !temporary || !password} className={primaryClass}>
            {busy ? t("auth.people.working") : t("auth.people.addSubmit")}
          </button>
        </div>
      </form>
      {created ? <p role="status" className="text-sm">{t("auth.people.created")}</p> : null}
      {error ? <Failure error={error} /> : null}
    </section>
  );
}

function Directory({ myId }: { myId: string }) {
  const { t } = useLocale();
  const [version, setVersion] = useState(0);
  const list = useApi(() => control.people(), [version]);
  const [open, setOpen] = useState<{ id: string; action: PersonAction } | null>(null);
  const reload = () => setVersion((v) => v + 1);

  function actions(person: Person): Array<{ action: PersonAction; label: string }> {
    const own = person.id === myId;
    return [
      ...(person.enabled
        ? own ? [] : [{ action: "disable" as const, label: t("auth.people.disable") }]
        : [{ action: "enable" as const, label: t("auth.people.enable") }]),
      { action: "password", label: t("auth.people.tempPassword") },
      { action: "email", label: t("auth.people.changeEmail") },
      { action: "role", label: person.role === "admin" ? t("auth.people.makeOperator") : t("auth.people.makeAdmin") },
    ];
  }

  const cell = (label: string, children: ReactNode, cls = "") => (
    <div role="cell" className={`flex min-w-0 gap-2 min-[900px]:block ${cls}`}>
      <span aria-hidden="true" className="w-20 shrink-0 text-xs text-muted-foreground min-[900px]:hidden">{label}</span>
      <span className="min-w-0 break-words">{children}</span>
    </div>
  );

  return (
    <>
      <section className={`${cardClass} flex min-w-0 flex-col gap-3`} aria-labelledby="people-list">
        <h2 id="people-list" className="text-base font-semibold">{t("auth.people.list")}</h2>
        {list.error ? <ErrorState error={list.error} context="people" /> : null}
        {list.pending ? <Pending label={t("auth.people.loading")} /> : null}
        {list.data ? (
          <div role="table" aria-labelledby="people-list" className="flex min-w-0 flex-col text-sm">
            <div role="row" className={`hidden border-b border-border pb-2 text-xs font-medium text-muted-foreground ${GRID}`}>
              <div role="columnheader">{t("auth.people.name")}</div>
              <div role="columnheader">{t("auth.people.id")}</div>
              <div role="columnheader">{t("auth.people.role")}</div>
              <div role="columnheader">{t("auth.people.email")}</div>
              <div role="columnheader">{t("auth.people.state")}</div>
            </div>
            {list.data.people.map((person) => {
              const mine = open?.id === person.id ? open : null;
              return (
                <div key={person.id} role="row" aria-label={person.name} className="min-w-0 border-b border-border py-3 last:border-b-0">
                  <div className={`flex min-w-0 flex-col gap-1 ${GRID}`}>
                    {cell(t("auth.people.name"), <>{person.name}{person.id === myId ? <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-xs">{t("auth.people.you")}</span> : null}</>, "font-medium")}
                    {cell(t("auth.people.id"), person.id, "font-mono")}
                    {cell(t("auth.people.role"), person.role === "admin" ? t("auth.people.roleAdmin") : t("auth.people.roleOperator"))}
                    {cell(t("auth.people.email"), person.email ?? t("auth.people.emailNone"))}
                    {cell(t("auth.people.state"), person.enabled ? t("auth.people.active") : t("auth.people.disabled"))}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {actions(person).map(({ action, label }) => (
                      <button
                        key={action}
                        type="button"
                        aria-label={t("auth.people.actionFor", { action: label, name: person.name })}
                        aria-expanded={mine?.action === action}
                        onClick={() => setOpen(mine?.action === action ? null : { id: person.id, action })}
                        className={quietClass}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  {mine ? (
                    <ActionForm
                      key={`${person.id}-${mine.action}`}
                      person={person}
                      action={mine.action}
                      label={t("auth.people.actionFor", {
                        action: actions(person).find((a) => a.action === mine.action)?.label ?? "",
                        name: person.name,
                      })}
                      onDone={() => { setOpen(null); reload(); }}
                      onCancel={() => setOpen(null)}
                    />
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : null}
      </section>
      <AddForm onAdded={reload} />
    </>
  );
}

export default function PeoplePage() {
  const { t } = useLocale();
  const session = useSession();
  return (
    <div className="flex min-w-0 max-w-4xl flex-col gap-6">
      <h1 className="text-[40px] leading-tight">{t("auth.people.title")}</h1>
      {!session.ready ? <Pending label={t("auth.people.loading")} /> : null}
      {session.ready && session.operator?.role !== "admin" ? (
        <p className="text-sm text-muted-foreground">{t("auth.people.adminOnly")}</p>
      ) : null}
      {session.ready && session.operator?.role === "admin" ? <Directory myId={session.operator.id} /> : null}
    </div>
  );
}
