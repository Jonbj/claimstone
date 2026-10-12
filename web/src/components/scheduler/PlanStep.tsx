import { useLocale } from "@/lib/i18n";
import type { ScheduleStatus } from "@/lib/scheduler";
import CopyButton from "./CopyButton";
import StepCard from "./StepCard";
import { utcRange } from "./format";

export default function PlanStep({ schedule }: { schedule: ScheduleStatus }) {
  const { t } = useLocale();
  const total = schedule.plan.max_total_requests;

  return (
    <StepCard n={1} title={t("sched.plan.title")} permits={t("sched.plan.permits")}
              forbids={t("sched.plan.forbids")} spend={t("sched.plan.spend", { n: total })}>
      <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead>
          <tr>
            <th scope="col">{t("sched.plan.flow")}</th>
            <th scope="col">{t("sched.plan.window")}</th>
            <th scope="col">{t("sched.plan.searches")}</th>
            <th scope="col">{t("sched.plan.max")}</th>
          </tr>
        </thead>
        <tbody>
          {schedule.plan.entries.map((entry) => (
            <tr key={entry.batch_id}>
              <td className="font-mono">{entry.flow_id.slice(0, 12)}</td>
              <td>{utcRange(entry.not_before, entry.expires_at)}</td>
              <td>{entry.units.length}</td>
              <td>{entry.max_total_requests}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <p>{t("sched.plan.total", { n: total })}</p>
      <p className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground">{t("sched.series.id")}</span>
        <code className="font-mono text-xs break-all">{schedule.schedule_id}</code>
        <CopyButton value={schedule.schedule_id} label={t("sched.series.copyPlanHash")} />
      </p>
    </StepCard>
  );
}
