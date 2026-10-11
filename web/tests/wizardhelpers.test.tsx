import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorSummary, FieldError, messageFor, problemsOf } from "@/components/wizard/problems";
import { explainParams, show } from "@/components/wizard/figures";
import { ControlError } from "@/lib/control";
import { LocaleProvider } from "@/lib/i18n";

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
      frozen_at: "2026-10-10",
    });
    expect(params).toMatchObject({
      topics: "2", terms: "5", searches: "5", searchesAll: "15", total: "8", literature: "7",
      operational: "1", floor: "0.80", classes: "2", added: "1", supplied: "separate",
      frozenAt: "2026-10-10",
    });
  });

  it("never rounds the floor away: 0.8 is 0.80, 0.825 stays 0.825", () => {
    expect(explainParams({ acquisition_floor: 0.8 }).floor).toBe("0.80");
    expect(explainParams({ acquisition_floor: 0.825 }).floor).toBe("0.825");
    expect(explainParams({ acquisition_floor: 1 }).floor).toBe("1.00");
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
    render(<FieldError problems={problemsOf(error)} path="topics[0].terms" id="e1" />);
    expect(screen.getByText("add a term").id).toBe("e1");
    expect(screen.queryByRole("alert")).toBeNull(); // the summary is the one announcement
  });

  it("ErrorSummary lists every problem, and a stale revision gets the reload advice", () => {
    render(<LocaleProvider><ErrorSummary error={error} /></LocaleProvider>);
    expect(screen.getByText("use lowercase")).toBeTruthy();
    cleanup();
    render(<LocaleProvider><ErrorSummary error={new ControlError(409, "STALE_REVISION", "saved from revision 1")} /></LocaleProvider>);
    expect(screen.getByRole("alert").textContent).toContain("changed elsewhere");
  });

  const inEnglish = (node: React.ReactElement) => render(<LocaleProvider>{node}</LocaleProvider>);

  it("ErrorSummary gives each known code a sentence of its own, with the server's message beneath", () => {
    const cases: Array<[string, RegExp]> = [
      ["DRAFT_CLOSED", /This draft is closed/],
      ["NAME_TAKEN", /A project with this name already exists/],
      ["INCOMPLETE", /steps 1 to 3 must all be saved/],
      ["UNAUTHORIZED", /Your session has ended/],
      ["PREVIEW_CHANGED", /no longer what would be created/],
      ["STALE_REVISION", /changed elsewhere/],
    ];
    for (const [code, sentence] of cases) {
      inEnglish(<ErrorSummary error={new ControlError(409, code, "the engine's own sentence")} />);
      expect(screen.getByText(sentence)).toBeTruthy();
      expect(screen.getByText("the engine's own sentence")).toBeTruthy();
      cleanup();
    }
  });

  it("ErrorSummary keeps the server's details under a generic validation heading", () => {
    inEnglish(<ErrorSummary error={error} />);
    expect(screen.getByText("Please fix these before continuing:")).toBeTruthy();
    expect(screen.getByText("use lowercase")).toBeTruthy();
  });

  it("ErrorSummary offers Reload only for a stale draft or a changed preview, and it calls back", () => {
    const onReload = vi.fn();
    inEnglish(<ErrorSummary error={new ControlError(409, "STALE_REVISION", "x")} onReload={onReload} />);
    fireEvent.click(screen.getByRole("button", { name: "Reload the draft" }));
    expect(onReload).toHaveBeenCalledTimes(1);
    cleanup();
    inEnglish(<ErrorSummary error={new ControlError(409, "PREVIEW_CHANGED", "x")} onReload={onReload} />);
    expect(screen.getByRole("button", { name: "Reload the draft" })).toBeTruthy();
    cleanup();
    inEnglish(<ErrorSummary error={new ControlError(409, "NAME_TAKEN", "x")} onReload={onReload} />);
    expect(screen.queryByRole("button", { name: "Reload the draft" })).toBeNull();
  });

  it("ErrorSummary takes focus when an error appears", () => {
    inEnglish(<ErrorSummary error={new ControlError(409, "DRAFT_CLOSED", "x")} />);
    expect(document.activeElement).toBe(screen.getByRole("alert"));
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
