import { useState } from "react";
import { control } from "@/lib/control";
import { formatUtc } from "@/lib/datetime";
import { useLocale } from "@/lib/i18n";
import type { MandateStatus, ScheduleStatus, Worker } from "@/lib/scheduler";
import { quietClass } from "@/components/wizard/stepTypes";
import GrantPanel from "./GrantPanel";
import MandateForm from "./MandateForm";
import StateWord from "./StateWord";
import StepCard from "./StepCard";
import { WorkerLine } from "./WorkersStrip";
import { identityName, ratio } from "./format";

function Mandate({ project, row, worker, onChanged }: {
  project: string; row: MandateStatus; worker: { worker: Worker; at: string } | undefined; onChanged: (full: boolean) => void;
}) {
  const { t } = useLocale();
  const enabled = row.mandate.authorized_by;
  const when = typeof row.mandate.created_ns === "number" ? new Date(row.mandate.created_ns / 1e6).toISOString() : null;
  return (
    <div role="group" aria-label={t("sched.mandate.rowLabel", { id: row.mandate_id.slice(0, 12) })}
         className="flex flex-col gap-1 border-t border-border pt-2 first:border-t-0 first:pt-0">
      <p className="flex flex-wrap items-center gap-2"><StateWord word={row.state} />
        {row.disabled_by ? <span>{t("sched.mandate.disabledBy", { name: identityName(row.disabled_by) })}</span> : null}</p>
      {enabled || when ? (
        <p>{t("sched.mandate.enabledBy", { name: identityName(enabled), at: when ? formatUtc(when) : "—" })}</p>
      ) : null}
      <p className="break-words">{t("sched.mandate.models", { extract: row.mandate.extract_model, review: row.mandate.review_model })}</p>
      <p>{t("sched.mandate.calls", { ratio: ratio(row.reserved_local_calls, row.mandate.max_total_local_calls) })}</p>
      <p>{t("sched.mandate.remaining", { n: row.remaining_local_calls })}</p>
      {row.pending_batches.map((b) => (
        <p key={b.batch_id} className="text-xs">
          {t("sched.mandate.pending", { stage: b.stage, n: b.awaiting_approval, max: b.max_total_requests })}
        </p>
      ))}
      {worker ? <WorkerLine name={t("sched.mandate.process")} worker={worker.worker} asOf={worker.at} /> : null}
      {row.state === "ENABLED" ? (
        <GrantPanel
          explanation={<p>{t("sched.mandate.disableNote")}</p>}
          confirmLabel={t("sched.mandate.disableConfirm")} actionLabel={t("sched.mandate.disableAction")} danger
          onConfirm={() => control.disableMandate(project, row.mandate_id)}
          onDone={() => onChanged(false)} onDiffers={() => onChanged(false)} />
      ) : null}
    </div>
  );
}

export default function MandateStep({ project, schedule, rows, workers, complete, onChanged }: {
  project: string; schedule: ScheduleStatus; rows: MandateStatus[] | null;
  workers: Record<string, { worker: Worker; at: string }>; complete: boolean;
  /** `full` is true after a mandate was created: its id is not in the list the page remembers. */
  onChanged: (full: boolean) => void;
}) {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const first = rows?.[0];
  const many = (rows?.length ?? 0) > 1;
  const active = (rows ?? []).some((r) => r.state === "ENABLED");
  return (
    <StepCard n={4} title={t("sched.mandate.title")} version={JSON.stringify(rows)} state={many ? null : first?.state ?? null}
              permits={t("sched.mandate.permits")} forbids={t("sched.mandate.forbids")}
              spend={many ? t("sched.mandate.spendMany") : first ? t("sched.mandate.spend", { n: first.mandate.max_total_local_calls }) : t("sched.mandate.spendNone")}>
      {rows === null ? <p>{t("sched.series.grantsFailed")}</p>
        : rows.length ? rows.map((row) => <Mandate key={row.mandate_id} project={project} row={row} worker={workers[row.mandate_id]} onChanged={onChanged} />)
        : <p>{complete ? t("sched.step.undecided") : t("sched.grant.notLoaded")}</p>}
      {rows !== null && !active && schedule.state === "PLANNED" ? <p>{t("sched.mandate.needsCalendar")}</p> : null}
      {rows !== null && !active && schedule.state === "AUTHORIZED" ? (
        open ? (
          <MandateForm project={project} schedule={schedule} onClose={() => setOpen(false)}
                       onSaved={() => { setOpen(false); onChanged(true); }} onDiffers={() => onChanged(false)} />
        ) : (
          <button type="button" onClick={() => setOpen(true)} className={`${quietClass} self-start`}>{t("sched.mandate.enable")}</button>
        )
      ) : null}
    </StepCard>
  );
}
