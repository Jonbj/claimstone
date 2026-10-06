<script lang="ts">
  // Index: the /projects list at once, then each selector's /summary in parallel.
  // S4 ships the scaffold: the full lazy index with per-selector summaries is S5.
  import { api } from "$lib/api";
  import ErrorState from "$lib/components/ErrorState.svelte";
  import Pending from "$lib/components/Pending.svelte";

  let projects = $state<Awaited<ReturnType<typeof api.projects>> | null>(null);
  let error = $state<Error | null>(null);

  $effect(() => {
    api
      .projects()
      .then((p) => (projects = p))
      .catch((e: Error) => (error = e));
  });
</script>

<h1>Projects</h1>
{#if error}
  <ErrorState error={error} />
{:else if projects === null}
  <Pending />
{:else}
  <ul>
    {#each projects.projects as project (project.name)}
      <li><a href={`/p/${encodeURIComponent(project.name)}`}>{project.name}</a></li>
    {/each}
  </ul>
{/if}