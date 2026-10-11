// The copy the wizard shows is complete: every step has its three explanations, every kind and
// every state has a gloss, and the five contract tokens survive translation untouched.
import { describe, expect, it } from "vitest";
import { CATALOGS } from "@/lib/i18n";

describe("wizard copy", () => {
  it("explains every step in three moments, in both languages", () => {
    for (const locale of ["en", "it"] as const) {
      for (const step of [1, 2, 3, 4]) {
        for (const moment of ["afterSave", "atCreation", "afterStart"]) {
          expect(CATALOGS[locale][`wizard.step${step}.${moment}`]).toBeTruthy();
        }
      }
    }
  });

  it("glosses every question kind and every draft status", () => {
    for (const locale of ["en", "it"] as const) {
      for (const kind of ["effect", "heterogeneity", "method", "premise", "operational"]) {
        expect(CATALOGS[locale][`wizard.kind.${kind}`]).toBeTruthy();
      }
      for (const status of ["open", "discarded", "created"]) {
        expect(CATALOGS[locale][`wizard.drafts.status.${status}`]).toBeTruthy();
      }
    }
  });

  it("keeps contract tokens canonical inside the prose", () => {
    for (const locale of ["en", "it"] as const) {
      expect(CATALOGS[locale]["wizard.step3.afterStart"]).toContain("INSUFFICIENT_ACQUISITION");
      expect(CATALOGS[locale]["wizard.kind.operational"]).toContain("operational");
    }
  });

  it("never promises a verdict for an operational question", () => {
    for (const locale of ["en", "it"] as const) {
      expect(CATALOGS[locale]["wizard.step2.atCreation"]).toContain("{operational}");
    }
  });

  const wizardCopy = (locale: "en" | "it") =>
    Object.entries(CATALOGS[locale]).filter(([key]) => key.startsWith("wizard."));

  it("step 2 names all five verdict states, untranslated", () => {
    for (const locale of ["en", "it"] as const) {
      const step2 = wizardCopy(locale)
        .filter(([key]) => key.startsWith("wizard.step2.") || key.startsWith("wizard.steps.2."))
        .map(([, text]) => text)
        .join(" ");
      for (const state of ["SUPPORTED", "CONTRADICTED", "CONTESTED_IN_LITERATURE", "UNANSWERED_IN_LITERATURE", "NEVER_ASKED"]) {
        expect(step2).toContain(state);
      }
    }
  });

  it("never says 'nothing starts' loosely, a 'tappa', or 'today' for a UTC date", () => {
    for (const locale of ["en", "it"] as const) {
      for (const [key, text] of wizardCopy(locale)) {
        for (const banned of ["nulla parte", "tappa", "data di oggi", "today's date"]) {
          expect(text.toLowerCase(), `${locale} ${key}`).not.toContain(banned);
        }
      }
    }
  });

  it("the Italian copy avoids the false friends and the mixed terms", () => {
    for (const [key, text] of wizardCopy("it")) {
      expect(text, key).not.toMatch(/\bevidenza\b/i); // "evidenze" in "profilo delle evidenze" is fine
      expect(text, key).not.toMatch(/domande di letteratura/i);
      expect(text, key).not.toMatch(/\bstadi[oi]\b/i);
    }
  });

  it("the note beside Save does not claim a draft is already saved", () => {
    expect(CATALOGS.en["wizard.draftNote"]).not.toMatch(/draft saved/i);
    expect(CATALOGS.it["wizard.draftNote"]).not.toMatch(/bozza salvata/i);
  });
});
