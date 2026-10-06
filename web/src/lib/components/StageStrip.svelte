<script lang="ts">
  // The pipeline, one node per stage (§4.1). A fraction always shows its denominator; a
  // dash means not knowable in principle, never zero (§4.2 rule 1). `outputs: null` is
  // "—" and the progress meter keeps its label.
  import Fraction from "./Fraction.svelte";

  type Stage = {
    name: string;
    outputs: number | null;
    inputs: number | null;
    rejected: number | null;
    progress: { done: number; total: number | null; label: string } | null;
    detail: string | null;
    last_write: string | null;
    implemented: boolean;
    [k: string]: unknown;
  };

  let { stages = [] }: { stages?: Stage[] } = $props();
</script>

<div class="strip">
  {#each stages as stage (stage.name)}
    <div class="node">
      <div class="name">{stage.name}</div>
      <div class="line">
        <Fraction numerator={stage.outputs} />
        out{#if stage.rejected !== null}<span class="sep"> ·</span>
          <span>{stage.rejected} rejected</span>{/if}
      </div>
      {#if stage.progress}
        {@const pct = stage.progress.total ? (100 * stage.progress.done) / stage.progress.total : 0}
        <div class="meter"><i style="width:{pct.toFixed(1)}%"></i></div>
        <div class="line">
          <Fraction numerator={stage.progress.done} denominator={stage.progress.total ?? null}
                    title={stage.progress.label} />
          <span class="muted">{stage.progress.label}</span>
        </div>
      {/if}
      {#if stage.detail}<div class="muted detail">{stage.detail}</div>{/if}
    </div>
  {/each}
</div>

<style>
  .strip {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
  }
  .node {
    border: 1px solid var(--border);
    border-radius: 0.5rem;
    padding: 0.5rem 0.75rem;
    min-width: 9rem;
    flex: 1 1 9rem;
  }
  .name {
    font-weight: 600;
  }
  .line {
    display: flex;
    gap: 0.25rem;
    align-items: baseline;
  }
  .meter {
    height: 0.3rem;
    border-radius: 0.2rem;
    background: var(--chip-bg);
    overflow: hidden;
    margin: 0.2rem 0;
  }
  .meter i {
    display: block;
    height: 100%;
    background: var(--accent);
  }
  .muted {
    color: var(--muted);
    font-size: 0.8rem;
  }
  .detail {
    margin-top: 0.2rem;
  }
</style>