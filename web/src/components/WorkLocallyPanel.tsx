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

export default function WorkLocallyPanel({ project, flowId, heading = true }: { project: string; flowId: string; heading?: boolean }) {
  const { t } = useLocale();
  const mandates = useApi(() => flowMandates(project, flowId), [project, flowId]);
  const [extract, setExtract] = useState("deepseek-v4.1-flash");
  const [review, setReview] = useState("mistral-large-3:675b");
  const [callsText, setCallsText] = useState("300");
  const [backend, setBackend] = useState<"ollama-cloud" | "llamacpp">("ollama-cloud");
  const [budgetText, setBudgetText] = useState("30");
  const [perCallText, setPerCallText] = useState("0.10");
  const [priceInText, setPriceInText] = useState("3.00");
  const [priceOutText, setPriceOutText] = useState("12.00");
  const [confirming, setConfirming] = useState<"enable" | string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const inFlight = useRef(false);
  const calls = Number(callsText);
  const cents = (text: string) => Math.round(Number(text) * 100);
  const metered = backend === "ollama-cloud";
  // The supervisor reserves `per call` for every call it plans and refuses to plan beyond the budget, so a
  // budget below calls x reserve starts a mandate that can never run (found 2026-10-21): refuse it here.
  const reservedCents = Number.isSafeInteger(calls) && calls >= 1 ? calls * cents(perCallText) : NaN;
  const coversReservations = !metered || (Number.isFinite(reservedCents) && reservedCents <= cents(budgetText));
  const meteredValid = !metered || [budgetText, perCallText, priceInText, priceOutText].every(
    (text) => text.trim().length > 0 && Number.isSafeInteger(cents(text)) && cents(text) >= 1) &&
    cents(perCallText) <= cents(budgetText) && coversReservations;
  const valid = meteredValid && extract.trim().length > 0 && review.trim().length > 0 &&
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
          ...(metered ? {
            backend: "ollama-cloud" as const, budget_cents: cents(budgetText),
            max_call_cents: cents(perCallText), price_in_cents: cents(priceInText),
            price_out_cents: cents(priceOutText),
          } : {}),
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

  return <section aria-label={t("workLocally.heading")} className="mb-5 rounded-xl border border-border bg-card p-4">
    {heading ? <h2 className="font-semibold">{t("workLocally.heading")}</h2> : null}
    {mandates.error ? <ErrorState error={mandates.error} context="local mandates" /> : null}
    {mandates.pending || mandates.refreshing ? <Pending label={t("workLocally.loading")} /> : null}
    {mandates.data && !mandates.refreshing ? active.length > 0 ? active.map((mandate) =>
      <div key={mandate.mandate_id} className="mt-3 text-sm">
        <p>{t("workLocally.state")}: {mandate.state}</p>
        <p>{t("workLocally.extract")}: {mandate.mandate.extract_model}</p>
        <p>{t("workLocally.review")}: {mandate.mandate.review_model}</p>
        <p>{t("workLocally.calls")}: {mandate.mandate.max_total_local_calls}</p>
        <p>{t("workLocally.backend")}: {mandate.model_backend ?? "llamacpp"}</p>
        {mandate.paid_budget ? <p>{t("workLocally.budgetUsed", {
          reserved: (mandate.paid_budget.reserved_cents / 100).toFixed(2),
          budget: (mandate.paid_budget.budget_cents / 100).toFixed(2),
        })}</p> : null}
        <p>{t("workLocally.reserved")}: {mandate.reserved_local_calls}</p>
        <p>{t("workLocally.remaining")}: {mandate.remaining_local_calls}</p>
        <p>{t("workLocally.pending")}: {mandate.pending_batches.length}</p>
        <details className="mt-2 text-xs text-muted-foreground"><summary className="min-h-11 cursor-pointer py-3">{t("flowAssay.details")}</summary>
          <p className="max-w-full truncate font-mono" title={mandate.mandate_id}>{t("workLocally.state")}: {mandate.state} · {mandate.mandate_id}</p>
          <p>{t("workLocally.flows")}: {mandate.flow_ids.join(", ")}</p>
          {mandate.pending_batches.map((batch) => <p key={batch.batch_id}>
            <span className="font-mono" title={batch.batch_id}>{batch.batch_id.slice(0, 12)}…</span> · {batch.stage} · {t("workLocally.awaiting")}: {batch.awaiting_approval}
          </p>)}
        </details>
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
        <label className="flex flex-col gap-1">{t("workLocally.backend")}
          <select value={backend} disabled={busy || confirming !== null}
            onChange={(event) => setBackend(event.target.value as "ollama-cloud" | "llamacpp")}
            className="min-h-11 rounded-md border bg-background px-3">
            <option value="ollama-cloud">{t("workLocally.backendCloud")}</option>
            <option value="llamacpp">{t("workLocally.backendLocal")}</option>
          </select></label>
        {metered ? <>
          {([["budget", budgetText, setBudgetText], ["perCall", perCallText, setPerCallText],
             ["priceIn", priceInText, setPriceInText], ["priceOut", priceOutText, setPriceOutText]] as const).map(
            ([key, value, setter]) => <label key={key} className="flex flex-col gap-1">{t(`workLocally.${key}`)}
              <input type="number" min="0.01" step="0.01" value={value} disabled={busy || confirming !== null}
                onChange={(event) => setter(event.target.value)}
                className="min-h-11 rounded-md border bg-background px-3" /></label>)}
          {meteredValid ? null : <p role="alert">{t("workLocally.meteredInvalid")}</p>}
          <p role={coversReservations ? undefined : "alert"} data-reservation>{t("workLocally.reservation", {
            count: callsText || "—", reserve: perCallText || "—",
            total: Number.isFinite(reservedCents) ? (reservedCents / 100).toFixed(2) : "—", budget: budgetText || "—" })}
            {coversReservations ? "" : ` ${t("workLocally.reservationShort")}`}</p>
          <p>{t("workLocally.explainMetered", { count: callsText || "—", budget: budgetText || "—" })}</p>
        </> : <p>{t("workLocally.explain", { count: callsText || "—" })}</p>}
        <button type="button" disabled={!valid || busy} onClick={() => setConfirming("enable")}
          className="min-h-11 self-start rounded-lg border border-border bg-card px-4 disabled:opacity-50">
          {t("workLocally.enable")}</button>
      </div> : null}
    {mandates.data && !mandates.refreshing && active.length === 0 ?
      mandates.data.map((mandate) => <div key={mandate.mandate_id} className="mt-2 text-sm">
        <p>{t("workLocally.state")}: {mandate.state}</p>
        <details className="text-xs text-muted-foreground"><summary className="min-h-11 cursor-pointer py-3">{t("flowAssay.details")}</summary><span className="block max-w-full truncate font-mono" title={mandate.mandate_id}>{mandate.mandate_id}</span></details>
      </div>) : null}
    {confirming ? <div role="dialog" aria-modal="true" aria-label={t("workLocally.confirm")}
      className="mt-4 rounded-lg bg-card p-5 ring-2 ring-primary">
      <h3 className="font-semibold">{confirming === "enable" ? t("workLocally.confirmEnable") : t("workLocally.confirmDisable")}</h3>
      {confirming === "enable" ? <ul className="list-disc pl-5 text-sm">
        <li>{t("workLocally.extract")}: {extract.trim()}</li>
        <li>{t("workLocally.review")}: {review.trim()}</li>
        <li>{t("workLocally.calls")}: {calls}</li>
        <li>{t("workLocally.backend")}: {metered ? t("workLocally.backendCloud") : t("workLocally.backendLocal")}</li>
        {metered ? <>
          <li>{t("workLocally.budget")}: {budgetText}</li>
          <li>{t("workLocally.perCall")}: {perCallText}</li>
          <li>{t("workLocally.priceIn")}: {priceInText}</li>
          <li>{t("workLocally.priceOut")}: {priceOutText}</li>
        </> : null}
      </ul> : <p className="text-sm">{confirming}</p>}
      <div className="mt-3 flex gap-3">
        <button type="button" disabled={busy} onClick={confirm}>{t("workLocally.confirmAction")}</button>
        <button type="button" disabled={busy} onClick={() => setConfirming(null)}>{t("workLocally.cancel")}</button>
      </div>
    </div> : null}
    {error ? <ErrorState error={error} context="local mandate" /> : null}
  </section>;
}
