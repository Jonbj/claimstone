<script lang="ts">
  // The question matrix (§4.1): registry order, per-class counts before the total
  // (§4.2 rule 2), the five verdicts plus dashed engine states (rule 3), every display
  // text verbatim (rule 5). An operator filter is the only allowed sorting (rule 6);
  // none is offered here — the server order is the order.
  import Chip from "./Chip.svelte";
  import Fraction from "./Fraction.svelte";

  export type MatrixRow = {
    id: string;
    kind: string;
    text: string;
    claims_by_class: Record<string, number>;
    claims: number | null;
    coverage: { sources: number | null; examined: number | null };
    direction_count: Record<string, unknown>;
    direction_count_note: string;
    gate_rejected_total: number;
    awaiting_review: number;
    state: string | null;
    provisional: boolean;
    blocking: string[];
    verdict: string | null;
    verdict_stale: boolean;
    unavailable: string;
    operational_not_applicable: boolean;
    note: string | null;
    [k: string]: unknown;
  };

  let {
    rows,
    base = "",
  }: { rows: MatrixRow[]; base?: string } = $props();
</script>

<section>
  <h3>the questions — registry order</h3>
  <table>
    <thead>
      <tr>
        <th>id</th><th>question</th><th>kind</th><th>claims per class</th>
        <th>coverage<br />speaking / examined</th><th>direction count</th>
        <th>gate rejected</th><th>awaiting review</th><th>verdict</th>
      </tr>
    </thead>
    <tbody>
      {#each rows as row (row.id)}
        <tr data-question-id={row.id}>
          <td class="mono">
            {#if base}
              <a href={`${base}/q/${encodeURIComponent(row.id)}`}>{row.id}</a>
            {:else}{row.id}{/if}
          </td>
          <td>{row.text}</td>
          <td>{row.kind}</td>
          <td>
            {#each Object.entries(row.claims_by_class) as [name, count] (name)}
              <span class="by-class" data-class={name}>{name} {count}</span>
            {:else}
              <span title="not knowable">—</span>
            {/each}
            <span class="muted">→ <Fraction numerator={row.claims} /> total</span>
          </td>
          <td>
            {#if row.coverage.sources === null}
              <span title="not knowable">— / —</span>
            {:else}
              {row.coverage.sources} / {row.coverage.examined}
            {/if}
          </td>
          <td>
            {#if Object.keys(row.direction_count).length}
              {#each Object.entries(row.direction_count) as [name, count] (name)}
                <span>{name} {String(count)}</span>
              {/each}
              <span class="muted">({row.direction_count_note})</span>
            {:else}
              <span title="not knowable">—</span>
            {/if}
          </td>
          <td>{row.gate_rejected_total}</td>
          <td>{row.awaiting_review}</td>
          <td>
            {#if row.operational_not_applicable}
              <Chip text="LITERATURE_VERDICT_NOT_APPLICABLE" /><br />
              <span class="muted">kind operational: no verdict</span>
            {:else if row.verdict}
              <Chip text={row.verdict} />
              {#if row.verdict_stale}<Chip text="stale" />{/if}
            {:else if row.state === "NO_VERIFIED_CLAIM"}
              <Chip text="NO_VERIFIED_CLAIM" />
            {:else if row.state}
              <Chip text={row.state} />
            {:else}
              <span class="chip dashed" title="not knowable">— no verdict</span>
            {/if}
            {#if row.provisional}
              <br /><Chip text={row.blocking.join(", ") || "provisional"} />
            {/if}
            {#if row.unavailable}
              <br /><span class="muted">historical — {row.unavailable}</span>
            {/if}
            {#if row.note}
              <br /><span class="muted">{row.note}</span>
            {/if}
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
  <p class="note">
    Claims are counted per class before they are pooled (invariant 6).
    NO_VERIFIED_CLAIM is the engine's categorical outcome and never a verdict: only a
    person can say <q>never asked</q>. No pooling, no R: a person reads the profile and signs.
  </p>
</section>

<style>
  table {
    border-collapse: collapse;
  }
  th,
  td {
    border: 1px solid var(--border);
    padding: 0.2rem 0.5rem;
    text-align: left;
    vertical-align: top;
  }
  .mono {
    font-family: ui-monospace, Menlo, Consolas, monospace;
  }
  .muted {
    color: var(--muted);
    font-size: 0.8rem;
  }
  .by-class {
    margin-right: 0.4rem;
  }
  .chip {
    display: inline-block;
    border: 1px dashed var(--border);
    border-radius: 0.5rem;
    padding: 0.05rem 0.45rem;
    font-size: 0.75rem;
    color: var(--muted);
  }
  .note {
    color: var(--muted);
    font-size: 0.85rem;
  }
</style>