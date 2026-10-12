import { useEffect, useRef, useState } from "react";
import type { FormEvent, InputHTMLAttributes, ReactNode, Ref } from "react";
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
const GRID = "min-[900px]:grid min-[900px]:grid-cols-[minmax(0,1.1fr)_minmax(0,.8fr)_minmax(0,.7fr)_minmax(0,1.1fr)_minmax(0,.6fr)_minmax(0,1.6fr)] min-[900px]:gap-x-4";

function asError(cause: unknown): Error {
  return cause instanceof Error ? cause : new Error(String(cause));
}

function isReauth(error: Error | null): boolean {
  return error instanceof ControlError && error.status === 403 && error.code === "REAUTH";
}

function Failure({ error, describedId }: { error: Error; describedId: string }) {
  const { t } = useLocale();
  if (isReauth(error)) {
    return <p id={describedId} role="alert" className="text-sm text-red-700 dark:text-red-400">{t("auth.people.reauth")}</p>;
  }
  return <ErrorState error={error} context="people" />;
}

/** A password field. `temporary` marks a password someone else will receive: password managers
 *  are told not to fill or save it (it is not this person's login). */
function PasswordInput({ label, value, onChange, autoComplete, temporary = false, inputRef, invalid, describedBy }: {
  label: string; value: string; onChange: (v: string) => void; autoComplete: string;
  temporary?: boolean; inputRef?: Ref<HTMLInputElement>; invalid?: boolean; describedBy?: string;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-sm font-medium">
      {label}
      <input
        ref={inputRef}
        type="password" value={value} required
        autoComplete={temporary ? "off" : autoComplete}
        {...(temporary ? { name: "temporary", "data-1p-ignore": true, "data-lpignore": "true" } : {})}
        aria-invalid={invalid ? true : undefined}
        aria-describedby={describedBy}
        onChange={(e) => onChange(e.target.value)} className={inputClass}
      />
    </label>
  );
}

function ActionForm({ person, action, label, formId, onDone, onCancel }: {
  person: Person; action: PersonAction; label: string; formId: string; onDone: () => void; onCancel: () => void;
}) {
  const { t } = useLocale();
  const session = useSession();
  const [password, setPassword] = useState("");
  const [extra, setExtra] = useState(action === "email" ? (person.email ?? "") : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  // Opening the form puts the cursor on its first field.
  useEffect(() => {
    formRef.current?.querySelector<HTMLInputElement>("input")?.focus();
  }, []);
  // A wrong password sends the cursor back to the password field.
  useEffect(() => {
    if (isReauth(error)) passwordRef.current?.focus();
  }, [error]);

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
      // Their own row changed: ask who I am now (a demoted admin loses this page at once).
      if (person.id === session.operator?.id) await session.recheck();
      onDone();
    } catch (cause) {
      const failure = asError(cause);
      setError(failure);
      if (failure instanceof ControlError && failure.code === "FORBIDDEN") void session.recheck();
    } finally {
      setPassword("");
      if (action === "password") setExtra("");
      setBusy(false);
    }
  }

  const reauth = isReauth(error);
  const describedId = `${formId}-reauth`;
  return (
    <form ref={formRef} id={formId} onSubmit={submit} aria-label={label} className="mt-3 flex max-w-xl min-w-0 flex-col gap-3 rounded-lg border border-border p-3">
      <p className="text-sm font-medium">{label}</p>
      {action === "password" ? (
        <PasswordInput label={t("auth.people.newTemp")} value={extra} onChange={setExtra} autoComplete="off" temporary />
      ) : null}
      {action === "email" ? (
        <label className="flex min-w-0 flex-col gap-1 text-sm font-medium">
          {t("auth.people.newEmail")}
          <input type="email" value={extra} onChange={(e) => setExtra(e.target.value)} autoComplete="off" className={inputClass} />
        </label>
      ) : null}
      <PasswordInput
        label={t("auth.people.yourPassword")} value={password} onChange={setPassword}
        autoComplete="current-password" inputRef={passwordRef}
        invalid={reauth} describedBy={reauth ? describedId : undefined}
      />
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={busy || !password || (action === "password" && !extra)} className={primaryClass}>
          {busy ? t("auth.people.working") : t("auth.people.confirm")}
        </button>
        <button type="button" onClick={onCancel} className={quietClass}>{t("auth.people.cancel")}</button>
      </div>
      {error ? <Failure error={error} describedId={describedId} /> : null}
    </form>
  );
}

function AddForm({ onAdded }: { onAdded: () => void }) {
  const { t } = useLocale();
  const session = useSession();
  const passwordRef = useRef<HTMLInputElement>(null);
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
      const failure = asError(cause);
      setError(failure);
      if (failure instanceof ControlError && failure.code === "FORBIDDEN") void session.recheck();
    } finally {
      setPassword("");
      setTemporary("");
      setBusy(false);
    }
  }

  useEffect(() => {
    if (isReauth(error)) passwordRef.current?.focus();
  }, [error]);
  const reauth = isReauth(error);

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
        <PasswordInput label={t("auth.people.newTemporary")} value={temporary} onChange={setTemporary} autoComplete="off" temporary />
        <PasswordInput
          label={t("auth.people.yourPassword")} value={password} onChange={setPassword}
          autoComplete="current-password" inputRef={passwordRef}
          invalid={reauth} describedBy={reauth ? "people-add-reauth" : undefined}
        />
        <div>
          <button type="submit" disabled={busy || !id.trim() || !name.trim() || !temporary || !password} className={primaryClass}>
            {busy ? t("auth.people.working") : t("auth.people.addSubmit")}
          </button>
        </div>
      </form>
      <p role="status" className="text-sm">{created ? t("auth.people.created") : ""}</p>
      {error ? <Failure error={error} describedId="people-add-reauth" /> : null}
    </section>
  );
}

