// Leaving the page with typing that was never saved asks the browser to warn (beforeunload).
// In-app navigation is not guarded: a router blocker needs a data router, and these tests mount
// a MemoryRouter; the draft is saved on the server only by an explicit Save.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StepQuestions from "@/components/wizard/StepQuestions";
import StepReview from "@/components/wizard/StepReview";
import StepSources from "@/components/wizard/StepSources";
import StepTopic from "@/components/wizard/StepTopic";
import { setCsrfToken } from "@/lib/control";
import type { DraftState } from "@/lib/control";
import { LocaleProvider } from "@/lib/i18n";

const draft: DraftState = {
  draft_id: "d1", revision: 3, status: "open", steps: {}, advanced: {}, figures: {}, project: null,
  last_failure: null, started_at: "t", updated_at: "t",
};
const template = {
  id: "general", label: "General", default_floor: 0.8,
  classes: [{ id: "ACA", name: "peer-reviewed", weight_hint: "highest", notes: "n" }],
  excluded_hosts: [], notation_presets: [{ id: "none", label: "None" }],
};

beforeEach(() => {
  setCsrfToken("tok");
  vi.stubGlobal("fetch", (url: string) =>
    Promise.resolve(new Response(JSON.stringify(url.includes("/new-templates/") ? template
      : { revision: 4, data: {}, figures: {} }), { status: 200, headers: { "Content-Type": "application/json" } })));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  setCsrfToken(null);
});

function leaving(): boolean {
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  return event.defaultPrevented;
}
const wrap = (node: React.ReactElement) =>
  render(<MemoryRouter><LocaleProvider>{node}</LocaleProvider></MemoryRouter>);

describe("beforeunload", () => {
  it("is silent for an untouched form, warns after typing, and is silent again after a save", async () => {
    wrap(<StepTopic draftId="d1" draft={draft} onSaved={vi.fn()} />);
    expect(leaving()).toBe(false);
    fireEvent.change(screen.getByLabelText("Project name"), { target: { value: "news-tone" } });
    expect(leaving()).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(leaving()).toBe(false));
  });

  it("typing back to the saved value is clean again", () => {
    wrap(<StepTopic draftId="d1" draft={draft} onSaved={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Project name"), { target: { value: "a" } });
    fireEvent.change(screen.getByLabelText("Project name"), { target: { value: "" } });
    expect(leaving()).toBe(false);
  });

  it("the handler is removed when the form goes away", () => {
    const { unmount } = wrap(<StepTopic draftId="d1" draft={draft} onSaved={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Project name"), { target: { value: "x" } });
    unmount();
    expect(leaving()).toBe(false);
  });

  it("covers the questions and the sources forms too", async () => {
    wrap(<StepQuestions draftId="d1" draft={draft} onSaved={vi.fn()} />);
    expect(leaving()).toBe(false);
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "x?" } });
    expect(leaving()).toBe(true);
    cleanup();
    wrap(<StepSources draftId="d1" draft={draft} onSaved={vi.fn()} />);
    fireEvent.click(await screen.findByLabelText(/ACA/));
    expect(leaving()).toBe(true);
  });

  it("unsaved Advanced edits on step 4 warn too", async () => {
    const step = (data: Record<string, unknown>) => ({ data, revision: 1 });
    const full: DraftState = { ...draft, steps: { "1": step({ name: "n" }), "2": step({}), "3": step({}) } };
    vi.stubGlobal("fetch", () => Promise.resolve(new Response(JSON.stringify({
      figures: {}, protocol_sha256: "a".repeat(64), revision: 3,
      files: { "topics.yaml": "T", "questions.yaml": "Q", "sources.yaml": "S" } }),
    { status: 200, headers: { "Content-Type": "application/json" } })));
    wrap(<StepReview draftId="d1" draft={full} onCreated={vi.fn()} onChanged={vi.fn()} />);
    await screen.findByRole("heading", { level: 2, name: "4 · Review and create" });
    expect(leaving()).toBe(false);
    fireEvent.change(screen.getByLabelText("topics.yaml"), { target: { value: "T2" } });
    expect(leaving()).toBe(true);
  });
});
