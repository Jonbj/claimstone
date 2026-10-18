import { useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import RowFields from "@/components/RowFields";
import StatePill from "@/components/StatePill";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { control } from "@/lib/control";
import type {
  NeedsYouRequired,
  OperationSummary,
  TodayProject,
} from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

// Today (spec F2): the page a person opens first. It answers three questions in this order —
// what is waiting for me, what is Claimstone doing on its own, what changed — and then lists the
// projects. Everything shown is a field of `GET /control/v1/today`; nothing is derived here
// beyond sums. A project the server could not read carries its `error` and does not blank the
// others. Each section says in one line what it is for, because the page was once opaque (D137).
const enc = encodeURIComponent;

type Ok = Extract<TodayProject, { needs_you: unknown }>;
type Failed = Extract<TodayProject, { error: string }>;

function flowPath(project: string, flowId: string): string {
  return `/p/${enc(project)}/f/${enc(flowId)}`;
}

function requiredLink(project: string, item: NeedsYouRequired): string {
  // An identity question is answered in the flow's Decisions; an adjudication card is a question
  // to sign on the reading desk; integrity and protocol stop the whole project, so they point at
  // its page.
  if (item.type === "identity") return `${flowPath(project, item.flow_id)}/decisions`;
  if (item.type === "adjudication") {
    return `${flowPath(project, item.flow_id)}/q/${enc(item.subject)}`;
  }
  return `/p/${enc(project)}`;
}

function Section({ id, tone, title, why, count, children }: {
  id: string;
  tone: "waits" | "acting" | "plain";
  title: string;
  why: string;
  count?: number;
  children: ReactNode;
}) {
  const ink = tone === "waits" ? "text-waits-ink" : tone === "acting" ? "text-acting-ink" : "text-foreground";
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3">
      <header>
        <h2 id={id} className={cn("flex items-baseline gap-2 text-lg font-semibold tracking-tight", ink)}>
          {title}
          {count !== undefined ? <span className="font-mono text-sm font-medium opacity-70">{count}</span> : null}
        </h2>
        <p className="mt-0.5 text-sm text-muted-foreground">{why}</p>
      </header>
      {children}
    </section>
  );
}

function Tile({ href, tone, value, label, hint }: {
  href: string;
  tone: "waits" | "acting" | "plain";
  value: number;
  label: string;
  hint: string;
}) {
  const accent = tone === "waits" && value > 0
    ? "border-l-4 border-l-waits"
    : tone === "acting" && value > 0
      ? "border-l-4 border-l-acting"
      : "";
  return (
    <a
      href={href}
      className={cn("flex flex-col gap-0.5 rounded-xl border border-border bg-card p-4 hover:bg-muted/60", accent)}
    >
      <span className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">{label}</span>
      <span className="font-mono text-4xl font-medium leading-tight">{value}</span>
      <span className="text-xs text-muted-foreground">{hint}</span>
    </a>
  );
}

// `t()` is only called with literal keys (a test enforces it, so the catalog can be audited with
// grep): the lookups below spell each key out. A type or stage the portal does not name shows as the
// server wrote it.
type T = (key: string) => string;
function typeLabel(t: T, type: string): string {
  switch (type) {
    case "adjudication": return t("today.waits.type.adjudication");
    case "integrity": return t("today.waits.type.integrity");
    case "protocol": return t("today.waits.type.protocol");
    case "identity": return t("today.waits.type.identity");
    default: return type;
  }
}
function stageLabel(t: T, stage: string): string {
  switch (stage) {
    case "discover": return t("today.stage.discover");
    case "acquire": return t("today.stage.acquire");
    case "normalize": return t("today.stage.normalize");
    case "extract": return t("today.stage.extract");
    case "review": return t("today.stage.review");
    case "synthesize": return t("today.stage.synthesize");
    case "adjudicate": return t("today.stage.adjudicate");
    case "intake": return t("today.stage.intake");
    case "decisions": return t("today.stage.decisions");
    case "export": return t("today.stage.export");
    default: return stage;
  }
}

interface Wait {
  project: string;
  flowId: string;
  subject: string;
  to: string;
  optional: boolean;
  type: string;
  sentence?: string;
}

function WaitCard({ w }: { w: Wait }) {
  const { t } = useLocale();
  const label = w.optional ? typeLabel(t, w.type) : typeLabel(t, w.type);
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-4 rounded-xl border border-border bg-card p-4",
        !w.optional && "border-l-4 border-l-waits",
      )}
    >
      <div className="min-w-0 flex-1 basis-72">
        <div className="flex flex-wrap items-center gap-2">
          <StatePill tone={w.optional ? "neutral" : "waits"}>
            {w.optional ? `○ ${t("today.waits.optional")}` : `● ${label}`}
          </StatePill>
        </div>
        <p className="mt-2 text-base font-medium">{w.optional ? t("today.waits.type.optional") : w.subject}</p>
        {w.sentence ? <p className="mt-0.5 text-sm text-muted-foreground">{w.sentence}</p> : null}
        <p className="mt-1.5 text-xs text-muted-foreground">
          {w.project} · <span className="font-mono">{w.flowId.slice(0, 12)}</span>
          {w.optional ? <> · <span className="font-mono">{w.subject}</span></> : null}
        </p>
      </div>
      <Link
        to={w.to}
        className={cn(
          "inline-flex min-h-11 items-center rounded-lg px-4 text-sm font-semibold",
          w.optional
            ? "border border-border hover:bg-muted"
            : "bg-primary text-primary-foreground hover:brightness-95",
        )}
        aria-label={`${t("today.waits.open")}: ${w.subject}`}
      >
        {w.optional ? w.subject : t("today.waits.open")}
      </Link>
    </div>
  );
}

