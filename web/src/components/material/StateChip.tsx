import { cn } from "@/lib/utils";

// An intake state as a chip in the v2.1 meaning colours (spec §1 rule 8). The word is always
// the server's own state, verbatim: the colour supports it, never replaces it, and an unknown
// state stays itself in the neutral chip.
const STATE_CLASS: Record<string, string> = {
  DUPLICATE: "bg-neutral-soft text-neutral-ink",
  POSSIBLE_VERSION: "bg-waits-soft text-waits-ink",       // violet: waits for you
  NEEDS_NEW_ROUND: "bg-provisional/15 text-provisional",  // amber: provisional
  READY: "bg-acting-soft text-acting-ink",                // teal: Claimstone acting
  RECEIVED: "bg-acting-soft text-acting-ink",
  CHECKING: "bg-acting-soft text-acting-ink",
  REJECTED: "bg-not-obtained/10 text-not-obtained",       // rose: not obtained
  COUNTED: "bg-done/10 text-done",                        // emerald: done
  REPORTED_SEPARATELY: "bg-done/10 text-done",
};

export default function StateChip({ state }: { state: string }) {
  return (
    <span
      data-intake-state={state}
      className={cn(
        "inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 font-mono text-xs font-semibold",
        STATE_CLASS[state] ?? "bg-neutral-soft text-neutral-ink",
      )}
    >
      {state}
    </span>
  );
}
