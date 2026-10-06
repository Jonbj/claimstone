import CommandBlock from "@/components/CommandBlock";
import type { Inbox } from "@/lib/api-types";

export type InboxCard = Inbox["cards"][number];

// The inbox cards (§4.1): server order preserved (§4.2 rule 6) — this component never
// sorts, ranks or filters. `cause`, `note` and `command` are display text rendered
// verbatim (rule 5); a command is text to copy, never something the page runs (rule 4)
// — the copy affordance is CommandBlock's, and it never executes.
export default function InboxCards({ cards }: { cards: InboxCard[] }) {
  if (cards.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">nothing open in this scope</p>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      {cards.map((card, index) => (
        <div
          key={index}
          data-card-index={index}
          className="grid items-baseline gap-3 rounded-lg border border-border bg-card px-3 py-2 md:grid-cols-[8rem_12rem_1fr]"
        >
          <span className="text-sm font-semibold">{card.category}</span>
          <span className="font-mono text-xs text-muted-foreground">
            {card.scope}
          </span>
          <div className="min-w-0 text-sm">
            <strong>{card.subject}</strong> — {card.cause}
            {card.command ? <CommandBlock command={card.command} /> : null}
            {card.note ? (
              <p className="mt-1 text-xs text-muted-foreground">{card.note}</p>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}
