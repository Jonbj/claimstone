import { useState } from "react";
import { Link } from "react-router";
import Chip from "@/components/Chip";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { control } from "@/lib/control";
import type { OperationSummary } from "@/lib/control";
import { useSession } from "@/lib/session";

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

export default function OperationsPanel({ project, flowId }: { project: string; flowId: string }) {
  const session = useSession();
  return (
    <section aria-label="Right now" className="rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
      <h2 className="mb-2 text-base font-semibold">Right now</h2>
      {!session.ready ? (
        <Pending label="checking session…" />
      ) : session.operator === null ? (
        <p className="text-sm text-muted-foreground">
          <Link to="/login" className="text-blue-600 hover:underline dark:text-blue-400">
            Sign in to see and authorize operations
          </Link>
        </p>
      ) : (
        <OperationsList project={project} flowId={flowId} />
      )}
    </section>
  );
}

function OperationsList({ project, flowId }: { project: string; flowId: string }) {
  const list = useApi(() => control.operations(project, flowId), [project, flowId]);
  const [confirming, setConfirming] = useState<OperationSummary | null>(null);
  if (list.error) return <ErrorState error={list.error} context="operations" />;
  if (list.pending || !list.data) return <Pending label="loading operations…" />;
  const operations = list.data.operations;
  if (operations.length === 0) {
    return <p className="text-sm text-muted-foreground">No operation is planned for this flow.</p>;
  }
  return (
    <>
      <ul className="flex flex-col gap-4">
        {operations.map((op) => (
          <li key={op.operation_id} className="border-b pb-3 text-sm last:border-b-0 last:pb-0">
            <div className="flex flex-wrap items-baseline gap-2">
              <Chip text={op.state} />
              <span className="font-medium">{op.stage ?? "—"}</span>
              <span className="font-mono text-xs text-muted-foreground">{op.operation_id}</span>
            </div>
            <p className="mt-1 text-muted-foreground">{op.state_note}</p>
            <dl className="mt-2 grid grid-cols-[10rem_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-[13px]">
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
              <dt className="text-muted-foreground">Last event</dt>
              <dd>
                {op.last_event}
                {op.last_event_at ? ` · ${op.last_event_at}` : " · — (no time recorded)"}
              </dd>
              <dt className="text-muted-foreground">Worker</dt>
              <dd>{op.worker_note}</dd>
            </dl>
            <div className="mt-2 flex flex-wrap gap-2">
              {op.state === "PLANNED" ? (
                <button
                  type="button"
                  className="min-h-11 rounded-md bg-teal-600 px-4 text-sm font-medium text-white hover:bg-teal-700"
                  onClick={() => setConfirming(op)}
                >
                  Authorize
                </button>
              ) : null}
              <button type="button" disabled title={NO_STOP_EVENT}
                      className="min-h-11 rounded-md px-4 text-sm opacity-50 ring-1 ring-gray-300">
                Pause
              </button>
              <button type="button" disabled title={NO_STOP_EVENT}
                      className="min-h-11 rounded-md px-4 text-sm opacity-50 ring-1 ring-gray-300">
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
         className="mt-4 rounded-lg bg-card p-5 ring-2 ring-teal-600">
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
                className="min-h-11 rounded-md bg-teal-600 px-4 text-sm font-medium text-white disabled:opacity-50">
          {running ? "Authorizing…" : "Confirm authorization"}
        </button>
        <button type="button" disabled={running} onClick={onClose}
                className="min-h-11 rounded-md px-4 text-sm ring-1 ring-gray-300">
          Cancel
        </button>
      </div>
    </div>
  );
}
