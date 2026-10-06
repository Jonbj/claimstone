<script lang="ts">
  // Invariant 1, end to end (§4.1): claim → review → chunk → document → acquisition →
  // candidate. A missing step is a named state, never an absence; the quote is rechecked
  // by the server (`quote_found`) and the failure is a named banner here.
  import Chip from "./Chip.svelte";

  export type LineageData = {
    claim_id: string;
    source_id: string;
    steps: {
      claim: Record<string, unknown>;
      review: Record<string, unknown> | null;
      chunk: {
        chunk_id: string;
        evidence_quote: string;
        generation_sha256: string | null;
        text_sha256: string | null;
        text: string | null;
        quote_found: boolean;
      } | null;
      document: Record<string, unknown> | null;
      document_pdf_instrument: string | null;
      acquisition: Record<string, unknown> | null;
      acquisition_candidate_key: string | null;
      candidate: Record<string, unknown> | null;
    };
    [k: string]: unknown;
  };

  let { lineage }: { lineage: LineageData } = $props();

  const claim = $derived(lineage.steps.claim as Record<string, string | null>);
  const review = $derived(lineage.steps.review);
  const chunk = $derived(lineage.steps.chunk);
  const document = $derived(lineage.steps.document);
  const acquisition = $derived(
    lineage.steps.acquisition as
      | { attempts?: Array<Record<string, unknown>>; [k: string]: unknown }
      | null,
  );
  const candidate = $derived(lineage.steps.candidate as Record<string, string> | null);

  // §4.2 rule 1: the marked text is the chunk's, with the quote's first occurrence
  // wrapped — server-checked, rendered verbatim (rule 5).
  const chunkText = $derived.by(() => {
    if (chunk === null) return { head: "", quote: "", tail: "" };
    const text = chunk.text ?? "";
    const quote = chunk.evidence_quote;
    const at = text.indexOf(quote);
    if (at < 0) return { head: text, quote: "", tail: "" };
    return { head: text.slice(0, at), quote, tail: text.slice(at + quote.length) };
  });
</script>

<section>
  <h3>the claim</h3>
  <div class="log">
    <div class="row">
      <span class="label">claim</span>
      <div class="body">
        {claim.claim}
        <br />stance {claim.stance} · question {claim.question_id} ·
        class {claim.source_class}
        <br />gate v{claim.claim_gate_version} rev {claim.gate_revision} ·
        {claim.backend}/{claim.model} ({claim.harness_version})
      </div>
    </div>
    <blockquote><q>{claim.evidence_quote}</q></blockquote>

    {#if review === null}
      <div class="row"><span class="label">review</span>
        <div class="body">awaiting review</div></div>
    {:else}
      <div class="row"><span class="label">review</span>
        <div class="body">
          {review.verdict} — {review.reason}
          <br />review v{review.review_version} · {review.reviewed_by ?? ""}
        </div></div>
    {/if}

    {#if chunk === null}
      <div class="row"><span class="label">chunk</span>
        <div class="body">not found in current ledgers</div></div>
    {:else}
      <div class="row"><span class="label">chunk</span>
        <div class="body">
          <span class="mono">{chunk.chunk_id}</span>
          · generation {(chunk.generation_sha256 ?? "").slice(0, 12)}
          · text {(chunk.text_sha256 ?? "").slice(0, 12)}
          {#if chunk.quote_found === false}
            <br /><Chip text="invariant 1 check fails on current data" />
          {/if}
          <br /><code data-testid="chunk-text">{chunkText.head}<mark>{chunkText.quote}</mark>{chunkText.tail}</code>
        </div></div>
    {/if}

    {#if document === null}
      <div class="row"><span class="label">document</span>
        <div class="body">not found in current ledgers</div></div>
    {:else}
      <div class="row"><span class="label">document</span>
        <div class="body">
          <span class="mono">{lineage.source_id}</span>
          · confirmed {document.fulltext_confirmed}
          · html v{document.html_parser_version}
          · jats v{document.jats_parser_version ?? "—"}
          {#if lineage.steps.document_pdf_instrument}
            · grobid {lineage.steps.document_pdf_instrument.slice(0, 40)}
          {/if}
          · {document.chunks} chunks · {document.references} refs
          · {document.body_chars} chars
          · generation {String(document.generation_sha256 ?? "").slice(0, 12)}
        </div></div>
    {/if}

    {#if acquisition === null}
      <div class="row"><span class="label">acquisition</span>
        <div class="body">not found in current ledgers</div></div>
    {:else}
      <div class="row"><span class="label">acquisition</span>
        <div class="body">
          <span class="mono">{String(acquisition.sha256 ?? "").slice(0, 16)}</span>
          · {acquisition.provenance}
          · licence {acquisition.licence}
          · oa {acquisition.oa_status}
          · {acquisition.campaign}
          · {acquisition.fetched_at}
          <br />stored at {acquisition.stored_path} (text only; raw bytes are never served)
          {#if (acquisition.attempts ?? []).length}
            <table>
              <thead><tr><th>attempt</th><th>status</th><th>class</th><th>fetch v</th></tr></thead>
              <tbody>
                {#each acquisition.attempts ?? [] as attempt (String(attempt.url))}
                  <tr>
                    <td>{attempt.url}</td>
                    <td>{attempt.http_status}</td>
                    <!-- §4.2 rule 5: the server's display text, verbatim -->
                    <td>{attempt.failure_display}</td>
                    <td>{attempt.fetch_version}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
        </div></div>
    {/if}

    {#if candidate === null}
      <div class="row"><span class="label">candidate</span>
        <div class="body">not found in current ledgers</div></div>
    {:else}
      <div class="row"><span class="label">candidate</span>
        <div class="body">
          class {candidate.source_class} · round {candidate.round} ·
          channel {candidate.channel} · {candidate.title ?? ""}
        </div></div>
    {/if}
  </div>
</section>

<style>
  .log {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .row {
    display: grid;
    grid-template-columns: 7rem 1fr;
    gap: 0.75rem;
    align-items: baseline;
  }
  .label {
    font-weight: 600;
    color: var(--muted);
  }
  .body {
    min-width: 0;
  }
  blockquote {
    margin: 0;
    border-left: 3px solid var(--border);
    padding-left: 0.75rem;
  }
  code {
    display: block;
    background: var(--code-bg);
    border: 1px solid var(--border);
    border-radius: 0.4rem;
    padding: 0.4rem 0.6rem;
    white-space: pre-wrap;
    font-size: 0.8rem;
    margin-top: 0.25rem;
  }
  mark {
    background: var(--pending);
    color: var(--bg);
  }
  table {
    border-collapse: collapse;
    margin-top: 0.25rem;
  }
  th,
  td {
    border: 1px solid var(--border);
    padding: 0.2rem 0.5rem;
    text-align: left;
    font-size: 0.85rem;
  }
  .mono {
    font-family: ui-monospace, Menlo, Consolas, monospace;
  }
</style>