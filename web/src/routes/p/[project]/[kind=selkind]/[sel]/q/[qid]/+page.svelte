<script lang="ts">
  // One question (§4.1): the profile, its results with claim links, and any recorded
  // verdict. `CommandBlock` shows the adjudicate command with its placeholders — a
  // person reads the profile and signs; an agent does not (§4.2 rule 4). Polls (rule 8).
  import { page } from "$app/state";
  import { api } from "$lib/api";
  import type { QuestionDetail } from "$lib/api-types";
  import Chip from "$lib/components/Chip.svelte";
  import CommandBlock from "$lib/components/CommandBlock.svelte";
  import ErrorState from "$lib/components/ErrorState.svelte";
  import Pending from "$lib/components/Pending.svelte";
  import { startPolling } from "$lib/poll";

  const project = $derived(decodeURIComponent(page.params.project));
  const kind = $derived(page.params.kind as "f" | "u");
  const sel = $derived(decodeURIComponent(page.params.sel));
  const qid = $derived(decodeURIComponent(page.params.qid));

  let detail = $state<QuestionDetail | null>(null);
  let error = $state<Error | null>(null);

  function load() {
    error = null;
    api
      .question(project, kind, sel, qid)
      .then((d) => (detail = d))
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
  const fields = $derived(detail?.profile_fields ?? null);

  // The adjudicate command, exactly as the inbox card carries it: placeholders only,
  // never a runnable button (§4.2 rule 4). The profile hash is the one `adjudicate`
  // will accept; absent means the profile is not built yet and there is nothing to sign.
  const adjudicateCommand = $derived.by(() => {
    if (!detail || !fields?.profile_sha256) return null;
    const round = detail.selector.round ? ` --round ${detail.selector.round}` : "";
    const manifest = detail.selector.manifest_only ? " --manifest-only" : "";
    return `claimstone adjudicate <workspace>/${project} ${detail.id}${round}${manifest}`
      + ` --profile-sha256 ${fields.profile_sha256}`
      + " --verdict <ONE_OF_FIVE> --rationale-file <file> --by <name>";
  });
</script>

{#if error}
  <ErrorState error={error} />
{:else if detail === null}
  <Pending label="loading question…" />
{:else}
  <h1>{detail.id}: {detail.text}</h1>

  <section>
    <h2>profile</h2>
    {#if fields}
      <p class="line">state {fields.state ?? "—"}{#if fields.provisional} · provisional{/if}</p>
      {#if fields.blocking.length}
        <p class="line">blocking: {fields.blocking.join(", ")}</p>
      {/if}
      <p class="line">
        coverage {fields.coverage.sources ?? "—"} / {fields.coverage.examined ?? "—"} examined
        · direction count
        {Object.entries(fields.direction_count).map(([k, v]) => `${k} ${String(v)}`).join(" ") || "—"}
        ({fields.direction_count_note})
      </p>
      <p class="line">
        gate rejected {JSON.stringify(fields.gate_rejected)}
        · reviewed, not usable {JSON.stringify(fields.reviewed_not_usable)}
        · awaiting review {fields.awaiting_review}
        · linkage {String(fields.linkage)}
      </p>
      {#if fields.extraction}
        <p class="line">extraction {JSON.stringify(fields.extraction)}</p>
      {/if}
      <p class="line mono">profile {fields.profile_sha256 ?? "—"}</p>
      {#if fields.stored_profile_stale}
        <p><Chip text="stored profile differs; showing current evidence, run synthesize before signing" /></p>
      {/if}
      {#if fields.unavailable}
        <p><Chip text={fields.unavailable} /> <span class="note">— profiles shown are historical</span></p>
      {/if}
    {:else}
      <p class="note">no profile for this scope: run synthesize</p>
    {/if}
  </section>

  <section>
    <h2>results</h2>
    <table>
      <thead>
        <tr><th>claim</th><th>source</th><th>stance</th><th>as written</th><th>sample</th></tr>
      </thead>
      <tbody>
        {#each detail.results as row (String(row.claim_id))}
          <tr>
            <td class="mono">
              <a href={`${base}/claim/${encodeURIComponent(String(row.claim_id))}`}>
                {String(row.claim_id).slice(0, 16)}
              </a>
            </td>
            <td>{String(row.source_id)}</td>
            <td>{String(row.stance)}</td>
            <td>{String(row.estimate_as_written ?? row.contrast_as_written ?? "")}</td>
            <td>{String(row.sample ?? "")}</td>
          </tr>
        {:else}
          <tr><td colspan="5">no results for this scope</td></tr>
        {/each}
      </tbody>
    </table>
  </section>

  <section>
    <h2>verdict</h2>
    {#if detail.operational_not_applicable}
      <p><Chip text="LITERATURE_VERDICT_NOT_APPLICABLE" /></p>
      <p class="note">kind operational: no verdict</p>
    {:else if detail.verdict}
      <p>
        <Chip text={detail.verdict.verdict} />
        · by {detail.verdict.adjudicated_by}
        · {detail.verdict.adjudicated_at}
        {#if detail.verdict_stale}<Chip text="stale" />{/if}
      </p>
    {:else}
      <p class="chip dashed">— no verdict recorded</p>
    {/if}
    {#if adjudicateCommand}
      <CommandBlock command={adjudicateCommand}
                    note="a person reads the profile and signs; an agent does not" />
    {/if}
  </section>
{/if}

<style>
  .line {
    margin: 0.25rem 0;
  }
  .note {
    color: var(--muted);
    font-size: 0.85rem;
  }
  .mono {
    font-family: ui-monospace, Menlo, Consolas, monospace;
    font-size: 0.85rem;
  }
  table {
    border-collapse: collapse;
  }
  th,
  td {
    border: 1px solid var(--border);
    padding: 0.2rem 0.5rem;
    text-align: left;
  }
  .chip {
    display: inline-block;
    border: 1px dashed var(--border);
    border-radius: 0.5rem;
    padding: 0.05rem 0.45rem;
    font-size: 0.75rem;
    color: var(--muted);
  }
</style>