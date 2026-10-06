import { CategoryBar } from "@/components/tremor/CategoryBar/CategoryBar";
import Chip from "@/components/Chip";
import Fraction from "@/components/Fraction";
import type { Overview } from "@/lib/api-types";

// §8.3 item 5: the floor panel per class — a CategoryBar with a marker at each
// class's floor, then the deficit `sentences` and the `disclosure` verbatim (rule 5).
// Colour never carries meaning alone (rule 7): the status word is always present,
// and a null is a dash, never a zero (rule 1).

type Bucket = {
  basis: string;
  basis_count: number | null;
  found: number | null;
  needed: number | null;
  floor: number;
  meets_floor: boolean;
};

type FloorPanelData = {
  overall: {
    basis: string;
    basis_count: number | null;
    found: number | null;
    rate: number | null;
    floor: number;
    floor_version: number;
    floor_set_at: string;
    status: string;
    final: boolean;
    blocking: string[];
  };
  by_class: Record<string, Bucket>;
  sentences: string[];
  disclosure: string;
};

export default function FloorPanel({ panel }: { panel: Overview["floor_panel"] }) {
  if (panel === null) return null;
  const data = panel as unknown as FloorPanelData;
  const classes = Object.entries(data.by_class);
  return (
    <section className="rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
      <h2 className="text-base font-semibold">Floor and deficit</h2>
      <p className="mt-1 flex flex-wrap items-baseline gap-2 text-sm">
        <span>
          {data.overall.basis} <Fraction numerator={data.overall.basis_count} /> /{" "}
          <Fraction numerator={data.overall.found} /> =
        </span>
        <strong>
          {data.overall.rate === null ? (
            <span title="not knowable">—</span>
          ) : (
            data.overall.rate.toFixed(2)
          )}
        </strong>
        <span>· floor {data.overall.floor}</span>
        <span>· v{data.overall.floor_version}</span>
        <span>· {data.overall.floor_set_at}</span>
        <Chip text={data.overall.status} />
        {data.overall.blocking.length > 0 ? (
          <span className="text-xs text-muted-foreground">
            not final: {data.overall.blocking.join(", ")}
          </span>
        ) : null}
      </p>
      {classes.length > 0 ? (
        <div className="mt-4 flex flex-col gap-4">
          {classes.map(([name, bucket]) => (
            <div key={name} data-floor-class={name}>
              <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
                <span className="font-mono text-[13px]">{name}</span>
                <span className="text-xs text-muted-foreground">
                  <Fraction numerator={bucket.basis_count} /> / <Fraction numerator={bucket.found} />{" "}
                  {bucket.basis} · needed <Fraction numerator={bucket.needed} /> · floor{" "}
                  {bucket.floor}
                </span>
                <Chip text={bucket.meets_floor ? "meets" : "below"} />
              </div>
              {bucket.found !== null && bucket.found > 0 ? (
                <CategoryBar
                  values={[
                    bucket.basis_count ?? 0,
                    Math.max(bucket.found - (bucket.basis_count ?? 0), 0),
                  ]}
                  colors={["emerald", "gray"]}
                  marker={{ value: bucket.floor * bucket.found, tooltip: `floor ${bucket.floor}` }}
                  showLabels={false}
                  className="mt-1.5 max-w-md"
                />
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
      {data.sentences.map((sentence, index) => (
        <p key={`${index}-${sentence}`} className="mt-2 text-sm text-muted-foreground">
          {sentence}
        </p>
      ))}
      <p className="mt-2 text-sm text-muted-foreground">{data.disclosure}</p>
    </section>
  );
}
