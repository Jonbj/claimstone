import { Link } from "react-router";
import type { Overview } from "@/lib/api-types";
import type { MatrixRow } from "@/components/QuestionMatrix";

// The guided journey (spec J2). The steps arrive from the server with their status, actor and
// summary; this file maps a status to a colour and a shape and prints the status word beside it
// (colour never alone). It computes no status and re-labels none.
export type Journey = Overview["journey"];
export type JourneyStep = Journey["steps"][number];

const STATUS: Record<JourneyStep["status"], { word: string; bar: string; mark: string; ink: string }> = {
  done: { word: "done", bar: "bg-done", mark: "bg-done text-white", ink: "text-done" },
  running: { word: "running", bar: "bg-acting", mark: "bg-acting text-white", ink: "text-acting-ink" },
  waits_for_you: { word: "waits for you", bar: "bg-waits", mark: "bg-waits text-white", ink: "text-waits-ink" },
  blocked: { word: "blocked", bar: "bg-not-obtained", mark: "bg-not-obtained text-white", ink: "text-not-obtained" },
  partial: {
    word: "partial",
    bar: "bg-gradient-to-r from-done from-50% to-gray-300 to-50%",
    mark: "bg-gradient-to-r from-done from-50% to-gray-300 to-50% text-foreground",
    ink: "text-foreground",
  },
  not_started: { word: "not started", bar: "bg-gray-300", mark: "bg-gray-200 text-gray-700", ink: "text-muted-foreground" },
  not_applicable: { word: "not applicable", bar: "bg-slate-400", mark: "bg-slate-300 text-slate-800", ink: "text-muted-foreground" },
};

const ACTOR: Record<JourneyStep["actor"], { word: string; cls: string }> = {
  claimstone: { word: "Claimstone", cls: "bg-acting-soft text-acting-ink" },
  you: { word: "you", cls: "bg-waits-soft text-waits-ink" },
};

// A figure is printed as received; null or absent is "—", never 0.
function show(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

const LABELS: Record<string, string> = {};

function Figures({ figures }: { figures: JourneyStep["figures"] }) {
  const entries = Object.entries(figures).filter(([, v]) => typeof v !== "object" || v === null);
  if (entries.length === 0) return null;
  return (
    <dl className="mt-1.5 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted-foreground">
      {entries.map(([key, value]) => (
        <div key={key} className="flex gap-1" data-figure={key}>
          <dt>{LABELS[key] ?? key.replace(/_/g, " ")}</dt>
          <dd className="font-mono text-foreground">{show(value)}</dd>
        </div>
      ))}
    </dl>
  );
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

export default function JourneySteps({
  journey, rows, base, writable,
}: {
  journey: Journey;
  rows: MatrixRow[];
  base: string;
  writable: boolean;
}) {
  const ready = readyToSign(rows);
  return (
    <section aria-label="The journey" className="flex flex-col gap-4">
      <h2 className="text-base font-semibold">The journey</h2>
      <SegmentBar steps={journey.steps} />
      <ol className="flex flex-col gap-3">
        {journey.steps.map((step) => {
          const s = STATUS[step.status];
          const a = ACTOR[step.actor];
          return (
            <li key={step.n} data-step={step.key} data-status={step.status}
                className="flex gap-3 rounded-lg bg-card p-4 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
              <span aria-hidden="true"
                    className={`flex size-7 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${s.mark}`}>
                {step.status === "done" ? "✓" : step.n}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-2">
                  <h3 className="text-sm font-semibold">{step.n}. {step.title}</h3>
                  <span className={`rounded-md px-1.5 text-xs ${a.cls}`} data-actor={step.actor}>{a.word}</span>
                  <span className={`text-xs font-medium ${s.ink}`} data-status-word>{s.word}</span>
                </div>
                <p className="mt-1 text-sm">{step.summary}</p>
                {step.key === "copies" ? <FloorLine figures={step.figures} /> : null}
                <Figures figures={step.figures} />
                {step.key === "sign" ? (
                  writable && ready.length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {ready.map((row) => (
                        <Link key={row.id} to={`${base}/q/${encodeURIComponent(row.id)}`}
                              className="inline-flex min-h-11 items-center rounded-md bg-waits px-4 text-sm font-medium text-white hover:opacity-90">
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
