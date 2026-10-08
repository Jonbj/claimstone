import { useState } from "react";
import type { FormEvent } from "react";
import ErrorState from "@/components/ErrorState";
import { control } from "@/lib/control";
import type { IntakeKind, Row } from "@/lib/control";
import StateChip from "./StateChip";
import { has, str } from "../decisions/rows";

// Propose material (spec F5): a kind, a value and an optional note. The server routes it
// before anything counts, and the row it answers with is shown as its own state and reason.
const KINDS: Array<{ value: IntakeKind; label: string }> = [
  { value: "reference", label: "Reference" },
  { value: "doi", label: "DOI" },
  { value: "url", label: "Link" },
];

export default function ProposeForm(
  { project, flowId, onDone }: { project: string; flowId: string; onDone: () => void },
) {
  const [kind, setKind] = useState<IntakeKind>("reference");
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [result, setResult] = useState<Row | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault(); // the CSP has form-action 'none': a native submit is never wanted
    if (busy || !value.trim()) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const body = note.trim() ? { kind, value: value.trim(), note: note.trim() }
        : { kind, value: value.trim() };
      const answer = await control.submitIntake(project, flowId, body);
      setResult(answer.intake);
      setValue("");
      setNote("");
      onDone();
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      aria-label="Propose material"
      className="rounded-xl bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800"
    >
      <h2 className="text-base font-semibold">Propose</h2>
      <p className="mb-3 mt-0.5 text-[13px] text-muted-foreground">
        A reference, DOI or link you think belongs here. The server routes it and says where it
        went; nothing is fetched and nothing counts.
      </p>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <div className="grid gap-3 sm:grid-cols-[minmax(0,160px)_minmax(0,1fr)]">
          <label className="flex flex-col gap-1 text-sm font-medium">
            Kind
            <select
              name="kind"
              value={kind}
              onChange={(e) => setKind(e.target.value as IntakeKind)}
              className="min-h-11 rounded-lg border border-border bg-card px-3 text-sm font-normal"
            >
              {KINDS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium">
            Value
            <input
              name="value"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={kind === "doi" ? "10.xxxx/…" : kind === "url" ? "https://…" : "the reference as written"}
              className="min-h-11 rounded-lg border border-border bg-card px-3 font-mono text-sm font-normal"
            />
          </label>
        </div>
        <label className="flex flex-col gap-1 text-sm font-medium">
          Note (optional)
          <input
            name="note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="min-h-11 rounded-lg border border-border bg-card px-3 text-sm font-normal"
          />
        </label>
        <div>
          <button
            type="submit"
            disabled={busy || !value.trim()}
            className="min-h-11 rounded-lg bg-rail px-4 text-sm font-semibold text-rail-foreground disabled:opacity-50"
          >
            {busy ? "Proposing…" : "Propose"}
          </button>
        </div>
      </form>
      {result ? (
        <div data-testid="propose-result" className="mt-3 rounded-lg bg-muted/50 p-3 text-[13px]">
          <p className="flex flex-wrap items-baseline gap-2">
            <span className="font-mono">{has(str(result.submitted) || str(result.value))}</span>
            <StateChip state={str(result.state)} />
            <span className="ml-auto font-mono text-xs text-muted-foreground">
              {has(result.recorded_at)}
            </span>
          </p>
          <p className="mt-1 text-muted-foreground">{has(result.reason)}</p>
        </div>
      ) : null}
      {error ? <ErrorState error={error} context="propose" /> : null}
    </section>
  );
}
