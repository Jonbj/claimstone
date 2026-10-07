import { Link, useParams } from "react-router";
import DecidedRecently from "@/components/decisions/DecidedRecently";
import OpenDecisionCard from "@/components/decisions/OpenDecisionCard";
import RecordOfferForm from "@/components/decisions/RecordOfferForm";
import RetryCampaignForm from "@/components/decisions/RetryCampaignForm";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { control } from "@/lib/control";
import { useSession } from "@/lib/session";

// Decisions (spec F5): what waits for a person in this flow, in the server's order — never
// re-sorted — followed by what was decided recently and the two recording forms. Reading the
// flow needs no session; deciding does, so signed out the page offers the sign-in link and no
// write control (spec §1 rule 11).
export default function DecisionsPage() {
  const { project: raw, sel: rawSel } = useParams();
  const project = raw ? decodeURIComponent(raw) : "";
  const sel = rawSel ? decodeURIComponent(rawSel) : "";
  const session = useSession();

  if (!session.ready) return <Pending label="checking the session…" />;
  if (!session.operator) {
    const next = `/p/${encodeURIComponent(project)}/f/${encodeURIComponent(sel)}/decisions`;
    return (
      <section className="flex flex-col gap-3 pt-6">
        <h1 className="text-[44px] leading-tight">Decisions</h1>
        <p className="text-sm text-muted-foreground">
          Sign in to{" "}
          <Link className="underline" to={`/login?next=${encodeURIComponent(next)}`}>
            record decisions
          </Link>{" "}
          in this flow. Reading the flow itself needs no session.
        </p>
      </section>
    );
  }
  return <DecisionsSignedIn project={project} flowId={sel} />;
}

function DecisionsSignedIn({ project, flowId }: { project: string; flowId: string }) {
  const list = useApi(() => control.decisions(project, flowId), [project, flowId]);
  const base = `/p/${encodeURIComponent(project)}/f/${encodeURIComponent(flowId)}`;
  const onDone = () => list.reload();

  if (list.error) return <ErrorState error={list.error} context="decisions" />;
  if (list.pending || !list.data) return <Pending label="computing…" />;
  const data = list.data;
  const required = data.open.filter((item) => item.required).length;

  return (
    <section className="flex flex-col gap-5">
      <header>
        <nav className="text-[13px] text-muted-foreground">
          <Link to={base} className="underline">the flow</Link> / Decisions
        </nav>
        <h1 className="mt-1 text-[44px] leading-tight">Decisions</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {data.open.length} open: {required} required, {data.open.length - required} optional.
          The order is the server's — required before optional, then acquisition metadata, then
          age; never by expected result.
        </p>
      </header>

      {list.refreshing ? <Pending label="refreshing…" /> : null}

      {data.open.length > 0 ? (
        <div className="flex flex-col gap-4">
          {data.open.map((item) => (
            <OpenDecisionCard
              key={item.id}
              item={item}
              project={project}
              flowId={flowId}
              onDone={onDone}
            />
          ))}
        </div>
      ) : (
        <section className="rounded-xl bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
          <p className="text-sm text-muted-foreground">
            nothing waits for a person in this flow
          </p>
        </section>
      )}

      <RecordOfferForm project={project} flowId={flowId} onDone={onDone} />
      <RetryCampaignForm project={project} flowId={flowId} onDone={onDone} />

      <section className="rounded-xl bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
        <h2 className="mb-2 text-base font-semibold">Decided recently</h2>
        <DecidedRecently rows={data.decided_recently} />
      </section>
    </section>
  );
}
