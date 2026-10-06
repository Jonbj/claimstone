<script lang="ts">
  // The inbox cards (§4.1): server order preserved (§4.2 rule 6) — this component never
  // sorts, ranks or filters; `cause`, `note` and `command` are display text rendered
  // verbatim (rule 5). A command is text to copy, never a button that runs anything
  // (rule 4) — the copy affordance is CommandBlock's, and it never executes.
  import CommandBlock from "./CommandBlock.svelte";

  export type InboxCard = {
    category: string;
    scope: string;
    subject: string;
    cause: string;
    command: string | null;
    note: string;
    [k: string]: unknown;
  };

  let { cards }: { cards: InboxCard[] } = $props();
</script>

<div class="cards">
  {#each cards as card, index (index)}
    <div class="card" data-card-index={index}>
      <span class="category">{card.category}</span>
      <span class="scope mono">{card.scope}</span>
      <div class="body">
        <strong>{card.subject}</strong> — {card.cause}
        {#if card.command}
          <CommandBlock command={card.command} />
        {/if}
        {#if card.note}
          <p class="note">{card.note}</p>
        {/if}
      </div>
    </div>
  {:else}
    <p class="note">nothing open in this scope</p>
  {/each}
</div>

<style>
  .cards {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .card {
    display: grid;
    grid-template-columns: 8rem 12rem 1fr;
    gap: 0.75rem;
    border: 1px solid var(--border);
    border-radius: 0.5rem;
    padding: 0.4rem 0.6rem;
    align-items: baseline;
  }
  .category {
    font-weight: 600;
  }
  .mono {
    font-family: ui-monospace, Menlo, Consolas, monospace;
    font-size: 0.8rem;
  }
  .body {
    min-width: 0;
  }
  .note {
    color: var(--muted);
    font-size: 0.8rem;
    margin: 0.25rem 0 0;
  }
</style>