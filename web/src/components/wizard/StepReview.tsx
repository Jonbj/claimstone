import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { control } from "@/lib/control";
import type { Created, DraftState, Preview } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import { StepHeading } from "./Field";
import { useLeaveWarning } from "./useLeaveWarning";
import { ErrorSummary } from "./problems";
import { explainParams } from "./figures";
import { areaClass, cardClass, primaryClass, quietClass } from "./stepTypes";

const FILES = ["topics.yaml", "questions.yaml", "sources.yaml"] as const;

export interface ReviewProps {
  draftId: string;
  draft: DraftState;
  /** Called with the creation result; the page then shows the created screen. */
  onCreated: (created: Created) => void;
  /** Called after an Advanced save or reset, so the page reloads the draft's revision. */
  onChanged: () => void;
  /** Reports the preview's figures so the explanation panel can quote them. */
  onFigures?: (figures: Preview["figures"]) => void;
  /** Re-reads the draft (stale revision, changed preview). */
  onReload?: () => void;
}

export default function StepReview(props: ReviewProps) {
  const { t } = useLocale();
  const missing = ["1", "2", "3"].filter((n) => !props.draft.steps[n]);
  if (missing.length) {
    return (
      <section className={cardClass}>
        <StepHeading>{t("wizard.step4.title")}</StepHeading>
        <p className="mt-2 text-sm text-muted-foreground">{t("wizard.step4.needSteps")}</p>
        <ul className="mt-2 flex gap-2">
          {missing.map((n) => (
            <li key={n}>
              <Link className="underline" to={`/new/${encodeURIComponent(props.draftId)}/${n}`}>
                {t(`wizard.steps.${n}.name`)}
              </Link>
            </li>
          ))}
        </ul>
      </section>
    );
  }
  return <ReviewForm {...props} />;
}

