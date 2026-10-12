import { useLocale } from "@/lib/i18n";
import { cumulativeOf, roundsOf } from "@/lib/scheduler";
import type { Admission } from "@/lib/scheduler";
import AdmissionLine from "./AdmissionLine";
import { percent, ratio } from "./format";

function Figures({ a }: { a: Admission }) {
  const { t } = useLocale();
  return (
    <>
      <span>{t("sched.series.confirmed")} <span>{ratio(a.confirmed, a.found)}</span></span>
      <span>{t("sched.res.acq.obtained", { n: a.obtained })}</span>
      <AdmissionLine a={a} />
      {typeof a.floor === "number" ? <span>{t("sched.res.acq.floor", { floor: percent(a.floor) })}</span> : null}
    </>
  );
}

// Acquisition across the whole series and per round: what was found stays the denominator of what
// was confirmed. A shape the panel does not recognise is "not available", never a zero.
export default function AcquisitionPanel({ audit }: { audit: unknown }) {
  const { t } = useLocale();
  const total = cumulativeOf(audit);
  const rounds = roundsOf(audit).filter((r) => r && typeof r === "object");
  const below = Array.isArray(total?.classes_below_floor) ? (total!.classes_below_floor as string[]) : [];
  const byClass = total?.by_class && typeof total.by_class === "object"
    ? Object.entries(total.by_class as Record<string, { rate?: number; floor?: number; meets_floor?: boolean }>) : [];
  return (
    <section aria-label={t("sched.res.acq.title")} className="flex flex-col gap-2 rounded-xl border border-border bg-card px-4 py-4 text-sm">
      <h2 className="text-base font-semibold">{t("sched.res.acq.title")}</h2>
      {total ? (
        <>
          <p className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <b>{total.status}</b>
            <Figures a={total} />
          </p>
          {below.length ? <p>{t("sched.res.acq.below", { classes: below.join(", ") })}</p> : null}
          {byClass.length ? (
            <ul className="text-xs">
              {byClass.map(([name, c]) => (
                <li key={name}>
                  {t("sched.res.acq.class", { name, rate: percent(c?.rate), floor: percent(c?.floor) })}
                  {typeof c?.meets_floor === "boolean"
                    ? ` · ${c.meets_floor ? t("sched.res.acq.meets") : t("sched.res.acq.under")}` : ""}
                </li>
              ))}
            </ul>
          ) : null}
        </>
      ) : <p>{t("sched.res.notAvailable")}</p>}
      {rounds.length ? (
        <div>
          <h3 className="font-medium">{t("sched.res.acq.byRound")}</h3>
          <ul className="flex flex-col gap-1 text-xs">
            {rounds.map((r, i) => (
              <li key={i} className="flex flex-wrap gap-x-4">
                <b>{r.round ?? r.flow_id ?? "—"}</b>
                {r.admission && typeof r.admission === "object" ? (
                  <>
                    <Figures a={r.admission} />
                    <span className="font-mono">{r.admission.status}</span>
                  </>
                ) : <span>{t("sched.series.noData")}</span>}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