function ActingCard({ project, op }: { project: string; op: OperationSummary }) {
  const { t } = useLocale();
  const limit = op.limits.spend_usd;
  const pct = limit !== null && limit > 0 ? Math.min(1, op.spent_usd / limit) : 0;
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-xl border border-border border-l-4 border-l-acting bg-card p-4">
      <div className="min-w-0 flex-1 basis-64">
        <div className="flex flex-wrap items-center gap-2">
          <StatePill tone="acting">
            <span aria-hidden="true" className="h-2 w-2 animate-pulse rounded-full bg-acting motion-reduce:animate-none" />
            {op.state}
          </StatePill>
          <span className="text-base font-medium">{op.stage ?? "—"}</span>
        </div>
        <p className="mt-1.5 text-sm text-muted-foreground">{op.state_note}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          <Link to={`/p/${enc(project)}`} className="text-link hover:underline">{project}</Link>
          {" · "}
          <span className="font-mono" title={op.operation_id}>{op.operation_id.slice(0, 12)}</span>
          {op.last_event_at ? <> · {t("today.acting.last")} {op.last_event}</> : null}
        </p>
      </div>
      {limit !== null ? (
        <div className="w-full max-w-xs">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{t("today.acting.spent")}</span>
            <span className="font-mono">{op.spent_usd.toFixed(2)} / {limit.toFixed(2)} USD</span>
          </div>
          <div className="mt-1.5 h-2 rounded-full bg-muted">
            <div className="h-full min-w-[3px] rounded-full bg-acting" style={{ width: `${pct * 100}%` }} />
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ProjectCard({ entry, onSeen }: { entry: Ok; onSeen: () => void }) {
  const { t } = useLocale();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Error | null>(null);
  const { changed } = entry;
  const stages = Object.entries(changed.counts);
  const waiting = entry.needs_you.required.length + entry.needs_you.optional.length;
  const acting = entry.continues_without_you?.length ?? 0;

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
    <article className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-base font-semibold">
          <Link to={`/p/${enc(entry.project)}`} className="hover:underline">
            {entry.project}
          </Link>
        </h3>
        <span className="text-xs text-muted-foreground">
          {entry.first_visit ? t("today.projects.firstVisit") : t("today.projects.since", { when: entry.since ?? "—" })}
        </span>
      </header>
      <div className="flex flex-wrap gap-2">
        {waiting > 0 ? <StatePill tone="waits">● {t("today.projects.waiting", { n: waiting })}</StatePill> : null}
        {acting > 0 ? <StatePill tone="acting">◐ {t("today.projects.working", { n: acting })}</StatePill> : null}
        {waiting === 0 && acting === 0 ? <StatePill tone="neutral">○ {t("today.projects.quiet")}</StatePill> : null}
      </div>
      {stages.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("today.projects.nothing")}</p>
      ) : (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {stages.map(([stage, n]) => {
            return (
              <li key={stage}>
                <span className="font-mono font-medium">{n}</span>{" "}
                <span className="text-muted-foreground">{stageLabel(t, stage)}</span>
              </li>
            );
          })}
        </ul>
      )}
      {changed.undated_rows > 0 ? (
        <p className="text-xs text-muted-foreground">{t("today.projects.undated", { n: changed.undated_rows })}</p>
      ) : null}
      {changed.newest.length > 0 ? (
        <details className="text-xs">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
            {t("today.projects.details")}
          </summary>
          <ul className="mt-2 flex flex-col gap-1">
            {changed.newest.map((row, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-2">
                <span className="font-mono text-muted-foreground">{row.when}</span>
                <span>{row.stage}</span>
                <RowFields row={row.row} />
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {failure ? <ErrorState error={failure} context="mark as seen" /> : null}
      <footer className="mt-auto flex flex-wrap gap-2 pt-1">
        <Link
          to={`/p/${enc(entry.project)}`}
          className="inline-flex min-h-11 items-center rounded-lg border border-border px-4 text-sm font-medium hover:bg-muted"
        >
          {t("today.projects.open")}
        </Link>
        <button
          type="button"
          onClick={() => void markSeen()}
          disabled={busy}
          className="min-h-11 rounded-lg px-3 text-sm text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
        >
          {busy ? t("today.projects.marking") : t("today.projects.seen")}
        </button>
      </footer>
    </article>
  );
}

function FailedCard({ p }: { p: Failed }) {
  const { t } = useLocale();
  return (
    <article className="rounded-xl border border-border bg-card p-4">
      <h3 className="text-base font-semibold">{p.project}</h3>
      <p className="mt-1 text-xs text-muted-foreground">{t("today.projects.unreadable")}</p>
      <div className="mt-2" data-testid="project-error">
        <ErrorState error={new Error(p.error)} context="today" />
      </div>
    </article>
  );
}

function TodayBody() {
  const { t } = useLocale();
  const today = useApi(() => control.today(), []);
  if (today.pending) return <Pending label={t("today.loading")} />;
  if (today.error) return <ErrorState error={today.error} context="today" />;
  const projects = today.data?.projects ?? [];
  if (projects.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("today.noProjects")}</p>;
  }
  const errored = projects.filter((p): p is Failed => p.error !== undefined);
  const ok = projects.filter((p): p is Ok => p.error === undefined);

  const required: Wait[] = ok.flatMap((p) =>
    p.needs_you.required.map((item) => ({
      project: p.project,
      flowId: item.flow_id,
      subject: item.subject,
      to: requiredLink(p.project, item),
      optional: false,
      type: item.type,
      sentence: item.cause,
    })),
  );
  const optional: Wait[] = ok.flatMap((p) =>
    p.needs_you.optional.map((item) => ({
      project: p.project,
      flowId: item.flow_id,
      subject: item.subject,
      to: `${flowPath(p.project, item.flow_id)}/decisions`,
      optional: true,
      type: item.type,
    })),
  );
  const waits = [...required, ...optional];
  const acting = ok.flatMap((p) =>
    (p.continues_without_you ?? []).map((op) => ({ project: p.project, op })),
  );

  return (
    <div className="flex flex-col gap-9">
      <div className="grid gap-3 min-[640px]:grid-cols-3">
        <Tile href="#waits" tone="waits" value={waits.length} label={t("today.tile.waits")} hint={t("today.tile.waitsHint")} />
        <Tile href="#acting" tone="acting" value={acting.length} label={t("today.tile.acting")} hint={t("today.tile.actingHint")} />
        <Tile href="#projects" tone="plain" value={projects.length} label={t("today.tile.projects")} hint={t("today.tile.projectsHint")} />
      </div>

      <Section id="waits" tone="waits" title={t("today.waits.title")} why={t("today.waits.why")} count={waits.length}>
        {waits.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-card p-5">
            <p className="font-medium">✓ {t("today.waits.none")}</p>
            <p className="mt-1 text-sm text-muted-foreground">{t("today.waits.noneHint")}</p>
          </div>
        ) : (
          waits.map((w) => <WaitCard key={`${w.project}:${w.flowId}:${w.subject}:${w.optional}`} w={w} />)
        )}
      </Section>

      <Section id="acting" tone="acting" title={t("today.acting.title")} why={t("today.acting.why")} count={acting.length}>
        {acting.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-card p-5">
            <p className="font-medium">○ {t("today.acting.none")}</p>
            <p className="mt-1 text-sm text-muted-foreground">{t("today.acting.noneHint")}</p>
          </div>
        ) : (
          acting.map(({ project, op }) => <ActingCard key={op.operation_id} project={project} op={op} />)
        )}
      </Section>

      <Section id="projects" tone="plain" title={t("today.projects.title")} why={t("today.projects.why")} count={projects.length}>
        <div className="grid gap-3 min-[900px]:grid-cols-[repeat(auto-fill,minmax(340px,1fr))]">
          {errored.map((p) => <FailedCard key={p.project} p={p} />)}
          {ok.map((p) => <ProjectCard key={p.project} entry={p} onSeen={today.reload} />)}
        </div>
      </Section>
    </div>
  );
}

export default function TodayPage() {
  const session = useSession();
  const { t } = useLocale();
  return (
    <section className="flex flex-col gap-8">
      <header className="flex flex-col gap-1.5">
        <h1 className="text-[32px] leading-tight">{t("today.title")}</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">{t("today.lede")}</p>
        {session.operator ? <p className="text-xs text-muted-foreground">{session.operator.name}</p> : null}
      </header>
      {!session.ready ? (
        <Pending label={t("today.checking")} />
      ) : session.operator ? (
        <TodayBody />
      ) : (
        <div className="rounded-xl border border-border bg-card p-5">
          <p className="text-sm">
            {t("today.signedOut")}{" "}
            <Link to="/login?next=%2F" className="text-link hover:underline">
              {t("today.signIn")}
            </Link>{" "}
            {t("today.orRead")}{" "}
            <Link to="/projects" className="text-link hover:underline">
              {t("today.projectsLink")}
            </Link>{" "}
            {t("today.orReadEnd")}
          </p>
        </div>
      )}
    </section>
  );
}
