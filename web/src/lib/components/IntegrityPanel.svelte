<script lang="ts">
  // Integrity (§4.1): can these numbers be trusted now. Every state is a named chip
  // with its word (§4.2 rule 7); a null is a dash, never zero (rule 1).
  import Chip from "./Chip.svelte";

  export type IntegrityData = {
    config: { state: string; error: string | null };
    registry: { state: string; error: string | null };
    ledger_repairs: number;
    orphans: number | null;
    invalid_flows: string[];
    instruments: string[];
    code: { revision: string | null; dirty: boolean | null; grobid_image: string };
    ledgers: Record<string, { rows: number; torn_tail: boolean; error: string | null }>;
    [k: string]: unknown;
  };

  let { integrity }: { integrity: IntegrityData } = $props();
</script>

<section>
  <h3>integrity — can these numbers be trusted now</h3>
  <p class="line"><b>config</b> <Chip text={integrity.config.state} />
    {#if integrity.config.error}<span class="note">{integrity.config.error}</span>{/if}</p>
  <p class="line"><b>registry</b> <Chip text={integrity.registry.state} />
    {#if integrity.registry.error}<span class="note">{integrity.registry.error}</span>{/if}</p>
  <p class="line"><b>ledger repairs</b> {integrity.ledger_repairs}</p>
  <p class="line"><b>orphans</b>
    {#if integrity.orphans === null}<span title="not knowable">—</span>{:else}{integrity.orphans}{/if}</p>
  {#each integrity.invalid_flows as fid (fid)}
    <p class="line"><b>invalid flow row</b> <Chip text="id is not the hash of its binding" />
      <span class="mono">{fid.slice(0, 16)}</span></p>
  {/each}
  <p class="line"><b>instruments</b>
    {#if integrity.instruments.length}
      <Chip text="NOT acknowledged" />
      {#each integrity.instruments as problem (problem)}
        <br /><span class="note">{problem}</span>
      {/each}
    {:else}
      <Chip text="acknowledged" />
    {/if}</p>
  <p class="line"><b>code</b> {(integrity.code.revision ?? "unknown").slice(0, 12)}
    {#if integrity.code.dirty}· dirty{/if}
    · grobid {(integrity.code.grobid_image ?? "").slice(0, 40)}</p>
  {#each Object.entries(integrity.ledgers).toSorted(([a], [b]) => a.localeCompare(b)) as [name, entry] (name)}
    <p class="line">
      <span class="mono">{name}</span> · {entry.rows} rows
      {#if entry.torn_tail}· <Chip text="torn tail" />{/if}
      {#if entry.error}· <Chip text={entry.error} />{/if}
    </p>
  {/each}
</section>

<style>
  .line {
    margin: 0.25rem 0;
  }
  .note {
    color: var(--muted);
    font-size: 0.85rem;
  }
  .mono {
    font-family: ui-monospace, Menlo, Consolas, monospace;
  }
</style>