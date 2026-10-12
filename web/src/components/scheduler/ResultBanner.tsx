import { useLocale } from "@/lib/i18n";
import type { PeriodicCumulativeDossier } from "@/lib/api-types";
import StateWord from "./StateWord";

// The dossier's state word and blockers exactly as the server sent them. It never says "ready" on its own and gives no verdict.
export default function ResultBanner({ dossier }: { dossier: PeriodicCumulativeDossier }) {
  const { t } = useLocale();
  return (
    <section aria-label={t("sched.res.dossier")} className="flex flex-col gap-2 rounded-xl border border-border bg-card px-4 py-4 text-sm">
      <h2 className="flex flex-wrap items-center gap-3 text-base font-semibold">
        {t("sched.res.dossier")} <StateWord word={dossier.state} />
      </h2>
      {dossier.blockers.length ? (
        <div>
          <b>{t("sched.res.blockers")}</b>
          <ul className="list-disc pl-5">
            {dossier.blockers.map((blocker) => <li key={blocker} className="font-mono text-xs">{blocker}</li>)}
          </ul>
        </div>
      ) : <p>{t("sched.res.noBlockers")}</p>}
      <p className="text-muted-foreground">{t("sched.res.noVerdict")}</p>
    </section>
  );
}
