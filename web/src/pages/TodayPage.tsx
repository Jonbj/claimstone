import { useState } from "react";
import { Link } from "react-router";
import RowFields from "@/components/RowFields";
import StatePill, { type PillTone } from "@/components/StatePill";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { control } from "@/lib/control";
import type {
  NeedsYouRequired,
  OperationSummary,
  TodayProject,
} from "@/lib/control";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

// Today (spec F2): what changed since the operator last looked and what waits for them, from
// `GET /control/v1/today`. The home screen's first structure is three sections — Waits for
// you, Claimstone is acting, What changed — and a projects strip (D137). Everything shown is a
// field of that answer; nothing is derived here. A project the server could not read carries its
// `error` and does not blank the others.
const enc = encodeURIComponent;

function flowPath(project: string, flowId: string): string {
  return `/p/${enc(project)}/f/${enc(flowId)}`;
}

function requiredLink(project: string, item: NeedsYouRequired): string {
  // An identity question is answered in the flow's Decisions (route wired when F5 merges); an
  // adjudication card is a question to sign on the reading desk; integrity and protocol stop the
  // whole project, so they point at its page.
  if (item.type === "identity") return `${flowPath(project, item.flow_id)}/decisions`;
  if (item.type === "adjudication") {
    return `${flowPath(project, item.flow_id)}/q/${enc(item.subject)}`;
  }
  return `/p/${enc(project)}`;
}

function SectionLabel({ tone, children }: { tone: PillTone | "plain"; children: React.ReactNode }) {
  const cls = tone === "waits" ? "text-waits-ink" : tone === "acting" ? "text-acting-ink" : "text-muted-foreground";
  return <h2 className={cn("section-label", cls)}>{children}</h2>;
}

function WaitCard({ project, flowId, subject, to, optional, sentence }: {
  project: string;
  flowId: string;
  subject: string;
  to: string;
  optional: boolean;
  sentence?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-4 rounded-xl border border-border bg-card p-4",
        !optional && "border-l-4 border-l-waits",
      )}
    >
      <div className="min-w-0 flex-1 basis-72">
        <div className="flex flex-wrap items-center gap-2">
          <StatePill tone={optional ? "neutral" : "waits"}>
            {optional ? "○ optional" : "● waits for you"}
          </StatePill>
          <span className="text-xs text-muted-foreground">
            {project} · <span className="font-mono">{flowId.slice(0, 12)}</span>
          </span>
        </div>
        <p className="mt-2 text-sm text-foreground">{sentence}</p>
      </div>
      <Link
        to={to}
        className="min-h-11 rounded-lg border border-border px-3 text-sm font-medium hover:bg-muted"
      >
        {subject}
      </Link>
    </div>
  );
}

function ActingCard({ project, op }: { project: string; op: OperationSummary }) {
  const limit = op.limits.spend_usd;
  const pct = limit !== null && limit > 0 ? Math.min(1, op.spent_usd / limit) : 0;
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatePill tone="acting">◐ {op.state}</StatePill>
        <span className="text-sm font-medium">{op.stage ?? "—"}</span>
        <span className="text-xs text-muted-foreground">{project}</span>
      </div>
      <p className="mt-2 text-sm text-muted-foreground">{op.state_note}</p>
      {limit !== null ? (
        <div className="mt-3 max-w-xs">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>Spent (real)</span>
            <span className="font-mono">{op.spent_usd.toFixed(2)} / {limit.toFixed(2)} USD</span>
          </div>
          <div className="mt-1 h-2 rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary" style={{ width: `${pct * 100}%` }} />
          </div>
        </div>
      ) : null}
      <p className="mt-2 font-mono text-xs text-muted-foreground" title={op.operation_id}>
        {op.operation_id.slice(0, 12)}
      </p>
    </div>
  );
}

