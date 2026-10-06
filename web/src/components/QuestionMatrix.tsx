import { Link } from "react-router";
import Chip from "@/components/Chip";
import Fraction from "@/components/Fraction";
import type { Overview } from "@/lib/api-types";

// The questions table (§8.3): registry order, per-class counts before the total
// (§4.2 rule 2), a mini bar of direction counts labelled with the counts and the
// server's note verbatim (rules 1 and 5), the five verdicts plus dashed engine
// states (rule 3). The server's row order is the DOM order — no operator filter
// is offered here, so none can reorder it (rule 6).
export type MatrixRow = Overview["questions"]["rows"][number];

// The direction segments are coloured by position, never by meaning: the words
// beside the bar carry the meaning (rule 7).
const SEGMENT_COLORS = ["bg-blue-500", "bg-sky-500", "bg-gray-300", "bg-indigo-400"];

export default function QuestionMatrix({
  rows,
  base = "",
}: {
  rows: MatrixRow[];
  base?: string;
}) {
  return (
    <div>
      <table className="w-full min-w-[620px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-foreground">
            <th className="p-2 font-semibold">ID</th>
            <th className="p-2 font-semibold">Question</th>
            <th className="p-2 font-semibold">Per class → total</th>
            <th className="p-2 font-semibold">Direction (count)</th>
            <th className="p-2 font-semibold">Status</th>
          </tr>
        </thead>
        <tbody className="text-muted-foreground">
          {rows.map((row) => {
            const directions = Object.entries(row.direction_count).map(
              ([name, count]) => [name, Number(count)] as const,
            );
            return (
              <tr key={row.id} data-question-id={row.id} className="border-b border-border/60">
                <td className="p-3 font-mono text-[13px] text-foreground">
                  {base ? (
                    <Link
                      to={`${base}/q/${encodeURIComponent(row.id)}`}
                      className="text-blue-600 hover:underline dark:text-blue-400"
                    >
                      {row.id}
                    </Link>
                  ) : (
                    row.id
                  )}
                </td>
                <td className="max-w-[280px] whitespace-normal p-3">{row.text}</td>
                <td className="p-3 font-mono text-[13px]">
                  {Object.keys(row.claims_by_class).length === 0 ? (
                    <span title="not knowable">—</span>
                  ) : (
                    Object.entries(row.claims_by_class).map(([name, count]) => (
                      <span key={name} className="by-class mr-1.5" data-class={name}>
                        {name} {count}
                      </span>
                    ))
                  )}
                  <span className="text-muted-foreground">
                    → <Fraction numerator={row.claims} /> total
                  </span>
                </td>
                <td className="p-3">
                  {directions.length === 0 ? (
                    <span title="not knowable">—</span>
                  ) : (
                    <>
                      <div className="flex h-1.5 w-[120px] gap-px" aria-hidden="true">
                        {directions.map(([name, count], index) => (
                          <div
                            key={name}
                            className={SEGMENT_COLORS[index % SEGMENT_COLORS.length]}
                            style={{ flexGrow: Math.max(count, 1) }}
                          />
                        ))}
                      </div>
                      <span className="text-xs">
                        {directions.map(([name, count]) => `${name} ${count}`).join(" · ")}{" "}
                        ({row.direction_count_note})
                      </span>
                    </>
                  )}
                </td>
                <td className="p-3">
                  {row.operational_not_applicable ? (
                    <>
                      <Chip text="LITERATURE_VERDICT_NOT_APPLICABLE" />
                      <br />
                      <span className="text-xs">kind operational: no verdict</span>
                    </>
                  ) : row.verdict ? (
                    <>
                      <Chip text={row.verdict} />
                      {row.verdict_stale ? <Chip text="stale" /> : null}
                    </>
                  ) : row.state === "NO_VERIFIED_CLAIM" ? (
                    <Chip text="NO_VERIFIED_CLAIM" />
                  ) : row.state ? (
                    <Chip text={row.state} />
                  ) : (
                    <span className="chip dashed" title="not knowable">
                      — no verdict
                    </span>
                  )}
                  {row.provisional ? (
                    <>
                      <br />
                      <Chip text={row.blocking.join(", ") || "provisional"} />
                    </>
                  ) : null}
                  {row.unavailable ? (
                    <>
                      <br />
                      <span className="text-xs">historical — {row.unavailable}</span>
                    </>
                  ) : null}
                  {row.note ? (
                    <>
                      <br />
                      <span className="text-xs">{row.note}</span>
                    </>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-muted-foreground">
        Claims are counted per class before they are pooled (invariant 6).
        NO_VERIFIED_CLAIM is the engine's categorical outcome and never a verdict:
        only a person can say "never asked". No pooling, no R: a person reads the
        profile and signs.
      </p>
    </div>
  );
}
