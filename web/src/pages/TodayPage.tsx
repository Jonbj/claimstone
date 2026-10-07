import { useState } from "react";
import { Link } from "react-router";
import Chip from "@/components/Chip";
import RowFields from "@/components/RowFields";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { control } from "@/lib/control";
import type {
  NeedsYouOptional,
  NeedsYouRequired,
  OperationSummary,
  TodayProject,
} from "@/lib/control";
import { useSession } from "@/lib/session";

// Today (spec F2): what changed since the operator last looked and what waits for them, from
// `GET /control/v1/today`. Everything shown is a field of that answer; nothing is derived here.
// A project the server could not read carries its `error` and does not blank the others.
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

function NeedsList({ project, entry }: {
  project: string;
  entry: Extract<TodayProject, { needs_you: unknown }>;
}) {
  const { required, optional } = entry.needs_you;
  if (required.length === 0 && optional.length === 0) {
    return <p className="text-sm text-muted-foreground">Nothing waits for you in this project.</p>;
  }
  return (
    <div className="flex flex-col gap-3">
      {required.length > 0 ? (
        <div>
          <h4 className="text-sm font-semibold text-waits-ink">Required · {required.length}</h4>
          <ul className="mt-1 flex flex-col gap-1.5">
            {required.map((item: NeedsYouRequired, i) => (
              <li key={`r${i}`} className="grid grid-cols-[7rem_minmax(0,1fr)] gap-x-3 text-sm">
                <span className="text-xs font-semibold uppercase text-waits-ink">{item.type}</span>
                <span>
                  <Link
                    to={requiredLink(project, item)}
                    className="font-mono text-[13px] text-blue-600 hover:underline dark:text-blue-400"
                  >
                    {item.subject}
                  </Link>
                  <span className="ml-2 text-muted-foreground">{item.cause}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {optional.length > 0 ? (
        <div>
          <h4 className="text-sm font-semibold">Optional · {optional.length}</h4>
          <ul className="mt-1 flex flex-col gap-1.5">
            {optional.map((item: NeedsYouOptional, i) => (
              <li key={`o${i}`} className="grid grid-cols-[7rem_minmax(0,1fr)] gap-x-3 text-sm">
                <span className="text-xs font-semibold uppercase text-muted-foreground">
                  {item.type}
                </span>
                <Link
                  to={`${flowPath(project, item.flow_id)}/decisions`}
                  className="font-mono text-[13px] text-blue-600 hover:underline dark:text-blue-400"
                >
                  {item.subject}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function Continues({ items }: { items: OperationSummary[] | null }) {
  // `null` is "the scheduler's queue is not reported", which is not the same as an empty list.
  if (items === null) {
    return <p className="text-sm text-muted-foreground">— not reported for this project.</p>;
  }
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">No operation is authorized or running.</p>;
  }
  return (
    <ul className="flex flex-col gap-2">
      {items.map((op) => (
        <li key={op.operation_id} className="text-sm">
          <div className="flex flex-wrap items-baseline gap-2">
            <Chip text={op.state} />
            <span className="font-medium">{op.stage ?? "—"}</span>
            <span className="font-mono text-xs text-muted-foreground">{op.operation_id}</span>
          </div>
          <p className="text-xs text-muted-foreground">{op.state_note}</p>
        </li>
      ))}
    </ul>
  );
}

function ProjectBlock({ entry, onSeen }: { entry: TodayProject; onSeen: () => void }) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Error | null>(null);

  if (entry.error !== undefined) {
    return (
      <section aria-label={entry.project} className="rounded-2xl bg-card p-5 shadow-sm">
        <h2 className="font-serif text-2xl">{entry.project}</h2>
        <div className="mt-2" data-testid="project-error">
          <ErrorState error={new Error(entry.error)} context="today" />
        </div>
      </section>
    );
  }

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
    <section aria-label={entry.project} className="flex flex-col gap-4 rounded-2xl bg-card p-5 shadow-sm">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="font-serif text-2xl">
          <Link to={`/p/${enc(entry.project)}`} className="hover:underline">
            {entry.project}
          </Link>
        </h2>
        <span className="text-sm text-muted-foreground">
          {entry.first_visit ? "first visit" : `since ${entry.since ?? "—"}`}
        </span>
        <button
          type="button"
          onClick={() => void markSeen()}
          disabled={busy}
          className="ml-auto min-h-11 rounded-lg border border-border px-4 text-sm font-medium hover:bg-muted disabled:opacity-50"
        >
          {busy ? "Marking…" : "Mark as seen"}
        </button>
      </header>
      {failure ? <ErrorState error={failure} context="mark as seen" /> : null}

      <div>
        <h3 className="text-sm font-semibold text-waits-ink">Needs you</h3>
        <div className="mt-2">
          <NeedsList project={entry.project} entry={entry} />
        </div>
      </div>

      <div className="grid gap-5 min-[900px]:grid-cols-2">
        <div>
          <h3 className="text-sm font-semibold">What changed</h3>
          {stages.length === 0 ? (
            <p className="mt-1 text-sm text-muted-foreground">No dated row since then.</p>
          ) : (
            <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm">
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
        <div>
          <h3 className="text-sm font-semibold text-acting-ink">Continues without you</h3>
          <div className="mt-1">
            <Continues items={entry.continues_without_you} />
          </div>
        </div>
      </div>
    </section>
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
  return (
    <div className="flex flex-col gap-5">
      {projects.map((entry) => (
        <ProjectBlock key={entry.project} entry={entry} onSeen={today.reload} />
      ))}
    </div>
  );
}

export default function TodayPage() {
  const session = useSession();
  return (
    <section className="flex flex-col gap-5">
      <header>
        <h1 className="font-serif text-5xl leading-tight font-normal">Since your last visit</h1>
        {session.operator ? (
          <p className="mt-1 text-sm text-muted-foreground">{session.operator.name}</p>
        ) : null}
      </header>
      {!session.ready ? (
        <Pending label="checking session…" />
      ) : session.operator ? (
        <TodayBody />
      ) : (
        <div className="rounded-2xl bg-card p-5 shadow-sm">
          <p className="text-sm">
            Today needs a session: what changed is counted per operator.{" "}
            <Link to="/login?next=%2F" className="text-blue-600 hover:underline dark:text-blue-400">
              Sign in
            </Link>{" "}
            or read the{" "}
            <Link to="/projects" className="text-blue-600 hover:underline dark:text-blue-400">
              Projects
            </Link>{" "}
            without one.
          </p>
        </div>
      )}
    </section>
  );
}
