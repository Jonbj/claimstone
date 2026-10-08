import { useParams } from "react-router";
import ErrorState from "@/components/ErrorState";
import LineageView from "@/components/Lineage";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { usePoll } from "@/hooks/usePoll";
import { api } from "@/lib/api";

// The claim lineage page (§8.3): invariant 1 end to end, claim → review → chunk →
// document → acquisition → candidate. Polls every 3 s (§4.2 rule 8).
export default function ClaimPage({ kind }: { kind: "f" | "u" }) {
  const { project: raw, sel: rawSel, cid: rawCid } = useParams();
  const project = raw ? decodeURIComponent(raw) : "";
  const sel = rawSel ? decodeURIComponent(rawSel) : "";
  const cid = rawCid ? decodeURIComponent(rawCid) : "";

  const lineage = useApi(() => api.claim(project, kind, sel, cid), [project, kind, sel, cid]);
  usePoll(project || null, () => lineage.reload());

  return (
    <section className="flex flex-col gap-5">
      <header>
        <h1 className="text-[22px] font-semibold">
          claim <span className="font-mono">{cid}</span>
          {lineage.refreshing ? (
            <span className="pending ml-3" role="status">
              refreshing…
            </span>
          ) : null}
        </h1>
      </header>
      {lineage.error ? (
        <ErrorState error={lineage.error} context="claim lineage" />
      ) : lineage.pending || !lineage.data ? (
        <Pending label="loading claim…" />
      ) : (
        <LineageView
          lineage={lineage.data}
          sourceHref={(key) =>
            `/p/${encodeURIComponent(project)}/${kind}/${encodeURIComponent(sel)}` +
            `/source/${encodeURIComponent(key)}`}
        />
      )}
    </section>
  );
}