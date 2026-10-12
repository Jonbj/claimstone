import { formatUtc } from "@/lib/datetime";
import { useLocale } from "@/lib/i18n";
import type { PeriodicCumulativeDossier } from "@/lib/api-types";

// Whether the dossier has been saved, and whether the saved one still matches the evidence. These are
// facts the server states; the page adds no judgement of its own.
export default function SaveStatus({ dossier }: { dossier: PeriodicCumulativeDossier }) {
  const { t } = useLocale();
  return (
    <section aria-label={t("sched.res.save.title")} className="flex flex-col gap-1 rounded-xl border border-border bg-card px-4 py-4 text-sm">
      <h2 className="text-base font-semibold">{t("sched.res.save.title")}</h2>
      {typeof dossier.finalized_dossier_id === "string" ? (
        <p>{t("sched.res.saved", { id: dossier.finalized_dossier_id.slice(0, 12),
                                   at: dossier.finalized_at ? formatUtc(dossier.finalized_at) : "—" })}</p>
      ) : <p>{t("sched.res.notSaved")}</p>}
      {dossier.snapshot_stale ? <p>{t("sched.res.snapshotStale")}</p> : null}
      {dossier.needs_finalization ? <p>{t("sched.res.needsSaving")}</p> : null}
      <p>{t("sched.res.save.history", { n: dossier.history_count })}</p>
    </section>
  );
}
