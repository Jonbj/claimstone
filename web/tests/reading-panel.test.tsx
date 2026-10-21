// The Human reading block: a profile that cannot be signed yet is still read from here, with the
// reason it cannot be signed, and an operational question is not listed.
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import Fold from "@/components/Fold";
import ReadingPanel from "@/components/ReadingPanel";
import type { MatrixRow } from "@/components/QuestionMatrix";

afterEach(cleanup);

const row = (over: Partial<MatrixRow>): MatrixRow => ({
  awaiting_review: 0, blocking: [], claims: 52, claims_by_class: { ACA: 52 },
  coverage: { examined: 9, sources: 8 }, direction_count: { SUPPORTS: 26, QUALIFIES: 24, CONTRADICTS: 2 },
  direction_count_note: "a count of results, not a verdict", display_state: "provisional",
  extraction: null, gate_rejected: { UNPARSEABLE_VALUE: 54 }, gate_rejected_total: 127, id: "Q01", kind: "effect",
  note: null, operational_not_applicable: false, partial: true, profile_sha256: "a".repeat(64),
  provisional: true, state: null, stored_profile_stale: false, text: "Does exercise reduce depressive symptoms?",
  unavailable: "", verdict: null, verdict_stale: false, ...over,
});

describe("ReadingPanel", () => {
  it("shows counts, coverage, rejections and what blocks signing, with a link to the profile", () => {
    render(<MemoryRouter><ReadingPanel base="/p/x/f/y"
      rows={[row({ blocking: ["awaiting_acquire", "awaiting_extract"] })]} /></MemoryRouter>);
    const card = document.querySelector('[data-question-id="Q01"]') as HTMLElement;
    expect(within(card).getByText(/SUPPORTS 26 · QUALIFIES 24 · CONTRADICTS 2/)).toBeTruthy();
    expect(within(card).getByText("a count of results, not a verdict")).toBeTruthy();
    expect(within(card).getByText("8 / 9")).toBeTruthy();
    expect(within(card).getByText(/127 \(UNPARSEABLE_VALUE 54\)/)).toBeTruthy();
    expect(within(card).getByText("awaiting_acquire, awaiting_extract")).toBeTruthy();
    expect(within(card).getByText("partial")).toBeTruthy();
    expect(within(card).getByRole("link", { name: "Open the evidence profile" }).getAttribute("href"))
      .toBe("/p/x/f/y/q/Q01");
  });

  it("lists no operational question and says nothing when there is no literature question", () => {
    const { container } = render(<MemoryRouter><ReadingPanel base="/p/x/f/y"
      rows={[row({ id: "Q09", kind: "operational", operational_not_applicable: true })]} /></MemoryRouter>);
    expect(container.textContent).toBe("");
  });
});

describe("Fold", () => {
  it("is closed until asked for and open when told to be", () => {
    render(<><Fold title="Closed one"><p>inside</p></Fold><Fold title="Open one" open><p>shown</p></Fold></>);
    expect((screen.getByText("Closed one").closest("details") as HTMLDetailsElement).open).toBe(false);
    expect((screen.getByText("Open one").closest("details") as HTMLDetailsElement).open).toBe(true);
  });
});
