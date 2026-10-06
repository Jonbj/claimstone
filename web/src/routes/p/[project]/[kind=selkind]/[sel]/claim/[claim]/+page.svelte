<script lang="ts">
  // The lineage page (§4.1): invariant 1 end to end. Polls every 3 s (§4.2 rule 8).
  import { page } from "$app/state";
  import { api } from "$lib/api";
  import type { Lineage } from "$lib/api-types";
  import ErrorState from "$lib/components/ErrorState.svelte";
  import LineageView from "$lib/components/Lineage.svelte";
  import Pending from "$lib/components/Pending.svelte";
  import { startPolling } from "$lib/poll";

  const project = $derived(decodeURIComponent(page.params.project));
  const kind = $derived(page.params.kind as "f" | "u");
  const sel = $derived(decodeURIComponent(page.params.sel));
  const claim = $derived(decodeURIComponent(page.params.claim));

  let lineage = $state<Lineage | null>(null);
  let error = $state<Error | null>(null);

  function load() {
    error = null;
    api
      .claim(project, kind, sel, claim)
      .then((l) => (lineage = l))
      .catch((e: Error) => (error = e));
  }

  $effect(() => {
    load();
    const stop = startPolling(() => api.poll(project), load);
    return stop;
  });
</script>

<h1>claim {claim}</h1>

{#if error}
  <ErrorState error={error} />
{:else if lineage === null}
  <Pending label="loading claim…" />
{:else}
  <LineageView lineage={lineage} />
{/if}