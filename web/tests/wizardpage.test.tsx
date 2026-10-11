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
let stepUnauthorized = false;
let stepStale = false;
let draftReadFails = false;
let discardStatus = 200;
let discardBodies: unknown[] = [];
let created = false;
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
    if (url === "/control/v1/new/d1/discard") {
      discardBodies.push(JSON.parse(String(init.body)));
      return discardStatus === 200 ? json(200, { revision: 4, status: "discarded" })
        : json(409, { error: { code: "STALE_REVISION", message: "saved from revision 3" } });
    }
    if (url === "/control/v1/new/d1" && draftReadFails) return json(500, { error: { code: "INTERNAL", message: "boom" } });
    if (url === "/control/v1/new/d1/create") {
      created = true;
      return json(201, { project: "news-tone", protocol_sha256: "b".repeat(64), files: { "topics.yaml": "h" },
        frozen: { registry_version: 1, frozen_at: "2026-10-10", floor_version: 1 } });
    }
    if (url === "/control/v1/new/d1") return json(200, draftBody);
    if (url === "/control/v1/new/d1/preview") {
      return json(200, { figures: { terms: 50, topics: 9 }, protocol_sha256: "a".repeat(64), revision: 1,
        files: { "topics.yaml": "T", "questions.yaml": "Q", "sources.yaml": "S" } });
    }
    if (url === "/control/v1/new/d1/steps/1" && stepStale) {
      return json(409, { error: { code: "STALE_REVISION", message: "saved from revision 1" } });
    }
    if (url === "/control/v1/new/d1/steps/1" && stepUnauthorized) {
      return json(401, { error: { code: "UNAUTHORIZED", message: "session ended" } });
    }
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
  stepUnauthorized = false;
  stepStale = false;
  draftReadFails = false;
  discardStatus = 200;
  discardBodies = [];
  created = false;
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
    expect(screen.getByText("Steps saved: 2 of 3")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open the project" }).getAttribute("href")).toBe("/p/done-one");
  });

  it("starting a project creates a draft and opens step 1", async () => {
    mount("/new");
    fireEvent.click(await screen.findByRole("button", { name: "Start a new project" }));
    await waitFor(() => expect(where).toBe("/new/d9/1"));
  });

  it("Discard asks first, sends the draft's revision once, and refreshes the list", async () => {
    mount("/new");
    fireEvent.click(await screen.findByRole("button", { name: "Discard" }));
    expect(discardBodies).toHaveLength(0);
    expect(screen.getByText("Discard this draft?")).toBeTruthy();
    const yes = screen.getByRole("button", { name: "Yes, discard" });
    fireEvent.click(yes);
    fireEvent.click(yes); // a second click while the first is in flight sends nothing
    await waitFor(() => expect(discardBodies).toHaveLength(1));
    expect(discardBodies[0]).toEqual({ base_revision: 3 });
    await waitFor(() => expect(requested.filter((r) => r === "GET /control/v1/new").length).toBe(2));
    expect(discardBodies).toHaveLength(1);
  });

  it("answering No sends nothing and brings the Discard button back", async () => {
    mount("/new");
    fireEvent.click(await screen.findByRole("button", { name: "Discard" }));
    fireEvent.click(screen.getByRole("button", { name: "No, keep it" }));
    expect(screen.getByRole("button", { name: "Discard" })).toBeTruthy();
    expect(discardBodies).toHaveLength(0);
  });

  it("a refused discard shows the server's error", async () => {
    discardStatus = 409;
    mount("/new");
    fireEvent.click(await screen.findByRole("button", { name: "Discard" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, discard" }));
    expect(await screen.findByText("saved from revision 3")).toBeTruthy();
    expect(screen.getByText("news-tone")).toBeTruthy();
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

  it("a session that ends mid-save keeps the typed text, and a re-check restores saving", async () => {
    mount("/new/d1/1");
    await screen.findByText("1 · The topic");
    fireEvent.change(screen.getByLabelText(/Project name/), { target: { value: "news-tone" } });
    fireEvent.change(screen.getByLabelText(/^Topic\b/), { target: { value: "News" } });
    stepUnauthorized = true;
    signedIn = false;
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    expect(await screen.findByText(/Your session ended/)).toBeTruthy();
    expect((screen.getByLabelText(/Project name/) as HTMLInputElement).value).toBe("news-tone");
    expect((screen.getByLabelText(/^Topic\b/) as HTMLInputElement).value).toBe("News");
    const link = screen.getByRole("link", { name: "Sign in in another tab" });
    expect(link.getAttribute("href")).toBe("/login?next=%2Fnew%2Fd1%2F1");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");

    stepUnauthorized = false;
    signedIn = true;
    fireEvent.click(screen.getByRole("button", { name: "I have signed in: check again" }));
    await waitFor(() => expect(screen.queryByText(/Your session ended/)).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(where).toBe("/new/d1/2"));
  });

  it("a still-signed-out re-check keeps the banner and does not throw", async () => {
    mount("/new/d1/1");
    await screen.findByText("1 · The topic");
    stepUnauthorized = true;
    signedIn = false;
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await screen.findByText(/Your session ended/);
    fireEvent.click(screen.getByRole("button", { name: "I have signed in: check again" }));
    await waitFor(() => expect(requested.filter((r) => r.includes("/session")).length).toBeGreaterThan(1));
    expect(screen.getByText(/Your session ended/)).toBeTruthy();
  });

  it("active Advanced edits are announced on every step, with a link to step 4", async () => {
    draftBody = { ...baseDraft, advanced: { "sources.yaml": "x" } };
    mount("/new/d1/2");
    expect(await screen.findByText(/Advanced edits are active/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Go to step 4" }).getAttribute("href")).toBe("/new/d1/4");
  });

  it("no notice without Advanced edits", async () => {
    mount("/new/d1/2");
    await screen.findByText("2 · The questions");
    expect(screen.queryByText(/Advanced edits are active/)).toBeNull();
  });

  it("a stale save offers Reload, which fetches the draft again", async () => {
    mount("/new/d1/1");
    await screen.findByText("1 · The topic");
    stepStale = true;
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    const reload = await screen.findByRole("button", { name: "Reload the draft" });
    const before = requested.filter((r) => r === "GET /control/v1/new/d1").length;
    fireEvent.click(reload);
    await waitFor(() => expect(requested.filter((r) => r === "GET /control/v1/new/d1").length).toBe(before + 1));
  });

  it("the preview's figures are quoted on step 4 only, and gone when the step changes", async () => {
    const step = (name: string) => ({ data: { name }, revision: 1 });
    draftBody = { ...baseDraft, steps: { "1": step("news-tone"), "2": step("x"), "3": step("y") },
      figures: { "1": { terms: 2, topics: 1 } } };
    mount("/new/d1/4");
    expect(await screen.findByText(/Project: news-tone · Topics: 9/)).toBeTruthy();
    await waitFor(() => expect(screen.getAllByText(/Project: news-tone/).length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole("link", { name: /^1\s*Topic/ }));
    expect(await screen.findByText("1 · The topic")).toBeTruthy();
    expect(screen.getByText(/topics: 1, terms: 2/)).toBeTruthy();
    expect(screen.queryByText(/50 terms/)).toBeNull();
  });

  it("a failed reload after a successful create keeps the success screen", async () => {
    const step = (name: string) => ({ data: { name }, revision: 1 });
    draftBody = { ...baseDraft, steps: { "1": step("news-tone"), "2": step("x"), "3": step("y") } };
    mount("/new/d1/4");
    fireEvent.click(await screen.findByLabelText(/I understand that the question registry/));
    draftReadFails = true;
    fireEvent.click(screen.getByRole("button", { name: "Create the project" }));
    expect(await screen.findByText("Project created")).toBeTruthy();
    await waitFor(() => expect(created).toBe(true));
    await waitFor(() => expect(requested.filter((r) => r === "GET /control/v1/new/d1").length).toBeGreaterThan(1));
    expect(screen.getByText("Project created")).toBeTruthy();
    expect(screen.getByText(/frozen at version 1 on 2026-10-10 \(UTC date\)/)).toBeTruthy();
    expect(screen.queryByText("boom")).toBeNull();
  });

  it("shows the reason the last creation attempt was refused, as the server wrote it", async () => {
    draftBody = { ...baseDraft, last_failure: "the generated files did not round-trip" };
    mount("/new/d1/1");
    expect(await screen.findByText(/The last attempt to create the project was refused/)).toBeTruthy();
    expect(screen.getByText("the generated files did not round-trip")).toBeTruthy();
  });

  it("reads the step strictly: 2abc, 04 and 0 are all step 1", async () => {
    for (const bad of ["2abc", "04", "0", "5"]) {
      cleanup();
      mount(`/new/d1/${bad}`);
      expect(await screen.findByText("1 · The topic")).toBeTruthy();
    }
  });
});
