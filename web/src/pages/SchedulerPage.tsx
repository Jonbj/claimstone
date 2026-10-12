import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import ProjectTabs from "@/components/ProjectTabs";
import StateWord from "@/components/scheduler/StateWord";
import WorkersStrip from "@/components/scheduler/WorkersStrip";
import { utcRange } from "@/components/scheduler/format";
import { useApi } from "@/hooks/useApi";
import { usePoll } from "@/hooks/usePoll";
import { ControlError, control } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import { overviewOfSeries } from "@/lib/scheduler";
import type { SchedulerIndex, SeriesOverview } from "@/lib/scheduler";
import { useSession } from "@/lib/session";

const buttonClass = "inline-flex min-h-11 items-center rounded-lg px-4 text-sm font-medium ring-1 ring-gray-300 hover:bg-gray-50 dark:ring-gray-700 dark:hover:bg-gray-900";

function Grant({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <span className="flex items-center gap-1 text-xs">
      <span className="text-muted-foreground">{label}</span>
      {children}
    </span>
  );
}

function SeriesRow({ view, project, more }: { view: SeriesOverview; project: string; more: boolean }) {
  const { t } = useLocale();
  // Policy and mandate states are the server's; "not decided" only when nothing is attached AND
  // no page remains that could hold it.
  const none = more ? t("sched.grant.notLoaded") : t("sched.grant.undecided");
  const id = view.schedule.schedule_id;
  return (
    <li aria-label={t("sched.index.rowLabel", { id: id.slice(0, 12) })}
        className="flex flex-col gap-2 rounded-xl border border-border bg-card px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <StateWord word={view.state} />
        <span className="text-sm">{t("sched.index.rounds", { n: view.rounds })}</span>
        <span className="text-sm text-muted-foreground">{utcRange(view.windowStart, view.windowEnd)}</span>
        <span className="text-sm text-muted-foreground">
          {t("sched.index.maxRequests", { n: view.schedule.plan.max_total_requests })}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-4">
        <Grant label={t("sched.grant.calendar")}><StateWord word={view.state} /></Grant>
        <Grant label={t("sched.grant.copies")}>
          {view.policies.length ? view.policies.map((p) => <StateWord key={p.policy_id} word={p.state} />) : <span>{none}</span>}
        </Grant>
        <Grant label={t("sched.grant.model")}>
          {view.mandates.length ? view.mandates.map((m) => <StateWord key={m.mandate_id} word={m.state} />) : <span>{none}</span>}
        </Grant>
      </div>
      <Link to={`/p/${encodeURIComponent(project)}/scheduler/s/${encodeURIComponent(id)}`}
            className="inline-flex min-h-11 items-center text-sm underline">
        {t("sched.index.open", { id: id.slice(0, 12) })}
      </Link>
    </li>
  );
}

function Body({ project }: { project: string }) {
  const { t } = useLocale();
  const first = useApi(() => control.schedulerIndex(project), [project]);
  const [extra, setExtra] = useState<SchedulerIndex[]>([]);
  const [restarted, setRestarted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [moreError, setMoreError] = useState<Error | null>(null);
  usePoll(project || null, () => first.reload());

  // Appended pages belong to one revision of the archive: when page one moves to another, they go.
  const revision = first.data?.archive.revision ?? null;
  useEffect(() => { setExtra([]); }, [revision]);

  if (first.error) return <ErrorState error={first.error} context="scheduler" />;
  if (first.pending || !first.data) return <Pending label={t("sched.loading")} />;

  const pages = [first.data, ...extra];
  const last = pages[pages.length - 1];
  const next = last.archive.next_cursor;
  const schedules = pages.flatMap((p) => p.schedules);
  const policies = pages.flatMap((p) => p.copy_policies);
  const mandates = pages.flatMap((p) => p.local_mandates);
  const views = schedules.map((s) => overviewOfSeries(s, policies, mandates))
    .sort((a, b) => Date.parse(b.windowStart) - Date.parse(a.windowStart) || 0);
  const single = mandates.filter((m) => !m.mandate.schedule_id);

  async function loadMore() {
    if (!next) return;
    setBusy(true);
    setMoreError(null);
    try {
      const page = await control.schedulerIndex(project, next);
      setRestarted(false);
      setExtra((previous) => [...previous, page]);
    } catch (cause) {
      if (cause instanceof ControlError && cause.code === "ARCHIVE_CHANGED") {
        setExtra([]);
        setRestarted(true);
        first.reload();
      } else {
        setMoreError(cause instanceof Error ? cause : new Error(String(cause)));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <WorkersStrip supervisor={first.data.workers.supervisor} operations={first.data.workers.operations} />
      <section aria-label={t("sched.index.series")} className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold">{t("sched.index.series")}</h2>
          <Link to={`/p/${encodeURIComponent(project)}/scheduler/new`} className={buttonClass}>
            {t("sched.index.new")}
          </Link>
        </div>
        {restarted ? <p role="status" className="text-sm">{t("sched.index.restarted")}</p> : null}
        {views.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("sched.index.empty")}</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {views.map((view) => (
              <SeriesRow key={view.schedule.schedule_id} view={view} project={project} more={next !== null} />
            ))}
          </ul>
        )}
        {moreError ? <ErrorState error={moreError} context="scheduler" /> : null}
        {next ? (
          <button type="button" onClick={loadMore} disabled={busy} className={`${buttonClass} self-start`}>
            {t("sched.index.loadMore")}
          </button>
        ) : null}
      </section>
      {single.length ? (
        <section aria-label={t("sched.index.singleMandates")} className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold">{t("sched.index.singleMandates")}</h2>
          <ul className="flex flex-col gap-2">
            {single.map((m) => (
              <li key={m.mandate_id} className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card px-4 py-2 text-sm">
                <StateWord word={m.state} />
                <span>{t("sched.index.remainingCalls", { n: m.remaining_local_calls })}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}

// The project's Scheduler index (read-only): the processes, the series, paging. The control API
// needs a session, so a signed-out visitor gets a sign-in line and no request.
export default function SchedulerPage() {
  const { t } = useLocale();
  const session = useSession();
  const { project: raw } = useParams();
  const project = raw ? decodeURIComponent(raw) : "";
  const here = `/p/${encodeURIComponent(project)}/scheduler`;
  return (
    <section className="flex flex-col gap-5">
      <ProjectTabs project={project} />
      <h1 className="font-serif text-4xl leading-tight font-normal">{t("sched.title")}</h1>
      {!session.ready ? (
        <Pending label={t("shell.checking")} />
      ) : !session.operator ? (
        <p className="text-sm">
          {t("sched.signedOut")}{" "}
          <Link className="underline" to={`/login?next=${encodeURIComponent(here)}`}>{t("sched.signIn")}</Link>
        </p>
      ) : (
        <Body project={project} />
      )}
    </section>
  );
}
