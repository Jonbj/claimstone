import type { ReactElement } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StepQuestions from "@/components/wizard/StepQuestions";
import StepTopic from "@/components/wizard/StepTopic";
import { setCsrfToken } from "@/lib/control";
import type { DraftState } from "@/lib/control";
import { LocaleProvider } from "@/lib/i18n";

const draft = (steps: DraftState["steps"] = {}): DraftState => ({
  draft_id: "d1", revision: 3, status: "open", steps, advanced: {}, figures: {}, project: null,
  last_failure: null, started_at: "t", updated_at: "t",
});

let calls: Array<{ url: string; body: unknown }>;
function mockFetch(status: number, body: unknown) {
  calls = [];
  vi.stubGlobal("fetch", (url: string, init: RequestInit) => {
    calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
    return Promise.resolve(new Response(JSON.stringify(body), {
      status, headers: { "Content-Type": "application/json" },
    }));
  });
}

beforeEach(() => setCsrfToken("tok"));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  setCsrfToken(null);
});

const wrap = (node: ReactElement) => render(<LocaleProvider>{node}</LocaleProvider>);

describe("StepTopic", () => {
  it("sends the trimmed terms and the draft's revision, then reports the figures", async () => {
    mockFetch(200, { revision: 4, data: {}, figures: { topics: 1, terms: 2 } });
    const onSaved = vi.fn();
    wrap(<StepTopic draftId="d1" draft={draft()} onSaved={onSaved} />);
    fireEvent.change(screen.getByLabelText(/Project name/), { target: { value: "news-tone" } });
    fireEvent.change(screen.getByLabelText(/^Topic/), { target: { value: "News" } });
    fireEvent.change(screen.getByLabelText(/Search terms/), { target: { value: "a b\n\n  c d  \n" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(calls[0].url).toBe("/control/v1/new/d1/steps/1");
    expect(calls[0].body).toEqual({ base_revision: 3, data: {
      name: "news-tone", description: "", topics: [{ label: "News", terms: ["a b", "c d"] }] } });
    expect(onSaved).toHaveBeenCalledWith({ step: 1, revision: 4, figures: { topics: 1, terms: 2 } });
  });

  it("shows the server's field error under the field and keeps what was typed", async () => {
    mockFetch(422, { error: { code: "VALIDATION", message: "name: bad", details: [
      { path: "name", message: "use lowercase letters" }] } });
    const onSaved = vi.fn();
    wrap(<StepTopic draftId="d1" draft={draft()} onSaved={onSaved} />);
    fireEvent.change(screen.getByLabelText(/Project name/), { target: { value: "Bad Name" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(screen.getAllByText("use lowercase letters").length).toBeGreaterThan(0));
    expect(onSaved).not.toHaveBeenCalled();
    expect((screen.getByLabelText(/Project name/) as HTMLInputElement).value).toBe("Bad Name");
  });

  it("starts from the saved draft, ids included, and can add and remove topics", () => {
    const saved = { "1": { revision: 2, data: { name: "news-tone", description: "scope",
      topics: [{ id: "T01", label: "News", terms: ["a", "b"] }] } } };
    wrap(<StepTopic draftId="d1" draft={draft(saved)} onSaved={vi.fn()} />);
    expect((screen.getByLabelText(/Project name/) as HTMLInputElement).value).toBe("news-tone");
    expect((screen.getByLabelText(/Search terms/) as HTMLTextAreaElement).value).toBe("a\nb");
    fireEvent.click(screen.getByRole("button", { name: "Add a topic" }));
    expect(screen.getAllByLabelText(/Search terms/)).toHaveLength(2);
    fireEvent.click(screen.getAllByRole("button", { name: /^Remove this topic/ })[1]);
    expect(screen.getAllByLabelText(/Search terms/)).toHaveLength(1);
  });
});

describe("StepQuestions", () => {
  it("sends text and kind, never a default kind, and glosses the chosen kind", async () => {
    mockFetch(200, { revision: 5, data: {}, figures: { questions_total: 1 } });
    const onSaved = vi.fn();
    wrap(<StepQuestions draftId="d1" draft={draft()} onSaved={onSaved} />);
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Does it work?" } });
    expect((screen.getByLabelText("Kind") as HTMLSelectElement).value).toBe("");
    fireEvent.change(screen.getByLabelText("Kind"), { target: { value: "operational" } });
    expect(screen.getByText(/no literature verdict applies/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(calls[0].body).toEqual({ base_revision: 3, data: {
      questions: [{ text: "Does it work?", kind: "operational" }] } });
  });

  it("the server's refusal of an empty kind appears under the question", async () => {
    mockFetch(422, { error: { code: "VALIDATION", message: "x", details: [
      { path: "questions[0].kind", message: "choose one of effect, heterogeneity" }] } });
    wrap(<StepQuestions draftId="d1" draft={draft()} onSaved={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "x?" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(screen.getAllByText(/choose one of effect/).length).toBeGreaterThan(0));
  });
});
