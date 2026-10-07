import { useState } from "react";
import type { FormEvent } from "react";
import ErrorState from "@/components/ErrorState";
import { control } from "@/lib/control";
import { str } from "./rows";

// Defer or decline an open decision (spec F5: offers and campaigns). Both need a reason the
// server judges (≥ 20 trimmed characters); a deferral also needs a future ISO date. The
// consequence sentence is the server's, on the row it appends — never composed here.
export default function DeferDecline(
  { project, flowId, decisionId, onDone, allowDecline }: {
    project: string;
    flowId: string;
    decisionId: string;
    onDone: () => void;
    /** An offer declines through its own stage route; a campaign through this one. */
    allowDecline: boolean;
  },
) {
  const [open, setOpen] = useState<"defer" | "decline" | null>(null);
  const [until, setUntil] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  async function submit(event: FormEvent, state: "deferred" | "declined") {
    event.preventDefault(); // the CSP has form-action 'none': a native submit is never wanted
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const body = state === "deferred"
        ? { state, until, reason }
        : { state, reason };
      await control.setDecisionState(project, flowId, decisionId, body);
      setOpen(null);
      setUntil("");
      setReason("");
      onDone();
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setOpen(open === "defer" ? null : "defer")}
          aria-expanded={open === "defer"}
          className="min-h-11 rounded-lg border border-border px-4 text-sm"
        >
          Defer…
        </button>
        {allowDecline ? (
          <button
            type="button"
            onClick={() => setOpen(open === "decline" ? null : "decline")}
            aria-expanded={open === "decline"}
            className="min-h-11 rounded-lg border border-border px-4 text-sm"
          >
            Decline…
          </button>
        ) : null}
      </div>
      {open === "defer" ? (
        <form onSubmit={(e) => void submit(e, "deferred")} className="flex flex-col gap-2">
          <label className="flex flex-col gap-1 text-sm font-medium">
            Returns to the open list on (ISO date)
            <input
              name="until"
              type="date"
              value={until}
              onChange={(e) => setUntil(e.target.value)}
              required
              className="min-h-11 rounded-lg border border-border bg-card px-3 text-sm font-normal"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium">
            Your reason
            <input
              name="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              required
              className="min-h-11 rounded-lg border border-border bg-card px-3 text-sm font-normal"
            />
          </label>
          <button
            type="submit"
            disabled={busy || !until || !reason.trim()}
            className="min-h-11 self-start rounded-lg border border-border px-4 text-sm disabled:opacity-50"
          >
            {busy ? "Deferring…" : "Defer"}
          </button>
        </form>
      ) : null}
      {open === "decline" ? (
        <form onSubmit={(e) => void submit(e, "declined")} className="flex flex-col gap-2">
          <label className="flex flex-col gap-1 text-sm font-medium">
            Your reason
            <input
              name="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              required
              className="min-h-11 rounded-lg border border-border bg-card px-3 text-sm font-normal"
            />
          </label>
          <button
            type="submit"
            disabled={busy || !reason.trim()}
            className="min-h-11 self-start rounded-lg border border-border px-4 text-sm disabled:opacity-50"
          >
            {busy ? "Declining…" : "Decline"}
          </button>
        </form>
      ) : null}
      {error ? <ErrorState error={error} context={str(open) || "decision"} /> : null}
    </div>
  );
}
