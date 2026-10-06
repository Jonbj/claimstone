<script lang="ts">
  // The inbox (§4.1): every project's cards, lazily, grouped by project then category.
  // Within a group the server order is preserved (§4.2 rule 6); the only reordering is
  // the operator-chosen category filter, which is a selection, not a sort.
  import { api } from "$lib/api";
  import type { Projects, Summary } from "$lib/api-types";
  import Chip from "$lib/components/Chip.svelte";
  import ErrorState from "$lib/components/ErrorState.svelte";
  import InboxCards from "$lib/components/InboxCards.svelte";
  import Pending from "$lib/components/Pending.svelte";

  type Group = { project: string; category: string; cards: never[] };

  let projects = $state<Projects | null>(null);
  let groups = $state<Group[]>([]);
  let error = $state<Error | null>(null);
  // The operator's category filter: `""` is every category (no filter).
  let category = $state("");

  const CATEGORIES = [
    "INTEGRITY", "PROTOCOL", "ACQUISITION", "CLASSIFICATION", "NORMALIZE",
    "EXTRACT", "REVIEW", "ADJUDICATION", "ADVISORY",
  ];

  function selectorRefs(p: Projects["projects"][number]) {
    const refs: Array<{ kind: "f" | "u"; sel: string }> = [];
    for (const flow of p.flows ?? []) refs.push({ kind: "f", sel: flow.flow_id });
    for (const unbound of p.unbound_selectors ?? []) {
      refs.push({ kind: "u", sel: unbound.slug });
    }
    return refs;
  }

  $effect(() => {
    api
      .projects()
      .then(async (p) => {
        projects = p;
        // Every project's selectors, lazily and in parallel: the inbox page's own data.
        const next: Group[] = [];
        await Promise.all(
          p.projects.map(async (project) => {
            if (project.config !== "OK") {
              next.push({
                project: project.name,
                category: "INTEGRITY",
                cards: [{
                  category: "INTEGRITY", scope: "project",
                  subject: "ConfigError", cause: project.config_error ?? "",
                  command: null, note: "",
                }] as never,
              });
              groups = [...next];
              return;
            }
            for (const ref of selectorRefs(project)) {
              try {
                const inbox = await api.inbox(project.name, ref.kind, ref.sel);
                for (const card of inbox.cards) {
                  next.push({
                    project: project.name,
                    category: card.category,
                    cards: [card] as never,
                  });
                }
              } catch {
                // A project whose inbox cannot be read keeps its place: the error state
                // is the index's job; here the absence is named, not zero.
                next.push({
                  project: project.name,
                  category: "INTEGRITY",
                  cards: [{
                    category: "INTEGRITY", scope: "project",
                    subject: project.name, cause: "inbox unreadable for this selector",
                    command: null, note: "",
                  }] as never,
                });
              }
              groups = [...next];
            }
          }),
        );
        // Group by project then category — the page's own order (§4.1), each group
        // keeping the server's card order inside it (rule 6).
        const byProject = new Map<string, Map<string, never[]>>();
        for (const g of next) {
          if (category && g.category !== category) continue;
          const perCategory = byProject.get(g.project) ?? new Map<string, never[]>();
          const cards = perCategory.get(g.category) ?? [];
          cards.push(...g.cards);
          perCategory.set(g.category, cards);
          byProject.set(g.project, perCategory);
        }
        const ordered: Group[] = [];
        for (const [project, perCategory] of byProject) {
          for (const cat of CATEGORIES) {
            const cards = perCategory.get(cat);
            if (cards) ordered.push({ project, category: cat, cards });
          }
        }
        groups = ordered;
      })
      .catch((e: Error) => (error = e));
  });
</script>

<h1>inbox</h1>

<p class="filter">
  category:
  <select bind:value={category} aria-label="filter by category">
    <option value="">every category</option>
    {#each CATEGORIES as cat (cat)}
      <option value={cat}>{cat}</option>
    {/each}
  </select>
  <span class="note">— the operator's only filter; within a group, server order (rule F13)</span>
</p>

{#if error}
  <ErrorState error={error} />
{:else if groups.length === 0}
  <Pending label="collecting cards…" />
{:else}
  {#each groups as group (group.project + "|" + group.category)}
    <section>
      <h2>{group.project} — {group.category}</h2>
      <InboxCards cards={group.cards} />
    </section>
  {/each}
{/if}

<style>
  .filter {
    display: flex;
    gap: 0.5rem;
    align-items: baseline;
  }
  select {
    border: 1px solid var(--border);
    border-radius: 0.4rem;
    background: var(--chip-bg);
    color: var(--fg);
    padding: 0.2rem 0.4rem;
  }
  .note {
    color: var(--muted);
    font-size: 0.85rem;
  }
</style>