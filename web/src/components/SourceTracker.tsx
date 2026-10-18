import { Tracker } from "@/components/tremor/Tracker/Tracker";
import NoticeBadge from "@/components/NoticeBadge";
import type { Overview } from "@/lib/api-types";
import { useLocale } from "@/lib/i18n";

// §8.3: one block per scoped candidate, in server order, with the server-provided
// state and its tooltip text — the client derives nothing (F11). Rose marks an
// acquisition that was not obtained; the state word is always present (rule 7).
export type TrackerEntry = Overview["source_tracker"][number];

const STATE_ORDER: TrackerEntry["state"][] = [
  "confirmed",
  "awaiting_normalize",
  "not_a_document",
  "not_obtained",
  "not_attempted",
  "unclassified",
];

const STATE_COLOR: Record<TrackerEntry["state"], string> = {
  confirmed: "bg-emerald-500",
  awaiting_normalize: "bg-blue-500",
  not_a_document: "bg-amber-400",
  not_obtained: "bg-rose-500",
  not_attempted: "bg-gray-300",
  unclassified: "bg-slate-400",
};

// Rule 5: the legend shows the API's own state words, verbatim — never a paraphrase.
const STATE_WORD: Record<TrackerEntry["state"], string> = {
  confirmed: "confirmed",
  awaiting_normalize: "awaiting_normalize",
  not_a_document: "not_a_document",
  not_obtained: "not_obtained",
  not_attempted: "not_attempted",
  unclassified: "unclassified",
};

export default function SourceTracker({ entries }: { entries: TrackerEntry[] }) {
  const { t } = useLocale();
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">no candidates in this scope</p>;
  }
  const noticed = entries.filter((entry) => entry.status?.state === "NOTICE_RECORDED");
  const counts = new Map<TrackerEntry["state"], number>();
  for (const entry of entries) counts.set(entry.state, (counts.get(entry.state) ?? 0) + 1);
  return (
    <div className="assay-tracker">
      <Tracker
        data={entries.map((entry) => ({
          key: entry.candidate_key,
          color: STATE_COLOR[entry.state],
          tooltip: entry.tooltip,
        }))}
        defaultBackgroundColor="bg-gray-200"
        hoverEffect
        aria-label="sources in this scope, server order"
      />
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {STATE_ORDER.filter((state) => counts.get(state)).map((state) => (
          <span key={state} data-tracker-state={state}>
            <span className={`mr-1 inline-block size-2 rounded-[1px] ${STATE_COLOR[state]}`} />
            {STATE_WORD[state]} {counts.get(state)}
          </span>
        ))}
      </div>
      {noticed.length > 0 ? (
        <div role="note" className="mt-3 rounded-lg border border-border bg-muted/50 p-3 text-sm">
          <p className="font-medium">{t("status.summary", { n: noticed.length })}</p>
          <ul className="mt-2 flex flex-col gap-1.5">
            {noticed.map((entry) => (
              <li key={entry.candidate_key} className="flex flex-wrap items-center gap-2 text-xs">
                <span className="max-w-prose truncate font-medium">{entry.title ?? entry.candidate_key}</span>
                <NoticeBadge status={entry.status} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
