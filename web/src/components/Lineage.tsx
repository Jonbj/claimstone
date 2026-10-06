import Chip from "@/components/Chip";
import type { ReactNode } from "react";
import type { Lineage } from "@/lib/api-types";

// Invariant 1, end to end (§8.3): a vertical list of the six steps — claim → review
// → chunk → document → acquisition → candidate. A missing step is a named state,
// never an absence; the quote is rechecked by the server (`quote_found`) and a
// failure is a rose callout here; the quote is marked inside the chunk text
// (server-checked, rendered verbatim — rule 5).

const claimOf = (lineage: Lineage) =>
  lineage.steps.claim as Record<string, string | number | null>;

function Step({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-3 md:grid-cols-[7rem_1fr]">
      <span className="text-sm font-semibold text-muted-foreground">{label}</span>
      <div className="min-w-0 text-sm">{children}</div>
    </div>
  );
}

export default function LineageView({ lineage }: { lineage: Lineage }) {
  const claim = claimOf(lineage);
  const review = lineage.steps.review as
    | { verdict: string; reason: string; review_version: number; reviewed_by: string | null }
    | null;
  const chunk = lineage.steps.chunk;
  const document = lineage.steps.document as
    | {
        fulltext_confirmed: boolean;
        html_parser_version: number;
        jats_parser_version: number | null;
        chunks: number;
        references: number;
        body_chars: number;
        generation_sha256: string | null;
      }
    | null;
  const acquisition = lineage.steps.acquisition as
    | {
        sha256: string | null;
        provenance: string;
        licence: string;
        oa_status: string;
        campaign: string;
        fetched_at: string;
        stored_path: string;
      }
    | null;
  const candidate = lineage.steps.candidate as Record<string, string> | null;

  // Rule 1: the marked text is the chunk's own, with the quote's first occurrence
  // wrapped. When the server cannot find it, the text stands unmarked and the rose
  // callout names the failure.
  const text = chunk?.text ?? "";
  const quote = chunk?.evidence_quote ?? "";
  const at = text.indexOf(quote);
  const head = at < 0 ? text : text.slice(0, at);
  const marked = at < 0 ? "" : quote;
  const tail = at < 0 ? "" : text.slice(at + quote.length);

  return (
    <section className="flex flex-col gap-4 rounded-lg bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
      <h2 className="text-base font-semibold">The claim</h2>
      <div className="flex flex-col gap-4">
        <Step label="claim">
          {claim.claim}
          <br />
          stance {claim.stance} · question {claim.question_id} · class {claim.source_class}
          <br />
          gate v{claim.claim_gate_version} rev {claim.gate_revision} · {claim.backend}/
          {claim.model} ({claim.harness_version})
        </Step>
        <blockquote className="border-l-[3px] border-border pl-3 text-sm">
          <q>{claim.evidence_quote}</q>
        </blockquote>

        {review === null ? (
          <Step label="review">awaiting review</Step>
        ) : (
          <Step label="review">
            {review.verdict} — {review.reason}
            <br />
            review v{review.review_version} · {review.reviewed_by ?? ""}
          </Step>
        )}

        {chunk === null ? (
          <Step label="chunk">not found in current ledgers</Step>
        ) : (
          <Step label="chunk">
            <span className="font-mono text-[13px]">{chunk.chunk_id}</span> · generation{" "}
            {(chunk.generation_sha256 ?? "").slice(0, 12)} · text{" "}
            {(chunk.text_sha256 ?? "").slice(0, 12)}
            {chunk.quote_found === false ? (
              <div className="mt-1 rounded-md bg-rose-50 px-3 py-2 text-rose-700 ring-1 ring-rose-200">
                <Chip text="invariant 1 check fails on current data" />
              </div>
            ) : null}
            <code
              data-testid="chunk-text"
              className="mt-1 block whitespace-pre-wrap rounded-md bg-muted/60 px-2.5 py-1.5 font-mono text-xs ring-1 ring-border"
            >
              {head}
              <mark>{marked}</mark>
              {tail}
            </code>
          </Step>
        )}

        {document === null ? (
          <Step label="document">not found in current ledgers</Step>
        ) : (
          <Step label="document">
            <span className="font-mono text-[13px]">{lineage.source_id}</span> · confirmed{" "}
            {String(document.fulltext_confirmed)} · html v{document.html_parser_version} · jats
            v{document.jats_parser_version ?? "—"}
            {lineage.steps.document_pdf_instrument
              ? ` · grobid ${lineage.steps.document_pdf_instrument.slice(0, 40)}`
              : ""}
            {" · "}
            {document.chunks} chunks · {document.references} refs · {document.body_chars} chars ·
            generation {(document.generation_sha256 ?? "").slice(0, 12)}
          </Step>
        )}

        {acquisition === null ? (
          <Step label="acquisition">not found in current ledgers</Step>
        ) : (
          <Step label="acquisition">
            <span className="font-mono text-[13px]">{(acquisition.sha256 ?? "").slice(0, 16)}</span>{" "}
            · {acquisition.provenance} · licence {acquisition.licence} · oa{" "}
            {acquisition.oa_status} · {acquisition.campaign} · {acquisition.fetched_at}
            <br />
            stored at {acquisition.stored_path} (text only; raw bytes are never served)
            <table className="mt-1 w-full border-collapse text-xs">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="p-1.5">attempt</th>
                  <th className="p-1.5">status</th>
                  <th className="p-1.5">class</th>
                  <th className="p-1.5">fetch v</th>
                </tr>
              </thead>
              <tbody>
                {lineage.steps.acquisition?.attempts.map((attempt) => (
                  <tr key={attempt.url ?? String(attempt.fetch_version)} className="border-b border-border/60">
                    <td className="p-1.5 font-mono">{attempt.url}</td>
                    <td className="p-1.5">{attempt.http_status}</td>
                    {/* Rule 5: the server's display text, verbatim */}
                    <td className="p-1.5">{attempt.failure_display}</td>
                    <td className="p-1.5">{attempt.fetch_version}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Step>
        )}

        {candidate === null ? (
          <Step label="candidate">not found in current ledgers</Step>
        ) : (
          <Step label="candidate">
            class {candidate.source_class} · round {candidate.round} · channel{" "}
            {candidate.channel} · {candidate.title ?? ""}
          </Step>
        )}
      </div>
    </section>
  );
}
