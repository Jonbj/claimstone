<script lang="ts">
  // §4.2 rule 1: no zero for an unknown. `null` renders "—" with the not-knowable
  // title; a number renders as a fraction. A pending fetch renders `Pending`
  // (the parent swaps this component out), never a zero.
  let {
    numerator,
    denominator = null,
    title = "not knowable",
  }: { numerator: number | null; denominator?: number | null; title?: string } = $props();

  const text = $derived(numerator === null ? "—" : String(numerator));
  const isUnknown = $derived(numerator === null);
</script>

<span class={isUnknown ? "fraction unknown" : "fraction"} title={isUnknown ? title : undefined}>
  {text}{#if !isUnknown && denominator !== null}<span class="denominator">/{denominator}</span>{/if}
</span>

<style>
  .fraction {
    font-variant-numeric: tabular-nums;
  }
  .unknown {
    color: var(--muted);
    cursor: help;
  }
  .denominator {
    color: var(--muted);
  }
</style>