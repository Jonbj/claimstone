import { useEffect, useId, useRef, useState } from "react";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { control } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import type { ScheduleStatus } from "@/lib/scheduler";
import { areaClass, inputClass, quietClass } from "@/components/wizard/stepTypes";
import { isUtcInstant } from "@/lib/cadence";
import GrantPanel from "./GrantPanel";
import { useStep } from "./StepCard";
import { requestsLine } from "./format";

const whole = (text: string, low: number, high: number): number | null => {
  const n = Number(text);
  return text.trim() !== "" && Number.isInteger(n) && n >= low && n <= high ? n : null;
};

// Planning a copy policy. It freezes limits and permits nothing: authorizing is a separate step on the
// frozen policy. There is no default host (the person names where copies may come from); the source
// classes are suggested from the first flow of the series, and the server refuses a class the project
// has not declared, in its own words. Everything typed stays when the server refuses.
export default function PolicyForm({ project, schedule, onSaved, onReread, onClose }: {
  project: string; schedule: ScheduleStatus; onSaved: () => void;
  /** After a 409: read again, but keep the form and what was typed. */
  onReread: () => void; onClose: () => void;
}) {
  const { t } = useLocale();
  const base = useId();
  const entries = schedule.plan.entries;
  const firstFlow = entries[0]?.flow_id ?? "";
  const overview = useApi(() => (firstFlow ? api.overview(project, "f", firstFlow) : Promise.resolve(null)), [project, firstFlow]);
  const suggested = Object.keys(overview.data?.floor_panel?.by_class ?? {}).sort();
  const [hostsText, setHostsText] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [other, setOther] = useState("");
  const [start, setStart] = useState(entries[0]?.not_before ?? "");
  const [end, setEnd] = useState(entries[entries.length - 1]?.expires_at ?? "");
  const [candidates, setCandidates] = useState("");
  const [each, setEach] = useState("");
  const [busy, setBusy] = useState(false);
  const step = useStep();
  const first = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { first.current?.focus(); }, []);

  const hosts = [...new Set(hostsText.split(/[\n,]/).map((h) => h.trim().toLowerCase()).filter(Boolean))];
  const classes = [...new Set([...picked, ...other.split(",").map((c) => c.trim()).filter(Boolean)])].sort();
  const nCandidates = whole(candidates, 1, 1000);
  const nEach = whole(each, 1, 20);
  const product = nCandidates !== null && nEach !== null ? requestsLine(nEach, nCandidates, nCandidates * nEach) : "—";
  const reason = hosts.length === 0 ? t("sched.new.reason.hosts")
    : classes.length === 0 ? t("sched.policy.reason.classes")
    : nCandidates === null || nEach === null ? t("sched.policy.reason.numbers")
    : !start.trim() || !end.trim() ? t("sched.policy.reason.window")
    : !isUtcInstant(start.trim()) || !isUtcInstant(end.trim()) ? t("sched.new.problem.FORMAT") : null;

  const label = (id: string, text: string) => <label htmlFor={`${base}-${id}`} className="text-sm font-medium">{text}</label>;
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border px-4 py-3">
      <div className="flex flex-col gap-1">
        {label("hosts", t("sched.policy.form.hosts"))}
        <textarea id={`${base}-hosts`} ref={first} value={hostsText} spellCheck={false} disabled={busy} onChange={(e) => setHostsText(e.target.value)} className={`${areaClass} w-full font-mono`} />
        <p className="text-xs text-muted-foreground">{t("sched.policy.form.hostsHelp")}</p>
      </div>
      <fieldset className="flex flex-col gap-1">
        <legend className="text-sm font-medium">{t("sched.policy.form.classes")}</legend>
        {suggested.map((name) => (
          <label key={name} className="flex min-h-11 items-center gap-2 text-sm break-all">
            <input type="checkbox" checked={picked.includes(name)} disabled={busy}
                   onChange={() => setPicked((cur) => (cur.includes(name) ? cur.filter((c) => c !== name) : [...cur, name]))} />
            {name}
          </label>
        ))}
        <div className="flex flex-col gap-1">
          {label("other", t("sched.policy.form.other"))}
          <input id={`${base}-other`} value={other} disabled={busy} onChange={(e) => setOther(e.target.value)} className={inputClass} />
        </div>
        <p className="text-xs text-muted-foreground">{t("sched.policy.form.classesHelp")}</p>
      </fieldset>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          {label("start", t("sched.new.round.start"))}
          <input id={`${base}-start`} value={start} disabled={busy} onChange={(e) => setStart(e.target.value)} className={`${inputClass} break-all`} />
        </div>
        <div className="flex flex-col gap-1">
          {label("end", t("sched.new.round.end"))}
          <input id={`${base}-end`} value={end} disabled={busy} onChange={(e) => setEnd(e.target.value)} className={`${inputClass} break-all`} />
        </div>
        <div className="flex flex-col gap-1">
          {label("cand", t("sched.policy.form.candidates"))}
          <input id={`${base}-cand`} type="number" min={1} max={1000} value={candidates} disabled={busy} onChange={(e) => setCandidates(e.target.value)} className={inputClass} />
        </div>
        <div className="flex flex-col gap-1">
          {label("each", t("sched.policy.form.each"))}
          <input id={`${base}-each`} type="number" min={1} max={20} value={each} disabled={busy} onChange={(e) => setEach(e.target.value)} className={inputClass} />
        </div>
      </div>
      <p className="text-sm">{t("sched.policy.form.product", { line: product })}</p>
      <p className="text-sm text-muted-foreground">{t("sched.policy.form.planning")}</p>
      <GrantPanel requireRead={false} confirmLabel="" actionLabel={t("sched.policy.form.save")} disabledReason={reason}
                  onConfirm={() => control.planCopyPolicy(project, {
                    schedule_id: schedule.schedule_id, allowed_hosts: hosts, source_classes: classes,
                    max_candidates: nCandidates!, max_requests_each: nEach!, not_before: start.trim(), expires_at: end.trim() })}
                  onDone={onSaved} onDiffers={onReread} onBusy={setBusy} />
      <button type="button" disabled={busy} onClick={() => { onClose(); step.focusHeading(); }} className={`${quietClass} self-start`}>{t("sched.grant.cancel")}</button>
    </div>
  );
}
