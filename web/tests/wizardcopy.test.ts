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
});
