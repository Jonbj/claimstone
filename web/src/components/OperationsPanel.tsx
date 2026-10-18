import { useState } from "react";
import { Link } from "react-router";
import Chip from "@/components/Chip";
import BatchesAwaitingAuthorization from "@/components/BatchesAwaitingAuthorization";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import PlanBatchForm from "@/components/PlanBatchForm";
import { useApi } from "@/hooks/useApi";
import { control } from "@/lib/control";
import type { OperationSummary } from "@/lib/control";
import { useSession } from "@/lib/session";
import { useLocale } from "@/lib/i18n";

// "Right now" (spec v2.1 F3): the flow's scheduler operations, from GET …/operations. Signed in
// only. Everything shown is the API's: the state word and its note verbatim, the limits, the
// money the ledger reported, the units whose cost it did not report (reserved, never 0) and
// `worker_note` where a heartbeat would be. Authorize exists for PLANNED only and POSTs the very
// limits it displayed. Pause and Resume are disabled: the scheduler's ledger has no stopping
// event (control_api.md B12), so they are never called.
const NO_STOP_EVENT =
  "pause and resume need a stopping event the scheduler's operation ledger does not accept yet; " +
  "they belong to the scheduler track";

function limit(value: number | null, unit = ""): string {
  return value === null ? "— (none set)" : `${value}${unit}`;
}

function stateSymbol(state: string): string {
  if (state === "PLANNED") return "●";
  if (state === "AUTHORIZED" || state === "RUNNING_OR_LOCK_HELD") return "◐";
  if (state === "COMPLETED") return "✓";
  if (state === "FAILED") return "■";
  if (state === "INTERRUPTED") return "▲";
  return "○";
}

export default function OperationsPanel({ project, flowId, namedRound = false, hasCandidates = false }: {
  project: string; flowId: string; namedRound?: boolean; hasCandidates?: boolean;
}) {
  const session = useSession();
  return (
    <section aria-label="Right now" className="rounded-xl border border-border bg-card p-4 sm:p-5">
      <h2 className="mb-2 text-base font-semibold">Right now</h2>
      {!session.ready ? (
        <Pending label="checking session…" />
      ) : session.operator === null ? (
        <p className="text-sm text-muted-foreground">
          <Link to="/login" className="text-provisional hover:underline">
            Sign in to see and authorize operations
          </Link>
        </p>
      ) : (
        <OperationsList project={project} flowId={flowId} namedRound={namedRound} hasCandidates={hasCandidates} />
      )}
    </section>
  );
}

