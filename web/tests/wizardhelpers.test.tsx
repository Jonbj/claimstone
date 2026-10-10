import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorSummary, FieldError, messageFor, problemsOf } from "@/components/wizard/problems";
import { explainParams, show } from "@/components/wizard/figures";
import { ControlError } from "@/lib/control";

afterEach(cleanup);

describe("show", () => {
  it("renders an unknown as a dash, never 0", () => {
    expect(show(null)).toBe("—");
    expect(show(undefined)).toBe("—");
    expect(show(Number.NaN)).toBe("—");
    expect(show("")).toBe("—");
    expect(show(0)).toBe("0"); // a known zero is a figure
    expect(show(12)).toBe("12");
  });
});

describe("explainParams", () => {
  it("maps figures to the placeholders the copy uses", () => {
    const params = explainParams({
      topics: 2, terms: 5, searches_per_index: 5, searches_all_indexes: 15,
      questions_total: 8, questions_literature: 7, questions_operational: 1,
      acquisition_floor: 0.8, classes: ["ACA", "WP"], excluded_hosts_added: 1, supplied_copies: "separate",
    });
    expect(params).toMatchObject({
      topics: "2", terms: "5", searches: "5", searchesAll: "15", total: "8", literature: "7",
      operational: "1", floor: "0.80", classes: "2", added: "1", supplied: "separate",
    });
  });

  it("shows a dash for what the server has not said", () => {
    const params = explainParams({});
    expect(params.floor).toBe("—");
    expect(params.classes).toBe("—");
    expect(params.terms).toBe("—");
  });
});

describe("problems", () => {
  const error = new ControlError(422, "VALIDATION", "name: bad", [
    { path: "name", message: "use lowercase" }, { path: "topics[0].terms", message: "add a term" },
  ]);

  it("reads the details of a ControlError and nothing else", () => {
    expect(problemsOf(error)).toHaveLength(2);
    expect(problemsOf(new Error("x"))).toEqual([]);
    expect(problemsOf(null)).toEqual([]);
    expect(messageFor(problemsOf(error), "name")).toBe("use lowercase");
    expect(messageFor(problemsOf(error), "other")).toBeNull();
  });

  it("FieldError shows only its own path", () => {
    render(<FieldError problems={problemsOf(error)} path="topics[0].terms" />);
    expect(screen.getByRole("alert").textContent).toBe("add a term");
  });

  it("ErrorSummary lists every problem, and a stale revision gets the reload advice", () => {
    render(<ErrorSummary error={error} />);
    expect(screen.getByText("use lowercase")).toBeTruthy();
    cleanup();
    render(<ErrorSummary error={new ControlError(409, "STALE_REVISION", "saved from revision 1")} />);
    expect(screen.getByRole("alert").textContent).toContain("changed elsewhere");
  });

  it("ErrorSummary shows nothing without an error", () => {
    const { container } = render(<ErrorSummary error={null} />);
    expect(container.textContent).toBe("");
  });
});

describe("useWide", () => {
  it("is wide when matchMedia is absent", async () => {
    const { default: probe } = await import("./support/WideProbe");
    vi.stubGlobal("matchMedia", undefined);
    render(probe());
    expect(screen.getByTestId("wide").textContent).toBe("wide");
    vi.unstubAllGlobals();
  });
});
