// The Source selection detail: advisory by construction, named failures, no figure on error.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import SelectionPanel from "@/components/SelectionPanel";
import type { Journey } from "@/components/JourneySteps";

type Selection = Journey["selection"];

const figures = {
  inventory_count: 830, screened_count: 48, unobserved_count: 782, direct: 3, context: 21,
  not_direct: 18, uncertain: 6, identity_observations: 3,
};

function declared(over: Partial<Selection["scopes"][number]> = {}): Selection {
  return {
    selection_version: 1, state: "DECLARED", advisory: true, assessment_status: "AI_PROVISIONAL",
    cohort_closed: false, admitted_candidates: 0,
    scopes: [{ scope_id: "l02-v2", question_id: "L02", state: "OK", figures, ...over }],
  };
}

describe("SelectionPanel", () => {
  afterEach(cleanup);

  it("says in words that it is advisory, and that nothing is admitted", () => {
    render(<SelectionPanel selection={declared()} />);
    expect(screen.getByText(/Advisory · AI_PROVISIONAL judgements/)).toBeTruthy();
    expect(screen.getByText(/cohort open · admitted 0/)).toBeTruthy();
  });

  it("shows the counts as received", () => {
    render(<SelectionPanel selection={declared()} />);
    const get = (name: string) => document.querySelector(`[data-figure="${name}"] dd`)?.textContent;
    expect(get("direct")).toBe("3");
    expect(get("context")).toBe("21");
    expect(get("not_direct")).toBe("18");
    expect(get("uncertain")).toBe("6");
    expect(get("unobserved_count")).toBe("782");
    expect(screen.getByText("L02")).toBeTruthy();
    expect(screen.getByText("l02-v2")).toBeTruthy();
  });

  it("no scope declared is a sentence, not a zero", () => {
    render(<SelectionPanel selection={{
      selection_version: 1, state: "NO_SCOPE_DECLARED", advisory: true,
      assessment_status: "AI_PROVISIONAL", cohort_closed: false, admitted_candidates: 0, scopes: [],
    }} />);
    expect(screen.getByText("No selection scope is declared for this flow.")).toBeTruthy();
    expect(screen.getByText("This does not mean there is nothing to select.")).toBeTruthy();
    expect(document.querySelector("[data-figure]")).toBeNull();
  });

  it("an unreadable declaration shows a sentence and no figures", () => {
    render(<SelectionPanel selection={{
      selection_version: 1, state: "SCOPES_FILE_INVALID", advisory: true,
      assessment_status: "AI_PROVISIONAL", cohort_closed: false, admitted_candidates: 0, scopes: [],
    }} />);
    expect(screen.getByText(/declaration cannot be read/)).toBeTruthy();
    expect(document.querySelector("[data-figure]")).toBeNull();
  });

  it.each([
    ["INVENTORY_UNREADABLE", /inventory file cannot be read/],
    ["INVENTORY_DRIFTED", /no longer matches the hash declared/],
    ["SCREENING_OUTSIDE_INVENTORY", /not in the declared inventory/],
    ["SELECTION_LEDGER_INVALID", /ledger is not valid/],
  ] as const)("a scope in %s names it and shows no figures", (state, text) => {
    render(<SelectionPanel selection={declared({ state, figures: null })} />);
    expect(screen.getByText(text)).toBeTruthy();
    expect(screen.getByText(state)).toBeTruthy();
    expect(document.querySelector("[data-figure]")).toBeNull();
  });
});
