import { Link, useParams } from "react-router";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import ProjectTabs from "@/components/ProjectTabs";
import CalendarStep from "@/components/scheduler/CalendarStep";
import MandateStep from "@/components/scheduler/MandateStep";
import PlanStep from "@/components/scheduler/PlanStep";
import PolicyStep from "@/components/scheduler/PolicyStep";
import ResultStep from "@/components/scheduler/ResultStep";
import RoundTimeline from "@/components/scheduler/RoundTimeline";
import { findSeriesGrants } from "@/components/scheduler/grants";
import { useApi } from "@/hooks/useApi";
import { usePoll } from "@/hooks/usePoll";
import { api } from "@/lib/api";
import { ControlError, control } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import { useSession } from "@/lib/session";

function Body({ project, id }: { project: string; id: string }) {
  const { t } = useLocale();
  // Three independent reads: a failure of one blanks only its own part of the page. The dossier is
  // the expensive one: read on load, and again only when the poll says the ledgers moved.
  const schedule = useApi(() => control.schedule(project, id), [project, id]);
  const dossier = useApi(() => api.periodicDossier(project, id), [project, id]);
  const grants = useApi(() => findSeriesGrants(project, id), [project, id]);
  usePoll(project || null, () => { schedule.reload(); dossier.reload(); grants.reload(); });

  if (schedule.error) {
    if (schedule.error instanceof ControlError && schedule.error.status === 404) {
      return <p role="alert">{t("sched.series.notFound")}</p>;
    }
    return <ErrorState error={schedule.error} context="scheduler" />;
  }
  if (schedule.pending || !schedule.data) return <Pending label={t("sched.loading")} />;
  const s = schedule.data;
  const rows = grants.data;

  return (
    <>
      {dossier.error ? (
        <div className="flex flex-col gap-1 rounded-xl border border-border bg-card px-4 py-3 text-sm">
          <b>{t("sched.series.timelineBlocked")}</b>
          <ErrorState error={dossier.error} context="dossier" />
        </div>
      ) : dossier.pending || !dossier.data ? (
        <Pending label={t("sched.series.timelineLoading")} />
      ) : (
        <RoundTimeline schedule={s} audit={dossier.data.audit} />
      )}
      <PlanStep schedule={s} />
      <CalendarStep schedule={s} />
      {grants.error ? <ErrorState error={grants.error} context="scheduler" /> : null}
      {grants.pending && !grants.error ? <Pending label={t("sched.loading")} /> : null}
      {!grants.pending ? (
        <>
          <PolicyStep rows={rows ? rows.policies : null} complete={rows?.complete ?? false} />
          <MandateStep rows={rows ? rows.mandates : null} workers={rows?.mandateWorkers ?? {}}
                       complete={rows?.complete ?? false} />
        </>
      ) : null}
      {rows && !rows.complete ? <p className="text-sm">{t("sched.series.grantsNotLoaded")}</p> : null}
      <ResultStep project={project} scheduleId={id} dossier={dossier.data} />
    </>
  );
}

// The series page (read-only): rounds on top, then Plan, Calendar, Future copies, Local model and
// Result. Each step says what it permits, what it does not and what it can spend.
export default function SeriesPage() {
  const { t } = useLocale();
  const session = useSession();
  const { project: rawProject, schedule: rawId } = useParams();
  const project = rawProject ? decodeURIComponent(rawProject) : "";
  const id = rawId ? decodeURIComponent(rawId) : "";
  const here = `/p/${encodeURIComponent(project)}/scheduler/s/${encodeURIComponent(id)}`;
  return (
    <section className="flex flex-col gap-5">
      <ProjectTabs project={project} />
      <nav aria-label="Breadcrumb" className="text-sm text-muted-foreground">
        <Link to={`/p/${encodeURIComponent(project)}/scheduler`} className="hover:underline">{t("sched.series.back")}</Link>
      </nav>
      <h1 className="font-serif text-4xl leading-tight font-normal">
        {t("sched.series.title")} <span className="font-mono text-2xl">{id.slice(0, 12)}</span>
      </h1>
      {!session.ready ? (
        <Pending label={t("shell.checking")} />
      ) : !session.operator ? (
        <p className="text-sm">
          {t("sched.signedOut")}{" "}
          <Link className="underline" to={`/login?next=${encodeURIComponent(here)}`}>{t("sched.signIn")}</Link>
        </p>
      ) : (
        <Body project={project} id={id} />
      )}
    </section>
  );
}