function ChangedCard({ entry, onSeen }: { entry: Extract<TodayProject, { needs_you: unknown }>; onSeen: () => void }) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Error | null>(null);
  const { changed } = entry;
  const stages = Object.entries(changed.counts);

  const markSeen = async () => {
    if (busy) return;
    setBusy(true);
    setFailure(null);
    try {
      await control.seen({ project: entry.project });
      onSeen();
    } catch (cause) {
      setFailure(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-base font-semibold">
          <Link to={`/p/${enc(entry.project)}`} className="hover:underline">
            {entry.project}
          </Link>
        </h3>
        <span className="text-xs text-muted-foreground">
          {entry.first_visit ? "first visit" : `since ${entry.since ?? "—"}`}
        </span>
        <button
          type="button"
          onClick={() => void markSeen()}
          disabled={busy}
          className="ml-auto min-h-11 rounded-lg border border-border px-3 text-sm font-medium hover:bg-muted disabled:opacity-50"
        >
          {busy ? "Marking…" : "Mark as seen"}
        </button>
      </header>
      {failure ? <div className="mt-2"><ErrorState error={failure} context="mark as seen" /></div> : null}
      {stages.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">No dated row since then.</p>
      ) : (
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {stages.map(([stage, n]) => (
            <li key={stage}>
              <span className="font-mono font-medium">{n}</span>{" "}
              <span className="text-muted-foreground">{stage}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-1 text-xs text-muted-foreground">
        {changed.undated_rows} rows carry no timestamp and are not counted.
      </p>
      {changed.newest.length > 0 ? (
        <ul className="mt-2 flex flex-col gap-0.5">
          {changed.newest.map((row, i) => (
            <li key={i} className="flex flex-wrap items-baseline gap-2 text-xs">
              <span className="font-mono text-muted-foreground">{row.when}</span>
              <span>{row.stage}</span>
              <RowFields row={row.row} />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function ProjectStrip({ entries }: { entries: Array<Extract<TodayProject, { needs_you: unknown }>> }) {
  return (
    <div className="flex flex-col gap-2">
      {entries.map((entry) => {
        const waiting = entry.needs_you.required.length + entry.needs_you.optional.length;
        const acting = entry.continues_without_you?.length ?? 0;
        const changed = Object.values(entry.changed.counts).reduce((a, b) => a + b, 0);
        return (
          <Link
            key={entry.project}
            to={`/p/${enc(entry.project)}`}
            className="flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-xl border border-border bg-card p-4 hover:bg-muted"
          >
            <span className="font-medium">{entry.project}</span>
            <span className="text-xs text-muted-foreground">
              {waiting} wait for you · {acting} acting · {changed} changed
            </span>
          </Link>
        );
      })}
    </div>
  );
}

function TodayBody() {
  const today = useApi(() => control.today(), []);
  if (today.pending) return <Pending label="loading today…" />;
  if (today.error) return <ErrorState error={today.error} context="today" />;
  const projects = today.data?.projects ?? [];
  if (projects.length === 0) {
    return <p className="text-sm text-muted-foreground">The server lists no project.</p>;
  }
  const errored = projects.filter((p): p is Extract<TodayProject, { error: string }> => p.error !== undefined);
  const ok = projects.filter((p): p is Extract<TodayProject, { needs_you: unknown }> => p.error === undefined);

  const required = ok.flatMap((p) =>
    p.needs_you.required.map((item) => ({
      project: p.project,
      flowId: item.flow_id,
      subject: item.subject,
      to: requiredLink(p.project, item),
      optional: false,
      sentence: item.cause,
    })),
  );
  const optional = ok.flatMap((p) =>
    p.needs_you.optional.map((item) => ({
      project: p.project,
      flowId: item.flow_id,
      subject: item.subject,
      to: `${flowPath(p.project, item.flow_id)}/decisions`,
      optional: true,
      sentence: item.type,
    })),
  );
  const acting = ok.flatMap((p) =>
    (p.continues_without_you ?? []).map((op) => ({ project: p.project, op })),
  );
  const changed = ok.filter((p) => Object.keys(p.changed.counts).length > 0 || p.changed.newest.length > 0);

  return (
    <div className="flex flex-col gap-8">
      {errored.map((p) => (
        <section key={p.project} aria-label={p.project} className="rounded-xl border border-border bg-card p-5">
          <h2 className="text-base font-semibold">{p.project}</h2>
          <div className="mt-2" data-testid="project-error">
            <ErrorState error={new Error(p.error)} context="today" />
          </div>
        </section>
      ))}

      <section aria-label="Waits for you" className="flex flex-col gap-3">
        <SectionLabel tone="waits">Waits for you · {required.length + optional.length}</SectionLabel>
        {required.length + optional.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nothing waits for you. A plan, a decision or a signature appears here when it needs a person.
          </p>
        ) : (
          <>
            {required.map((w) => (
              <WaitCard key={`${w.project}:${w.subject}`} {...w} />
            ))}
            {optional.map((w) => (
              <WaitCard key={`${w.project}:${w.subject}`} {...w} />
            ))}
          </>
        )}
      </section>

      <section aria-label="Claimstone is acting" className="flex flex-col gap-3">
        <SectionLabel tone="acting">Claimstone is acting · {acting.length}</SectionLabel>
        {acting.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Claimstone is not acting. Authorize a plan or start a mandate to set it working.
          </p>
        ) : (
          acting.map(({ project, op }) => (
            <ActingCard key={op.operation_id} project={project} op={op} />
          ))
        )}
      </section>

      <section aria-label="What changed" className="flex flex-col gap-3">
        <SectionLabel tone="plain">What changed</SectionLabel>
        {changed.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nothing has changed since your last visit.
          </p>
        ) : (
          changed.map((p) => <ChangedCard key={p.project} entry={p} onSeen={today.reload} />)
        )}
      </section>

      <section aria-label="Projects" className="flex flex-col gap-3">
        <SectionLabel tone="plain">Projects</SectionLabel>
        <ProjectStrip entries={ok} />
      </section>
    </div>
  );
}

export default function TodayPage() {
  const session = useSession();
  return (
    <section className="flex flex-col gap-7">
      <header>
        <h1 className="text-[28px] leading-tight">Since your last visit</h1>
        {session.operator ? (
          <p className="mt-1 text-sm text-muted-foreground">{session.operator.name}</p>
        ) : null}
      </header>
      {!session.ready ? (
        <Pending label="checking session…" />
      ) : session.operator ? (
        <TodayBody />
      ) : (
        <div className="rounded-xl border border-border bg-card p-5">
          <p className="text-sm">
            Today needs a session: what changed is counted per operator.{" "}
            <Link to="/login?next=%2F" className="text-primary hover:underline">
              Sign in
            </Link>{" "}
            or read the{" "}
            <Link to="/projects" className="text-primary hover:underline">
              Projects
            </Link>{" "}
            without one.
          </p>
        </div>
      )}
    </section>
  );
}
