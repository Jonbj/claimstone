<script lang="ts">
  // The "computing…" state: a fetch that has not answered yet (§3.2). A zero is never
  // shown for an unknown (§4.2 rule 1).
  let { label = "computing…" }: { label?: string } = $props();
</script>

<span class="pending" role="status">{label}</span>

<style>
  .pending {
    color: var(--pending);
    font-style: italic;
    font-size: 0.8rem;
  }
</style>