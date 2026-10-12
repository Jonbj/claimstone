import { useEffect, useId, useRef, useState } from "react";
import { control } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import type { ScheduleStatus } from "@/lib/scheduler";
import { inputClass, quietClass } from "@/components/wizard/stepTypes";
import GrantPanel from "./GrantPanel";

// Enabling a local model for the series. The flows it applies to are the DISPLAYED schedule's, in
// order, and are never typed; the server refuses if they changed meanwhile and the page reads again.
export default function MandateForm({ project, schedule, onSaved, onDiffers, onClose }: {
  project: string; schedule: ScheduleStatus; onSaved: () => void; onDiffers: () => void; onClose: () => void;
}) {
  const { t } = useLocale();
  const base = useId();
  const [extract, setExtract] = useState("");
  const [review, setReview] = useState("");
  const [cap, setCap] = useState("");
  const first = useRef<HTMLInputElement>(null);
  useEffect(() => { first.current?.focus(); }, []);
  const flowIds = schedule.plan.entries.map((e) => e.flow_id);
  const calls = Number(cap);
  const same = extract.trim() !== "" && extract.trim() === review.trim();
  const reason = !extract.trim() || !review.trim() ? t("sched.mandate.reason.models")
    : same ? t("sched.mandate.sameModels")
    : !(cap.trim() !== "" && Number.isInteger(calls) && calls >= 1 && calls <= 100000) ? t("sched.mandate.reason.cap") : null;

  const field = (id: string, text: string, value: string, set: (v: string) => void, ref?: React.Ref<HTMLInputElement>, type = "text") => (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={`${base}-${id}`} className="text-sm font-medium">{text}</label>
      <input id={`${base}-${id}`} ref={ref} type={type} value={value} onChange={(e) => set(e.target.value)}
             aria-invalid={id === "review" && same ? true : undefined}
             className={`${inputClass} break-all`} />
    </div>
  );
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border px-4 py-3">
      <div className="grid gap-3 sm:grid-cols-2">
        {field("extract", t("sched.mandate.form.extract"), extract, setExtract, first)}
        {field("review", t("sched.mandate.form.review"), review, setReview)}
        {field("cap", t("sched.mandate.form.cap"), cap, setCap, undefined, "number")}
      </div>
      <p className="text-xs text-muted-foreground">{t("sched.mandate.form.flows", { n: flowIds.length })}</p>
      <GrantPanel confirmLabel={t("sched.grant.read")} actionLabel={t("sched.mandate.enableAction")} disabledReason={reason}
                  onConfirm={() => control.enableSeriesMandate(project, {
                    schedule_id: schedule.schedule_id, flow_ids: flowIds,
                    extract_model: extract.trim(), review_model: review.trim(), max_total_local_calls: calls })}
                  onDone={onSaved} onDiffers={onDiffers} />
      <button type="button" onClick={onClose} className={`${quietClass} self-start`}>{t("sched.grant.cancel")}</button>
    </div>
  );
}
