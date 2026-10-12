import { useLocale } from "@/lib/i18n";
import type { MandateStatus, Worker } from "@/lib/scheduler";
import StateWord from "./StateWord";
import StepCard from "./StepCard";
import { WorkerLine } from "./WorkersStrip";
import { identityName, ratio } from "./format";

function Mandate({ row, worker }: { row: MandateStatus; worker: { worker: Worker; at: string } | undefined }) {
  const { t } = useLocale();
  const disabledBy = identityName(row.disabled_by);
  return (
    <div className="flex flex-col gap-1">
      <p className="flex items-center gap-2"><StateWord word={row.state} />
        {disabledBy ? <span>{t("sched.mandate.disabledBy", { name: disabledBy })}</span> : null}</p>
      <p>{t("sched.mandate.models", { extract: row.mandate.extract_model, review: row.mandate.review_model })}</p>
      <p>{t("sched.mandate.calls", { ratio: ratio(row.reserved_local_calls, row.mandate.max_total_local_calls) })}</p>
      <p>{t("sched.mandate.remaining", { n: row.remaining_local_calls })}</p>
      {row.pending_batches.map((b) => (
        <p key={b.batch_id} className="text-xs">
          {t("sched.mandate.pending", { stage: b.stage, n: b.awaiting_approval, max: b.max_total_requests })}
        </p>
      ))}
      {worker ? <WorkerLine name={t("sched.mandate.process")} worker={worker.worker} asOf={worker.at} /> : null}
    </div>
  );
}

export default function MandateStep({ rows, workers, complete }: {
  rows: MandateStatus[] | null; workers: Record<string, { worker: Worker; at: string }>; complete: boolean;
}) {
  const { t } = useLocale();
  const first = rows?.[0];
  return (
    <StepCard n={4} title={t("sched.mandate.title")} state={first?.state ?? null}
              permits={t("sched.mandate.permits")} forbids={t("sched.mandate.forbids")}
              spend={first ? t("sched.mandate.spend", { n: first.mandate.max_total_local_calls }) : t("sched.mandate.spendNone")}>
      {rows === null ? <p>{t("sched.series.grantsFailed")}</p>
        : rows.length ? rows.map((row) => <Mandate key={row.mandate_id} row={row} worker={workers[row.mandate_id]} />)
        : <p>{complete ? t("sched.grant.undecided") : t("sched.grant.notLoaded")}</p>}
    </StepCard>
  );
}
