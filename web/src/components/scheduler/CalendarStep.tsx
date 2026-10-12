import { formatUtc } from "@/lib/datetime";
import { control } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import type { ScheduleStatus } from "@/lib/scheduler";
import GrantPanel from "./GrantPanel";
import StepCard from "./StepCard";
import { identityName, utcRange } from "./format";

// The calendar grant. PLANNED permits nothing; Authorize sends the plan hash and the request ceiling
// exactly as this page shows them. AUTHORIZED can be revoked (later starts stop). REVOKED is final:
// the server refuses to authorize a revoked schedule, so no action is offered.
export default function CalendarStep({ project, schedule, onChanged }: {
  project: string; schedule: ScheduleStatus; onChanged: () => void;
}) {
  const { t } = useLocale();
  const entries = schedule.plan.entries;
  const searches = entries.reduce((n, e) => n + e.units.length, 0);
  const ceiling = schedule.plan.max_total_requests;
  return (
    <StepCard n={2} title={t("sched.calendar.title")} state={schedule.state}
              permits={t("sched.calendar.permits")} forbids={t("sched.calendar.forbids")}
              spend={t("sched.calendar.spend", { n: ceiling })}>
      {schedule.state === "PLANNED" ? <p>{t("sched.calendar.none")}</p> : null}
      {schedule.events.length ? (
        <ul className="flex flex-col gap-1">
          {schedule.events.map((event, i) => (
            <li key={i} className="text-xs">
              <span className="font-mono">{event.event}</span>{" · "}
              {identityName(event.identity)}{" · "}{formatUtc(event.at)}
            </li>
          ))}
        </ul>
      ) : null}
      {schedule.state === "PLANNED" ? (
        <GrantPanel
          explanation={<p>{t("sched.calendar.summary", { rounds: entries.length, searches,
            window: entries.length ? utcRange(entries[0].not_before, entries[entries.length - 1].expires_at) : "—", n: ceiling })}</p>}
          confirmLabel={t("sched.grant.read")} actionLabel={t("sched.calendar.authorize")}
          onConfirm={() => control.authorizeSchedule(project, schedule.schedule_id,
            { plan_sha256: schedule.schedule_id, max_total_requests: ceiling })}
          onDone={onChanged} onDiffers={onChanged} />
      ) : null}
      {schedule.state === "AUTHORIZED" ? (
        <GrantPanel
          explanation={<p>{t("sched.calendar.revokeNote")}</p>}
          confirmLabel={t("sched.calendar.revokeConfirm")} actionLabel={t("sched.calendar.revoke")} danger
          onConfirm={() => control.revokeSchedule(project, schedule.schedule_id, schedule.schedule_id)}
          onDone={onChanged} onDiffers={onChanged} />
      ) : null}
      {schedule.state === "REVOKED" ? <p>{t("sched.calendar.revokedNote")}</p> : null}
    </StepCard>
  );
}
