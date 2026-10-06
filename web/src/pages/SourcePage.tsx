import { useParams } from "react-router";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import SourceDossierView from "@/components/SourceDossier";
import { useApi } from "@/hooks/useApi";
import { usePoll } from "@/hooks/usePoll";
import { api } from "@/lib/api";

// The source dossier page (§8.3): one candidate's whole trail. Polls every 3 s
// (§4.2 rule 8).
export default function SourcePage({ kind }: { kind: "f" | "u" }) {
  const { project: raw, sel: rawSel, key: rawKey } = useParams();
  const project = raw ? decodeURIComponent(raw) : "";
  const sel = rawSel ? decodeURIComponent(rawSel) : "";
  const candidateKey = rawKey ? decodeURIComponent(rawKey) : "";

  const dossier = useApi(() => api.source(project, kind, sel, candidateKey), [
    project,
    kind,
    sel,
    candidateKey,
  ]);
  usePoll(project || null, () => dossier.reload());

  return (
    <section className="flex flex-col gap-5">
      <header>
        <h1 className="text-[22px] font-semibold">
          source <span className="font-mono">{candidateKey}</span>
          {dossier.refreshing ? (
            <span className="pending ml-3" role="status">
              refreshing…
            </span>
          ) : null}
        </h1>
      </header>
      {dossier.error ? (
        <ErrorState error={dossier.error} context="source dossier" />
      ) : dossier.pending || !dossier.data ? (
        <Pending label="loading source…" />
      ) : (
        <SourceDossierView dossier={dossier.data} />
      )}
    </section>
  );
}