import type { DraftState, Figures } from "@/lib/control";

export interface Saved {
  step: number;
  revision: number;
  figures: Figures;
}

export interface StepProps {
  draftId: string;
  draft: DraftState;
  onSaved: (saved: Saved) => void;
  /** Re-reads the draft after a stale revision. */
  onReload?: () => void;
}

export const inputClass = "min-h-11 rounded-lg border border-border bg-card px-3 text-sm font-normal";
export const areaClass = "min-h-24 rounded-lg border border-border bg-card px-3 py-2 text-sm font-normal";
// v3 "Assay" (D137): amber is the one primary action, so the shared primary class is the
// brand amber, not the dark rail it used to be.
export const primaryClass = "min-h-11 rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground hover:brightness-95 disabled:opacity-50";
export const quietClass = "min-h-11 rounded-lg border border-border px-3 text-sm";
// v3 cards are `rounded-xl border bg-card`; the old ring/shadow leaked the gray palette.
export const cardClass = "rounded-xl border border-border bg-card p-5";
