<script lang="ts">
  // Admin (§4.1): credentials presence only — booleans, never values (§1.3: no secrets
  // in the frontend). Configured and available backends, instrument versions.
  import { api } from "$lib/api";
  import type { Admin } from "$lib/api-types";
  import ErrorState from "$lib/components/ErrorState.svelte";
  import Pending from "$lib/components/Pending.svelte";

  let admin = $state<Admin | null>(null);
  let error = $state<Error | null>(null);

  $effect(() => {
    api
      .admin()
      .then((a) => (admin = a))
      .catch((e: Error) => (error = e));
  });
</script>

<h1>admin</h1>

{#if error}
  <ErrorState error={error} />
{:else if admin === null}
  <Pending label="loading admin…" />
{:else}
  <section>
    <h2>credentials — presence only</h2>
    {#each Object.entries(admin.credentials) as [name, present] (name)}
      <p class="line">{name}: {present ? "set" : "not set"}</p>
    {/each}
    <p class="note">{admin.key_rotation_note}</p>
  </section>

  <section>
    <h2>model backends</h2>
    <p class="line">configured: {admin.backends.configured.join(", ")}</p>
    <p class="line">available: {admin.backends.available.join(", ")}</p>
    <p class="note">{admin.backends_note}</p>
  </section>

  <section>
    <h2>instrument versions</h2>
    {#each Object.entries(admin.instruments).toSorted(([a], [b]) => String(a).localeCompare(String(b))) as [name, version] (String(name))}
      <p class="line mono">{name} {version}</p>
    {/each}
    <p class="note">Every version the design record must acknowledge; the integrity
      panel reports whether it does.</p>
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
</style>