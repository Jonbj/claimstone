import type { SourceDossier } from "@/lib/api-types";

// One candidate's whole trail (§8.3 source dossier): every acquisition row in ledger
// order, the document, active chunks, the advisory rows and the claim count per
// question. Every `failure_display` is rendered verbatim (§4.2 rule 5) — the UI never
// re-derives it from `failure_class`.
const of = (row: { [k: string]: unknown }, field: string) =>
  row[field] === undefined || row[field] === null ? "—" : String(row[field]);

export default function SourceDossierView({ dossier }: { dossier: SourceDossier }) {
  const candidate = dossier.candidate;
  const claims = Object.entries(dossier.claims_by_question);
  const document = dossier.document;

  return (
    <>
      <section className="rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
        <h2 className="mb-1 text-base font-semibold">candidate</h2>
        <p className="text-sm">
          <span className="font-mono text-[13px]">{dossier.candidate_key}</span>
          {" · source "}
          {dossier.source_id}
          {" · class "}
          {of(candidate ?? {}, "source_class")}
          {" · round "}
          {of(candidate ?? {}, "round")}
          {" · channel "}
          {of(candidate ?? {}, "channel")}
        </p>
        {candidate?.title ? (
          <p className="mt-1 text-sm text-muted-foreground">{String(candidate.title)}</p>
        ) : null}
      </section>

      <section className="rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
        <h2 className="mb-1 text-base font-semibold">acquisitions — every row, ledger order</h2>
        {dossier.acquisitions.length > 0 ? (
          <table className="mt-2 w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="p-2 font-semibold">#</th>
                <th className="p-2 font-semibold">provenance</th>
                <th className="p-2 font-semibold">outcome</th>
                <th className="p-2 font-semibold">licence</th>
                <th className="p-2 font-semibold">fetched</th>
              </tr>
            </thead>
            <tbody>
              {dossier.acquisitions.map((row, index) => (
                <tr key={index} data-row-index={index} className="border-b border-border/60">
                  <td className="p-2">{index + 1}</td>
                  <td className="p-2">{of(row, "provenance")}</td>
                  <td className="p-2">
                    {row.acquired
                      ? "acquired"
                      : row.attempts[0]
                        ? row.attempts[0].failure_display
                        : "—"}
                  </td>
                  <td className="p-2">{of(row, "licence")}</td>
                  <td className="p-2">{of(row, "fetched_at")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="mt-1 text-sm text-muted-foreground">no rows</p>
        )}
        {dossier.counted_acquisition ? (
          <p className="mt-2 text-xs text-muted-foreground">
            counted (collapsed) row: {of(dossier.counted_acquisition, "fetched_at")} ·{" "}
            {of(dossier.counted_acquisition, "provenance")}
          </p>
        ) : (
          <p className="mt-2 text-xs text-muted-foreground">no counted acquisition row</p>
        )}
      </section>

      <section className="rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
        <h2 className="mb-1 text-base font-semibold">document and chunks</h2>
        <p className="text-sm">
          {document
            ? `confirmed ${String(document.fulltext_confirmed)} · ${of(document, "chunks")} chunks declared`
            : "no document row"}
          {" · active chunks: "}
          {dossier.active_chunks === null ? (
            <span title="not knowable">—</span>
          ) : (
            dossier.active_chunks
          )}
        </p>
      </section>

      <section className="rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
        <h2 className="mb-1 text-base font-semibold">advisory — AI provisional</h2>
        {Object.entries(dossier.advisory).some(([, rows]) => rows.length > 0) ? (
          Object.entries(dossier.advisory).map(([ledger, rows]) =>
            rows.length > 0 ? (
              <div key={ledger} className="grid gap-2 py-0.5 text-sm md:grid-cols-[12rem_1fr]">
                <span className="font-semibold">{ledger}</span>
                <div>
                  {rows.map((row, index) => (
                    <p key={index}>
                      {String(row.assessment_status)} ·{" "}
                      {String(row.role ?? row.related_kind ?? "")}
                    </p>
                  ))}
                </div>
              </div>
            ) : null,
          )
        ) : (
          <p className="mt-1 text-sm text-muted-foreground">no advisory rows</p>
        )}
        <p className="mt-2 text-xs text-muted-foreground">{dossier.advisory_note}</p>
      </section>

      <section className="rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
        <h2 className="mb-1 text-base font-semibold">claims by question</h2>
        <p className="text-sm">
          {claims.length > 0
            ? claims.map(([qid, count]) => (
                <span key={qid} className="mr-3 font-mono text-[13px]">
                  {qid} {count}
                </span>
              ))
            : "none"}
        </p>
      </section>
    </>
  );
}