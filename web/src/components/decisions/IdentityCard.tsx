import { useState } from "react";
import type { FormEvent } from "react";
import ErrorState from "@/components/ErrorState";
import { control } from "@/lib/control";
import type { IdentityAnswer, OpenDecision } from "@/lib/control";
import { cn } from "@/lib/utils";
import { has, linksOf, str } from "./rows";

// One open identity question (spec F5): a POSSIBLE_VERSION intake item a person answers.
// The four answers are the API's own words; the reason is required except for `not_sure`,
// and the ≥ 20 trimmed-character rule is a client-side hint only — the server decides and
// its 422 is shown as given.
const ANSWERS: Array<{ value: IdentityAnswer; label: string }> = [
  { value: "same_work", label: "Same work" },
  { value: "version_of", label: "An earlier version of it" },
  { value: "different", label: "Different works" },
  { value: "not_sure", label: "Not sure — keep pending" },
];

const MIN_REASON_CHARS = 20;

export default function IdentityCard(
  { item, project, flowId, onDone }: {
    item: OpenDecision;
    project: string;
    flowId: string;
    onDone: () => void;
  },
) {
  const row = item.item;
  const candidate = str(linksOf(row).candidate_key);
  const [answer, setAnswer] = useState<IdentityAnswer | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // A hint, never a gate: the server is the authority on the reason's length.
  const shortReason = answer !== null && answer !== "not_sure" &&
    reason.trim().length < MIN_REASON_CHARS;

  async function submit(event: FormEvent) {
    event.preventDefault(); // the CSP has form-action 'none': a native submit is never wanted
    if (answer === null || busy) return;
    setBusy(true);
    setError(null);
    try {
      const body = answer === "not_sure" && !reason.trim()
        ? { answer }
        : { answer, reason };
      await control.resolveIntake(project, flowId, item.id, body);
      onDone();
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      aria-label={`identity ${item.id}`}
      data-open-id={item.id}
      className="flex flex-col gap-3 rounded-xl bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800"
    >
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="rounded-full bg-waits-soft px-2.5 py-0.5 text-xs font-semibold text-waits-ink">
          Required · identity
        </span>
        <span className="font-mono text-[13px] text-muted-foreground">candidate {candidate}</span>
        <span className="ml-auto font-mono text-xs text-muted-foreground">{has(item.recorded_at)}</span>
      </div>
      <p className="text-[17px] font-medium">
        Is this the same work as candidate {candidate}?
      </p>
      <p className="text-sm">
        <span className="font-mono">{has(str(row.submitted) || str(row.value))}</span>
        <span className="ml-2 text-xs text-muted-foreground">
          {str(row.kind)} · {str(row.state)}
        </span>
      </p>
      <p className="text-[13px] text-muted-foreground">{has(row.reason)}</p>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <div role="group" aria-label="Your answer" className="flex flex-wrap gap-2">
          {ANSWERS.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={answer === option.value}
              onClick={() => setAnswer(option.value)}
              className={cn(
                "min-h-11 rounded-lg px-4 text-sm",
                answer === option.value
                  ? "border-2 border-rail font-medium"
                  : "border border-border",
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
        <label className="flex flex-col gap-1 text-sm font-medium">
          Your reason
          <input
            name="reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="min-h-11 rounded-lg border border-border bg-card px-3 text-sm font-normal"
          />
        </label>
        {shortReason ? (
          <p data-testid="reason-hint" className="text-xs text-muted-foreground">
            The server requires at least {MIN_REASON_CHARS} trimmed characters for this answer
            (none for not sure); it decides, and its refusal is shown as given.
          </p>
        ) : null}
        <div>
          <button
            type="submit"
            disabled={answer === null || busy}
            className="min-h-11 rounded-lg bg-rail px-4 text-sm font-semibold text-rail-foreground disabled:opacity-50"
          >
            {busy ? "Recording…" : "Record answer"}
          </button>
        </div>
      </form>
      {error ? <ErrorState error={error} context="identity" /> : null}
      <p className="text-xs text-muted-foreground">
        Recorded as a relationship. Both records are kept; nothing is merged, and a version is
        never counted as an additional independent study.
      </p>
    </section>
  );
}
