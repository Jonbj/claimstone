// F2: `QuestionMatrix` renders per-class counts before the total (DOM order), and the
// five verdicts never collapse — NO_VERIFIED_CLAIM is rendered dashed, apart (§4.2 rules
// 2 and 3). The fixture is the committed overview payload the API serves.
import { render, screen } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";
import QuestionMatrix, { type MatrixRow } from "$lib/components/QuestionMatrix.svelte";
import overview from "./fixtures/projects/example-news-and-returns/flows/0df548e3743689e1a0dd099da697aee4842e8a573f1225a8da13fec128a248cd/overview.json";
import unboundOverview from "./fixtures/projects/example-news-and-returns/unbound/-/overview.json";

const rows = overview.questions.rows as unknown as MatrixRow[];
// The row with claims: Q02 carries ACA 2 → 2 total.
const withClaims = rows.find((r) => Object.keys(r.claims_by_class).length > 0)!;
const withoutClaims = rows.find((r) => Object.keys(r.claims_by_class).length === 0)!;

describe("F2: QuestionMatrix — per class before the total", () => {
  it("renders each class count before the total in the same cell, class first", () => {
    const { container } = render(QuestionMatrix, { rows: [withClaims] });
    const cell = container.querySelector("td:nth-child(4)")!;
    const byClass = cell.querySelector(".by-class")!;
    expect(byClass.textContent).toContain("ACA 2");
    expect(cell.textContent!.indexOf("ACA 2")).toBeLessThan(
      cell.textContent!.indexOf("2 total"),
    );
  });

  it("renders a question with no claims as a dash with the not-knowable title, never 0", () => {
    const nullClaims: MatrixRow = { ...withoutClaims, claims: null };
    const { container } = render(QuestionMatrix, { rows: [nullClaims] });
    const cell = container.querySelector("td:nth-child(4)")!;
    expect(cell.textContent).toContain("— total");
    expect(cell.textContent).not.toContain("0 total");
    expect(cell.querySelector("[title='not knowable']")).toBeTruthy();
  });

  it("renders the direction count with its note, verbatim, when the count is not empty", () => {
    const counted: MatrixRow = {
      ...withClaims,
      direction_count: { SUPPORTS: 2 },
      direction_count_note: "a count, not a strength",
    };
    const { container } = render(QuestionMatrix, { rows: [counted] });
    const text = container.textContent!;
    expect(text).toContain("SUPPORTS 2");
    expect(text).toContain("(a count, not a strength)");
  });

  it("keeps the registry order: the server's row order is the DOM order", () => {
    const { container } = render(QuestionMatrix, { rows });
    const rendered = [...container.querySelectorAll("[data-question-id]")].map(
      (el) => el.getAttribute("data-question-id"),
    );
    expect(rendered).toEqual(rows.map((r) => r.id));
  });

  it("renders NO_VERIFIED_CLAIM as a dashed engine state, never as a verdict chip", () => {
    const { container } = render(QuestionMatrix, { rows: [withoutClaims] });
    const chip = container.querySelector(".chip.dashed")!;
    expect(chip.textContent).toBe("NO_VERIFIED_CLAIM");
  });

  it("renders the INSUFFICIENT_ACQUISITION rows with no state as no-verdict dashes", () => {
    const unboundRows = unboundOverview.questions.rows as unknown as MatrixRow[];
    const { container } = render(QuestionMatrix, { rows: unboundRows });
    expect(container.textContent).toContain("— no verdict");
  });
});