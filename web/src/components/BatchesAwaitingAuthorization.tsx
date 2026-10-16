import { useEffect, useRef, useState } from "react";
import ErrorState from "@/components/ErrorState";
import { useApi } from "@/hooks/useApi";
import { ControlError, control } from "@/lib/control";
import type { BatchSummary } from "@/lib/control";
import { useLocale } from "@/lib/i18n";

function hostsOf(batch: BatchSummary): string[] {
  return [...new Set(batch.units.flatMap((unit) => unit.allowed_hosts))].sort();
}

export default function BatchesAwaitingAuthorization({ project, flowId, refreshToken, onAuthorized }: {
  project: string; flowId: string; refreshToken: number; onAuthorized: () => void;
}) {
  const { t } = useLocale();
  const list = useApi(() => control.batches(project, flowId), [project, flowId, refreshToken]);
  const [confirming, setConfirming] = useState<BatchSummary | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [planChanged, setPlanChanged] = useState(false);
  const [waitingForFresh, setWaitingForFresh] = useState(false);
  const [running, setRunning] = useState(false);
  const inFlight = useRef(false);
  const staleRead = useRef(list.data);
  useEffect(() => {
    if (waitingForFresh && list.data !== staleRead.current) setWaitingForFresh(false);
  }, [waitingForFresh, list.data]);
  const awaiting = waitingForFresh ? [] :
    (list.data?.batches.filter((batch) => batch.awaiting_approval > 0) ?? []);

  async function confirm() {
    if (!confirming || inFlight.current) return;
    inFlight.current = true;
    setRunning(true);
    setError(null);
    try {
      await control.authorizeBatch(project, flowId, confirming.batch_id, {
        operation_ids: confirming.operation_ids,
        max_total_requests: confirming.max_total_requests,
      });
      setConfirming(null);
      setPlanChanged(false);
      list.reload();
      onAuthorized();
    } catch (cause) {
      if (cause instanceof ControlError && cause.code === "PLAN_DIFFERS") {
        staleRead.current = list.data;
        setWaitingForFresh(true);
        setConfirming(null);
        setPlanChanged(true);
        list.reload();
      } else {
        setError(cause instanceof Error ? cause : new Error(String(cause)));
      }
    } finally {
      inFlight.current = false;
      setRunning(false);
    }
  }

  return (
    <>
      {planChanged ? <p role="alert" className="mb-3 text-sm">{t("authorizeBatch.planChanged")}</p> : null}
      {list.error ? <div className="mb-3"><ErrorState error={list.error} context="batches" /></div> : null}
      {awaiting.length > 0 ? (
        <section aria-label={t("authorizeBatch.heading")} className="mb-5 rounded-md border border-border p-4">
          <h3 className="font-semibold">{t("authorizeBatch.heading")}</h3>
          <ul className="mt-3 flex flex-col gap-4">
            {awaiting.map((batch) => {
              const hosts = hostsOf(batch);
              return <li key={batch.batch_id} className="border-b pb-4 text-sm last:border-b-0 last:pb-0">
                <p className="font-medium">{batch.stage} · {batch.batch_id}</p>
                <p>{t("authorizeBatch.awaiting", { awaiting: batch.awaiting_approval, selected: batch.selected })}</p>
                <p>{t("authorizeBatch.ceiling", { count: batch.max_total_requests })}</p>
                <p>{t("authorizeBatch.hosts", { hosts: hosts.join(", ") || "—" })}</p>
                {batch.units.some((unit) => unit.use_apis) ? <p>{t("authorizeBatch.useApis")}</p> : null}
                <details className="mt-1">
                  <summary>{t("authorizeBatch.skipped", { count: batch.skipped.length })}</summary>
                  <ul className="mt-1 list-disc pl-5">
                    {batch.skipped.map((item, index) =>
                      <li key={index}>{item.subject}: {item.reason}</li>)}
                  </ul>
                </details>
                <button type="button" disabled={running}
                        onClick={() => { setConfirming(batch); setError(null); setPlanChanged(false); }}
                        className="mt-3 min-h-11 rounded-md bg-teal-600 px-4 text-sm font-medium text-white hover:bg-teal-700 disabled:opacity-50">
                  {t("authorizeBatch.open")}
                </button>
              </li>;
            })}
          </ul>
        </section>
      ) : null}
      {confirming ? (
        <div role="dialog" aria-modal="true" aria-label={t("authorizeBatch.dialog")}
             className="mb-5 rounded-lg bg-card p-5 ring-2 ring-teal-600">
          <h3 className="text-base font-semibold">{t("authorizeBatch.confirmTitle", { stage: confirming.stage })}</h3>
          <p className="mt-1 text-sm">{t("authorizeBatch.confirmIntro")}</p>
          <ul className="mt-1 list-disc pl-5 text-sm">
            <li>{t("authorizeBatch.operations", { count: confirming.operation_ids.length })}</li>
            <li>{t("authorizeBatch.ceiling", { count: confirming.max_total_requests })}</li>
            <li>{t("authorizeBatch.hosts", { hosts: hostsOf(confirming).join(", ") || "—" })}</li>
          </ul>
          {error ? <div className="mt-2"><ErrorState error={error} context="authorize batch" /></div> : null}
          <div className="mt-3 flex gap-2">
            <button type="button" disabled={running} onClick={confirm}
                    className="min-h-11 rounded-md bg-teal-600 px-4 text-sm font-medium text-white disabled:opacity-50">
              {running ? t("authorizeBatch.authorizing") : t("authorizeBatch.confirm")}
            </button>
            <button type="button" disabled={running} onClick={() => { setConfirming(null); setError(null); }}
                    className="min-h-11 rounded-md px-4 text-sm ring-1 ring-gray-300">
              {t("authorizeBatch.cancel")}
            </button>
          </div>
        </div>
      ) : null}
    </>
  );
}
