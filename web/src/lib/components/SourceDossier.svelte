<script lang="ts">
  // One candidate's whole trail (§4.1): every acquisition row in ledger order, the
  // document, active chunks, advisory rows and the claim count per question. Every
  // `failure_display` is rendered verbatim (§4.2 rule 5) — the UI never re-derives it
  // from `failure_class`.
  import type { SourceDossier } from "$lib/api-types";

  let { dossier }: { dossier: SourceDossier } = $props();
</script>

<section>
  <h3>candidate</h3>
  <p class="line">
    <span class="mono">{dossier.candidate_key}</span>
    · source {dossier.source_id}
    · class {dossier.candidate?.source_class ?? "—"}
    · round {dossier.candidate?.round ?? "—"}
  </p>
</section>

<section>
  <h3>acquisitions — every row, ledger order</h3>
  <table>
    <thead>
      <tr><th>#</th><th>provenance</th><th>outcome</th><th>licence</th><th>fetched</th></tr>
    </thead>
    <tbody>
      {#each dossier.acquisitions as row, index (index)}
        <tr data-row-index={index}>
          <td>{index + 1}</td>
          <td>{row.provenance ?? "—"}</td>
          <td>
            {#if row.acquired}acquired{:else}{row.attempts?.[0]?.failure_display ?? "—"}{/if}
          </td>
          <td>{row.licence ?? "—"}</td>
          <td>{row.fetched_at ?? "—"}</td>
        </tr>
      {:else}
        <tr><td colspan="5">no rows</td></tr>
      {/each}
    </tbody>
  </table>
  {#if dossier.counted_acquisition}
    <p class="note">counted (collapsed) row: {dossier.counted_acquisition.fetched_at ?? "—"}
      · {dossier.counted_acquisition.provenance ?? "—"}</p>
  {:else}
    <p class="note">no counted acquisition row</p>
  {/if}
</section>

<section>
  <h3>document and chunks</h3>
  <p class="line">
    {#if dossier.document}
      confirmed {dossier.document.fulltext_confirmed}
      · {dossier.document.chunks} chunks declared
    {:else}
      no document row
    {/if}
    · active chunks: {dossier.active_chunks ?? "not knowable"}
  </p>
</section>

<section>
  <h3>advisory — AI provisional</h3>
  <div class="log">
    {#each Object.entries(dossier.advisory) as [ledger, rows] (ledger)}
      {#if rows.length}
        <div class="row">
          <span class="label">{ledger}</span>
          <span class="body">
            {#each rows as row (row)}
              <br />{row.assessment_status} · {row.role ?? row.related_kind ?? ""}
            {/each}
          </span>
        </div>
      {/if}
    {:else}
      <p class="note">no advisory rows</p>
    {/each}
  </div>
  <p class="note">{dossier.advisory_note}</p>
</section>

<section>
  <h3>claims by question</h3>
  <p class="line">
    {#each Object.entries(dossier.claims_by_question) as [qid, count] (qid)}
      <span>{qid} {count}</span>
    {:else}
      none
    {/each}
  </p>
</section>

<style>
  .line {
    margin: 0.25rem 0;
  }
  .note {
    color: var(--muted);
    font-size: 0.85rem;
    margin: 0.25rem 0;
  }
  table {
    border-collapse: collapse;
  }
  th,
  td {
    border: 1px solid var(--border);
    padding: 0.2rem 0.5rem;
    text-align: left;
  }
  .log {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .row {
    display: grid;
    grid-template-columns: 12rem 1fr;
    gap: 0.75rem;
    align-items: baseline;
  }
  .label {
    font-weight: 600;
  }
  .mono {
    font-family: ui-monospace, Menlo, Consolas, monospace;
  }
</style>