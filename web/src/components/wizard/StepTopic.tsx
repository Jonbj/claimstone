import { useState } from "react";
import type { FormEvent } from "react";
import { control } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
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

export default function StepTopic({ draftId, draft, onSaved }: StepProps) {
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
        <h2 className="text-base font-semibold">{t("wizard.step1.title")}</h2>
        <p className="mb-3 mt-0.5 text-[13px] text-muted-foreground">{t("wizard.step1.intro")}</p>
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm font-medium">
            {t("wizard.step1.name")}
            <input value={name} onChange={(e) => setName(e.target.value)} className={`${inputClass} font-mono`} />
            <span className="text-[13px] font-normal text-muted-foreground">{t("wizard.step1.nameHelp")}</span>
          </label>
          <FieldError problems={problems} path="name" />
          <label className="flex flex-col gap-1 text-sm font-medium">
            {t("wizard.step1.description")}
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} className={areaClass} />
            <span className="text-[13px] font-normal text-muted-foreground">{t("wizard.step1.descriptionHelp")}</span>
          </label>
          <FieldError problems={problems} path="description" />
        </div>
      </section>

      <section className={cardClass}>
        <h2 className="text-base font-semibold">{t("wizard.step1.topics")}</h2>
        <FieldError problems={problems} path="topics" />
        <div className="mt-3 flex flex-col gap-4">
          {topics.map((row, index) => (
            <fieldset key={row.id ?? `new-${index}`} className="flex flex-col gap-2 rounded-lg border border-border p-3">
              <label className="flex flex-col gap-1 text-sm font-medium">
                {t("wizard.step1.topicLabel")}
                <input value={row.label} onChange={(e) => update(index, { label: e.target.value })} className={inputClass} />
              </label>
              <FieldError problems={problems} path={`topics[${index}].label`} />
              <label className="flex flex-col gap-1 text-sm font-medium">
                {t("wizard.step1.terms")}
                <textarea value={row.terms} onChange={(e) => update(index, { terms: e.target.value })} className={`${areaClass} font-mono`} />
                <span className="text-[13px] font-normal text-muted-foreground">{t("wizard.step1.termsHelp")}</span>
              </label>
              <FieldError problems={problems} path={`topics[${index}].terms`} />
              <div>
                <button
                  type="button"
                  disabled={topics.length === 1}
                  onClick={() => setTopics((rows) => rows.filter((_, i) => i !== index))}
                  className={quietClass}
                >
                  {t("wizard.step1.removeTopic")}
                </button>
              </div>
            </fieldset>
          ))}
        </div>
        <button type="button" onClick={() => setTopics((rows) => [...rows, { label: "", terms: "" }])} className={`${quietClass} mt-3`}>
          {t("wizard.step1.addTopic")}
        </button>
      </section>

      <ErrorSummary error={error} />
      <div className="flex items-center gap-3">
        <button type="submit" disabled={busy} className={primaryClass}>
          {busy ? t("wizard.saving") : t("wizard.saveContinue")}
        </button>
        <span className="text-[13px] text-muted-foreground">{t("wizard.draftNote")}</span>
      </div>
    </form>
  );
}
