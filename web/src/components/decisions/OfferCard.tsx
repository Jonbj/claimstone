import { useState } from "react";
import Chip from "@/components/Chip";
import ErrorState from "@/components/ErrorState";
import { control } from "@/lib/control";
import type { OfferStage, OpenDecision } from "@/lib/control";
import { cn } from "@/lib/utils";
import DeferDecline from "./DeferDecline";
import { has, str } from "./rows";

// One open purchase offer (spec F5). The stage buttons are exactly those the decision rules
// allow from the offer's state (`decisions._NEXT_BY_HAND`, mirrored here for display only —
// the server refuses anything else). `copy_provided` and `copy_verified` are possession the
// server derives from intake: shown as words, never offered as buttons.
const STAGE_BUTTONS: Record<string, Array<{ stage: OfferStage; label: string }>> = {
  proposed: [
    { stage: "approved", label: "Approve" },
    { stage: "declined", label: "Decline" },
  ],
  approved: [
    { stage: "bought_externally", label: "Bought externally" },
    { stage: "declined", label: "Decline" },
  ],
  bought_externally: [],
  deferred: [], // a deferred offer moves only by deferring again or declining
};

export default function OfferCard(
  { item, project, flowId, onDone }: {
    item: OpenDecision;
    project: string;
    flowId: string;
    onDone: () => void;
  },
) {
  const row = item.item;
  const state = str(row.state);
  const possession = str(row.possession);
  const [busyStage, setBusyStage] = useState<OfferStage | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const buttons = STAGE_BUTTONS[state] ?? [];

  async function stage(to: OfferStage) {
    if (busyStage !== null) return;
    setBusyStage(to);
    setError(null);
    try {
      await control.stageOffer(project, flowId, item.id, to);
      onDone();
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusyStage(null);
    }
  }

  return (
    <section
      aria-label={`offer ${item.id}`}
      data-open-id={item.id}
      className="flex flex-col gap-3 rounded-xl bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800"
    >
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="rounded-full bg-neutral-soft px-2.5 py-0.5 text-xs font-semibold text-neutral-ink">
          Optional · purchase offer
        </span>
        <span className="font-mono text-[13px] text-muted-foreground">
          candidate {str(row.candidate_key)}
        </span>
        <span className="ml-auto flex items-baseline gap-2 font-mono text-xs text-muted-foreground">
          {str(row.verified_at) ? <>verified {str(row.verified_at)}</> : null}
        </span>
      </div>
      <p className="flex flex-wrap items-baseline gap-2 text-[17px] font-medium">
        A verified offer for candidate {str(row.candidate_key)}
        <Chip text={state} />
      </p>
      <dl className="grid gap-2 text-[13px] sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg bg-muted/50 p-3">
          <dt className="text-xs text-muted-foreground">Work and version</dt>
          <dd className="mt-0.5">{has(row.work_version)}</dd>
        </div>
        <div className="rounded-lg bg-muted/50 p-3">
          <dt className="text-xs text-muted-foreground">Vendor · price</dt>
          <dd className="mt-0.5">
            {has(row.vendor)} · {has(row.price)} {has(row.currency)} · tax {has(row.tax_status)}
          </dd>
        </div>
        <div className="rounded-lg bg-muted/50 p-3">
          <dt className="text-xs text-muted-foreground">Terms</dt>
          <dd className="mt-0.5 break-all">
            {str(row.terms_url) ? (
              <a href={str(row.terms_url)} target="_blank" rel="noreferrer" className="underline">
                {str(row.terms_url)}
              </a>
            ) : (
              "—"
            )}
          </dd>
        </div>
        <div className="rounded-lg bg-muted/50 p-3">
          <dt className="text-xs text-muted-foreground">Why it might help</dt>
          <dd className="mt-0.5">{has(row.resolves)}</dd>
        </div>
      </dl>
      {possession ? (
        <p className="flex flex-wrap items-baseline gap-2 text-sm">
          <span
            className={cn(
              "rounded-full px-2.5 py-0.5 text-xs font-semibold",
              possession === "copy_verified"
                ? "bg-done/10 text-done"
                : "bg-acting-soft text-acting-ink",
            )}
          >
            {possession}
          </span>
          <span className="text-xs text-muted-foreground">
            possession the server derives from intake; it is never set by hand
          </span>
        </p>
      ) : null}
      {state === "deferred" ? (
        <p className="text-[13px] text-muted-foreground">
          deferred until {has(row.until)} — the date has come, so it is on the open list again
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        {buttons.map((button) => (
          <button
            key={button.stage}
            type="button"
            disabled={busyStage !== null}
            onClick={() => void stage(button.stage)}
            className="min-h-11 rounded-lg border border-border px-4 text-sm disabled:opacity-50"
          >
            {busyStage === button.stage ? "Recording…" : button.label}
          </button>
        ))}
      </div>
      {state !== "bought_externally" ? (
        <DeferDecline
          project={project}
          flowId={flowId}
          decisionId={item.id}
          onDone={onDone}
          allowDecline={buttons.length === 0}
        />
      ) : null}
      {error ? <ErrorState error={error} context="offer" /> : null}
      <p className="text-xs text-muted-foreground">
        Approving is permission to buy this exact offer, not a purchase; the purchase happens
        outside Claimstone. A changed price, vendor or terms is a new offer; this one becomes
        obsolete, linked. A 403 is never an offer.
      </p>
    </section>
  );
}