function Directory({ myId }: { myId: string }) {
  const { t } = useLocale();
  const session = useSession();
  const list = useApi(() => control.people(), []);
  const [open, setOpen] = useState<{ id: string; action: PersonAction } | null>(null);
  const [restore, setRestore] = useState<{ id: string; action: PersonAction } | null>(null);
  const toggles = useRef(new Map<string, HTMLButtonElement>());

  // A 403 FORBIDDEN means the ledger no longer says admin: ask who I am now.
  const forbidden = list.error instanceof ControlError && list.error.code === "FORBIDDEN";
  useEffect(() => {
    if (forbidden) void session.recheck();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [forbidden]);

  // When a form closes, the cursor returns to the button that opened it (or the row's first button).
  useEffect(() => {
    if (open !== null || restore === null) return;
    const exact = toggles.current.get(`${restore.id}:${restore.action}`);
    const sibling = [...toggles.current.entries()].find(([key]) => key.startsWith(`${restore.id}:`))?.[1];
    (exact ?? sibling)?.focus();
    setRestore(null);
  }, [open, restore]);

  function close() {
    if (open) setRestore(open);
    setOpen(null);
  }

  function actions(person: Person): Array<{ action: PersonAction; label: string }> {
    const own = person.id === myId;
    return [
      ...(person.enabled
        ? own ? [] : [{ action: "disable" as const, label: t("auth.people.disable") }]
        : [{ action: "enable" as const, label: t("auth.people.enable") }]),
      // Their own password is changed from My account, where the current one is asked for.
      ...(own ? [] : [{ action: "password" as const, label: t("auth.people.tempPassword") }]),
      { action: "email", label: t("auth.people.changeEmail") },
      { action: "role", label: person.role === "admin" ? t("auth.people.makeOperator") : t("auth.people.makeAdmin") },
    ];
  }

  // The labels beside each value are for the stacked look under 900 px; the header row below
  // names the columns for assistive technology, so the visible labels are hidden from it.
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
            <div role="row" className={`sr-only border-b border-border pb-2 text-xs font-medium text-muted-foreground min-[900px]:not-sr-only ${GRID}`}>
              <div role="columnheader">{t("auth.people.name")}</div>
              <div role="columnheader">{t("auth.people.id")}</div>
              <div role="columnheader">{t("auth.people.role")}</div>
              <div role="columnheader">{t("auth.people.email")}</div>
              <div role="columnheader">{t("auth.people.state")}</div>
              <div role="columnheader">{t("auth.people.actions")}</div>
            </div>
            {list.data.people.map((person) => {
              const mine = open?.id === person.id ? open : null;
              const own = person.id === myId;
              const formId = `people-form-${person.id}`;
              return (
                <div key={person.id} className="min-w-0 border-b border-border py-3 last:border-b-0">
                  <div role="row" aria-label={person.name} className={`flex min-w-0 flex-col gap-1 ${GRID}`}>
                    {cell(t("auth.people.name"), <>{person.name}{own ? <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-xs">{t("auth.people.you")}</span> : null}</>, "font-medium")}
                    {cell(t("auth.people.id"), person.id, "font-mono")}
                    {cell(t("auth.people.role"), person.role === "admin" ? t("auth.people.roleAdmin") : t("auth.people.roleOperator"))}
                    {cell(t("auth.people.email"), person.email ?? t("auth.people.emailNone"))}
                    {cell(t("auth.people.state"), person.enabled ? t("auth.people.active") : t("auth.people.disabled"))}
                    <div role="cell" className="mt-2 flex min-w-0 flex-col gap-2 min-[900px]:mt-0">
                      <div className="flex flex-wrap gap-2">
                        {actions(person).map(({ action, label }) => {
                          const expanded = mine?.action === action;
                          return (
                            <button
                              key={action}
                              type="button"
                              ref={(node) => {
                                const key = `${person.id}:${action}`;
                                if (node) toggles.current.set(key, node);
                                else toggles.current.delete(key);
                              }}
                              aria-label={t("auth.people.actionFor", { action: label, name: person.name })}
                              aria-expanded={expanded}
                              aria-controls={expanded ? formId : undefined}
                              onClick={() => (expanded ? close() : setOpen({ id: person.id, action }))}
                              className={quietClass}
                            >
                              {label}
                            </button>
                          );
                        })}
                      </div>
                      {own ? <p className="text-[13px] text-muted-foreground">{t("auth.people.ownPassword")}</p> : null}
                    </div>
                  </div>
                  {mine ? (
                    <ActionForm
                      key={`${person.id}-${mine.action}`}
                      person={person}
                      action={mine.action}
                      formId={formId}
                      label={t("auth.people.actionFor", {
                        action: actions(person).find((a) => a.action === mine.action)?.label ?? "",
                        name: person.name,
                      })}
                      onDone={() => { close(); list.reload(); }}
                      onCancel={close}
                    />
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : null}
      </section>
      <AddForm onAdded={() => list.reload()} />
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
