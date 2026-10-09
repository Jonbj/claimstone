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

const HALF = "bg-gradient-to-r from-done from-50% to-gray-300 to-50%";
const DASHED = "border-2 border-dashed border-slate-400";

const STATUS: Record<JourneyBlock["status"], { word: string; mark: string }> = {
  done: { word: "done", mark: "bg-done" },
  partial: { word: "partial", mark: HALF },
  running: { word: "running", mark: "bg-acting" },
  waits_for_you: { word: "waits for you", mark: "bg-waits" },
  blocked: { word: "blocked", mark: "bg-not-obtained" },
  not_started: { word: "not started", mark: "bg-gray-300" },
  not_applicable: { word: "not applicable", mark: DASHED },
  idle: { word: "nothing waiting", mark: "bg-gray-300" },
  advisory: { word: "advisory", mark: "border-2 border-provisional bg-transparent" },
  not_declared: { word: "not declared", mark: DASHED },
  unavailable: { word: "unavailable", mark: "border-2 border-dashed border-not-obtained" },
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
          const s = STATUS[block.status] ?? { word: String(block.status).replace(/_/g, " "), mark: "bg-gray-300" };
          const on = block.key === selected;
          return (
            <button key={block.key} type="button" role="tab" id={`tab-${block.key}`}
                    aria-selected={on} tabIndex={on ? 0 : -1}
                    onKeyDown={(event) => onKeyDown(event, index)} aria-controls={`panel-${block.key}`}
                    data-block={block.key} data-status={block.status}
                    onClick={() => isBlockKey(block.key) && choose(block.key)}
                    className={cn(
                      "flex min-h-[104px] flex-col gap-1 rounded-xl bg-card p-3 text-left ring-1 ring-gray-200 hover:bg-gray-50",
                      "dark:ring-gray-800 dark:hover:bg-gray-900 aria-selected:ring-2 aria-selected:ring-foreground",
                    )}>
              <span className="text-xs tracking-wide text-muted-foreground uppercase">{on ? <span aria-hidden="true">▾ </span> : null}{block.title}</span>
              <span className="flex items-center gap-2 font-semibold">
                <span aria-hidden="true" className={cn("size-4 shrink-0 rounded-full", s.mark)} />
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
             className="flex flex-col gap-5 rounded-xl bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
          {panels[key]}
        </div>
      ))}
    </section>
  );
}
