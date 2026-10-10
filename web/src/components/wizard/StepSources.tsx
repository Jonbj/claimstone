import { useId, useState } from "react";
import type { FormEvent } from "react";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { control } from "@/lib/control";
import type { WizardTemplate } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import Field, { StepHeading } from "./Field";
import { ErrorSummary, FieldError, messageFor, problemsOf } from "./problems";
import { useLeaveWarning } from "./useLeaveWarning";
import { areaClass, cardClass, inputClass, primaryClass } from "./stepTypes";
import type { StepProps } from "./stepTypes";

const TEMPLATE = "general";

interface SavedSources {
  classes?: string[];
  acquisition_floor?: number;
  floor_rationale?: string;
  supplied_copies?: string;
  notation?: string;
  value_labels?: string[];
  extra_excluded_hosts?: string[];
}

export default function StepSources(props: StepProps) {
  const template = useApi(() => control.newTemplate(TEMPLATE), []);
  if (template.error) return <ErrorState error={template.error} context="template" />;
  if (template.pending || !template.data) return <Pending label="…" />;
  return <SourcesForm {...props} template={template.data} />;
}

function SourcesForm({ draftId, draft, onSaved, onReload, template }: StepProps & { template: WizardTemplate }) {
  const { t } = useLocale();
  const saved = draft.steps["3"]?.data as SavedSources | undefined;
  const [classes, setClasses] = useState<string[]>(saved?.classes ?? []);
  const [floor, setFloor] = useState(String(saved?.acquisition_floor ?? template.default_floor.toFixed(2)));
  const [rationale, setRationale] = useState(saved?.floor_rationale ?? "");
  const [supplied, setSupplied] = useState(saved?.supplied_copies ?? "");
  const [notation, setNotation] = useState(saved?.notation ?? "none");
  const [custom, setCustom] = useState(notation === "custom" ? (saved?.value_labels ?? []).join("\n") : "");
  const [hosts, setHosts] = useState((saved?.extra_excluded_hosts ?? []).join("\n"));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const problems = problemsOf(error);
  const snapshot = JSON.stringify([classes, floor, rationale, supplied, notation, custom, hosts]);
  const markSaved = useLeaveWarning(snapshot);
  const groupId = useId();
  const lines = (text: string) => text.split("\n").map((s) => s.trim()).filter(Boolean);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const data = {
        template: template.id,
        classes,
        acquisition_floor: Number(floor.trim().replace(/^([^,]*),([^,]*)$/, "$1.$2")), // 0,8 is 0.8
        floor_rationale: rationale,
        supplied_copies: supplied,
        notation,
        custom_value_labels: notation === "custom" ? lines(custom) : [],
        extra_excluded_hosts: lines(hosts),
      };
      const result = await control.newSaveStep(draftId, 3, draft.revision, data);
      markSaved(snapshot);
      onSaved({ step: 3, revision: result.revision, figures: result.figures });
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusy(false);
    }
  }

  const toggle = (id: string) =>
    setClasses((held) => (held.includes(id) ? held.filter((x) => x !== id) : [...held, id]));

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <section className={cardClass}>
        <StepHeading>{t("wizard.step3.title")}</StepHeading>
        <p className="mb-3 mt-0.5 text-[13px] text-muted-foreground">{t("wizard.step3.intro")}</p>

        <fieldset
          className="flex flex-col gap-2"
          aria-describedby={`${groupId}-classes ${messageFor(problems, "classes") ? `${groupId}-classes-e` : ""}`.trim()}
        >
          <legend className="text-sm font-medium">{t("wizard.step3.classes")}</legend>
          <p id={`${groupId}-classes`} className="text-[13px] text-muted-foreground">{t("wizard.step3.classesHelp")}</p>
          {template.classes.map((c) => (
            <label key={c.id} className="flex items-start gap-2 rounded-lg border border-border p-2 text-sm">
              <input type="checkbox" checked={classes.includes(c.id)} onChange={() => toggle(c.id)} className="mt-1" />
              <span>
                <span className="font-mono text-xs">{c.id}</span> {c.name}
                <span className="block text-[13px] text-muted-foreground">{c.notes}</span>
              </span>
            </label>
          ))}
          <FieldError problems={problems} path="classes" id={`${groupId}-classes-e`} />
        </fieldset>

        <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,160px)_minmax(0,1fr)]">
          <Field label={t("wizard.step3.floor")} help={t("wizard.step3.floorHelp")} problems={problems} path="acquisition_floor">
            {(props) => (
              <input {...props} value={floor} onChange={(e) => setFloor(e.target.value)} inputMode="decimal" className={`${inputClass} font-mono`} />
            )}
          </Field>
          <Field label={t("wizard.step3.rationale")} help={t("wizard.step3.rationaleHelp")} problems={problems} path="floor_rationale">
            {(props) => (
              <textarea {...props} value={rationale} onChange={(e) => setRationale(e.target.value)} className={areaClass} />
            )}
          </Field>
        </div>

        <fieldset className="mt-4 flex flex-col gap-2">
          <legend className="text-sm font-medium">{t("wizard.step3.supplied")}</legend>
          {(["count", "separate"] as const).map((value) => (
            <label key={value} className="flex items-center gap-2 text-sm">
              <input type="radio" name="supplied" checked={supplied === value} onChange={() => setSupplied(value)} />
              {value === "count" ? t("wizard.step3.suppliedCount") : t("wizard.step3.suppliedSeparate")}
            </label>
          ))}
          <p className="text-[13px] text-muted-foreground">{t("wizard.step3.suppliedHelp")}</p>
          <FieldError problems={problems} path="supplied_copies" />
        </fieldset>

        <div className="mt-4 flex flex-col gap-2">
          <Field label={t("wizard.step3.notation")} problems={problems} path="notation">
            {(props) => (
              <select {...props} value={notation} onChange={(e) => setNotation(e.target.value)} className={inputClass}>
                {template.notation_presets.map((p) => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                ))}
                <option value="custom">{t("wizard.step3.notationCustom")}</option>
              </select>
            )}
          </Field>
          {notation === "custom" ? (
            <Field label={t("wizard.step3.customLabels")} help={t("wizard.step3.customLabelsHelp")} problems={problems} path="custom_value_labels">
              {(props) => (
                <textarea {...props} value={custom} onChange={(e) => setCustom(e.target.value)} className={`${areaClass} font-mono`} />
              )}
            </Field>
          ) : null}
        </div>

        <div className="mt-4 flex flex-col gap-1">
          <Field label={t("wizard.step3.hosts")} help={t("wizard.step3.hostsHelp")} problems={problems} path="extra_excluded_hosts">
            {(props) => (
              <textarea {...props} value={hosts} onChange={(e) => setHosts(e.target.value)} className={`${areaClass} font-mono`} />
            )}
          </Field>
          <p className="text-[13px] text-muted-foreground">
            {t("wizard.step3.fixedHosts", { hosts: template.excluded_hosts.join(", ") })}
          </p>
        </div>
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
