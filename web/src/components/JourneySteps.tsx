import { Link } from "react-router";
import { formatUtc, isIsoTimestamp } from "@/lib/datetime";
import type { Overview } from "@/lib/api-types";
import type { MatrixRow } from "@/components/QuestionMatrix";
import { useLocale } from "@/lib/i18n";

// The guided journey (spec J2). The steps arrive from the server with their status, actor and
// summary; this file maps a status to a colour and a shape and prints the status word beside it
// (colour never alone). It computes no status and re-labels none.
export type Journey = Overview["journey"];
export type JourneyStep = Journey["steps"][number];

const STATUS: Record<JourneyStep["status"], { word: string; symbol: string; bar: string; mark: string; ink: string; chip: string }> = {
  done: { word: "done", symbol: "✓", bar: "bg-done", mark: "bg-done/15 text-done", ink: "text-done", chip: "bg-done/15 text-done" },
  running: { word: "running", symbol: "◐", bar: "bg-acting", mark: "bg-acting-soft text-acting-ink", ink: "text-acting-ink", chip: "bg-acting-soft text-acting-ink" },
  waits_for_you: { word: "waits for you", symbol: "●", bar: "bg-waits", mark: "bg-waits-soft text-waits-ink", ink: "text-waits-ink", chip: "bg-waits-soft text-waits-ink" },
  blocked: { word: "blocked", symbol: "■", bar: "bg-not-obtained", mark: "bg-not-obtained/15 text-not-obtained", ink: "text-not-obtained", chip: "bg-not-obtained/15 text-not-obtained" },
  partial: { word: "partial", symbol: "▲", bar: "bg-provisional", mark: "bg-waits-soft text-waits-ink", ink: "text-provisional", chip: "bg-waits-soft text-waits-ink" },
  not_started: { word: "not started", symbol: "○", bar: "bg-neutral-soft", mark: "bg-neutral-soft text-neutral-ink", ink: "text-muted-foreground", chip: "bg-neutral-soft text-neutral-ink" },
  not_applicable: { word: "not applicable", symbol: "○", bar: "bg-neutral-soft", mark: "bg-neutral-soft text-neutral-ink", ink: "text-muted-foreground", chip: "bg-neutral-soft text-neutral-ink" },
};

const ACTOR: Record<JourneyStep["actor"], { word: string; cls: string }> = {
  claimstone: { word: "Claimstone", cls: "bg-acting-soft text-acting-ink" },
  you: { word: "you", cls: "bg-waits-soft text-waits-ink" },
};

// A figure is printed as received; null or absent is "—", never 0.
function show(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value) && value.every((x) => typeof x === "string")) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

const LABELS: Record<string, string> = {};

function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || (Array.isArray(value) && value.length === 0) || value === "";
}

function Figures({ figures }: { figures: JourneyStep["figures"] }) {
  // `status` only restates the step (the floor line already reads it); an empty `drifted_parts` says
  // nothing; `note` is a sentence, not a figure. Every numeric figure stays, null shown as "—".
  const entries = Object.entries(figures).filter(([key, v]) => {
    if (key === "status" || key === "note") return false;
    if (key === "drifted_parts" && isEmpty(v)) return false;
    return typeof v !== "object" || v === null || (Array.isArray(v) && v.every((x) => typeof x === "string"));
  });
  const note = typeof figures.note === "string" && figures.note ? figures.note : null;
  if (entries.length === 0 && note === null) return null;
  return (
    <>
      {entries.length > 0 ? (
        <dl className="mt-1.5 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted-foreground">
          {entries.map(([key, value]) => (
            <div key={key} className="flex gap-1" data-figure={key}>
              <dt>{LABELS[key] ?? key.replace(/_/g, " ")}</dt>
              {isIsoTimestamp(value) ? (
                <dd className="font-mono text-foreground" title={value}>{formatUtc(value)}</dd>
              ) : (
                <dd className="font-mono text-foreground">{show(value)}</dd>
              )}
            </div>
          ))}
        </dl>
      ) : null}
      {note ? <p className="mt-1 text-xs text-muted-foreground" data-note>{note}</p> : null}
    </>
  );
}

