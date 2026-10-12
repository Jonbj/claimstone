import { useRef, useState } from "react";
import { control } from "@/lib/control";
import type { PeriodicCumulativeDossier } from "@/lib/api-types";
import { useLocale } from "@/lib/i18n";
import { primaryClass } from "@/components/wizard/stepTypes";

type Verification = { holds: boolean; problems: string[] };
interface Made { exportId: string; dossierId: string; createdNow: boolean; verified: Verification | null; error: string | null }

// The verified package of the saved cumulative dossier. It can be made only for a dossier that is
// ready for human reading, saved, and still current; the id sent is the one the page shows now. A
// package is verified right after it is made, and the download appears only when it holds. The ids
// are kept for this visit only: the server has no listing of packages.
export default function ExportPanel({ project, scheduleId, dossier, onStale }: {
  project: string; scheduleId: string; dossier: PeriodicCumulativeDossier; onStale: () => void;
}) {
  const { t } = useLocale();
  const [made, setMade] = useState<Made[]>([]);
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const running = useRef(false);
  const current = typeof dossier.finalized_dossier_id === "string" ? dossier.finalized_dossier_id : null;
  const reason = dossier.state !== "READY_FOR_HUMAN_READING" ? t("sched.export.notReady")
    : current === null ? t("sched.export.notSaved")
    : dossier.snapshot_stale !== false ? t("sched.res.snapshotStale") : null;

  async function create() {
    if (running.current || reason !== null || current === null) return;
    running.current = true;
    setBusy(true);
    setRefusal(null);
    try {
      const created = await control.createPeriodicExport(project, scheduleId, current);
      const entry: Made = { exportId: created.export_id, dossierId: created.dossier_id, createdNow: created.created_now, verified: null, error: null };
      setMade((list) => [entry, ...list.filter((m) => m.exportId !== entry.exportId)]);
      try {
        const verified = await control.verifyPeriodicExport(project, created.export_id);
        setMade((list) => list.map((m) => (m.exportId === entry.exportId ? { ...m, verified: { holds: verified.holds, problems: verified.problems } } : m)));
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : String(cause);
        setMade((list) => list.map((m) => (m.exportId === entry.exportId ? { ...m, error: message } : m)));
      }
    } catch (cause) {
      // Stale or unfinished: the server's sentence as given, and the dossier is read again. No retry.
      setRefusal(cause instanceof Error ? cause.message : String(cause));
      onStale();
    } finally {
      running.current = false;
      setBusy(false);
    }
  }

  // The download: check the package once more first, and let the navigation go only if it still holds.
  async function download(event: React.MouseEvent, exportId: string) {
    event.preventDefault();
    const update = (patch: Partial<Made>) => setMade((list) => list.map((m) => (m.exportId === exportId ? { ...m, ...patch } : m)));
    try {
      const verified = await control.verifyPeriodicExport(project, exportId);
      update({ verified: { holds: verified.holds, problems: verified.problems }, error: null });
      if (!verified.holds) return;
      const link = document.createElement("a");
      link.href = control.periodicExportDownloadPath(project, exportId);
      link.download = "";
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (cause) {
      update({ verified: null, error: cause instanceof Error ? cause.message : String(cause) });
    }
  }

  return (
    <section aria-label={t("sched.export.title")} className="flex flex-col items-start gap-2 text-sm">
      <h3 className="font-semibold">{t("sched.export.title")}</h3>
      <p className="text-xs text-muted-foreground">{t("sched.export.intro")}</p>
      {reason ? <p>{reason}</p> : null}
      {refusal ? <p role="alert" className="text-red-700 dark:text-red-400">{refusal}</p> : null}
      <button type="button" onClick={create} disabled={busy || reason !== null} className={primaryClass}>
        {busy ? t("sched.grant.working") : t("sched.export.create")}
      </button>
      {made.map((m) => (
        <div key={m.exportId} role="group" aria-label={t("sched.export.rowLabel", { id: m.exportId.slice(0, 12) })}
             className="flex w-full flex-col gap-1 rounded-lg border border-border px-3 py-2">
          <p className="break-all font-mono text-xs">{m.exportId}</p>
          <p>{m.createdNow ? t("sched.export.createdNow") : t("sched.export.existed")}</p>
          {m.dossierId !== current ? <p>{t("sched.export.historical")}</p> : null}
          {m.error ? <p role="alert" className="text-red-700 dark:text-red-400">{m.error}</p> : null}
          {m.verified === null && !m.error ? <p>{t("sched.export.verifying")}</p> : null}
          {m.verified ? (
            <>
              <p><b>{m.verified.holds ? t("sched.export.holds") : t("sched.export.fails")}</b></p>
              {m.verified.problems.length ? (
                <div>
                  <p>{t("sched.export.problems")}</p>
                  <ul className="list-disc pl-5">{m.verified.problems.map((p, i) => <li key={i} className="break-words">{p}</li>)}</ul>
                </div>
              ) : null}
              {m.verified.holds ? (
                <>
                  <a href={control.periodicExportDownloadPath(project, m.exportId)} download
                     onClick={(e) => { void download(e, m.exportId); }} className="inline-flex min-h-11 items-center underline">{t("sched.export.download")}</a>
                  <p className="text-xs text-muted-foreground">{t("sched.export.contents")}</p>
                </>
              ) : null}
            </>
          ) : null}
        </div>
      ))}
    </section>
  );
}