function ReviewForm({ draftId, draft, onCreated, onChanged, onFigures, onReload }: ReviewProps) {
  const { t } = useLocale();
  const preview = useApi(() => control.newPreview(draftId), [draftId, draft.revision]);
  const [edits, setEdits] = useState<Record<string, string>>({});
  useLeaveWarning(JSON.stringify(edits)); // saving or resetting empties `edits`, which is the baseline
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState<"create" | "files" | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const reload = () => {
    onReload?.();
    preview.reload();
  };

  // Tell the page what the server computed, so the explanation panel can quote it. An effect, not a
  // call during render: setting the parent's state while rendering a child is a React error.
  useEffect(() => {
    if (preview.data) onFigures?.(preview.data.figures);
  }, [preview.data, onFigures]);

  async function run(kind: "create" | "files", work: () => Promise<void>) {
    if (busy) return;
    setBusy(kind);
    setError(null);
    try {
      await work();
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusy(null);
    }
  }

  const resetFiles = () =>
    run("files", async () => {
      await control.newSaveAdvanced(draftId, draft.revision, {});
      setEdits({});
      onChanged();
    });

  if (preview.error) {
    // The preview can fail for a reason only a reset cures (an override frozen on an earlier UTC
    // day), so the reset must not live only inside the form that this error replaces.
    return (
      <div className="flex flex-col gap-3">
        <ErrorState error={preview.error} context="preview" />
        {Object.keys(draft.advanced).length ? (
          <section className={cardClass}>
            <p className="text-[13px] text-muted-foreground">{t("wizard.step4.resetHelp")}</p>
            <ErrorSummary error={error} onReload={reload} />
            <button type="button" disabled={busy !== null} onClick={() => void resetFiles()} className={`${quietClass} mt-2`}>
              {t("wizard.step4.resetFiles")}
            </button>
          </section>
        ) : null}
      </div>
    );
  }
  if (preview.pending || !preview.data) return <Pending label={t("wizard.loading")} />;
  const data = preview.data;
  const name = String((draft.steps["1"].data as { name?: string }).name ?? "");
  const params = explainParams(data.figures, { name });

  const unsaved = Object.entries(edits).some(([file, text]) => text !== data.files[file]);

  const create = (event: FormEvent) => {
    event.preventDefault(); // the CSP has form-action 'none'
    if (!confirmed || unsaved) return;
    void run("create", async () => onCreated(await control.newCreate(draftId, data.protocol_sha256)));
  };

  const saveFiles = () =>
    run("files", async () => {
      const changed = Object.fromEntries(
        Object.entries(edits).filter(([file, text]) => text !== data.files[file]),
      );
      await control.newSaveAdvanced(draftId, draft.revision, { ...draft.advanced, ...changed });
      setEdits({});
      onChanged();
    });

  return (
    <form onSubmit={create} className="flex flex-col gap-4">
      <section className={cardClass}>
        <StepHeading>{t("wizard.step4.title")}</StepHeading>
        <p className="mb-3 mt-0.5 text-[13px] text-muted-foreground">{t("wizard.step4.intro")}</p>
        <p className="text-sm">{t("wizard.step4.summary", params)}</p>
        <h3 className="mt-4 text-sm font-semibold">{t("wizard.step4.files")}</h3>
        <ul className="mt-1 list-disc pl-5 font-mono text-xs">
          {FILES.map((file) => (
            <li key={file}>{file}</li>
          ))}
        </ul>
        <p className="mt-1 break-all font-mono text-xs text-muted-foreground">{data.protocol_sha256}</p>

        <details className="mt-4 rounded-lg border border-border p-3">
          <summary className="cursor-pointer text-sm font-medium">{t("wizard.step4.advanced")}</summary>
          <p className="my-2 text-[13px] text-muted-foreground">{t("wizard.step4.advancedHelp")}</p>
          {FILES.map((file) => (
            <label key={file} className="mb-3 flex flex-col gap-1 text-sm font-medium">
              <span className="font-mono text-xs">{file}</span>
              <textarea
                aria-label={file}
                value={edits[file] ?? data.files[file]}
                onChange={(e) => setEdits((held) => ({ ...held, [file]: e.target.value }))}
                className={`${areaClass} min-h-48 font-mono text-xs`}
              />
            </label>
          ))}
          <div className="flex gap-2">
            <button type="button" disabled={busy !== null} onClick={() => void saveFiles()} className={quietClass}>
              {t("wizard.step4.saveFiles")}
            </button>
            <button type="button" disabled={busy !== null} onClick={() => void resetFiles()} className={quietClass}>
              {t("wizard.step4.resetFiles")}
            </button>
          </div>
        </details>
      </section>

      <section className={cardClass}>
        <h3 className="text-sm font-semibold">{t("wizard.step4.notStartedTitle")}</h3>
        <p className="mt-1 text-[13px] text-muted-foreground">{t("wizard.step4.notStarted")}</p>
        <p className="mt-1 text-[13px] text-muted-foreground">{t("wizard.step4.privacy")}</p>
        <h3 className="mt-4 text-sm font-semibold">{t("wizard.step4.nextTitle")}</h3>
        <ol className="mt-1 list-decimal pl-5 text-[13px] text-muted-foreground">
          <li>{t("wizard.step4.next1")}</li>
          <li>{t("wizard.step4.next2")}</li>
          <li>{t("wizard.step4.next3")}</li>
          <li>{t("wizard.step4.next4")}</li>
          <li>{t("wizard.step4.next5")}</li>
        </ol>
      </section>

      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} className="mt-1" />
        <span>{t("wizard.step4.confirm")}</span>
      </label>

      <ErrorSummary error={error} onReload={reload} />
      {unsaved ? <p className="text-sm text-destructive">{t("wizard.step4.unsaved")}</p> : null}
      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" disabled={!confirmed || unsaved || busy !== null} className={primaryClass}>
          {busy === "create" ? t("wizard.step4.creating") : t("wizard.step4.create")}
        </button>
        <button type="button" disabled className={`${quietClass} opacity-50`} aria-describedby="start-note">
          {t("wizard.step4.startDisabled")}
        </button>
        <span id="start-note" className="text-[13px] text-muted-foreground">{t("wizard.step4.startNote")}</span>
      </div>
    </form>
  );
}