function OperationsList({ project, flowId, namedRound, hasCandidates }: {
  project: string; flowId: string; namedRound: boolean; hasCandidates: boolean;
}) {
  const { t } = useLocale();
  const list = useApi(() => control.operations(project, flowId), [project, flowId]);
  const [confirming, setConfirming] = useState<OperationSummary | null>(null);
  const [batchRefreshToken, setBatchRefreshToken] = useState(0);
  const operations = list.data?.operations ?? [];
  const firstPlannedIndex = operations.findIndex((op) => op.state === "PLANNED");
  function refreshAfterPlanning() {
    list.reload();
    setBatchRefreshToken((token) => token + 1);
  }
  return (
    <>
      {namedRound ? <PlanBatchForm project={project} flowId={flowId} hasCandidates={hasCandidates} primary={!operations.some((op) => op.state === "PLANNED")}
                                   onPlanned={refreshAfterPlanning} /> : null}
      <BatchesAwaitingAuthorization project={project} flowId={flowId} refreshToken={batchRefreshToken}
                                    onAuthorized={list.reload} />
      {list.error ? <ErrorState error={list.error} context="operations" /> : null}
      {list.pending || !list.data ? <Pending label="loading operations…" /> : null}
      {list.data && operations.length === 0 ? <p className="text-sm text-muted-foreground">No operation is planned for this flow.</p> : null}
      <ul className="flex flex-col gap-4">
        {operations.map((op, index) => (
          <li key={op.operation_id} className="border-t border-border py-4 text-sm first:border-t-0">
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="inline-flex items-center gap-1"><span aria-hidden="true">{stateSymbol(op.state)}</span><Chip text={op.state} /></span>
              <span className="font-medium">{op.stage ?? "—"}</span>
            </div>
            <p className="mt-1 text-muted-foreground">{op.state_note}</p>
            {op.limits.spend_usd !== null && op.limits.spend_usd > 0 ? (
              <div className="mt-3 max-w-md" aria-label={t("flowAssay.budgetStatus", { spent: op.spent_usd, limit: op.limits.spend_usd, unknown: op.units_with_unknown_cost })}>
                <div className="flex justify-between gap-2 text-xs text-muted-foreground"><span>Spent, as reported</span><span className="font-mono">{op.spent_usd} / {op.limits.spend_usd} USD</span></div>
                <svg className="mt-1 h-3 w-full" viewBox="0 0 100 10" preserveAspectRatio="none" role="img" aria-label={t("flowAssay.budgetUsed")}>
                  <rect x="0" y="0" width="100" height="10" rx="5" fill="var(--muted)" />
                  <rect x="0" y="0" width={Math.min(100, Math.max(0, op.spent_usd / op.limits.spend_usd * 100))} height="10" rx="5" fill="var(--primary)" />
                </svg>
                <p className="text-xs text-muted-foreground">{t("flowAssay.reservedUnknown", { unknown: op.units_with_unknown_cost })}</p>
              </div>
            ) : null}
            <dl className="mt-2 grid grid-cols-[minmax(0,8rem)_minmax(0,1fr)] gap-x-3 gap-y-1 text-[13px]">
              <dt className="text-muted-foreground">Limits</dt>
              <dd>
                network requests {limit(op.limits.network_requests)} · model calls{" "}
                {limit(op.limits.model_calls)} · spend {limit(op.limits.spend_usd, " USD")}
              </dd>
              <dt className="text-muted-foreground">Spent, as reported</dt>
              <dd className="font-mono">{op.spent_usd} USD</dd>
              <dt className="text-muted-foreground">Cost not reported</dt>
              <dd>
                {op.units_with_unknown_cost === 0
                  ? "none"
                  : `${op.units_with_unknown_cost} completed unit(s) did not report a cost: ` +
                    "reserved at their limit, not counted as 0"}
              </dd>
              <dt className="text-muted-foreground">Units completed</dt>
              <dd className="font-mono">{op.units_completed}</dd>
            </dl>
            <details className="mt-3 text-xs text-muted-foreground">
              <summary className="min-h-11 cursor-pointer py-3">{t("flowAssay.details")}</summary>
              <p className="max-w-full truncate font-mono" title={op.operation_id}>{op.operation_id}</p>
              <dl className="mt-2 grid grid-cols-[minmax(0,8rem)_minmax(0,1fr)] gap-x-3 gap-y-1">
              <dt>Last event</dt>
              <dd>
                {op.last_event}
                {op.last_event_at ? ` · ${op.last_event_at}` : " · — (no time recorded)"}
              </dd>
              <dt>Worker</dt>
              <dd>{op.worker_note}</dd>
              </dl>
            </details>
            <div className="mt-2 flex flex-wrap gap-2">
              {op.state === "PLANNED" ? (
                <button
                  type="button"
                  className={`min-h-11 rounded-lg px-4 text-sm font-medium hover:brightness-95 ${index === firstPlannedIndex ? "bg-primary text-primary-foreground" : "border border-border bg-card"}`}
                  onClick={() => setConfirming(op)}
                >
                  Authorize
                </button>
              ) : null}
              <button type="button" disabled title={NO_STOP_EVENT}
                      className="min-h-11 rounded-lg border border-border px-4 text-sm opacity-50">
                Pause
              </button>
              <button type="button" disabled title={NO_STOP_EVENT}
                      className="min-h-11 rounded-lg border border-border px-4 text-sm opacity-50">
                Resume
              </button>
            </div>
          </li>
        ))}
      </ul>
      {confirming ? (
        <AuthorizeDialog
          project={project}
          flowId={flowId}
          op={confirming}
          onClose={() => setConfirming(null)}
          onDone={() => {
            setConfirming(null);
            list.reload();
          }}
        />
      ) : null}
    </>
  );
}

function AuthorizeDialog({ project, flowId, op, onClose, onDone }: {
  project: string; flowId: string; op: OperationSummary; onClose: () => void; onDone: () => void;
}) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  async function confirm() {
    setRunning(true);
    setError(null);
    try {
      // The limits go back exactly as the list returned them: the server refuses a plan that differs.
      await control.authorizeOperation(project, flowId, op.operation_id, op.limits);
      onDone();
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
      setRunning(false);
    }
  }

  return (
    <div role="dialog" aria-modal="true" aria-label="Authorize operation"
         className="mt-4 rounded-lg bg-card p-5 ring-2 ring-primary">
      <h3 className="text-base font-semibold">Authorize {op.stage ?? "operation"}?</h3>
      <p className="mt-1 text-sm">
        This authorizes exactly these limits, and nothing above them:
      </p>
      <ul className="mt-1 list-disc pl-5 text-sm">
        <li>network requests: {limit(op.limits.network_requests)}</li>
        <li>model calls: {limit(op.limits.model_calls)}</li>
        <li>spend: {limit(op.limits.spend_usd, " USD")}</li>
      </ul>
      {error ? <div className="mt-2"><ErrorState error={error} context="authorize" /></div> : null}
      <div className="mt-3 flex gap-2">
        <button type="button" disabled={running} onClick={confirm}
                className="min-h-11 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50">
          {running ? "Authorizing…" : "Confirm authorization"}
        </button>
        <button type="button" disabled={running} onClick={onClose}
                className="min-h-11 rounded-lg border border-border px-4 text-sm">
          Cancel
        </button>
      </div>
    </div>
  );
}
