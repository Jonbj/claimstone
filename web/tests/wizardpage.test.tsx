import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/control";
import { LocaleProvider } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";
import NewProjectsPage from "@/pages/NewProjectsPage";
import WizardPage from "@/pages/WizardPage";

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

let requested: string[];
let signedIn = true;
let draftBody: Record<string, unknown>;
const baseDraft = {
  draft_id: "d1", revision: 1, status: "open", steps: {}, advanced: {}, figures: {}, project: null,
  last_failure: null, started_at: "t", updated_at: "t",
};

let where = "";
function Where() {
  where = useLocation().pathname;
  return null;
}

function mount(path: string) {
  requested = [];
  vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
  vi.stubGlobal("fetch", (url: string, init: RequestInit) => {
    requested.push(`${init?.method ?? "GET"} ${url}`);
    if (url.startsWith("/control/v1/session")) {
      return signedIn ? json(200, { operator: { id: "o1", name: "Ada" }, csrf_token: "t" })
        : json(401, { error: { code: "UNAUTHORIZED", message: "no session" } });
    }
    if (url === "/control/v1/new" && init?.method === "POST") return json(201, { draft_id: "d9", revision: 1 });
    if (url === "/control/v1/new") return json(200, { drafts: [
      { draft_id: "d1", status: "open", revision: 3, steps_saved: [1, 2], project_name: "news-tone", project: null, updated_at: "t" },
      { draft_id: "d2", status: "created", revision: 9, steps_saved: [1, 2, 3], project_name: "done-one", project: "done-one", updated_at: "t" },
    ] });
    if (url === "/control/v1/new/d1") return json(200, draftBody);
    if (url === "/control/v1/new/d1/steps/1") return json(200, { revision: 2, data: {}, figures: { topics: 1, terms: 2 } });
    return json(404, { error: { code: "NOT_FOUND", message: "no" } });
  });
  render(
    <MemoryRouter initialEntries={[path]}>
      <LocaleProvider>
        <SessionProvider>
          <Where />
          <Routes>
            <Route path="/new" element={<NewProjectsPage />} />
            <Route path="/new/:draft/:step" element={<WizardPage />} />
            <Route path="/login" element={<p>login page</p>} />
          </Routes>
        </SessionProvider>
      </LocaleProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  setCsrfToken(null);
  signedIn = true;
  draftBody = { ...baseDraft };
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("NewProjectsPage", () => {
  it("lists my drafts with their state, and a created one links to its project", async () => {
    mount("/new");
    expect(await screen.findByText("news-tone")).toBeTruthy();
    expect(screen.getByText("2 of 3 steps saved")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open the project" }).getAttribute("href")).toBe("/p/done-one");
  });

  it("starting a project creates a draft and opens step 1", async () => {
    mount("/new");
    fireEvent.click(await screen.findByRole("button", { name: "Start a new project" }));
    await waitFor(() => expect(where).toBe("/new/d9/1"));
  });

  it("signed out it offers the sign-in link and shows no draft", async () => {
    signedIn = false;
    mount("/new");
    expect(await screen.findByText(/Sign in to create a project/)).toBeTruthy();
    expect(requested.some((r) => r === "GET /control/v1/new")).toBe(false);
  });
});

describe("WizardPage", () => {
  it("shows step 1 with its explanation, and moves to step 2 after a save", async () => {
    mount("/new/d1/1");
    expect(await screen.findByText("1 · The topic")).toBeTruthy();
    expect(screen.getByText("What Claimstone will do")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/Project name/), { target: { value: "news-tone" } });
    fireEvent.change(screen.getByLabelText(/^Topic\b/), { target: { value: "News" } });
    fireEvent.change(screen.getByLabelText(/Search terms/), { target: { value: "a b" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(where).toBe("/new/d1/2"));
    expect(requested).toContain("POST /control/v1/new/d1/steps/1");
  });

  it("a discarded draft says so and shows no form", async () => {
    draftBody = { ...baseDraft, status: "discarded" };
    mount("/new/d1/1");
    expect(await screen.findByText(/This draft was discarded/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save and continue" })).toBeNull();
  });

  it("a created draft shows the created screen, with nothing started", async () => {
    draftBody = { ...baseDraft, status: "created", project: "news-tone" };
    mount("/new/d1/4");
    expect(await screen.findByText("Project created")).toBeTruthy();
    expect(screen.getByText(/Nothing has started/)).toBeTruthy();
  });

  it("an unknown step number falls back to step 1", async () => {
    mount("/new/d1/99");
    expect(await screen.findByText("1 · The topic")).toBeTruthy();
  });

  it("calls no stage, network or model route — only the draft routes", async () => {
    mount("/new/d1/1");
    await screen.findByText("1 · The topic");
    expect(requested.every((r) => r.includes("/control/v1/new") || r.includes("/control/v1/session"))).toBe(true);
  });
});
