import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { control } from "@/lib/control";
import type { DraftSummary } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import { useSession } from "@/lib/session";

// The operator's own drafts: continue, discard, or start a new one. Drafts are private; the server
// never lists another operator's. Signed out, the page offers the sign-in link and no write control.
export default function NewProjectsPage() {
  const session = useSession();
  const { t } = useLocale();
  if (!session.ready) return <Pending label="…" />;
  if (!session.operator) {
    return (
      <section className="flex flex-col gap-3 pt-6">
        <h1 className="text-[44px] leading-tight">{t("wizard.title")}</h1>
        <p className="text-sm text-muted-foreground">
          {t("wizard.signIn")}{" "}
          <Link className="underline" to={`/login?next=${encodeURIComponent("/new")}`}>{t("wizard.signInLink")}</Link>
        </p>
      </section>
    );
  }
  return <Drafts />;
}

function nextStep(draft: DraftSummary): number {
  for (const n of [1, 2, 3]) if (!draft.steps_saved.includes(n)) return n;
  return 4;
}

function Drafts() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const list = useApi(() => control.newDrafts(), []);
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState<string | null>(null); // the draft whose Discard awaits an answer
  const [discarding, setDiscarding] = useState<string[]>([]); // drafts with a discard in flight
  const inFlight = useRef(new Set<string>()); // synchronous guard: state lags behind a fast double click

  async function start() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const made = await control.newStart();
      navigate(`/new/${encodeURIComponent(made.draft_id)}/1`);
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusy(false);
    }
  }

  async function discard(draft: DraftSummary) {
    if (inFlight.current.has(draft.draft_id)) return;
    inFlight.current.add(draft.draft_id);
    setDiscarding((held) => [...held, draft.draft_id]);
    setError(null);
    try {
      await control.newDiscard(draft.draft_id, draft.revision);
      list.reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      inFlight.current.delete(draft.draft_id);
      setDiscarding((held) => held.filter((id) => id !== draft.draft_id));
      setAsking(null);
    }
  }

  return (
    <section className="flex flex-col gap-5">
      <header>
        <h1 className="text-[44px] leading-tight">{t("wizard.title")}</h1>
        <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">{t("wizard.lede")}</p>
      </header>
      <div>
        <button
          type="button"
          onClick={() => void start()}
          disabled={busy}
          className="min-h-11 rounded-lg bg-rail px-4 text-sm font-semibold text-rail-foreground disabled:opacity-50"
        >
          {t("wizard.drafts.start")}
        </button>
      </div>
      {error ? <ErrorState error={error} context="drafts" /> : null}
      <section className="rounded-xl bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
        <h2 className="text-base font-semibold">{t("wizard.drafts.title")}</h2>
        {list.error ? (
          <ErrorState error={list.error} context="drafts" />
        ) : list.pending || !list.data ? (
          <Pending label="…" />
        ) : list.data.drafts.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">{t("wizard.drafts.empty")}</p>
        ) : (
          <ul className="mt-3 flex flex-col gap-2">
            {list.data.drafts.map((draft) => (
              <li key={draft.draft_id} className="flex flex-wrap items-center gap-3 rounded-lg border border-border p-3 text-sm">
                {/* the project name is what the operator typed: shown as typed, never translated */}
                <span className="font-mono">{draft.project_name ?? t("wizard.drafts.untitled")}</span>
                <span className="text-muted-foreground">{t(`wizard.drafts.status.${draft.status}`)}</span>
                <span className="text-muted-foreground">{t("wizard.drafts.stepsSaved", { n: draft.steps_saved.length })}</span>
                <span className="ml-auto flex gap-2">
                  {draft.status === "open" ? (
                    <>
                      <Link className="underline" to={`/new/${encodeURIComponent(draft.draft_id)}/${nextStep(draft)}`}>
                        {t("wizard.drafts.resume")}
                      </Link>
                      {asking === draft.draft_id ? (
                        <span className="flex items-center gap-2">
                          <span>{t("wizard.drafts.discardSure")}</span>
                          <button
                            type="button"
                            className="underline"
                            disabled={discarding.includes(draft.draft_id)}
                            onClick={() => void discard(draft)}
                          >
                            {t("wizard.drafts.discardYes")}
                          </button>
                          <button
                            type="button"
                            className="underline"
                            disabled={discarding.includes(draft.draft_id)}
                            onClick={() => setAsking(null)}
                          >
                            {t("wizard.drafts.discardNo")}
                          </button>
                        </span>
                      ) : (
                        <button type="button" className="underline" onClick={() => setAsking(draft.draft_id)}>
                          {t("wizard.drafts.discard")}
                        </button>
                      )}
                    </>
                  ) : null}
                  {draft.status === "created" && draft.project ? (
                    <Link className="underline" to={`/p/${encodeURIComponent(draft.project)}`}>
                      {t("wizard.drafts.openProject")}
                    </Link>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}
