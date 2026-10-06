<script lang="ts">
  // Index (§4.1): `/projects` at once — the cheap route with no `compute()` — then each
  // selector's `/summary` in parallel, filling the cards as they arrive (§3.2). A card's
  // numbers show `Pending` while computing, never a zero (§4.2 rule 1). Server order
  // everywhere (rule 6): the projects list and each flow/unbound list are the API's.
  import { api, ApiError } from "$lib/api";
  import type { Projects, Summary } from "$lib/api-types";
  import Chip from "$lib/components/Chip.svelte";
  import ErrorState from "$lib/components/ErrorState.svelte";
  import Pending from "$lib/components/Pending.svelte";

  type SelectorRef =
    | { kind: "f"; sel: string; label: string; note: string }
    | { kind: "u"; sel: string; label: string; note: string };

  let projects = $state<Projects | null>(null);
  let error = $state<ApiError | Error | null>(null);
  // One summary per (project, selector) — a null value means "computing…".
  let summaries = $state<Record<string, Summary | ApiError | Error>>({});

  function key(project: string, kind: string, sel: string): string {
    return `${project}|${kind}|${sel}`;
  }

  $effect(() => {
    api
      .projects()
      .then((p) => {
        projects = p;
        // Every selector of every project, in parallel — the request that fixes I4.
        for (const project of p.projects) {
          if (project.config !== "OK") continue;
          for (const flow of project.flows ?? []) {
            const k = key(project.name, "f", flow.flow_id);
            api
              .summary(project.name, "f", flow.flow_id)
              .then((s) => (summaries[k] = s))
              .catch((e: ApiError | Error) => (summaries[k] = e));
          }
          for (const unbound of project.unbound_selectors ?? []) {
            const k = key(project.name, "u", unbound.slug);
            api
              .summary(project.name, "u", unbound.slug)
              .then((s) => (summaries[k] = s))
              .catch((e: ApiError | Error) => (summaries[k] = e));
          }
        }
      })
      .catch((e: ApiError | Error) => (error = e));
  });

  function selectorRef(
    project: string,
    kind: "f" | "u",
    sel: string,
    label: string,
  ): SelectorRef {
    const note =
      kind === "u"
        ? "legacy: data and no flow — protocol not verified"
        : "";
    return { kind, sel, label, note };
  }

  function verdictText(summary: Summary | ApiError | Error | undefined): string {
    if (!(summary instanceof Object) || summary instanceof ApiError
        || summary instanceof Error) return "";
    const counts = (summary as Summary).verdicts;
    if (!counts) return "";
    return ` · ${counts.awaiting_adjudication} awaiting a person · ${counts.adjudicated} signed`
      + (counts.stale ? ` · ${counts.stale} stale` : "");
  }
</script>

<h1>projects</h1>
<p class="note">
  One server, every project, all of it read-only. A round with candidates and no flow is
  legacy: protocol not verified.
</p>

{#if error}
  <ErrorState error={error} />
{:else if projects === null}
  <Pending label="loading projects…" />
{:else}
  {#each projects.projects as project (project.name)}
    <div class="project" data-project={project.name}>
      <h2>
        {#if project.config === "OK"}
          <a href={`/p/${encodeURIComponent(project.name)}`}>{project.name}</a>
        {:else}
          {project.name}
        {/if}
      </h2>
      {#if project.config !== "OK"}
        <p><Chip text="ConfigError" /> <span class="note">{project.config_error}</span></p>
      {:else}
        <p class="note">
          registry v{project.registry_version} · {project.registry_sha256}
        </p>
        {#if project.registry_drift}
          <p><Chip text="registry drift" /> <span class="note">{project.registry_drift}</span></p>
        {/if}
        {#if project.integrity_error}
          <p><Chip text="LEDGER_CORRUPT" />
            <span class="note">{project.integrity_error}</span></p>
        {/if}
        {#each project.flows ?? [] as flow (flow.flow_id)}
          {@const k = key(project.name, "f", flow.flow_id)}
          {@const ref = selectorRef(project.name, "f", flow.flow_id, flow.selector_label)}
          <p class="selector-line">
            flow
            <a class="mono" href={`/p/${encodeURIComponent(project.name)}/f/${encodeURIComponent(ref.sel)}`}>
              {ref.sel.slice(0, 12)}
            </a>
            · {ref.label}
            · {flow.binding_state}
            {#if flow.bound_after_data} · bound after data existed{/if}
            {#if flow.title} · {flow.title}{/if}
            {#if summaries[k] === undefined}
              · <Pending label="computing…" />
            {:else if summaries[k] instanceof ApiError || summaries[k] instanceof Error}
              · <span class="note" title={(summaries[k] as Error).message}>summary unavailable</span>
            {:else}
              {@const summary = summaries[k] as Summary}
              {#if summary.floor_status}· floor {summary.floor_status}{/if}
              {verdictText(summary)}
              {#if Object.keys(summary.inbox_counts).length}
                · inbox {Object.entries(summary.inbox_counts).map(([c, n]) => `${c} ${n}`).join(" · ")}
              {/if}
            {/if}
          </p>
        {/each}
        {#each project.unbound_selectors ?? [] as unbound (unbound.slug)}
          {@const k = key(project.name, "u", unbound.slug)}
          {@const ref = selectorRef(project.name, "u", unbound.slug, unbound.label)}
          <p class="selector-line">
            legacy
            <a class="mono" href={`/p/${encodeURIComponent(project.name)}/u/${encodeURIComponent(ref.sel)}`}>
              {ref.label}
            </a>
            · <Chip text="protocol not verified" />
            {#if summaries[k] === undefined}
              · <Pending label="computing…" />
            {:else if summaries[k] instanceof ApiError || summaries[k] instanceof Error}
              · <span class="note" title={(summaries[k] as Error).message}>summary unavailable</span>
            {:else}
              {@const summary = summaries[k] as Summary}
              {#if summary.floor_status}· floor {summary.floor_status}{/if}
              {verdictText(summary)}
            {/if}
          </p>
        {/each}
      {/if}
    </div>
  {/each}
{/if}

<style>
  .project {
    border: 1px solid var(--border);
    border-radius: 0.5rem;
    padding: 0.5rem 1rem;
    margin: 0.5rem 0;
  }
  h2 {
    margin: 0.25rem 0;
  }
  .note {
    color: var(--muted);
    font-size: 0.85rem;
  }
  .selector-line {
    margin: 0.2rem 0;
  }
  .mono {
    font-family: ui-monospace, Menlo, Consolas, monospace;
  }
</style>