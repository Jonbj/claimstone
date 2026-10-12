import { useLocale } from "@/lib/i18n";

export interface FigureValues {
  searchesPerRound: number;
  searchesTotal: number;
  requestsPerRound: number;
  requestsTotal: number;
}

// The preview of a series' size. A figure that cannot be computed yet (the flow's searches are not
// read, or no source is ticked) is a dash, never a zero. The server's `max_total_requests` is the
// figure that counts, and the panel says so.
export default function FiguresPanel({ values }: { values: FigureValues | null }) {
  const { t } = useLocale();
  const show = (n: number | undefined) => (values && n ? String(n) : "—");
  return (
    <section aria-label={t("sched.new.figures.title")} className="flex flex-col gap-1 rounded-xl border border-border bg-card px-4 py-3 text-sm">
      <h2 className="text-base font-semibold">{t("sched.new.figures.title")}</h2>
      <p>{t("sched.new.figures.perRound", { n: show(values?.searchesPerRound) })}</p>
      <p>{t("sched.new.figures.total", { n: show(values?.searchesTotal) })}</p>
      <p>{t("sched.new.figures.requestsRound", { n: show(values?.requestsPerRound) })}</p>
      <p><b>{t("sched.new.figures.ceiling", { n: show(values?.requestsTotal) })}</b></p>
      <p className="text-xs text-muted-foreground">{t("sched.new.figures.note")}</p>
    </section>
  );
}
