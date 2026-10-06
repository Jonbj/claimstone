// F1: `NO_VERIFIED_CLAIM` is not mapped to `UNANSWERED_IN_LITERATURE` or `NEVER_ASKED`;
// an unknown word stays itself; the five verdicts map; the engine states are dashed.
import { describe, expect, it } from "vitest";
import { ENGINE_STATES, VERDICTS, word } from "$lib/vocabulary";

describe("F1: vocabulary", () => {
  it("maps exactly the five verdicts", () => {
    for (const v of VERDICTS) {
      const w = word(v);
      expect(w.isVerdict).toBe(true);
      expect(w.dashed).toBe(false);
      expect(w.cls).not.toBe("v-unknown");
    }
    expect(word("SUPPORTED").cls).toBe("v-supported");
    expect(word("NEVER_ASKED").cls).toBe("v-never-asked");
  });

  it("renders NO_VERIFIED_CLAIM dashed, never a verdict", () => {
    const w = word("NO_VERIFIED_CLAIM");
    expect(w.isVerdict).toBe(false);
    expect(w.dashed).toBe(true);
    // The class must not be any verdict's class.
    expect(w.cls).not.toBe(word("UNANSWERED_IN_LITERATURE").cls);
    expect(w.cls).not.toBe(word("NEVER_ASKED").cls);
  });

  it("renders LITERATURE_VERDICT_NOT_APPLICABLE dashed, never a verdict", () => {
    const w = word("LITERATURE_VERDICT_NOT_APPLICABLE");
    expect(w.isVerdict).toBe(false);
    expect(w.dashed).toBe(true);
  });

  it("keeps an unknown word itself, neutral, never mapped to a verdict", () => {
    const w = word("SOME_FUTURE_WORD");
    expect(w.cls).toBe("v-unknown");
    expect(w.isVerdict).toBe(false);
    expect(w.dashed).toBe(false);
    // None of the five verdicts' classes leaks into an unknown word.
    for (const v of VERDICTS) {
      expect(w.cls).not.toBe(word(v).cls);
    }
  });

  it("lists the two engine states", () => {
    expect([...ENGINE_STATES]).toEqual(
      expect.arrayContaining(["NO_VERIFIED_CLAIM", "LITERATURE_VERDICT_NOT_APPLICABLE"]),
    );
  });
});