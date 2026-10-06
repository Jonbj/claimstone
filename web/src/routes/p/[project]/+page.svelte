<script lang="ts">
  // The project page (§4.1): integrity, flows, unbound (legacy) selectors, whole-project
  // activity. Polls `/projects/{p}/poll` every 3 s (§4.2 rule 8): when the ledgers
  // signature moves and the tab is visible, the whole view's data is fetched again —
  // no full reload.
  import { page } from "$app/state";
  import { api } from "$lib/api";
  import type { Activity, Integrity, Projects } from "$lib/api-types";
  import ErrorState from "$lib/components/ErrorState.svelte";
  import IntegrityPanel from "$lib/components/IntegrityPanel.svelte";
  import Pending from "$lib/components/Pending.svelte";
  import Chip from "$lib/components/Chip.svelte";
  import { startPolling } from "$lib/poll";

  const project = $derived(decodeURIComponent(page.params.project));

  let integrity = $state<Integrity | null>(null);
  let index = $state<Projects | null>(null);
  let activity = $state<Activity | null>(null);
  let error = $state<Error | null>(null);

  function load() {
    error = null;
    Promise.all([
      api.integrity(project),
      api.projects(),
      api.activity(project, 50),
    ])
      .then(([i, p, a]) => {
        integrity = i;
        index = p;
        activity = a;
      })
      .catch((e: Error) => (error = e));
  }

  $effect(() => {
    load();
    // Rule 8: a project-scoped page re-reads the ledgers' signature every 3 s.
    const stop = startPolling(() => api.poll(project), load);
    return stop;
  });

  const card = $derived(
    index?.projects.find((p) => p.name === project) ?? null,
  );
  const flows = $derived(card?.flows ?? []);
  const unbound = $derived(card?.unbound_selectors ?? []);
</script>

<h1>{project}</h1>

{#if error}
  <ErrorState error={error} />
{:else if integrity === null || index === null || activity === null}
  <Pending label="loading project…" />
{:else}
  <IntegrityPanel integrity={integrity} />

  <section>
    <h2>flows</h2>
    {#each flows as flow (flow.flow_id)}
      <p class="line">
        <a class="mono" href={`/p/${encodeURIComponent(project)}/f/${encodeURIComponent(flow.flow_id)}`}>
          flow {flow.flow_id.slice(0, 12)}
        </a>
        · {flow.selector_label}
        · <Chip text={flow.binding_state} />
        {#if flow.title}· {flow.title}{/if}
        {#if flow.bound_after_data}
          · <span class="note">bound after data existed: rows written before binding are
            not verified against this protocol</span>
        {/if}
      </p>
    {:else}
      <p class="note">no flows; rounds with candidates are legacy</p>
    {/each}
  </section>

  <section>
    <h2>legacy rounds</h2>
    {#each unbound as entry (entry.slug)}
      <p class="line">
        <a class="mono" href={`/p/${encodeURIComponent(project)}/u/${encodeURIComponent(entry.slug)}`}>
          {entry.label}
        </a>
        · <Chip text="protocol not verified" />
      </p>
    {:else}
      <p class="note">none</p>
    {/each}
  </section>

  <section>
    <h2>activity — whole project</h2>
    {#each activity.activity as row (row)}
      <p class="line">
        <span class="mono muted">{row.when}</span>
        <span>{row.stage}</span>
        <span class="muted">{JSON.stringify(row.row).slice(0, 220)}</span>
      </p>
    {:else}
      <p class="note">no rows yet</p>
    {/each}
    <p class="note">Scoped rows carry their own timestamps; rows without one have no
      trustworthy time and are not shown.</p>
  </section>
{/if}

<style>
  .line {
    margin: 0.25rem 0;
    display: flex;
    gap: 0.75rem;
    align-items: baseline;
    flex-wrap: wrap;
  }
  .note {
    color: var(--muted);
    font-size: 0.85rem;
  }
  .muted {
    color: var(--muted);
  }
  .mono {
    font-family: ui-monospace, Menlo, Consolas, monospace;
    font-size: 0.85rem;
  }
</style>