import { useEffect, useState } from "react";
import ErrorState from "@/components/ErrorState";
import InboxCards, { type InboxCard } from "@/components/InboxCards";
import Pending from "@/components/Pending";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, ApiError } from "@/lib/api";

// The inbox (§4.1): every project's cards, fetched lazily and in parallel per selector,
// grouped by project then category. Within a group the server order is preserved
// (§4.2 rule 6); the operator's category filter is the only filter — a selection
// control, not a sort, and not a form (rule 4; the F10 scan sees no `<form`).
const CATEGORIES = [
  "INTEGRITY",
  "PROTOCOL",
  "ACQUISITION",
  "CLASSIFICATION",
  "NORMALIZE",
  "EXTRACT",
  "REVIEW",
  "ADJUDICATION",
  "ADVISORY",
] as const;

type Group = { project: string; category: string; cards: InboxCard[] };

const NO_FILTER = "all";

function unreadableCard(subject: string, cause: string): InboxCard {
  return {
    category: "INTEGRITY",
    scope: "project",
    subject,
    cause,
    command: null,
    note: "",
  };
}

export default function InboxPage() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [error, setError] = useState<Error | null>(null);
  const [collecting, setCollecting] = useState(true);
  // The operator's only filter: `""` is every category (no filter).
  const [category, setCategory] = useState("");

  useEffect(() => {
    let alive = true;
    api
      .projects()
      .then(async (index) => {
        // Cards accumulate as each selector's inbox answers: per project in parallel,
        // per selector in the server's order. The grouping below is order-preserving.
        // Seeded in the API's project order, so groups render in server order (§4.2 rule 6)
        // and not in the order the per-selector answers happen to arrive (review of R3).
        const byProject = new Map<string, Map<string, InboxCard[]>>(
          index.projects.map((project) => [project.name, new Map<string, InboxCard[]>()]),
        );
        const add = (project: string, card: InboxCard) => {
          const perCategory = byProject.get(project) ?? new Map<string, InboxCard[]>();
          const cards = perCategory.get(card.category) ?? [];
          cards.push(card);
          perCategory.set(card.category, cards);
          byProject.set(project, perCategory);
        };
        const flush = () => {
          if (!alive) return;
          const ordered: Group[] = [];
          for (const [project, perCategory] of byProject) {
            for (const cat of CATEGORIES) {
              const cards = perCategory.get(cat);
              if (cards) ordered.push({ project, category: cat, cards });
            }
          }
          setGroups(ordered);
        };
        await Promise.all(
          index.projects.map(async (project) => {
            if (project.config !== "OK") {
              add(
                project.name,
                unreadableCard("ConfigError", project.config_error ?? ""),
              );
              flush();
              return;
            }
            const refs: Array<{ kind: "f" | "u"; sel: string }> = [
              ...(project.flows ?? []).map((flow) => ({
                kind: "f" as const,
                sel: flow.flow_id,
              })),
              ...(project.unbound_selectors ?? []).map((unbound) => ({
                kind: "u" as const,
                sel: unbound.slug,
              })),
            ];
            for (const ref of refs) {
              try {
                const inbox = await api.inbox(project.name, ref.kind, ref.sel);
                if (!alive) return;
                for (const card of inbox.cards) add(project.name, card);
              } catch (cause: unknown) {
                // A selector whose inbox cannot be read keeps its place: the absence
                // is named, not zeroed (§4.2 rule 1), with the error's own code and message
                // — a LEDGER_CORRUPT names its ledger and line (review of R3).
                if (!alive) return;
                const code = cause instanceof ApiError ? cause.code : "UNREACHABLE";
                const message = cause instanceof Error ? cause.message : String(cause);
                add(
                  project.name,
                  unreadableCard(`${ref.kind === "f" ? "flow" : "legacy"} ${ref.sel.slice(0, 12)}`,
                                 `${code}: ${message}`),
                );
              }
              flush();
            }
          }),
        );
        if (alive) setCollecting(false);
      })
      .catch((cause: unknown) => {
        if (!alive) return;
        setError(cause instanceof Error ? cause : new Error(String(cause)));
        setCollecting(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  // The filter runs at render time over the collected groups: choosing a category
  // refetches nothing and reorders nothing (§4.2 rule 6).
  const visible = category === "" ? groups : groups.filter((g) => g.category === category);

  return (
    <section>
      <h1 className="text-[22px] font-semibold">Inbox</h1>
      <p className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <span>category:</span>
        <Select
          value={category === "" ? NO_FILTER : category}
          onValueChange={(value) => setCategory(value === NO_FILTER ? "" : value)}
        >
          <SelectTrigger size="sm" aria-label="filter by category">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NO_FILTER}>every category</SelectItem>
            {CATEGORIES.map((cat) => (
              <SelectItem key={cat} value={cat}>
                {cat}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-xs text-muted-foreground">
          — the operator's only filter; within a group, server order (F13)
        </span>
      </p>
      <div className="mt-3">
        {error ? (
          <ErrorState error={error} />
        ) : visible.length === 0 ? (
          collecting ? (
            <Pending label="collecting cards…" />
          ) : (
            <p className="text-sm text-muted-foreground">no cards</p>
          )
        ) : (
          visible.map((group) => (
            <section key={`${group.project}|${group.category}`} className="mt-4">
              <h2 className="mb-2 text-sm font-semibold">
                {group.project} — {group.category}
              </h2>
              <InboxCards cards={group.cards} />
            </section>
          ))
        )}
      </div>
    </section>
  );
}
