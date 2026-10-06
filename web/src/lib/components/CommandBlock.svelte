<script lang="ts">
  // §4.2 rule 4: no verdict input of any kind. This shows a CLI command with its
  // placeholders and a copy button; it never executes anything.
  let { command, note = "" }: { command: string; note?: string } = $props();

  let copied = $state(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(command);
      copied = true;
      setTimeout(() => (copied = false), 2000);
    } catch {
      // clipboard permission denied: the text stays selectable, nothing executes
      copied = false;
    }
  }
</script>

<div class="command-block">
  {#if note}<p class="note">{note}</p>{/if}
  <div class="row">
    <code>{command}</code>
    <button type="button" onclick={copy} aria-label="copy command to clipboard">
      {copied ? "copied" : "copy"}
    </button>
  </div>
</div>

<style>
  .command-block {
    margin: 0.5rem 0;
  }
  .row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }
  code {
    display: block;
    flex: 1;
    background: var(--code-bg);
    border: 1px solid var(--border);
    border-radius: 0.4rem;
    padding: 0.4rem 0.6rem;
    overflow-x: auto;
    white-space: pre;
    font-size: 0.8rem;
  }
  button {
    border: 1px solid var(--border);
    border-radius: 0.4rem;
    background: var(--chip-bg);
    color: var(--fg);
    padding: 0.3rem 0.7rem;
    cursor: pointer;
    font-size: 0.8rem;
  }
  .note {
    color: var(--muted);
    font-size: 0.8rem;
    margin: 0 0 0.25rem;
  }
</style>