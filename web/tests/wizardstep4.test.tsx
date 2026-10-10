import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StepReview from "@/components/wizard/StepReview";
import { setCsrfToken } from "@/lib/control";
import type { DraftState } from "@/lib/control";
import { LocaleProvider } from "@/lib/i18n";

const step = (data: Record<string, unknown>) => ({ data, revision: 2 });
const full = (): DraftState => ({
  draft_id: "d1", revision: 6, status: "open",
  steps: { "1": step({ name: "news-tone" }), "2": step({}), "3": step({}) },
  advanced: { "sources.yaml": "OLD" }, figures: {}, project: null, last_failure: null,
  started_at: "t", updated_at: "t",
});

const preview = {
  figures: { topics: 1, terms: 2, questions_total: 2, questions_literature: 1, questions_operational: 1,
             classes: ["ACA"], acquisition_floor: 0.8 },
  protocol_sha256: "a".repeat(64), revision: 6,
  files: { "topics.yaml": "T", "questions.yaml": "Q", "sources.yaml": "S" },
};

let calls: Array<{ method: string; url: string; body: unknown }>;
let createStatus = 201;
let previewStatus = 200;
beforeEach(() => {
  previewStatus = 200;
  setCsrfToken("tok");
  calls = [];
  createStatus = 201;
  vi.stubGlobal("fetch", (url: string, init: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : null });
    let body: unknown = preview;
    let status = 200;
    if (url.endsWith("/create")) {
      status = createStatus;
      body = createStatus === 201
        ? { project: "news-tone", protocol_sha256: "b".repeat(64), files: { "topics.yaml": "h" },
            frozen: { registry_version: 1, frozen_at: "2026-10-10", floor_version: 1 } }
        : { error: { code: "NAME_TAKEN", message: "a project named news-tone already exists" } };
    }
    if (url.endsWith("/advanced")) body = { revision: 7 };
    if (url.endsWith("/preview") && previewStatus !== 200) {
      status = previewStatus;
      body = { error: { code: "VALIDATION", message: "frozen_at is not today" } };
    }
    return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  setCsrfToken(null);
});

const mount = (draft = full(), handlers: Partial<{ onCreated: () => void; onChanged: () => void }> = {}) =>
  render(
    <MemoryRouter>
      <LocaleProvider>
        <StepReview draftId="d1" draft={draft} onCreated={handlers.onCreated ?? vi.fn()} onChanged={handlers.onChanged ?? vi.fn()} />
      </LocaleProvider>
    </MemoryRouter>,
  );

describe("StepReview", () => {
  it("asks for steps 1 to 3 first when they are not all saved", () => {
    const draft = { ...full(), steps: { "1": step({}) } };
    mount(draft);
    expect(screen.getByText(/Steps 1 to 3 must be saved/)).toBeTruthy();
    expect(calls).toHaveLength(0);
  });

  it("shows the summary from the server's preview, and the files", async () => {
    mount();
    expect(await screen.findByText(/Project news-tone: 1 topics, 2 questions \(1 literature, 1 operational\)/)).toBeTruthy();
    expect(screen.getAllByText("topics.yaml").length).toBeGreaterThan(0);
  });

  it("Create needs the confirmation, and Start research is disabled with its reason", async () => {
    mount();
    const create = (await screen.findByRole("button", { name: "Create the project" })) as HTMLButtonElement;
    expect(create.disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Start research" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Not available yet/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText(/I understand that the question registry/));
    expect(create.disabled).toBe(false);
  });

  it("creates, reports the result, and sends only the one create request", async () => {
    const onCreated = vi.fn();
    mount(full(), { onCreated });
    fireEvent.click(await screen.findByLabelText(/I understand that the question registry/));
    fireEvent.click(screen.getByRole("button", { name: "Create the project" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    const writes = calls.filter((c) => c.method !== "GET");
    expect(writes.map((c) => c.url)).toEqual(["/control/v1/new/d1/create"]);
    expect(writes[0].body).toEqual({ confirm: true, protocol_sha256: "a".repeat(64) });
    expect(onCreated.mock.calls[0][0].project).toBe("news-tone");
  });

  it("shows the server's refusal when the name was taken meanwhile", async () => {
    createStatus = 409;
    mount();
    fireEvent.click(await screen.findByLabelText(/I understand that the question registry/));
    fireEvent.click(screen.getByRole("button", { name: "Create the project" }));
    expect(await screen.findByText(/already exists/)).toBeTruthy();
  });

  it("Advanced sends only the changed files, keeping earlier overrides", async () => {
    const onChanged = vi.fn();
    mount(full(), { onChanged });
    await screen.findAllByText("sources.yaml");
    fireEvent.click(screen.getByText("Advanced: edit the generated files"));
    fireEvent.change(screen.getByLabelText("topics.yaml"), { target: { value: "T2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save file changes" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    const post = calls.find((c) => c.url.endsWith("/advanced"))!;
    expect(post.body).toEqual({ base_revision: 6, files: { "sources.yaml": "OLD", "topics.yaml": "T2" } });
  });

  it("Reset sends an empty override", async () => {
    mount();
    await screen.findAllByText("sources.yaml");
    fireEvent.click(screen.getByText("Advanced: edit the generated files"));
    fireEvent.click(screen.getByRole("button", { name: "Reset to generated files" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/advanced"))).toBe(true));
    expect(calls.find((c) => c.url.endsWith("/advanced"))!.body).toEqual({ base_revision: 6, files: {} });
  });

  it("when the preview fails with an override present, the error stays and so does a reset", async () => {
    previewStatus = 422;
    const onChanged = vi.fn();
    mount(full(), { onChanged });
    expect(await screen.findByText(/frozen_at is not today/)).toBeTruthy();
    expect(screen.getByText(/reset them so they are generated again/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Reset to generated files" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(calls.find((c) => c.url.endsWith("/advanced"))!.body).toEqual({ base_revision: 6, files: {} });
  });
});
