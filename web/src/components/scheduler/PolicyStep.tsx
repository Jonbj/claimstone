import { useState } from "react";
import { control } from "@/lib/control";
import { formatUtc } from "@/lib/datetime";
import { useLocale } from "@/lib/i18n";
import type { PolicyStatus, ScheduleStatus } from "@/lib/scheduler";
import { quietClass } from "@/components/wizard/stepTypes";
import GrantPanel from "./GrantPanel";
import PolicyForm from "./PolicyForm";
import StateWord from "./StateWord";
import StepCard from "./StepCard";
import { identityName, ratio, requestsLine, utcRange } from "./format";

// One policy, with its own state and its own action. Authorize sends the hash and the three limits
// exactly as this row shows them; Revoke sends the hash.
function Policy({ project, row, calendarState, onChanged }: {
  project: string; row: PolicyStatus; calendarState: string; onChanged: (full: boolean) => void;
}) {
  const { t } = useLocale();
  const p = row.policy;
  return (
    <div role="group" aria-label={t("sched.policy.rowLabel", { id: row.policy_id.slice(0, 12) })}
         className="flex flex-col gap-1 border-t border-border pt-2 first:border-t-0 first:pt-0">
      <p><StateWord word={row.state} /></p>
      <p className="break-words">{t("sched.policy.hosts", { hosts: p.allowed_hosts.join(", ") })}</p>
      <p className="break-words">{t("sched.policy.classes", { classes: p.source_classes.join(", ") })}</p>
      <p>{utcRange(p.not_before, p.expires_at)}</p>
      <p>{requestsLine(p.max_requests_each, p.max_candidates, p.max_total_requests)}</p>
      <p>{t("sched.policy.reserved", { ratio: ratio(row.reserved_candidates, p.max_candidates) })}</p>
      <p>{t("sched.policy.requests", { n: row.reserved_requests })}</p>
      {row.events.map((event, i) => (
        <p key={i} className="text-xs">
          <span className="font-mono">{event.event}</span>{" · "}{identityName(event.identity)}{" · "}{formatUtc(event.at)}
        </p>
      ))}
      {calendarState === "REVOKED" && row.state !== "REVOKED" ? <p>{t("sched.policy.calendarRevoked")}</p> : null}
      {row.state === "PLANNED" ? (
        <GrantPanel
          explanation={<p>{t("sched.policy.plannedNote")}</p>}
          confirmLabel={t("sched.grant.read")} actionLabel={t("sched.policy.authorize")}
          onConfirm={() => control.authorizeCopyPolicy(project, row.policy_id, {
            policy_sha256: row.policy_id, max_candidates: p.max_candidates,
            max_requests_each: p.max_requests_each, max_total_requests: p.max_total_requests })}
          onDone={() => onChanged(false)} onDiffers={() => onChanged(false)} />
      ) : null}
      {row.state === "AUTHORIZED" ? (
        <GrantPanel
          explanation={<p>{t("sched.policy.revokeNote")}</p>}
          confirmLabel={t("sched.policy.revokeConfirm")} actionLabel={t("sched.policy.revoke")} danger
          onConfirm={() => control.revokeCopyPolicy(project, row.policy_id, row.policy_id)}
          onDone={() => onChanged(false)} onDiffers={() => onChanged(false)} />
      ) : null}
      {row.state === "REVOKED" ? <p>{t("sched.policy.revokedNote")}</p> : null}
    </div>
  );
}

/** `rows` is null when the grants could not be read at all; an empty list is "not decided". */
export default function PolicyStep({ project, schedule, rows, complete, onChanged }: {
  project: string; schedule: ScheduleStatus; rows: PolicyStatus[] | null; complete: boolean;
  /** `full` is true after a policy was created: its id is not in the list the page remembers. */
  onChanged: (full: boolean) => void;
}) {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const first = rows?.[0];
  const many = (rows?.length ?? 0) > 1;
  const spend = many ? t("sched.policy.spendMany") : first
    ? t("sched.policy.spend", { line: requestsLine(first.policy.max_requests_each, first.policy.max_candidates, first.policy.max_total_requests) })
    : t("sched.policy.spendNone");
  return (
    <StepCard n={3} title={t("sched.policy.title")} version={JSON.stringify(rows)} state={many ? null : first?.state ?? null}
              permits={t("sched.policy.permits")} forbids={t("sched.policy.forbids")} spend={spend}>
      {rows === null ? <p>{t("sched.series.grantsFailed")}</p>
        : rows.length ? rows.map((row) => <Policy key={row.policy_id} project={project} row={row} calendarState={schedule.state} onChanged={onChanged} />)
        : <p>{complete ? t("sched.step.undecided") : t("sched.grant.notLoaded")}</p>}
      {rows !== null && schedule.state !== "REVOKED" ? (
        open ? (
          <PolicyForm project={project} schedule={schedule} onClose={() => setOpen(false)}
                      onSaved={() => { setOpen(false); onChanged(true); }} onReread={() => onChanged(false)} />
        ) : (
          <button type="button" onClick={() => setOpen(true)} className={`${quietClass} self-start`}>{rows && rows.length ? t("sched.policy.planAnother") : t("sched.policy.plan")}</button>
        )
      ) : null}
    </StepCard>
  );
}
