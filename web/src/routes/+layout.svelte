<script lang="ts">
  import { page } from "$app/state";
  import "../app.css";
  import ThemeToggle from "$lib/components/ThemeToggle.svelte";

  let { children } = $props();

  let revision: string | null = $state(null);
  let revisionDirty: boolean | null = $state(null);
  let metaFailed = $state(false);

  // The header shows the API's code identity: one GET, rendered verbatim (§4.2 rule 5).
  $effect(() => {
    fetch("/api/v1/meta")
      .then((r) => r.json())
      .then((meta) => {
        revision = meta.code?.revision ?? null;
        revisionDirty = meta.code?.dirty ?? null;
      })
      .catch(() => {
        metaFailed = true;
      });
  });

  // Breadcrumb: the current path's segments, minus the route groups ("p", "q", "claim",
  // "source") and the selector kinds ("f", "u") — those are structure, not places.
  const crumbSegments = $derived(
    page.url.pathname
      .split("/")
      .filter(Boolean)
      .filter((s) => !["p", "q", "claim", "source", "f", "u"].includes(s))
      .map(decodeURIComponent),
  );
</script>

<header class="portal-header">
  <nav class="crumbs" aria-label="Breadcrumb">
    <a href="/">portal</a>
    {#each crumbSegments as segment (segment)}
      <span class="crumb-sep" aria-hidden="true">/</span>
      <span class="crumb-current">{segment}</span>
    {/each}
  </nav>
  <div class="portal-header-right">
    <span class="badge" title="This view derives from the ledgers and writes nothing">
      read-only derived view
    </span>
    <span class="revision">
      {#if metaFailed}
        <span title="the API is unreachable">rev unreachable</span>
      {:else if revision !== null}
        rev {revision.slice(0, 12)}{#if revisionDirty === true} (dirty){/if}
      {:else}
        <span title="code revision not loaded yet">…</span>
      {/if}
    </span>
    <ThemeToggle />
  </div>
</header>

<main>
  {@render children()}
</main>

<style>
  .portal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    padding: 0.5rem 1rem;
    border-bottom: 1px solid var(--border);
  }
  .crumbs {
    display: flex;
    gap: 0.25rem;
    align-items: center;
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
  }
  .crumb-sep {
    color: var(--muted);
  }
  .crumb-current {
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .portal-header-right {
    display: flex;
    gap: 0.75rem;
    align-items: center;
    white-space: nowrap;
  }
  .badge {
    border: 1px solid var(--border);
    border-radius: 0.5rem;
    padding: 0.1rem 0.5rem;
    font-size: 0.75rem;
    color: var(--muted);
  }
  .revision {
    font-family: ui-monospace, Menlo, Consolas, monospace;
    font-size: 0.75rem;
    color: var(--muted);
  }
</style>