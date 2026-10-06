<script lang="ts">
  // The flow/legacy overview (§4.1): binding banner, scoped stage strip, floor panel,
  // question matrix, this scope's inbox, scoped activity. Polls every 3 s (rule 8).
  import { page } from "$app/state";
  import { api } from "$lib/api";
  import type { Overview } from "$lib/api-types";
  import Chip from "$lib/components/Chip.svelte";
  import ErrorState from "$lib/components/ErrorState.svelte";
  import FloorPanel from "$lib/components/FloorPanel.svelte";
  import InboxCards from "$lib/components/InboxCards.svelte";
  import Pending from "$lib/components/Pending.svelte";
  import QuestionMatrix from "$lib/components/QuestionMatrix.svelte";
  import StageStrip from "$lib/components/StageStrip.svelte";
  import { startPolling } from "$lib/poll";

  const project = $derived(decodeURIComponent(page.params.project));
  const kind = $derived(page.params.kind as "f" | "u");
  const sel = $derived(decodeURIComponent(page.params.sel));

  let overview = $state<Overview | null>(null);
  let error = $state<Error | null>(null);

  function load() {
    error = null;
    api
      .overview(project, kind, sel)
      .then((o) => (overview = o))
      .catch((e: Error) => (error = e));
  }

  $effect(() => {
    load();
    const stop = startPolling(() => api.poll(project), load);
    return stop;
  });

  const base = $derived(
    `/p/${encodeURIComponent(project)}/${kind}/${encodeURIComponent(sel)}`,
  );
</script>

{#if error}
  <ErrorState error={error} />
{:else if overview === null}
  <Pending label="computing…" />
{:else}
  <h1>{overview.selector_label}{#if overview.legacy} — legacy{/if}</h1>

  {#if overview.legacy}
    <section>
      <h2>binding</h2>
      <p><Chip text="legacy: protocol not verified" /></p>
      <p class="note">{overview.selector_label} has data and no flow: nothing binds it to
        the protocol it ran under. `claimstone flow create` binds one; until then its
        figures are shown, not certified.</p>
    </section>
  {:else if overview.binding_state}
    <section>
      <h2>binding</h2>
      <p><Chip text={overview.binding_state.state} />
        {#if overview.binding_state.differences.length}
          — differs in: {overview.binding_state.differences.join(", ")}
        {:else}
          — no differences
        {/if}</p>
      <p class="note">The binding is compared against the live project and never supplies
        a value to a computation (review F4).</p>
      {#if overview.flow?.bound_after_data}
        <p class="note">bound after data existed: rows written before binding are not
          verified against this protocol</p>
      {/if}
    </section>
  {/if}

  {#each overview.errors as err (err)}
    <section>
      <h2>ledger integrity</h2>
      <p><Chip text={err} /></p>
      <p class="note">Figures that depend on a damaged ledger are withheld, not zero.</p>
    </section>
  {/each}

  {#if overview.unavailable}
    <section>
      <h2>corpus</h2>
      <p><Chip text={overview.unavailable} /></p>
    </section>
  {/if}

  <section>
    <h2>the pipeline</h2>
    <StageStrip stages={overview.state.stages as never} />
    <p class="note">A fraction always shows its denominator; a dash means not knowable in
      principle, never zero.</p>
  </section>

  <FloorPanel panel={overview.floor_panel as never} />

  <QuestionMatrix rows={overview.questions.rows as never} {base} />

  <section>
    <h2>inbox — what a person can do next</h2>
    <InboxCards cards={overview.inbox as never} />
    <p class="note">Commands are text to copy, never buttons: no route here starts work.
      Cards sort by category then subject, never by expected result (review F13).</p>
  </section>

  <section>
    <h2>activity — this scope only</h2>
    {#each overview.activity as row (row)}
      <p class="line">
        <span class="mono muted">{row.when}</span>
        <span>{row.stage}</span>
        <span class="muted">{JSON.stringify(row.row).slice(0, 220)}</span>
      </p>
    {:else}
      <p class="note">no rows in this scope</p>
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