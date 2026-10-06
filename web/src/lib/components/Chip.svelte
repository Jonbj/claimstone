<script lang="ts">
  import { word } from "$lib/vocabulary";
  let { text, title = "" }: { text: string; title?: string } = $props();
  const w = $derived(word(text));
</script>

<!-- §4.2 rule 7: colour never carries meaning alone — the word is always there. -->
<span class="chip {w.cls}" class:dashed={w.dashed} title={title || text}>{text}</span>

<style>
  .chip {
    display: inline-block;
    border-radius: 0.5rem;
    padding: 0.05rem 0.45rem;
    font-size: 0.75rem;
    border: 1px solid var(--border);
    background: var(--chip-bg);
    white-space: nowrap;
  }
  .dashed {
    border-style: dashed;
  }
  .v-supported {
    border-color: #2e7d32;
    color: #2e7d32;
  }
  .v-contradicted {
    border-color: #c62828;
    color: #c62828;
  }
  .v-contested {
    border-color: #ef6c00;
    color: #ef6c00;
  }
  .v-unanswered {
    border-color: #6d4c41;
    color: #6d4c41;
  }
  .v-never-asked {
    border-color: #455a64;
    color: #455a64;
  }
  .v-engine {
    color: var(--muted);
  }
  .v-unknown {
    color: var(--muted);
  }
  :root[data-theme="dark"] .v-supported {
    color: #81c784;
    border-color: #81c784;
  }
  :root[data-theme="dark"] .v-contradicted {
    color: #ef9a9a;
    border-color: #ef9a9a;
  }
  :root[data-theme="dark"] .v-contested {
    color: #ffcc80;
    border-color: #ffcc80;
  }
  :root[data-theme="dark"] .v-unanswered {
    color: #bcaaa4;
    border-color: #bcaaa4;
  }
  :root[data-theme="dark"] .v-never-asked {
    color: #90a4ae;
    border-color: #90a4ae;
  }
</style>