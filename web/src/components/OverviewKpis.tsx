import { CategoryBar } from "@/components/tremor/CategoryBar/CategoryBar";
import { DonutChart } from "@/components/tremor/DonutChart/DonutChart";
import { ProgressBar } from "@/components/tremor/ProgressBar/ProgressBar";
import { getColorClassName, type AvailableChartColorsKeys } from "@/components/tremor/utils/chartColors";
import type { ReactNode } from "react";
import type { Overview } from "@/lib/api-types";

// The four KPI cards (§8.3). Every number is a field the API returns — the donut is
// fed only by `question_state_counts`, never by counting rows on the client (F11),
// and a null is a dash with the not-knowable title, never a zero (rule 1).

type Stage = {
  name: string;
  outputs: number | null;
  rejected: number | null;
  progress: { done: number; total: number; label: string } | null;
};

type Floor = {
  basis: string;
  confirmed: number | null;
  obtained: number | null;
  found: number | null;
  rate: number | null;
  floor: number;
  status: string;
};

// The donut's state colours, in the server's own state order. The board fixed four
// (blue, indigo-like violet, amber, gray); the other four are this step's choice.
const STATE_ORDER: (keyof Overview["question_state_counts"])[] = [
  "signed",
  "stale",
  "awaiting_a_person",
  "provisional",
  "no_verified_claim",
  "not_applicable",
  "historical",
  "no_profile",
];

const STATE_COLORS: AvailableChartColorsKeys[] = [
  "blue",
  "fuchsia",
  "violet",
  "amber",
  "gray",
  "cyan",
  "lime",
  "pink",
];

function KpiCard({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
      {children}
    </div>
  );
}

export default function OverviewKpis({ overview }: { overview: Overview }) {
  const stages = overview.state.stages as unknown as Stage[];
  const extract = stages.find((stage) => stage.name === "extract") ?? null;
  const review = stages.find((stage) => stage.name === "review") ?? null;
  const floor = overview.state.floor as unknown as Floor | null;

  // The rate's numerator is the admissibility basis's own count: confirmed once any
  // confirmation exists, obtained before stage 3 has run (admissibility.rate).
  const numerator =
    floor === null || floor.found === null
      ? null
      : floor.basis === "confirmed"
        ? floor.confirmed
        : floor.obtained;
  const denominator = floor?.found ?? null;

  const counts = overview.question_state_counts;
  const donutData = STATE_ORDER.map((state) => ({ state, count: counts[state] }));
  const total = donutData.reduce((sum, entry) => sum + entry.count, 0);

  return (
    <section className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
      <KpiCard>
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Acquisition rate</span>
          {floor ? (
            <span
              className={`rounded-md px-2 py-px text-xs font-medium ${
                floor.status === "OK"
                  ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                  : "bg-amber-50 text-amber-700 ring-1 ring-amber-200"
              }`}
            >
              {floor.status}
            </span>
          ) : null}
        </div>
        <div className="mt-1 text-[30px] font-semibold">
          {floor?.rate == null ? (
            <span title="not knowable">—</span>
          ) : (
            floor.rate.toFixed(2)
          )}
        </div>
        {floor !== null && numerator !== null && denominator !== null && denominator > 0 ? (
          <div className="mt-3">
            <CategoryBar
              values={[numerator, Math.max(denominator - numerator, 0)]}
              colors={["emerald", "gray"]}
              marker={{ value: floor.floor * denominator, tooltip: `floor ${floor.floor}` }}
            />
          </div>
        ) : null}
        <div className="mt-1.5 flex justify-between text-xs text-muted-foreground">
          <span>
            {numerator ?? "—"} / {denominator ?? "—"} {floor?.basis ?? ""} of found
          </span>
          <span>{floor ? `floor ${floor.floor}` : ""}</span>
        </div>
      </KpiCard>

      <KpiCard>
        <span className="text-sm text-muted-foreground">Annotations accepted</span>
        <div className="mt-1 text-[30px] font-semibold">
          {extract?.outputs == null ? <span title="not knowable">—</span> : extract.outputs}
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          {extract?.rejected == null ? (
            <span title="not knowable">— rejected by the gate (not recorded)</span>
          ) : (
            `${extract.rejected} rejected by the gate`
          )}
        </p>
      </KpiCard>

      <KpiCard>
        <span className="text-sm text-muted-foreground">Independently reviewed</span>
        <div className="mt-1 text-[30px] font-semibold">
          {review?.progress == null ? (
            <span title="not knowable">—</span>
          ) : (
            <>
              {review.progress.done}{" "}
              <span className="text-base text-muted-foreground">/ {review.progress.total}</span>
            </>
          )}
        </div>
        {review?.progress ? (
          <div className="mt-3.5">
            <ProgressBar value={review.progress.done} max={review.progress.total} />
          </div>
        ) : null}
        <p className="mt-1.5 text-xs text-muted-foreground">{review?.progress?.label ?? "—"}</p>
      </KpiCard>

      <KpiCard>
        <div className="flex items-center gap-4">
          <DonutChart
            data={donutData.map((entry) => ({ state: entry.state, count: entry.count }))}
            category="state"
            value="count"
            colors={STATE_COLORS}
            showLabel
            label={String(total)}
            className="h-20 w-20 shrink-0"
          />
          <div className="flex flex-col gap-0.5 text-xs text-muted-foreground">
            <span className="text-sm text-muted-foreground">Questions</span>
            {donutData
              .filter((entry) => entry.count > 0)
              .map((entry) => (
                <span key={entry.state} className="flex items-center gap-1.5">
                  <span
                    aria-hidden="true"
                    className={`inline-block size-2 rounded-full ${getColorClassName(
                      STATE_COLORS[STATE_ORDER.indexOf(entry.state)],
                      "bg",
                    )}`}
                  />
                  {entry.state} {entry.count}
                </span>
              ))}
          </div>
        </div>
      </KpiCard>
    </section>
  );
}
