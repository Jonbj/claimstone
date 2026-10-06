// F2: `QuestionMatrix` renders per-class counts before the total (DOM order), and the
// five verdicts never collapse — NO_VERIFIED_CLAIM is rendered dashed, apart (§4.2 rules
// 2 and 3). The fixture is the committed overview payload the API serves.
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import QuestionMatrix, { type MatrixRow } from "@/components/QuestionMatrix";
import overview from "./fixtures/projects/example-news-and-returns/flows/0df548e3743689e1a0dd099da697aee4842e8a573f1225a8da13fec128a248cd/overview.json";
import unboundOverview from "./fixtures/projects/example-news-and-returns/unbound/-/overview.json";

const rows = overview.questions.rows as unknown as MatrixRow[];
// The row with claims: Q02 carries ACA 2 → 2 total.
const withClaims = rows.find((r) => Object.keys(r.claims_by_class).length > 0)!;
const withoutClaims = rows.find((r) => Object.keys(r.claims_by_class).length === 0)!;

describe("F2: QuestionMatrix — per class before the total", () => {
  it("renders each class count before the total in the same cell, class first", () => {
    const { container } = render(
      <MemoryRouter>
        <QuestionMatrix rows={[withClaims]} />
      </MemoryRouter>,
    );
    const cell = container.querySelector("td:nth-child(3)")!;
    const byClass = cell.querySelector(".by-class")!;
    expect(byClass.textContent).toContain("ACA 2");
    expect(cell.textContent!.indexOf("ACA 2")).toBeLessThan(
      cell.textContent!.indexOf("2 total"),
    );
  });

  it("renders a question with no claims as a dash with the not-knowable title, never 0", () => {
    const nullClaims: MatrixRow = { ...withoutClaims, claims: null };
    const { container } = render(
      <MemoryRouter>
        <QuestionMatrix rows={[nullClaims]} />
      </MemoryRouter>,
    );
    const cell = container.querySelector("td:nth-child(3)")!;
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
    const { container } = render(
      <MemoryRouter>
        <QuestionMatrix rows={[counted]} />
      </MemoryRouter>,
    );
    const text = container.textContent!;
    expect(text).toContain("SUPPORTS 2");
    expect(text).toContain("(a count, not a strength)");
  });

  it("keeps the registry order: the server's row order is the DOM order", () => {
    const { container } = render(
      <MemoryRouter>
        <QuestionMatrix rows={rows} />
      </MemoryRouter>,
    );
    const rendered = [...container.querySelectorAll("[data-question-id]")].map((el) =>
      el.getAttribute("data-question-id"),
    );
    expect(rendered).toEqual(rows.map((r) => r.id));
  });

  it("renders NO_VERIFIED_CLAIM as a dashed engine state, never as a verdict chip", () => {
    const { container } = render(
      <MemoryRouter>
        <QuestionMatrix rows={[withoutClaims]} />
      </MemoryRouter>,
    );
    const chip = container.querySelector(".chip.dashed")!;
    expect(chip.textContent).toBe("NO_VERIFIED_CLAIM");
  });

  it("renders rows without a profile as no_profile, never as awaiting a person", () => {
    // Review of R4: the cell shows the server's display_state, the word the donut counts.
    const unboundRows = unboundOverview.questions.rows as unknown as MatrixRow[];
    const { container } = render(
      <MemoryRouter>
        <QuestionMatrix rows={unboundRows} />
      </MemoryRouter>,
    );
    expect(container.textContent).toContain("no_profile");
    expect(container.textContent).not.toContain("awaiting_a_person");
  });

  it("heads a provisional NO_VERIFIED_CLAIM row with provisional, never with the engine word", () => {
    // Review of R4: an unfinished reading is not a finding that nothing exists.
    const row = { ...withoutClaims, provisional: true, state: "NO_VERIFIED_CLAIM",
                  display_state: "provisional", blocking: ["awaiting_review"] } as MatrixRow;
    const { container } = render(
      <MemoryRouter>
        <QuestionMatrix rows={[row]} />
      </MemoryRouter>,
    );
    const first = container.querySelector(".chip")!;
    expect(first.textContent).toBe("provisional");
    expect(container.textContent).toContain("engine: NO_VERIFIED_CLAIM");
  });
});
