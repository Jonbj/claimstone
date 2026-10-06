import { Link } from "react-router";
import Chip from "@/components/Chip";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useApi } from "@/hooks/useApi";
import { api, ApiError } from "@/lib/api";
import type { Projects, Summary } from "@/lib/api-types";
import { cn } from "@/lib/utils";

// Index (§8.3): one card per project; its flows and unbound selectors are rows, each
// row filling in from its own `/summary`, fetched lazily and in parallel — the request
// pattern that fixes I4 (§3.2). A row shows a skeleton while its summary computes,
// never a zero (§4.2 rule 1). Server order everywhere (rule 6): the projects list,
// each flow list and each unbound list are exactly the API's.
type ProjectCard_ = Projects["projects"][number];

function SummarySkeleton() {
  // §8.3 "a skeleton while pending": pulsing bars carrying the pending state's name,
  // so rule 1's "a pending fetch renders Pending" holds in visual skeleton form too.
  return (
    <span
      role="status"
      aria-label="computing…"
      className="inline-flex items-center gap-2 align-middle"
      data-testid="summary-skeleton"
    >
      <span className="h-3 w-12 animate-pulse rounded bg-muted-foreground/25" />
      <span className="h-3 w-20 animate-pulse rounded bg-muted-foreground/25" />
      <span className="h-3 w-16 animate-pulse rounded bg-muted-foreground/25" />
    </span>
  );
}

function FloorBadge({ status }: { status: string }) {
  // §8.3: amber means below floor. The server's status word travels verbatim
  // (§4.2 rule 5); colour only repeats what the word already says (rule 7).
  const below = status !== "OK";
  return (
    <Badge
      variant="outline"
      className={cn(
        "text-[11px]",
        below &&
          "border-amber-500 text-amber-700 dark:border-amber-400 dark:text-amber-300",
      )}
    >
      floor {status}
    </Badge>
  );
}

function summaryBits(summary: Summary): string[] {
  // The counts are the API's; nothing here derives a meaning the server did not send.
  const bits: string[] = [];
  if (summary.verdicts) {
    bits.push(
      `${summary.verdicts.awaiting_adjudication} awaiting a person`,
      `${summary.verdicts.adjudicated} signed`,
    );
    if (summary.verdicts.stale) bits.push(`${summary.verdicts.stale} stale`);
  }
  return bits;
}

// One row per selector: it fetches its own summary, so the cheap `/projects` answer
// paints every row at once and each row's numbers arrive when they are computed.
function SelectorRow({
  project,
  kind,
  sel,
  label,
  bindingState,
  boundAfterData,
  title,
}: {
  project: string;
  kind: "f" | "u";
  sel: string;
  label: string;
  bindingState?: string;
  boundAfterData?: boolean;
  title?: string | null;
}) {
  const summary = useApi(() => api.summary(project, kind, sel), [project, kind, sel]);
  const to = `/p/${encodeURIComponent(project)}/${kind}/${encodeURIComponent(sel)}`;
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
      {kind === "f" ? (
        <>
          <span className="text-muted-foreground">flow</span>
          <Link
            to={to}
            className="font-mono text-[13px] text-blue-600 hover:underline dark:text-blue-400"
          >
            {sel.slice(0, 12)}
          </Link>
          <span>{label}</span>
          {bindingState ? <Chip text={bindingState} /> : null}
          {boundAfterData ? (
            <span className="text-xs text-muted-foreground">
              bound after data existed
            </span>
          ) : null}
          {title ? <span className="text-xs text-muted-foreground">{title}</span> : null}
        </>
      ) : (
        <>
          <span className="text-muted-foreground">legacy</span>
          <Link
            to={to}
            className="font-mono text-[13px] text-blue-600 hover:underline dark:text-blue-400"
          >
            {label}
          </Link>
          <Chip text="protocol not verified" />
        </>
      )}
      {summary.pending ? (
        <SummarySkeleton />
      ) : summary.error ? (
        // The error's code and message on screen, never a generic "unavailable" with the
        // reason hidden in a tooltip: LEDGER_CORRUPT names the ledger and line (review of R3).
        <span className="flex flex-wrap items-baseline gap-2 text-xs" role="alert">
          <Chip text={summary.error instanceof ApiError ? summary.error.code : "UNREACHABLE"} />
          <span className="text-muted-foreground">{summary.error.message}</span>
        </span>
      ) : summary.data ? (
        <>
          {summary.data.floor_status ? (
            <FloorBadge status={summary.data.floor_status} />
          ) : null}
          {summaryBits(summary.data).map((bit) => (
            <span key={bit} className="text-xs text-muted-foreground">
              {bit}
            </span>
          ))}
          {Object.keys(summary.data.inbox_counts).length ? (
            <span className="text-xs text-muted-foreground">
              inbox{" "}
              {Object.entries(summary.data.inbox_counts)
                .map(([c, n]) => `${c} ${n}`)
                .join(" · ")}
            </span>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function ProjectCard({ project }: { project: ProjectCard_ }) {
  return (
    <Card data-project={project.name}>
      <CardHeader>
        <CardTitle>
          {project.config === "OK" ? (
            <Link
              to={`/p/${encodeURIComponent(project.name)}`}
              className="hover:underline"
            >
              {project.name}
            </Link>
          ) : (
            project.name
          )}
        </CardTitle>
        {project.config !== "OK" ? (
          <CardDescription className="flex flex-wrap items-baseline gap-2">
            <Chip text="ConfigError" />
            <span>{project.config_error}</span>
          </CardDescription>
        ) : (
          <CardDescription>
            registry v{project.registry_version} · {project.registry_sha256}
          </CardDescription>
        )}
        {project.registry_drift ? (
          <p className="flex flex-wrap items-baseline gap-2 text-sm">
            <Chip text="registry drift" />
            <span className="text-muted-foreground">{project.registry_drift}</span>
          </p>
        ) : null}
        {project.integrity_error ? (
          <p className="flex flex-wrap items-baseline gap-2 text-sm">
            <Chip text="LEDGER_CORRUPT" />
            <span className="text-muted-foreground">{project.integrity_error}</span>
          </p>
        ) : null}
      </CardHeader>
      {project.config === "OK" ? (
        <CardContent className="flex flex-col gap-2">
          {(project.flows ?? []).map((flow) => (
            <SelectorRow
              key={flow.flow_id}
              project={project.name}
              kind="f"
              sel={flow.flow_id}
              label={flow.selector_label}
              bindingState={flow.binding_state}
              boundAfterData={flow.bound_after_data}
              title={flow.title}
            />
          ))}
          {(project.unbound_selectors ?? []).map((unbound) => (
            <SelectorRow
              key={unbound.slug}
              project={project.name}
              kind="u"
              sel={unbound.slug}
              label={unbound.label}
            />
          ))}
        </CardContent>
      ) : null}
    </Card>
  );
}

export default function IndexPage() {
  const projects = useApi(() => api.projects(), []);
  return (
    <section className="flex flex-col gap-5">
      <header>
        <h1 className="text-[22px] font-semibold">Projects</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          One server, every project, all of it read-only. A round with candidates and no
          flow is legacy: protocol not verified.
        </p>
      </header>
      {projects.pending ? (
        <Pending label="loading projects…" />
      ) : projects.error ? (
        <ErrorState error={projects.error} />
      ) : (
        projects.data?.projects.map((project) => (
          <ProjectCard key={project.name} project={project} />
        ))
      )}
    </section>
  );
}
