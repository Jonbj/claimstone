<script lang="ts">
  // The source dossier page (§4.1). Polls every 3 s (§4.2 rule 8).
  import { page } from "$app/state";
  import { api } from "$lib/api";
  import type { SourceDossier } from "$lib/api-types";
  import ErrorState from "$lib/components/ErrorState.svelte";
  import Pending from "$lib/components/Pending.svelte";
  import SourceDossierView from "$lib/components/SourceDossier.svelte";
  import { startPolling } from "$lib/poll";

  const project = $derived(decodeURIComponent(page.params.project));
  const kind = $derived(page.params.kind as "f" | "u");
  const sel = $derived(decodeURIComponent(page.params.sel));
  const keyParam = $derived(decodeURIComponent(page.params.key));

  let dossier = $state<SourceDossier | null>(null);
  let error = $state<Error | null>(null);

  function load() {
    error = null;
    api
      .source(project, kind, sel, keyParam)
      .then((d) => (dossier = d))
      .catch((e: Error) => (error = e));
  }

  $effect(() => {
    load();
    const stop = startPolling(() => api.poll(project), load);
    return stop;
  });
</script>

<h1>source {keyParam}</h1>

{#if error}
  <ErrorState error={error} />
{:else if dossier === null}
  <Pending label="loading source…" />
{:else}
  <SourceDossierView dossier={dossier} />
{/if}