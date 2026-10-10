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
}

export const inputClass = "min-h-11 rounded-lg border border-border bg-card px-3 text-sm font-normal";
export const areaClass = "min-h-24 rounded-lg border border-border bg-card px-3 py-2 text-sm font-normal";
export const primaryClass = "min-h-11 rounded-lg bg-rail px-4 text-sm font-semibold text-rail-foreground disabled:opacity-50";
export const quietClass = "min-h-11 rounded-lg border border-border px-3 text-sm";
export const cardClass = "rounded-xl bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800";
