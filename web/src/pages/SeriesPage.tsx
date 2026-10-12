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
import { useApi } from "@/hooks/useApi";
import { usePoll } from "@/hooks/usePoll";
import { DOSSIER_MIN_MS, REFRESH_MS, useAsOf, useIdleReload, useVisibleInterval } from "@/hooks/useSchedulerRefresh";
import { useSeriesGrants } from "@/hooks/useSeriesGrants";
import { api } from "@/lib/api";
import { ControlError, control } from "@/lib/control";
import { formatUtc } from "@/lib/datetime";
import { useLocale } from "@/lib/i18n";
import { useSession } from "@/lib/session";

function Body({ project, id }: { project: string; id: string }) {
  const { t } = useLocale();
  // Three independent reads: a failure of one blanks only its own part of the page. The ledger poll
  // and a 15 s visible-tab timer ask for a refresh; each read ignores the ask while it is in flight,
  // and the dossier, which is expensive, is read at most once every 45 s.
  const schedule = useApi(() => control.schedule(project, id), [project, id]);
  const dossier = useApi(() => api.periodicDossier(project, id), [project, id]);
  const grants = useSeriesGrants(project, id);
  const reloadSchedule = useIdleReload(schedule.reload, schedule.pending || schedule.refreshing);
  const reloadDossier = useIdleReload(dossier.reload, dossier.pending || dossier.refreshing, DOSSIER_MIN_MS);
  const refresh = () => { reloadSchedule(); reloadDossier(); void grants.refresh(); };
  usePoll(project || null, refresh);
  useVisibleInterval(refresh, REFRESH_MS);
  const dossierAsOf = useAsOf(dossier.data);
  // After a write the page reads what it changed again (no local state says "done"): the schedule and,
  // since its state is in the audit, the dossier.
  const afterCalendar = () => { schedule.reload(); dossier.reload(); };
  // A new policy or mandate has an id the remembered list does not hold: walk the index again.
  const afterGrant = (full: boolean) => { schedule.reload(); void grants.reload(full); };

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
        <>
          <RoundTimeline schedule={s} audit={dossier.data.audit} />
          {dossierAsOf ? <p className="text-xs text-muted-foreground">{t("sched.asOf", { time: formatUtc(dossierAsOf) })}</p> : null}
        </>
      )}
      <PlanStep schedule={s} />
      <CalendarStep project={project} schedule={s} onChanged={afterCalendar} />
      {grants.error ? <ErrorState error={grants.error} context="scheduler" /> : null}
      {grants.pending && !grants.error ? <Pending label={t("sched.loading")} /> : null}
      {!grants.pending ? (
        <>
          <PolicyStep project={project} schedule={s} rows={rows ? rows.policies : null} complete={rows?.complete ?? false} onChanged={afterGrant} />
          <MandateStep project={project} schedule={s} rows={rows ? rows.mandates : null} workers={rows?.mandateWorkers ?? {}}
                       complete={rows?.complete ?? false} onChanged={afterGrant} />
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
        <Link to={`/p/${encodeURIComponent(project)}/scheduler`} className="inline-flex min-h-11 items-center hover:underline">{t("sched.series.back")}</Link>
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
