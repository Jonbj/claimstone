import { Link, useParams } from "react-router";
import Chip from "@/components/Chip";
import ErrorState from "@/components/ErrorState";
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
      <header>
        <h1 className="text-[22px] font-semibold">
          {project}
          {refreshing ? (
            <span className="pending ml-3" role="status">
              refreshing…
            </span>
          ) : null}
        </h1>
      </header>

      {integrity.pending ? (
        <Pending label="loading integrity…" />
      ) : integrity.error ? (
        <ErrorState error={integrity.error} context="integrity" />
      ) : integrity.data ? (
        <IntegrityPanel integrity={integrity.data} />
      ) : null}

      {index.pending ? (
        <Pending label="loading selectors…" />
      ) : index.error ? (
        <ErrorState error={index.error} context="projects" />
      ) : card ? (
        <>
          <section>
            <h2 className="mb-2 text-sm font-semibold">flows</h2>
            {(card.flows ?? []).map((flow) => (
              <p
                key={flow.flow_id}
                className="flex flex-wrap items-baseline gap-2 py-0.5 text-sm"
              >
                <Link
                  to={`/p/${encodeURIComponent(project)}/f/${encodeURIComponent(flow.flow_id)}`}
                  className="font-mono text-[13px] text-blue-600 hover:underline dark:text-blue-400"
                >
                  flow {flow.flow_id.slice(0, 12)}
                </Link>
                <span>· {flow.selector_label} ·</span>
                <Chip text={flow.binding_state} />
                {flow.title ? <span>· {flow.title}</span> : null}
                {flow.bound_after_data ? (
                  <span className="text-xs text-muted-foreground">
                    · bound after data existed: rows written before binding are not
                    verified against this protocol
                  </span>
                ) : null}
              </p>
            ))}
            {(card.flows ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">
                no flows; rounds with candidates are legacy
              </p>
            ) : null}
          </section>

          <section>
            <h2 className="mb-2 text-sm font-semibold">legacy rounds</h2>
            {(card.unbound_selectors ?? []).map((entry) => (
              <p key={entry.slug} className="flex flex-wrap items-baseline gap-2 py-0.5 text-sm">
                <Link
                  to={`/p/${encodeURIComponent(project)}/u/${encodeURIComponent(entry.slug)}`}
                  className="font-mono text-[13px] text-blue-600 hover:underline dark:text-blue-400"
                >
                  {entry.label}
                </Link>
                <Chip text="protocol not verified" />
              </p>
            ))}
            {(card.unbound_selectors ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">none</p>
            ) : null}
          </section>
        </>
      ) : (
        <ErrorState
          error={new Error("the API's project list does not name this project")}
          context="projects"
        />
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold">activity — whole project</h2>
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
                  {JSON.stringify(row.row).slice(0, 220)}
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
