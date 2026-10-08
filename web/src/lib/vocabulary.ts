// §4.2 rule 3: exactly the five verdicts are mapped; `NO_VERIFIED_CLAIM` and
// `LITERATURE_VERDICT_NOT_APPLICABLE` are engine states rendered dashed, never verdicts;
// an unknown word stays itself in a neutral chip — never mapped to a verdict.

export const VERDICTS = [
  "SUPPORTED",
  "CONTRADICTED",
  "CONTESTED_IN_LITERATURE",
  "UNANSWERED_IN_LITERATURE",
  "NEVER_ASKED",
] as const;

export type Verdict = (typeof VERDICTS)[number];

// Engine outcome states: kept apart from the verdicts (invariant 2, §4.2 rule 3).
export const ENGINE_STATES = ["NO_VERIFIED_CLAIM", "LITERATURE_VERDICT_NOT_APPLICABLE"] as const;

export type EngineState = (typeof ENGINE_STATES)[number];

export interface WordStyle {
  readonly cls: string;
  readonly dashed: boolean;
  readonly isVerdict: boolean;
}

const VERDICT_CLASS: Record<Verdict, string> = {
  SUPPORTED: "v-supported",
  CONTRADICTED: "v-contradicted",
  CONTESTED_IN_LITERATURE: "v-contested",
  UNANSWERED_IN_LITERATURE: "v-unanswered",
  NEVER_ASKED: "v-never-asked",
};

/** A display word mapped to its CSS class. Never a new word, never a re-mapping. */
export function word(word: string): WordStyle {
  if ((VERDICTS as readonly string[]).includes(word)) {
    return { cls: VERDICT_CLASS[word as Verdict], dashed: false, isVerdict: true };
  }
  if ((ENGINE_STATES as readonly string[]).includes(word)) {
    return { cls: "v-engine", dashed: true, isVerdict: false };
  }
  // Unknown: rendered as itself, neutral chip, never mapped to a verdict.
  return { cls: "v-unknown", dashed: false, isVerdict: false };
}

// Plain words for the displayed question states (server `display_state`) and the two engine
// states. A person reads the word; the code stays available as the element's title. The five
// verdicts are not here: they are shown as themselves.
const STATE_WORDS: Record<string, string> = {
  signed: "signed",
  stale: "signature out of date",
  awaiting_a_person: "waits for you",
  provisional: "provisional",
  no_verified_claim: "no verified claim",
  not_applicable: "not applicable",
  historical: "historical",
  no_profile: "no profile yet",
  NO_VERIFIED_CLAIM: "no verified claim",
  LITERATURE_VERDICT_NOT_APPLICABLE: "no literature verdict (operational)",
};

/** The human word for a state code; a code with no entry is shown as itself. */
export function stateLabel(code: string): string {
  return STATE_WORDS[code] ?? code;
}
