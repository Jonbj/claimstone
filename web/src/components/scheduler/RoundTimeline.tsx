import { useLocale } from "@/lib/i18n";
import { ancestorsOf, roundsOf } from "@/lib/scheduler";
import type { AuditRound, ScheduleStatus } from "@/lib/scheduler";
import { useNow } from "@/hooks/useSchedulerRefresh";
import AdmissionLine from "./AdmissionLine";
import StateWord from "./StateWord";
import { ratio, utcRange } from "./format";

type Entry = ScheduleStatus["plan"]["entries"][number];

/** What the cell says about the schedule: "planned" before it can run (PLANNED, or AUTHORIZED with a
 *  window not yet open), the schedule's own state word when it is anything but AUTHORIZED (REVOKED),
 *  nothing once an authorized window is open. */
function Standing({ state, entry, now }: { state: string; entry: Entry; now: number }) {
  const { t } = useLocale();
  if (state === "PLANNED" || (state === "AUTHORIZED" && Date.parse(entry.not_before) > now)) {
    return <span className="text-xs font-medium">{t("sched.series.planned")}</span>;
  }
  return state === "AUTHORIZED" ? null : <StateWord word={state} />;
}

function Cell({ entry, round, state, now }: { entry: Entry; round: AuditRound | undefined; state: string; now: number }) {
  const { t } = useLocale();
  const name = round?.round ?? entry.flow_id.slice(0, 12);
  const admission = round?.admission;
  const ops = Object.entries(round?.operations ?? {});
  return (
    <li className="flex min-w-0 flex-col gap-1 rounded-xl border border-border bg-card px-3 py-3 text-sm">
      <b className="break-words">{name}</b>
      <span className="text-xs text-muted-foreground">{utcRange(entry.not_before, entry.expires_at)}</span>
      <span className="flex flex-wrap items-center gap-2">
        <Standing state={state} entry={entry} now={now} />
        {round?.binding_state ? <StateWord word={round.binding_state} /> : null}
      </span>
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
              </span>
              <span className="flex flex-wrap gap-x-3 text-xs"><AdmissionLine a={admission} /></span>
              <span className="font-mono text-xs break-words">{admission.status}</span>
              {admission.found === 0 ? <span className="text-xs">{t("sched.series.noCandidates")}</span> : null}
            </>
          ) : null}
        </>
      ) : <span className="text-xs text-muted-foreground">{t("sched.series.noData")}</span>}
    </li>
  );
}

function Earlier({ rounds }: { rounds: AuditRound[] }) {
  const { t } = useLocale();
  if (!rounds.length) return null;
  return (
    <section aria-label={t("sched.series.earlier")} className="flex flex-col gap-1 text-xs">
      <h3 className="font-medium">{t("sched.series.earlier")}</h3>
      <ul className="flex flex-col gap-1">
        {rounds.map((r, i) => (
          <li key={`${r.flow_id}-${i}`} className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <b>{r.round ?? "—"}</b>
            <span className="font-mono">{String(r.flow_id ?? "").slice(0, 12)}</span>
            {r.binding_state ? <StateWord word={r.binding_state} /> : null}
            {r.admission ? (
              <>
                <span className="font-mono">{r.admission.status}</span>
                <AdmissionLine a={r.admission} />
              </>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

// One cell per plan entry, in window order, then the earlier rounds of the lineage. Counts are the
// server's, verbatim; `found` stays the denominator of what was confirmed.
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
          return <Cell key={entry.batch_id} entry={entry} round={row} state={schedule.state} now={now} />;
        })}
      </ol>
      <Earlier rounds={ancestorsOf(audit)} />
    </section>
  );
}
