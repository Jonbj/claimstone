import { Link, useParams } from "react-router";
import Chip from "@/components/Chip";
import ErrorState from "@/components/ErrorState";
import RowFields from "@/components/RowFields";
import IntegrityPanel from "@/components/IntegrityPanel";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { usePoll } from "@/hooks/usePoll";
import { api } from "@/lib/api";

// The project page (§4.1): integrity, flows, unbound (legacy) selectors, whole-project
// activity. Polls `/projects/{p}/poll` every 3 s (§4.2 rule 8): when the ledgers
// signature moves and the tab is visible, this view's data is fetched again — no full
// reload — and a discreet "refreshing…" shows while the same view recomputes (the R2
// review's rule: keep the numbers on screen, name the refresh).
export default function ProjectPage() {
  const { project: raw } = useParams();
  const project = raw ? decodeURIComponent(raw) : "";

  const integrity = useApi(() => api.integrity(project), [project]);
  const index = useApi(() => api.projects(), []);
  const activity = useApi(() => api.activity(project, 50), [project]);

  usePoll(project || null, () => {
    integrity.reload();
    index.reload();
    activity.reload();
  });

  const card =
    index.data?.projects.find((candidate) => candidate.name === project) ?? null;
  const refreshing =
    integrity.refreshing || index.refreshing || activity.refreshing;

  return (
    <section className="flex flex-col gap-5">
      <header className="flex flex-col gap-2">
        <nav aria-label="Breadcrumb" className="text-sm text-muted-foreground">
          <Link to="/projects" className="hover:underline">Projects</Link> / {project}
        </nav>
        <h1 className="font-serif text-5xl leading-tight font-normal">
          {project}
          {refreshing ? (
            <span className="pending ml-3 font-sans text-sm" role="status">
              refreshing…
            </span>
          ) : null}
        </h1>
        {card && card.config === "OK" ? (
          <p className="font-mono text-xs text-muted-foreground">
            registry v{card.registry_version} · {card.registry_sha256}
          </p>
        ) : null}
      </header>

      <section aria-label="Research" className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold">Research</h2>
        {index.pending ? (
          <Pending label="loading selectors…" />
        ) : index.error ? (
          <ErrorState error={index.error} context="projects" />
        ) : card ? (
          <ul className="flex flex-wrap gap-3">
            {(card.flows ?? []).map((flow) => (
              <li key={flow.flow_id} className="rounded-xl border border-border bg-card px-4 py-2">
                <Link
                  to={`/p/${encodeURIComponent(project)}/f/${encodeURIComponent(flow.flow_id)}`}
                  className="flex min-h-11 flex-col justify-center hover:underline"
                >
                  <b>{flow.title ?? `flow ${flow.flow_id.slice(0, 12)}`}</b>
                  <span className="text-xs text-muted-foreground">{flow.selector_label}</span>
                </Link>
                <div className="flex flex-wrap items-baseline gap-2">
                  <Chip text={flow.binding_state} />
                  {flow.bound_after_data ? (
                    <span className="text-xs text-muted-foreground">
                      bound after data existed: rows written before binding are not verified
                      against this protocol
                    </span>
                  ) : null}
                </div>
              </li>
            ))}
            {(card.unbound_selectors ?? []).map((entry) => (
              <li
                key={entry.slug}
                className="rounded-xl border border-dashed border-border bg-card px-4 py-2"
              >
                <Link
                  to={`/p/${encodeURIComponent(project)}/u/${encodeURIComponent(entry.slug)}`}
                  className="flex min-h-11 flex-col justify-center hover:underline"
                >
                  <b>{entry.label}</b>
                  <span className="text-xs text-muted-foreground">legacy round</span>
                </Link>
                <Chip text="protocol not verified" />
              </li>
            ))}
            {(card.flows ?? []).length + (card.unbound_selectors ?? []).length === 0 ? (
              <li className="text-sm text-muted-foreground">No flows and no legacy rounds.</li>
            ) : null}
          </ul>
        ) : (
          <ErrorState
            error={new Error("the API's project list does not name this project")}
            context="projects"
          />
        )}
      </section>

      <section aria-label="Integrity">
        {integrity.pending ? (
          <Pending label="loading integrity…" />
        ) : integrity.error ? (
          <ErrorState error={integrity.error} context="integrity" />
        ) : integrity.data ? (
          <IntegrityPanel integrity={integrity.data} />
        ) : null}
      </section>

      <section id="activity">
        <h2 className="mb-2 text-sm font-semibold">Activity — whole project</h2>
        {activity.pending ? (
          <Pending label="loading activity…" />
        ) : activity.error ? (
          <ErrorState error={activity.error} context="activity" />
        ) : (
          <>
            {activity.data?.activity.map((row, i) => (
              <p
                key={i}
                className="flex flex-wrap items-baseline gap-3 py-0.5 text-sm"
              >
                <span className="font-mono text-xs text-muted-foreground">
                  {row.when}
                </span>
                <span>{row.stage}</span>
                <span className="text-xs text-muted-foreground">
                  <RowFields row={row.row as Record<string, unknown>} />
                </span>
              </p>
            ))}
            {activity.data?.activity.length === 0 ? (
              <p className="text-sm text-muted-foreground">no rows yet</p>
            ) : null}
            <p className="mt-2 text-xs text-muted-foreground">
              Scoped rows carry their own timestamps; rows without one have no
              trustworthy time and are not shown.
            </p>
          </>
        )}
      </section>
    </section>
  );
}
