import { useState } from "react";
import { Link } from "react-router";
import Chip from "@/components/Chip";
import { stateLabel } from "@/lib/vocabulary";
import type { Journey } from "@/components/JourneySteps";
import type { MatrixRow } from "@/components/QuestionMatrix";

// The journey's right column (spec J2), except "Right now", which is the OperationsPanel.
// Everything is the server's: a null collection renders its note, never 0 or an empty claim.
function count(value: number | null): string {
  return value === null ? "—" : String(value);
}

export function RunningNote({ journey }: { journey: Journey }) {
  if (journey.running !== null) return null;
  return (
    <p className="text-xs text-muted-foreground" data-running-note>
      {journey.running_note ?? "operations are not readable"}
    </p>
  );
}

const TOPICS_SHOWN = 4;

export function TheTopic({ topics }: { topics: Journey["topics"] }) {
  const [all, setAll] = useState(false);
  const shown = all ? topics : topics.slice(0, TOPICS_SHOWN);
  const hidden = topics.length - TOPICS_SHOWN;
  return (
    <section aria-label="The topic" className="rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
      <h2 className="mb-2 text-base font-semibold">The topic</h2>
      {topics.length === 0 ? (
        <p className="text-sm text-muted-foreground">no topics declared</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {shown.map((topic) => (
            <li key={topic.id} className="text-sm" data-topic={topic.id}>
              <b>{topic.label}</b>
              <span className="block text-xs text-muted-foreground">
                {topic.terms.length > 0 ? topic.terms.join(" · ") : "—"}
              </span>
            </li>
          ))}
        </ul>
      )}
      {hidden > 0 ? (
        <button type="button" aria-expanded={all} onClick={() => setAll((v) => !v)}
                className="mt-2 inline-flex min-h-11 items-center rounded-md px-3 text-sm ring-1 ring-gray-300 hover:bg-gray-50 dark:ring-gray-700 dark:hover:bg-gray-900">
          {all ? "Show fewer topics" : `Show all ${topics.length} topics`}
        </button>
      ) : null}
    </section>
  );
}

function stateWord(row: MatrixRow): string {
  if (row.operational_not_applicable) return "LITERATURE_VERDICT_NOT_APPLICABLE";
  if (row.verdict) return row.verdict;
  return row.display_state === "no_verified_claim" ? "NO_VERIFIED_CLAIM" : row.display_state;
}

export function TheQuestions({ rows, base }: { rows: MatrixRow[]; base: string }) {
  return (
    <section aria-label="The questions" className="rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
      <h2 className="mb-2 text-base font-semibold">The questions</h2>
      <ul className="flex flex-col gap-2">
        {rows.map((row) => (
          <li key={row.id} data-question-id={row.id} className="flex items-baseline gap-2 text-sm">
            <Link to={`${base}/q/${encodeURIComponent(row.id)}`}
                  className="font-mono text-[13px] text-blue-600 hover:underline dark:text-blue-400">
              {row.id}
            </Link>
            <span className="min-w-0 flex-1 text-muted-foreground">{row.text}</span>
            <Chip text={stateWord(row)} label={stateLabel(stateWord(row))} />
          </li>
        ))}
      </ul>
    </section>
  );
}

export function NeedsYou({ needs, base, writable }: {
  needs: Journey["needs_you"]; base: string; writable: boolean;
}) {
  return (
    <section aria-label="Needs you" className="rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
      <h2 className="mb-2 text-base font-semibold">Needs you</h2>
      {needs.required === null && needs.optional === null ? (
        <p className="text-sm text-muted-foreground" data-needs-note>
          {needs.note ?? "decisions are not readable"}
        </p>
      ) : (
        <dl className="flex flex-col gap-1 text-sm">
          <div className="flex justify-between"><dt>Required decisions</dt><dd className="font-mono">{count(needs.required)}</dd></div>
          <div className="flex justify-between"><dt>Optional decisions</dt><dd className="font-mono">{count(needs.optional)}</dd></div>
        </dl>
      )}
      <p className="mt-1 flex justify-between text-sm">
        <span>Ready to sign</span><span className="font-mono">{needs.ready_to_sign}</span>
      </p>
      {writable ? (
        <Link to={`${base}/decisions`}
              className="mt-3 inline-flex min-h-11 items-center rounded-md px-4 text-sm font-medium ring-1 ring-gray-300 hover:bg-gray-50 dark:ring-gray-700 dark:hover:bg-gray-900">
          Open decisions
        </Link>
      ) : null}
    </section>
  );
}