// The floor line says nothing about a step that has not begun or has found nothing yet.
function showsFloor(step: JourneyStep): boolean {
  const found = step.figures.found;
  return step.status !== "not_started" && typeof found === "number" && found > 0;
}

function FloorLine({ figures }: { figures: JourneyStep["figures"] }) {
  const rate = figures.rate;
  const floor = figures.floor;
  const status = figures.status;
  if (status === "OK") {
    return <p className="mt-1 text-sm font-medium" data-floor="met">floor met · {show(rate)} ≥ {show(floor)}</p>;
  }
  if (status === "INSUFFICIENT_ACQUISITION") {
    return <p className="mt-1 text-sm font-medium" data-floor="below">below floor · {show(rate)} of {show(floor)}</p>;
  }
  return <p className="mt-1 text-sm font-medium" data-floor="unknown">floor — · {show(rate)} of {show(floor)}</p>;
}

// Questions the existing matrix marks as waiting for a person to sign.
export function readyToSign(rows: MatrixRow[]): MatrixRow[] {
  return rows.filter((row) => row.display_state === "awaiting_a_person");
}

export function SegmentBar({ steps }: { steps: JourneyStep[] }) {
  return (
    <ol aria-label="Journey progress" className="flex h-2 gap-1">
      {steps.map((step) => (
        <li key={step.n} className={`flex-1 rounded-full ${STATUS[step.status].bar}`}
            title={`${step.n}. ${step.title}: ${STATUS[step.status].word}`} />
      ))}
    </ol>
  );
}

// `keys`, `heading` and `bar` let a block panel show part of the journey: the flow page puts step 1
// under Protocol, steps 2-7 under Pipeline and step 8 under Human reading. Defaults keep the whole
// journey, as before. Nothing here decides a status; the steps are the server's.
export default function JourneySteps({
  journey, rows, base, writable, keys, heading = "The journey", bar = true,
}: {
  journey: Journey;
  rows: MatrixRow[];
  base: string;
  writable: boolean;
  keys?: readonly string[];
  heading?: string | null;
  bar?: boolean;
}) {
  const { t } = useLocale();
  const ready = readyToSign(rows);
  const steps = keys ? journey.steps.filter((step) => keys.includes(step.key)) : journey.steps;
  return (
    <section aria-label={heading ?? "Journey steps"} className="flex flex-col gap-4">
      {heading === null ? null : <h2 className="text-base font-semibold">{heading}</h2>}
      {bar ? <SegmentBar steps={steps} /> : null}
      <ol className="overflow-hidden rounded-xl border border-border bg-card">
        {steps.map((step) => {
          const s = STATUS[step.status];
          const a = ACTOR[step.actor];
          return (
            <li key={step.n} data-step={step.key} data-status={step.status}
                className={`flex gap-4 border-t border-border p-4 first:border-t-0 sm:px-5 ${step.status === "blocked" ? "bg-not-obtained/5" : ""}`}>
              <span aria-hidden="true"
                    className={`flex size-7 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${s.mark}`}>
                {s.symbol}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-semibold">{step.n}. {step.title}</h3>
                  <span className={`rounded-md px-1.5 text-xs ${a.cls}`} data-actor={step.actor}>{a.word}</span>
                  <span className={`ml-auto rounded-full px-2.5 py-1 text-xs font-semibold ${s.chip}`}><span aria-hidden="true">{s.symbol} </span><span data-status-word>{s.word}</span></span>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">{step.summary}</p>
                {step.key === "copies" && showsFloor(step) ? <FloorLine figures={step.figures} /> : null}
                {Object.keys(step.figures).length > 0 ? <details className="mt-1 text-xs text-muted-foreground"><summary className="min-h-11 cursor-pointer py-3">{t("flowAssay.figures")}</summary><Figures figures={step.figures} /></details> : null}
                {step.key === "sign" ? (
                  writable && ready.length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {ready.map((row) => (
                        <Link key={row.id} to={`${base}/q/${encodeURIComponent(row.id)}`}
                              className="inline-flex min-h-11 items-center rounded-lg border border-border bg-card px-4 text-sm font-medium hover:bg-muted">
                          Read and sign {row.id}
                        </Link>
                      ))}
                    </div>
                  ) : null
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
