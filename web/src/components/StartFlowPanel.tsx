import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import ErrorState from "@/components/ErrorState";
import { control } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import { useSession } from "@/lib/session";

const ROUND = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

export default function StartFlowPanel({ project }: { project: string }) {
  const { t } = useLocale();
  const session = useSession();
  const navigate = useNavigate();
  const [title, setTitle] = useState(() => t("startFlow.defaultTitle"));
  const [round, setRound] = useState(() => `first-${new Date().toISOString().slice(0, 10)}`);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [validation, setValidation] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const problem = !title.trim() || title.length > 120 ? t("startFlow.titleInvalid")
      : !ROUND.test(round) ? t("startFlow.roundInvalid") : null;
    setValidation(problem);
    if (problem) return;
    setBusy(true);
    setError(null);
    try {
      const result = await control.startFlow(project, { title, round });
      navigate(`/p/${encodeURIComponent(project)}/f/${encodeURIComponent(result.flow_id)}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
      setBusy(false);
    }
  }

  return (
    <section aria-label={t("startFlow.heading")} className="rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
      <h3 className="text-base font-semibold">{t("startFlow.heading")}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{t("startFlow.noRequest")}</p>
      {!session.ready ? <p>{t("shell.checking")}</p> : session.operator === null ? (
        <Link to={`/login?next=${encodeURIComponent(`/p/${encodeURIComponent(project)}`)}`}
              className="text-blue-600 hover:underline dark:text-blue-400">{t("startFlow.signIn")}</Link>
      ) : (
        <form onSubmit={submit} noValidate className="mt-4 flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">{t("startFlow.title")}
            <input value={title} maxLength={121} disabled={busy} onChange={(e) => setTitle(e.target.value)}
                   className="min-h-11 rounded-md border bg-background px-3" />
          </label>
          <label className="flex flex-col gap-1 text-sm">{t("startFlow.round")}
            <input value={round} disabled={busy} onChange={(e) => setRound(e.target.value)}
                   className="min-h-11 rounded-md border bg-background px-3" />
          </label>
          {validation ? <p role="alert" className="text-sm text-not-obtained">{validation}</p> : null}
          {error ? <ErrorState error={error} context="flow" /> : null}
          <button type="submit" disabled={busy} className="min-h-11 self-start rounded-md bg-teal-600 px-4 text-sm font-medium text-white disabled:opacity-50">
            {busy ? t("startFlow.creating") : t("startFlow.create")}
          </button>
        </form>
      )}
    </section>
  );
}
