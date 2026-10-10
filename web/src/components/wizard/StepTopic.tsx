import { useState } from "react";
import type { FormEvent } from "react";
import { control } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import Field, { StepHeading } from "./Field";
import { ErrorSummary, FieldError, problemsOf } from "./problems";
import { areaClass, cardClass, inputClass, primaryClass, quietClass } from "./stepTypes";
import type { StepProps } from "./stepTypes";

interface TopicRow {
  id?: string;
  label: string;
  terms: string;
}

interface SavedTopic {
  name?: string;
  description?: string;
  topics?: Array<{ id: string; label: string; terms: string[] }>;
}

export default function StepTopic({ draftId, draft, onSaved, onReload }: StepProps) {
  const { t } = useLocale();
  const saved = draft.steps["1"]?.data as SavedTopic | undefined;
  const [name, setName] = useState(saved?.name ?? "");
  const [description, setDescription] = useState(saved?.description ?? "");
  const [topics, setTopics] = useState<TopicRow[]>(
    saved?.topics?.map((x) => ({ id: x.id, label: x.label, terms: x.terms.join("\n") }))
      ?? [{ label: "", terms: "" }],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const problems = problemsOf(error);

  const update = (index: number, patch: Partial<TopicRow>) =>
    setTopics((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  async function submit(event: FormEvent) {
    event.preventDefault(); // the CSP has form-action 'none': a native submit is never wanted
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const data = {
        name: name.trim(),
        description,
        topics: topics.map((row) => ({
          ...(row.id ? { id: row.id } : {}),
          label: row.label,
          terms: row.terms.split("\n").map((s) => s.trim()).filter(Boolean),
        })),
      };
      const result = await control.newSaveStep(draftId, 1, draft.revision, data);
      onSaved({ step: 1, revision: result.revision, figures: result.figures });
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <section className={cardClass}>
        <StepHeading>{t("wizard.step1.title")}</StepHeading>
        <p className="mb-3 mt-0.5 text-[13px] text-muted-foreground">{t("wizard.step1.intro")}</p>
        <div className="flex flex-col gap-3">
          <Field label={t("wizard.step1.name")} help={t("wizard.step1.nameHelp")} problems={problems} path="name">
            {(props) => (
              <input {...props} value={name} onChange={(e) => setName(e.target.value)} className={`${inputClass} font-mono`} />
            )}
          </Field>
          <Field label={t("wizard.step1.description")} help={t("wizard.step1.descriptionHelp")} problems={problems} path="description">
            {(props) => (
              <textarea {...props} value={description} onChange={(e) => setDescription(e.target.value)} className={areaClass} />
            )}
          </Field>
        </div>
      </section>

      <section className={cardClass}>
        <h2 className="text-base font-semibold">{t("wizard.step1.topics")}</h2>
        <FieldError problems={problems} path="topics" />
        <div className="mt-3 flex flex-col gap-4">
          {topics.map((row, index) => {
            const legend = t("wizard.step1.topicLegend", { n: index + 1 });
            return (
              <fieldset key={row.id ?? `new-${index}`} className="flex flex-col gap-2 rounded-lg border border-border p-3">
                <legend className="px-1 text-sm font-semibold">{legend}</legend>
                <Field label={t("wizard.step1.topicLabel")} problems={problems} path={`topics[${index}].label`}>
                  {(props) => (
                    <input {...props} value={row.label} onChange={(e) => update(index, { label: e.target.value })} className={inputClass} />
                  )}
                </Field>
                <Field
                  label={t("wizard.step1.terms")}
                  help={t("wizard.step1.termsHelp")}
                  problems={problems}
                  path={`topics[${index}].terms`}
                >
                  {(props) => (
                    <textarea
                      {...props}
                      value={row.terms}
                      onChange={(e) => update(index, { terms: e.target.value })}
                      className={`${areaClass} font-mono`}
                    />
                  )}
                </Field>
                <div>
                  <button
                    type="button"
                    disabled={topics.length === 1}
                    aria-label={`${t("wizard.step1.removeTopic")} (${legend})`}
                    onClick={() => setTopics((rows) => rows.filter((_, i) => i !== index))}
                    className={quietClass}
                  >
                    {t("wizard.step1.removeTopic")}
                  </button>
                </div>
              </fieldset>
            );
          })}
        </div>
        <button type="button" onClick={() => setTopics((rows) => [...rows, { label: "", terms: "" }])} className={`${quietClass} mt-3`}>
          {t("wizard.step1.addTopic")}
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
