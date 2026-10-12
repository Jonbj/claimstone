import { useLocale } from "@/lib/i18n";
import { formatUtc } from "@/lib/datetime";
import type { ScheduleStatus } from "@/lib/scheduler";
import StepCard from "./StepCard";
import { identityName } from "./format";

export default function CalendarStep({ schedule }: { schedule: ScheduleStatus }) {
  const { t } = useLocale();
  return (
    <StepCard n={2} title={t("sched.calendar.title")} state={schedule.state}
              permits={t("sched.calendar.permits")} forbids={t("sched.calendar.forbids")}
              spend={t("sched.calendar.spend", { n: schedule.plan.max_total_requests })}>
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
    </StepCard>
  );
}
