import { useLocale } from "@/lib/i18n";
import type { Admission } from "@/lib/scheduler";
import { percent } from "./format";

// The parts of an admission that say how far its figures can still move: the rate with the basis it
// counts, the upper bound, whether the figures are final, and every blocking entry as the server sent
// it. The status word itself is the caller's, because it sits in a different element in each place.
export default function AdmissionLine({ a }: { a: Admission }) {
  const { t } = useLocale();
  const blocking = Array.isArray(a.blocking) ? a.blocking : [];
  return (
    <>
      <span>
        {t("sched.series.rate", { rate: percent(a.rate) })}
        {typeof a.basis === "string" ? ` (${t("sched.series.basis", { basis: a.basis })})` : ""}
      </span>
      {typeof a.rate_upper === "number" ? <span>{t("sched.series.rateUpper", { rate: percent(a.rate_upper) })}</span> : null}
      {typeof a.final === "boolean" ? <span>{a.final ? t("sched.series.final") : t("sched.series.notFinal")}</span> : null}
      {blocking.length ? <span className="font-mono break-words">{t("sched.series.blocking", { items: blocking.join(", ") })}</span> : null}
    </>
  );
}
