import { Link, useParams } from "react-router";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import ProjectTabs from "@/components/ProjectTabs";
import AcquisitionPanel from "@/components/scheduler/AcquisitionPanel";
import QuestionRows from "@/components/scheduler/QuestionRows";
import ResultBanner from "@/components/scheduler/ResultBanner";
import { useApi } from "@/hooks/useApi";
import { usePoll } from "@/hooks/usePoll";
import { ApiError, api } from "@/lib/api";
import type { PeriodicCumulativeDossier } from "@/lib/api-types";
import { useLocale } from "@/lib/i18n";
import { useSession } from "@/lib/session";

// A file made from the payload the page read, handed over through a temporary object URL. Nothing
// is requested again: the file is what is on screen.
function download(dossier: PeriodicCumulativeDossier, name: string): void {
  const url = URL.createObjectURL(new Blob([JSON.stringify(dossier, null, 2)], { type: "application/json" }));
  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
  } finally {
    URL.revokeObjectURL(url);
  }
}

function Body({ project, id }: { project: string; id: string }) {
  const { t } = useLocale();
  // Read once on load, and again only when the poll says the ledgers moved.
  const dossier = useApi(() => api.periodicDossier(project, id), [project, id]);
  const projects = useApi(() => api.projects(), []);
  usePoll(project || null, () => dossier.reload());

  if (dossier.error) {
    if (dossier.error instanceof ApiError && dossier.error.code === "NOT_FOUND") {
      return <p role="alert">{t("sched.series.notFound")}</p>;
    }
    return <ErrorState error={dossier.error} context="dossier" />;
  }
  if (dossier.pending || !dossier.data) return <Pending label={t("sched.loading")} />;
  const d = dossier.data;
  const card = projects.data?.projects.find((p) => p.name === project);
  const wholeStore = (card?.unbound_selectors ?? []).some((u) => u.slug === "-");
  const saved = typeof d.finalized_dossier_id === "string" && d.snapshot_stale === false;

  return (
    <>
      <ResultBanner dossier={d} />
      <AcquisitionPanel audit={d.audit} />
      <QuestionRows project={project} profiles={d.profiles} decisions={d.human_decisions} wholeStore={wholeStore} />
      <div className="flex flex-col items-start gap-1">
        <button type="button" onClick={() => download(d, `periodic-dossier-${id.slice(0, 12)}.json`)}
                className="inline-flex min-h-11 items-center rounded-lg px-4 text-sm font-medium ring-1 ring-gray-300 hover:bg-gray-50 dark:ring-gray-700 dark:hover:bg-gray-900">
          {saved ? t("sched.res.download.saved") : t("sched.res.download.live")}
        </button>
        <p className="text-xs text-muted-foreground">{t("sched.res.download.note")}</p>
      </div>
    </>
  );
}

// The cumulative result of a series (read-only): the dossier state, the acquisition figures, the
// questions with their profiles and signatures, and a download of what was read.
export default function CumulativeResultPage() {
  const { t } = useLocale();
  const session = useSession();
  const { project: rawProject, schedule: rawId } = useParams();
  const project = rawProject ? decodeURIComponent(rawProject) : "";
  const id = rawId ? decodeURIComponent(rawId) : "";
  const series = `/p/${encodeURIComponent(project)}/scheduler/s/${encodeURIComponent(id)}`;
  return (
    <section className="flex flex-col gap-5">
      <ProjectTabs project={project} />
      <nav aria-label="Breadcrumb" className="text-sm text-muted-foreground">
        <Link to={series} className="hover:underline">{t("sched.res.back")}</Link>
      </nav>
      <h1 className="font-serif text-4xl leading-tight font-normal">{t("sched.result.title")}</h1>
      {!session.ready ? (
        <Pending label={t("shell.checking")} />
      ) : !session.operator ? (
        <p className="text-sm">
          {t("sched.signedOut")}{" "}
          <Link className="underline" to={`/login?next=${encodeURIComponent(`${series}/result`)}`}>{t("sched.signIn")}</Link>
        </p>
      ) : (
        <Body project={project} id={id} />
      )}
    </section>
  );
}
