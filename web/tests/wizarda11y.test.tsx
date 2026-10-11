// Accessibility of the wizard forms: legends, help linked rather than inside labels, errors linked
// and announced once (by the summary), focus on the new step's heading, the rail's current step.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StepQuestions from "@/components/wizard/StepQuestions";
import StepTopic from "@/components/wizard/StepTopic";
import WizardShell from "@/components/wizard/WizardShell";
import LocaleSwitch from "@/components/LocaleSwitch";
import { setCsrfToken } from "@/lib/control";
import type { DraftState } from "@/lib/control";
import { LocaleProvider } from "@/lib/i18n";

const draft = (steps: DraftState["steps"] = {}): DraftState => ({
  draft_id: "d1", revision: 3, status: "open", steps, advanced: {}, figures: {}, project: null,
  last_failure: null, started_at: "t", updated_at: "t",
});

function mockFetch(status: number, body: unknown) {
  vi.stubGlobal("fetch", () =>
    Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })));
}

beforeEach(() => setCsrfToken("tok"));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  setCsrfToken(null);
});

const wrap = (node: React.ReactElement) =>
  render(<MemoryRouter><LocaleProvider>{node}</LocaleProvider></MemoryRouter>);

const describedText = (el: HTMLElement) =>
  (el.getAttribute("aria-describedby") ?? "").split(" ").filter(Boolean)
    .map((id) => document.getElementById(id)?.textContent ?? "").join(" | ");

describe("topic and question groups", () => {
  it("each topic is a group with a legend, and its Remove button names it", () => {
    wrap(<StepTopic draftId="d1" draft={draft()} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Add a topic" }));
    expect(screen.getByRole("group", { name: "Topic 1" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "Topic 2" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Remove this topic.*Topic 2/ })).toBeTruthy();
  });

  it("a question's legend uses its saved id, else its number", () => {
    const saved = { "2": { revision: 1, data: { questions: [
      { id: "Q02", text: "a?", kind: "effect" }, { text: "b?", kind: "" }] } } };
    wrap(<StepQuestions draftId="d1" draft={draft(saved)} onSaved={vi.fn()} />);
    expect(screen.getByRole("group", { name: "Question Q02" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "Question 2" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Remove this question.*Question Q02/ })).toBeTruthy();
  });
});

describe("help and errors are linked to their input", () => {
  it("help text is outside the label and described-by the input", () => {
    wrap(<StepTopic draftId="d1" draft={draft()} onSaved={vi.fn()} />);
    const name = screen.getByLabelText("Project name");
    expect(describedText(name)).toMatch(/2 to 63 lowercase letters/);
    expect(screen.getByText("Project name").textContent).toBe("Project name");
    expect(name.getAttribute("aria-invalid")).toBeNull();
  });

  it("a field error is linked, marks the input invalid, and only the summary is an alert", async () => {
    mockFetch(422, { error: { code: "VALIDATION", message: "x", details: [
      { path: "name", message: "use lowercase letters" }] } });
    wrap(<StepTopic draftId="d1" draft={draft()} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(screen.getByLabelText("Project name").getAttribute("aria-invalid")).toBe("true"));
    expect(describedText(screen.getByLabelText("Project name"))).toMatch(/use lowercase letters/);
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getAllByRole("alert")[0].tabIndex).toBe(-1);
  });
});

describe("focus and the rail", () => {
  it("a step takes focus on its heading when it appears", () => {
    wrap(<StepTopic draftId="d1" draft={draft()} onSaved={vi.fn()} />);
    expect(document.activeElement).toBe(screen.getByRole("heading", { level: 2, name: "1 · The topic" }));
  });

  it("the current step has screen-reader text, and the others do not", () => {
    wrap(<WizardShell draftId="d1" current={2} saved={[1]} explain={null}>x</WizardShell>);
    const links = screen.getAllByRole("link");
    expect(links[1].getAttribute("aria-current")).toBe("step");
    expect(links[1].textContent).toMatch(/current/);
    expect(links[0].textContent).not.toMatch(/current/);
  });
});

describe("LocaleSwitch", () => {
  it("keeps EN and IT as names and gives the language's name as a tooltip", () => {
    wrap(<LocaleSwitch />);
    expect(screen.getByRole("button", { name: "IT" }).getAttribute("title")).toBe("Italiano");
    expect(screen.getByRole("button", { name: "EN" }).getAttribute("title")).toBe("English");
  });
});
