import type { KeyboardEvent, ReactNode } from "react";
import { useSearchParams } from "react-router";
import type { Journey } from "@/components/JourneySteps";
import { cn } from "@/lib/utils";

// The six blocks of the research flow as a strip of tiles with the selected block's detail under
// it (spec 2026-10-09). The server decides each tile's status and figure (`journey.blocks`); this
// file maps a status to a mark and prints the status word beside it (colour never alone), keeps the
// selection in the URL (`?block=`), and renders the panels it is given. It computes no status.
export type JourneyBlock = Journey["blocks"][number];

export const BLOCK_KEYS = ["protocol", "pipeline", "selection", "intake", "execution", "reading"] as const;
export type BlockKey = (typeof BLOCK_KEYS)[number];

function isBlockKey(value: string | null): value is BlockKey {
  return value !== null && (BLOCK_KEYS as readonly string[]).includes(value);
}

const STATUS: Record<JourneyBlock["status"], { word: string; symbol: string; ink: string }> = {
  done: { word: "done", symbol: "✓", ink: "text-done" },
  partial: { word: "partial", symbol: "▲", ink: "text-provisional" },
  running: { word: "running", symbol: "◐", ink: "text-acting-ink" },
  waits_for_you: { word: "waits for you", symbol: "●", ink: "text-waits-ink" },
  blocked: { word: "blocked", symbol: "■", ink: "text-not-obtained" },
  not_started: { word: "not started", symbol: "○", ink: "text-muted-foreground" },
  not_applicable: { word: "not applicable", symbol: "○", ink: "text-muted-foreground" },
  idle: { word: "nothing waiting", symbol: "○", ink: "text-muted-foreground" },
  advisory: { word: "advisory", symbol: "▲", ink: "text-provisional border border-provisional" },
  not_declared: { word: "not declared", symbol: "○", ink: "text-muted-foreground" },
  unavailable: { word: "unavailable", symbol: "■", ink: "text-not-obtained" },
};

// On open: the first block, in strip order, that waits for you or is blocked; otherwise Pipeline.
export function defaultBlock(blocks: JourneyBlock[]): BlockKey {
  const first = blocks.find((b) => b.status === "waits_for_you" || b.status === "blocked");
  return first !== undefined && isBlockKey(first.key) ? first.key : "pipeline";
}

export default function BlockMap({ blocks, panels }: {
  blocks: JourneyBlock[];
  panels: Record<BlockKey, ReactNode>;
}) {
  const [params, setParams] = useSearchParams();
  const asked = params.get("block");
  const selected: BlockKey = isBlockKey(asked) ? asked : defaultBlock(blocks);

  // Roving tabindex: arrows, Home and End move the selection and the focus together.
  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const last = blocks.length - 1;
    const target =
      event.key === "ArrowRight" ? (index === last ? 0 : index + 1)
      : event.key === "ArrowLeft" ? (index === 0 ? last : index - 1)
      : event.key === "Home" ? 0
      : event.key === "End" ? last
      : null;
    if (target === null) return;
    event.preventDefault();
    const key = blocks[target].key;
    if (!isBlockKey(key)) return;
    choose(key);
    document.getElementById(`tab-${key}`)?.focus();
  }

  function choose(key: BlockKey) {
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      next.set("block", key);
      return next;
    }, { replace: true });
  }

  return (
    <section aria-label="Blocks of the research flow" className="flex flex-col gap-3.5">
      <div role="tablist" aria-label="Blocks" className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
        {blocks.map((block, index) => {
          const s = STATUS[block.status] ?? { word: String(block.status).replace(/_/g, " "), symbol: "○", ink: "text-muted-foreground" };
          const on = block.key === selected;
          return (
            <button key={block.key} type="button" role="tab" id={`tab-${block.key}`}
                    aria-selected={on} tabIndex={on ? 0 : -1}
                    onKeyDown={(event) => onKeyDown(event, index)} aria-controls={`panel-${block.key}`}
                    data-block={block.key} data-status={block.status}
                    onClick={() => isBlockKey(block.key) && choose(block.key)}
                    className={cn(
                      "flex min-h-24 min-w-0 flex-col gap-1 rounded-xl border border-border bg-card p-3.5 text-left hover:bg-muted/40",
                      "aria-selected:outline-2 aria-selected:-outline-offset-2 aria-selected:outline-foreground",
                    )}>
              <span className="text-xs tracking-wide text-muted-foreground uppercase">{on ? <span aria-hidden="true">▾ </span> : null}{block.title}</span>
              <span className={cn("flex items-center gap-2 font-semibold", s.ink)}>
                <span aria-hidden="true" className={cn("flex size-5 shrink-0 items-center justify-center rounded-full text-sm", s.ink)}>{s.symbol}</span>
                <span data-status-word>{s.word}</span>
              </span>
              <span className="text-xs text-muted-foreground" data-block-figure>{block.figure}</span>
            </button>
          );
        })}
      </div>
      {BLOCK_KEYS.map((key) => (
        <div key={key} role="tabpanel" id={`panel-${key}`} aria-labelledby={`tab-${key}`}
             hidden={key !== selected} data-panel={key}
             className="flex flex-col gap-5 rounded-xl border border-border bg-card p-4 sm:p-5">
          {panels[key]}
        </div>
      ))}
    </section>
  );
}
