<script lang="ts">
  // The floor panel (§4.1): overall status, per-class buckets, then the `sentences` and
  // `disclosure` display texts, verbatim (§4.2 rule 5). Colour never carries meaning
  // alone (rule 7): every status word is present, and a null is a dash, never zero.
  import Chip from "./Chip.svelte";
  import Fraction from "./Fraction.svelte";

  type Bucket = {
    basis_count: number | null;
    found: number | null;
    needed: number | null;
    floor: number;
    meets_floor: boolean;
    [k: string]: unknown;
  };
  export type FloorPanelData = {
    overall: {
      basis: string;
      basis_count: number | null;
      found: number | null;
      rate: number | null;
      floor: number;
      floor_version: number;
      floor_set_at: string;
      status: string;
      final: boolean;
      blocking: string[];
      [k: string]: unknown;
    };
    by_class: Record<string, Bucket>;
    sentences: string[];
    disclosure: string;
    [k: string]: unknown;
  } | null;

  let { panel }: { panel: FloorPanelData } = $props();
</script>

{#if panel}
  <section>
    <h3>floor and deficit</h3>
    <p class="line">
      {panel.overall.basis}
      <Fraction numerator={panel.overall.basis_count} /> /
      <Fraction numerator={panel.overall.found} /> =
      <strong>{panel.overall.rate === null ? "—" : panel.overall.rate.toFixed(2)}</strong>
      · floor {panel.overall.floor}
      · v{panel.overall.floor_version}
      · {panel.overall.floor_set_at}
      · <Chip text={panel.overall.status} />
      {#if panel.overall.blocking.length}
        <span class="muted">not final: {panel.overall.blocking.join(", ")}</span>
      {/if}
    </p>
    {#if Object.keys(panel.by_class).length}
      <table>
        <thead>
          <tr><th>class</th><th>basis / found</th><th>needed</th><th>floor</th><th></th></tr>
        </thead>
        <tbody>
          {#each Object.entries(panel.by_class) as [name, bucket] (name)}
            <tr>
              <td class="mono">{name}</td>
              <td><Fraction numerator={bucket.basis_count} /> / <Fraction numerator={bucket.found} /></td>
              <td><Fraction numerator={bucket.needed} /></td>
              <td>{bucket.floor}</td>
              <td><Chip text={bucket.meets_floor ? "meets" : "below"} /></td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
    {#each panel.sentences as sentence (sentence)}
      <p class="note">{sentence}</p>
    {/each}
    <p class="note">{panel.disclosure}</p>
  </section>
{/if}

<style>
  .line {
    margin: 0.25rem 0;
  }
  .note {
    color: var(--muted);
    font-size: 0.85rem;
    margin: 0.25rem 0;
  }
  .muted {
    color: var(--muted);
    font-size: 0.85rem;
  }
  table {
    border-collapse: collapse;
    margin: 0.5rem 0;
  }
  th,
  td {
    border: 1px solid var(--border);
    padding: 0.2rem 0.5rem;
    text-align: left;
  }
  .mono {
    font-family: ui-monospace, Menlo, Consolas, monospace;
  }
</style>