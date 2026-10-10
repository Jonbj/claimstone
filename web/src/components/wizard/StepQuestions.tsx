import { useState } from "react";
import type { FormEvent } from "react";
import { control } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import { ErrorSummary, FieldError, problemsOf } from "./problems";
import { areaClass, cardClass, inputClass, primaryClass, quietClass } from "./stepTypes";
import type { StepProps } from "./stepTypes";

// The engine's kinds, as the engine spells them. They stay canonical on screen; the gloss is beside.
const KINDS = ["effect", "heterogeneity", "method", "premise", "operational"] as const;

interface QuestionRow {
  id?: string;
  text: string;
  kind: string;
}

export default function StepQuestions({ draftId, draft, onSaved, onReload }: StepProps) {
  const { t } = useLocale();
  const saved = draft.steps["2"]?.data as { questions?: QuestionRow[] } | undefined;
  const [rows, setRows] = useState<QuestionRow[]>(saved?.questions ?? [{ text: "", kind: "" }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const problems = problemsOf(error);

  const update = (index: number, patch: Partial<QuestionRow>) =>
    setRows((list) => list.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const data = { questions: rows.map((row) => ({ ...(row.id ? { id: row.id } : {}), text: row.text, kind: row.kind })) };
      const result = await control.newSaveStep(draftId, 2, draft.revision, data);
      onSaved({ step: 2, revision: result.revision, figures: result.figures });
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <section className={cardClass}>
        <h2 className="text-base font-semibold">{t("wizard.step2.title")}</h2>
        <p className="mb-3 mt-0.5 text-[13px] text-muted-foreground">{t("wizard.step2.intro")}</p>
        <FieldError problems={problems} path="questions" />
        <div className="flex flex-col gap-4">
          {rows.map((row, index) => (
            <fieldset key={row.id ?? `new-${index}`} className="flex flex-col gap-2 rounded-lg border border-border p-3">
              <label className="flex flex-col gap-1 text-sm font-medium">
                {t("wizard.step2.question")}
                <textarea value={row.text} onChange={(e) => update(index, { text: e.target.value })} className={areaClass} />
              </label>
              <FieldError problems={problems} path={`questions[${index}].text`} />
              <label className="flex flex-col gap-1 text-sm font-medium">
                {t("wizard.step2.kind")}
                <select
                  value={row.kind}
                  onChange={(e) => update(index, { kind: e.target.value })}
                  className={`${inputClass} font-mono`}
                >
                  <option value="" />
                  {KINDS.map((kind) => (
                    <option key={kind} value={kind}>{kind}</option>
                  ))}
                </select>
              </label>
              {row.kind ? (
                <p className="text-[13px] text-muted-foreground">{t(`wizard.kind.${row.kind}`)}</p>
              ) : null}
              <FieldError problems={problems} path={`questions[${index}].kind`} />
              <div>
                <button
                  type="button"
                  disabled={rows.length === 1}
                  onClick={() => setRows((list) => list.filter((_, i) => i !== index))}
                  className={quietClass}
                >
                  {t("wizard.step2.removeQuestion")}
                </button>
              </div>
            </fieldset>
          ))}
        </div>
        <button type="button" onClick={() => setRows((list) => [...list, { text: "", kind: "" }])} className={`${quietClass} mt-3`}>
          {t("wizard.step2.addQuestion")}
        </button>
      </section>

      <ErrorSummary error={error} onReload={onReload} />
      <div className="flex items-center gap-3">
        <button type="submit" disabled={busy} className={primaryClass}>
          {busy ? t("wizard.saving") : t("wizard.saveContinue")}
        </button>
        <span className="text-[13px] text-muted-foreground">{t("wizard.draftNote")}</span>
      </div>
    </form>
  );
}
