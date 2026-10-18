import { CategoryBar } from "@/components/tremor/CategoryBar/CategoryBar";
import Chip from "@/components/Chip";
import Fraction from "@/components/Fraction";
import type { Overview } from "@/lib/api-types";
import { Link, useSearchParams } from "react-router";
import { useLocale } from "@/lib/i18n";

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

export function BlockedFloorPanel({ panel, base, writable }: { panel: Overview["floor_panel"]; base: string; writable: boolean }) {
  const { t } = useLocale();
  const [params] = useSearchParams();
  if (!panel || panel.overall.status !== "INSUFFICIENT_ACQUISITION") return null;
  const { basis_count, found, rate, floor } = (panel as unknown as FloorPanelData).overall;
  const actual = rate === null ? 0 : Math.min(Math.max(rate, 0), 1) * 100;
  const threshold = Math.min(Math.max(floor, 0), 1) * 100;
  return (
    <section aria-label={t("flowAssay.noVerdict")} className="flex flex-wrap items-center gap-6 rounded-xl bg-rail p-5 text-rail-foreground sm:p-7">
      <div className="min-w-0 flex-[2_1_360px]">
        <span className="inline-flex rounded-full bg-not-obtained/20 px-3 py-1 text-xs font-semibold text-rail-foreground">{t("flowAssay.noVerdict")}</span>
        <h2 className="mt-3 text-xl font-semibold">{t("flowAssay.belowFloor")}</h2>
        <p className="mt-2 text-sm leading-relaxed text-rail-muted">{t("flowAssay.reason")}</p>
      </div>
      <div className="min-w-0 flex-[1_1_220px]">
        <p className="font-mono text-3xl font-semibold text-primary">{rate === null ? "—" : rate.toFixed(2)}</p>
        <p className="mt-1 text-xs text-rail-muted">{t("flowAssay.rate", { confirmed: basis_count ?? "—", found: found ?? "—", rate: rate === null ? "—" : rate.toFixed(2) })}</p>
        <svg className="mt-3 h-5 w-full" viewBox="0 0 100 20" preserveAspectRatio="none" role="img" aria-label={t("flowAssay.floor", { floor: floor.toFixed(2) })}>
          <rect x="0" y="5" width="100" height="10" rx="5" fill="var(--rail-active)" />
          <rect x="0" y="5" width={actual} height="10" rx="5" fill="var(--primary)" />
          <path d={`M ${threshold} 1 V 19`} stroke="var(--rail-foreground)" strokeWidth="1" />
        </svg>
        <p className="text-xs text-rail-muted">{t("flowAssay.floor", { floor: floor.toFixed(2) })}</p>
      </div>
      {writable ? <div className="flex flex-[1_1_100%] flex-wrap gap-2">
        <Link to={`${base}?block=execution`} className={`inline-flex min-h-11 items-center rounded-lg px-4 text-sm font-semibold ${params.get("block") === "execution" ? "border border-rail-muted text-rail-foreground" : "bg-primary text-primary-foreground"}`}>{t("flowAssay.recover")}</Link>
        <Link to={`${base}/material`} className="inline-flex min-h-11 items-center rounded-lg border border-rail-muted px-4 text-sm font-semibold text-rail-foreground">{t("flowAssay.supply")}</Link>
      </div> : null}
    </section>
  );
}

export default function FloorPanel({ panel }: { panel: Overview["floor_panel"] }) {
  if (panel === null) return null;
  const data = panel as unknown as FloorPanelData;
  const classes = Object.entries(data.by_class);
  return (
    <section className="rounded-xl border border-border bg-card p-5">
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
