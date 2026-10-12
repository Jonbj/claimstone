import { useLocale } from "@/lib/i18n";
import { roundsOf } from "@/lib/scheduler";
import type { AuditRound, ScheduleStatus } from "@/lib/scheduler";
import { useNow } from "@/hooks/useSchedulerRefresh";
import { percent, ratio, utcRange } from "./format";

function Cell({ entry, round, planned }: {
  entry: ScheduleStatus["plan"]["entries"][number]; round: AuditRound | undefined; planned: boolean;
}) {
  const { t } = useLocale();
  const name = round?.round ?? entry.flow_id.slice(0, 12);
  const admission = round?.admission;
  const ops = Object.entries(round?.operations ?? {});
  return (
    <li className="flex flex-col gap-1 rounded-xl border border-border bg-card px-3 py-3 text-sm">
      <b>{name}</b>
      <span className="text-xs text-muted-foreground">{utcRange(entry.not_before, entry.expires_at)}</span>
      {planned ? <span className="text-xs font-medium">{t("sched.series.planned")}</span> : null}
      {round ? (
        <>
          <span className="text-xs">
            {t("sched.series.operations")}: {ops.length ? ops.map(([k, n]) => `${k}: ${n}`).map((s) => <span key={s} className="mr-2 font-mono">{s}</span>) : t("sched.series.noOperations")}
          </span>
          <span className="text-xs">
            {t("sched.series.searches")} <span>{ratio(round.successful_queries, round.planned_queries)}</span>
          </span>
          {admission ? (
            <>
              <span className="text-xs">
                {t("sched.series.confirmed")} <span>{ratio(admission.confirmed, admission.found)}</span>
                {" · "}{t("sched.series.rate", { rate: percent(admission.rate) })}
              </span>
              <span className="font-mono text-xs">{admission.status}</span>
              {admission.found === 0 ? <span className="text-xs">{t("sched.series.noCandidates")}</span> : null}
            </>
          ) : null}
        </>
      ) : <span className="text-xs text-muted-foreground">{t("sched.series.noData")}</span>}
    </li>
  );
}

// One cell per plan entry, in window order. Counts are the server's, verbatim; `found` stays the
// denominator of what was obtained. A round is "planned" until the schedule is authorized and the
// window has opened.
export default function RoundTimeline({ schedule, audit }: { schedule: ScheduleStatus; audit: unknown }) {
  const { t } = useLocale();
  const rounds = roundsOf(audit);
  const now = useNow(30_000);
  return (
    <section aria-label={t("sched.series.timeline")} className="flex flex-col gap-2">
      <h2 className="text-sm font-semibold">{t("sched.series.timeline")}</h2>
      <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {schedule.plan.entries.map((entry, i) => {
          const row = rounds[i]?.flow_id === entry.flow_id ? rounds[i] : undefined;
          const planned = schedule.state !== "AUTHORIZED" || Date.parse(entry.not_before) > now;
          return <Cell key={entry.batch_id} entry={entry} round={row} planned={planned} />;
        })}
      </ol>
    </section>
  );
}
