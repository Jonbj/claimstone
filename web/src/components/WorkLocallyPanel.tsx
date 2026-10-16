import { useRef, useState } from "react";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { control } from "@/lib/control";
import type { MandateStatus } from "@/lib/scheduler";
import { useLocale } from "@/lib/i18n";

async function flowMandates(project: string, flowId: string): Promise<MandateStatus[]> {
  const rows: MandateStatus[] = [];
  let cursor: string | null = null;
  let revision: string | null = null;
  do {
    const page = await control.schedulerIndex(project, cursor);
    if (revision !== null && page.archive.revision !== revision) {
      throw new Error("ARCHIVE_CHANGED");
    }
    revision = page.archive.revision;
    rows.push(...page.local_mandates.filter((mandate) => mandate.flow_ids.includes(flowId)));
    cursor = page.archive.next_cursor;
  } while (cursor);
  return rows;
}

export default function WorkLocallyPanel({ project, flowId }: { project: string; flowId: string }) {
  const { t } = useLocale();
  const mandates = useApi(() => flowMandates(project, flowId), [project, flowId]);
  const [extract, setExtract] = useState("");
  const [review, setReview] = useState("");
  const [callsText, setCallsText] = useState("");
  const [confirming, setConfirming] = useState<"enable" | string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const inFlight = useRef(false);
  const calls = Number(callsText);
  const valid = extract.trim().length > 0 && review.trim().length > 0 &&
    extract.trim() !== review.trim() && callsText.trim().length > 0 &&
    Number.isSafeInteger(calls) && calls >= 1;
  const active = mandates.data?.filter((mandate) => mandate.state === "ENABLED") ?? [];

  async function confirm() {
    if (!confirming || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      if (confirming === "enable") {
        await control.enableFlowMandate(project, flowId, {
          flow_id: flowId, extract_model: extract.trim(), review_model: review.trim(),
          max_total_local_calls: calls,
        });
      } else {
        await control.disableMandate(project, confirming);
      }
      setConfirming(null);
      mandates.reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return <section aria-label={t("workLocally.heading")} className="mb-5 rounded-md border border-border p-4">
    <h2 className="font-semibold">{t("workLocally.heading")}</h2>
    {mandates.error ? <ErrorState error={mandates.error} context="local mandates" /> : null}
    {mandates.pending || mandates.refreshing ? <Pending label={t("workLocally.loading")} /> : null}
    {mandates.data && !mandates.refreshing ? active.length > 0 ? active.map((mandate) =>
      <div key={mandate.mandate_id} className="mt-3 text-sm">
        <p>{t("workLocally.state")}: {mandate.state} · {mandate.mandate_id}</p>
        <p>{t("workLocally.extract")}: {mandate.mandate.extract_model}</p>
        <p>{t("workLocally.review")}: {mandate.mandate.review_model}</p>
        <p>{t("workLocally.calls")}: {mandate.mandate.max_total_local_calls}</p>
        <p>{t("workLocally.reserved")}: {mandate.reserved_local_calls}</p>
        <p>{t("workLocally.remaining")}: {mandate.remaining_local_calls}</p>
        <p>{t("workLocally.flows")}: {mandate.flow_ids.join(", ")}</p>
        <p>{t("workLocally.pending")}: {mandate.pending_batches.length}</p>
        {mandate.pending_batches.map((batch) => <p key={batch.batch_id}>
          {batch.batch_id} · {batch.stage} · {t("workLocally.awaiting")}: {batch.awaiting_approval}
        </p>)}
        <button type="button" disabled={busy} onClick={() => setConfirming(mandate.mandate_id)}
          className="min-h-11 rounded-md border px-3">{t("workLocally.disable")}</button>
      </div>) : <div className="mt-3 flex flex-col gap-3 text-sm">
        <label className="flex flex-col gap-1">{t("workLocally.extract")}
          <input value={extract} disabled={busy || confirming !== null} onChange={(event) => setExtract(event.target.value)}
            className="min-h-11 rounded-md border bg-background px-3" /></label>
        <label className="flex flex-col gap-1">{t("workLocally.review")}
          <input value={review} disabled={busy || confirming !== null} onChange={(event) => setReview(event.target.value)}
            className="min-h-11 rounded-md border bg-background px-3" /></label>
        {extract.trim() && extract.trim() === review.trim() ? <p role="alert">{t("workLocally.different")}</p> : null}
        <label className="flex flex-col gap-1">{t("workLocally.calls")}
          <input type="number" min="1" step="1" placeholder="100" value={callsText} disabled={busy || confirming !== null}
            onChange={(event) => setCallsText(event.target.value)}
            className="min-h-11 rounded-md border bg-background px-3" /></label>
        <p>{t("workLocally.explain", { count: callsText || "—" })}</p>
        <button type="button" disabled={!valid || busy} onClick={() => setConfirming("enable")}
          className="min-h-11 self-start rounded-md bg-teal-600 px-4 text-white disabled:opacity-50">
          {t("workLocally.enable")}</button>
      </div> : null}
    {mandates.data && !mandates.refreshing && active.length === 0 ?
      mandates.data.map((mandate) => <p key={mandate.mandate_id} className="mt-2 text-sm">
        {t("workLocally.state")}: {mandate.state} · {mandate.mandate_id}
      </p>) : null}
    {confirming ? <div role="dialog" aria-modal="true" aria-label={t("workLocally.confirm")}
      className="mt-4 rounded-lg bg-card p-5 ring-2 ring-teal-600">
      <h3 className="font-semibold">{confirming === "enable" ? t("workLocally.confirmEnable") : t("workLocally.confirmDisable")}</h3>
      {confirming === "enable" ? <ul className="list-disc pl-5 text-sm">
        <li>{t("workLocally.extract")}: {extract.trim()}</li>
        <li>{t("workLocally.review")}: {review.trim()}</li>
        <li>{t("workLocally.calls")}: {calls}</li>
      </ul> : <p className="text-sm">{confirming}</p>}
      <div className="mt-3 flex gap-3">
        <button type="button" disabled={busy} onClick={confirm}>{t("workLocally.confirmAction")}</button>
        <button type="button" disabled={busy} onClick={() => setConfirming(null)}>{t("workLocally.cancel")}</button>
      </div>
    </div> : null}
    {error ? <ErrorState error={error} context="local mandate" /> : null}
  </section>;
}
