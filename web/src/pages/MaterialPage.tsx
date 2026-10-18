import { useState } from "react";
import { Link, useParams } from "react-router";
import CitationLeads from "@/components/material/CitationLeads";
import CopiesNeeded from "@/components/material/CopiesNeeded";
import IntakeList from "@/components/material/IntakeList";
import ProposeForm from "@/components/material/ProposeForm";
import UploadForm from "@/components/material/UploadForm";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { control } from "@/lib/control";
import { useSession } from "@/lib/session";

// Add material (spec F5): propose a reference, DOI or link; upload a PDF for one candidate;
// and the intake list with each item's state and reason. Reading the flow needs no session;
// adding material does, so signed out the page offers the sign-in link and no write control
// (spec §1 rule 11).
export default function MaterialPage() {
  const { project: raw, sel: rawSel } = useParams();
  const project = raw ? decodeURIComponent(raw) : "";
  const sel = rawSel ? decodeURIComponent(rawSel) : "";
  const session = useSession();

  if (!session.ready) return <Pending label="checking the session…" />;
  if (!session.operator) {
    const next = `/p/${encodeURIComponent(project)}/f/${encodeURIComponent(sel)}/material`;
    return (
      <section className="flex flex-col gap-3 pt-6">
        <h1 className="text-[44px] leading-tight">Add material</h1>
        <p className="text-sm text-muted-foreground">
          Sign in to{" "}
          <Link className="underline" to={`/login?next=${encodeURIComponent(next)}`}>
            add material
          </Link>{" "}
          to this flow. Reading the flow itself needs no session.
        </p>
      </section>
    );
  }
  return <MaterialSignedIn project={project} flowId={sel} />;
}

function MaterialSignedIn({ project, flowId }: { project: string; flowId: string }) {
  const base = `/p/${encodeURIComponent(project)}/f/${encodeURIComponent(flowId)}`;
  const list = useApi(() => control.intake(project, flowId), [project, flowId]);
  const overview = useApi(() => api.overview(project, "f", flowId), [project, flowId]);
  const [target, setTarget] = useState("");
  const onDone = () => { list.reload(); overview.reload(); };
  const choose = (key: string) => {
    setTarget(key);
    document.getElementById("upload")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <section className="flex flex-col gap-5">
      <header>
        <nav className="text-[13px] text-muted-foreground">
          <Link to={base} className="underline">the flow</Link> / Add material
        </nav>
        <h1 className="mt-1 text-[44px] leading-tight">Add material</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          A reference, DOI, link or PDF you think belongs here. Nothing is counted until it
          passes the same checks as anything Claimstone finds.
        </p>
      </header>

      {list.refreshing ? <Pending label="refreshing…" /> : null}

      {overview.data ? (
        <CopiesNeeded entries={overview.data.source_tracker} intake={list.data?.items ?? []} onChoose={choose} />
      ) : overview.error ? (
        <ErrorState error={overview.error} context="the candidate list" />
      ) : null}

      {overview.data ? (
        <CitationLeads project={project} flowId={flowId} leads={overview.data.citation_suggestions} onDone={onDone} />
      ) : null}

      <ProposeForm project={project} flowId={flowId} onDone={onDone} />
      <UploadForm project={project} flowId={flowId} onDone={onDone} target={target} onTarget={setTarget} />

      <section className="rounded-xl border border-border bg-card p-5">
        <h2 className="text-base font-semibold">Proposed material</h2>
        <p className="mb-3 mt-0.5 text-[13px] text-muted-foreground">
          newest first, the server's order — one line per item with its latest state
        </p>
        {list.error ? (
          <ErrorState error={list.error} context="intake" />
        ) : list.pending || !list.data ? (
          <Pending label="the intake list…" />
        ) : (
          <IntakeList items={list.data.items} decisionsTo={`${base}/decisions`} />
        )}
      </section>
    </section>
  );
}
