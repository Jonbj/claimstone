import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

// A state pill that always carries its word and a symbol (● waits, ◐ acting, ✓ done,
// ▲ partial, ■ blocked, ○ neutral). The colour supports the word, never replaces it — the
// caller writes the symbol and the word together (§4.2 rule 7 / D137).
export type PillTone = "waits" | "acting" | "done" | "partial" | "blocked" | "neutral";

const TONE: Record<PillTone, string> = {
  waits: "bg-waits-soft text-waits-ink",
  acting: "bg-acting-soft text-acting-ink",
  done: "bg-done/10 text-done",
  partial: "bg-provisional/15 text-provisional",
  blocked: "bg-not-obtained/10 text-not-obtained",
  neutral: "bg-neutral-soft text-neutral-ink",
};

export default function StatePill({ tone, children }: { tone: PillTone; children: ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold",
        TONE[tone],
      )}
    >
      {children}
    </span>
  );
}
