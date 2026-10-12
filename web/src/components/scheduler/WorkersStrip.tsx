import { useLocale } from "@/lib/i18n";
import { formatUtc } from "@/lib/datetime";
import { workerAlert } from "@/lib/scheduler";
import type { Worker } from "@/lib/scheduler";
import StateWord from "./StateWord";

/** One process: its state word and when it was last heard from. Only the supervisor can raise an
 *  operational alert; any other process that is not ALIVE gets the contract's neutral sentence
 *  (normally STOPPED between supervisor passes). A process is never a research outcome. */
export function WorkerLine({ name, worker, asOf }: { name: string; worker: Worker; asOf?: string }) {
  const { t } = useLocale();
  const alert = workerAlert(worker);
  const neutral = !alert && worker.state !== "ALIVE";
  return (
    <div role={alert ? "status" : undefined} aria-label={alert ? name : undefined}
         className="flex flex-col gap-1 rounded-lg border border-border bg-card px-3 py-2 text-sm">
      <span className="flex flex-wrap items-center gap-2">
        <b>{name}</b>
        <StateWord word={worker.state} />
        {worker.phase ? <span className="flex items-center gap-1 text-muted-foreground">{t("sched.workers.phase")} <StateWord word={worker.phase} /></span> : null}
      </span>
      <span className="text-xs text-muted-foreground">
        {worker.last_seen_at
          ? t("sched.workers.lastSeen", { at: formatUtc(worker.last_seen_at) })
          : t("sched.workers.neverSeen")}
        {worker.age_seconds !== null ? ` · ${t("sched.workers.age", { seconds: Math.round(worker.age_seconds) })}` : ""}
        {asOf ? ` · ${t("sched.asOf", { time: formatUtc(asOf) })}` : ""}
      </span>
      {alert ? <span>{t("sched.workers.alert")}</span> : null}
      {neutral ? <span className="text-xs text-muted-foreground">{t("sched.workers.neutral")}</span> : null}
    </div>
  );
}

export default function WorkersStrip({ supervisor, operations }: { supervisor: Worker; operations: Worker }) {
  const { t } = useLocale();
  return (
    <section aria-label={t("sched.workers.title")} className="flex flex-col gap-2">
      <h2 className="text-sm font-semibold">{t("sched.workers.title")}</h2>
      <div className="grid gap-2 sm:grid-cols-2">
        <WorkerLine name={t("sched.workers.supervisor")} worker={supervisor} />
        <WorkerLine name={t("sched.workers.operations")} worker={operations} />
      </div>
      <p className="text-xs text-muted-foreground">{t("sched.workers.note")}</p>
    </section>
  );
}
