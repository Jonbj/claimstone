// F6: the states pass. One failed or empty state per page that had none: Projects (empty), Project
// (empty and unlisted), Flow, Claim and Source (failed). Today, Question, Export, Admin and Login
// have theirs in their own test files.
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/control";
import { SessionProvider } from "@/lib/session";
import ClaimPage from "@/pages/ClaimPage";
import FlowOverviewPage from "@/pages/FlowOverviewPage";
import IndexPage from "@/pages/IndexPage";
import ProjectPage from "@/pages/ProjectPage";
import SourcePage from "@/pages/SourcePage";

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}
const failure = (code: string, message: string) =>
  json(500, { api_version: 1, error: { code, message } });

function mount(path: string, routes: Record<string, (url: string) => Promise<Response>>) {
  vi.stubGlobal("fetch", (url: string) => {
    if (url.startsWith("/control/v1/session")) {
      return json(401, { error: { code: "UNAUTHORIZED", message: "no" } });
    }
    if (url.includes("/poll")) return json(200, { api_version: 1, ledgers: {} });
    for (const [fragment, handler] of Object.entries(routes)) {
      if (url.includes(fragment)) return handler(url);
    }
    return json(404, { api_version: 1, error: { code: "NOT_FOUND", message: `no route ${url}` } });
  });
  render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider>
        <Routes>
          <Route path="/projects" element={<IndexPage />} />
          <Route path="/p/:project" element={<ProjectPage />} />
          <Route path="/p/:project/f/:sel" element={<FlowOverviewPage kind="f" />} />
          <Route path="/p/:project/f/:sel/claim/:cid" element={<ClaimPage kind="f" />} />
          <Route path="/p/:project/f/:sel/source/:key" element={<SourcePage kind="f" />} />
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  );
}

const card = (name: string, flows: unknown[] = [], unbound: unknown[] = []) => ({
  name, config: "OK", config_error: null, registry_version: 1, registry_sha256: "h",
  registry_drift: null, integrity_error: null, flows, unbound_selectors: unbound,
});

describe("F6: states pass", () => {
  beforeEach(() => setCsrfToken(null));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("Projects: an empty list is said, not left blank", async () => {
    mount("/projects", { "/api/v1/projects": () => json(200, { api_version: 1, projects: [] }) });
    expect(await screen.findByText("The server lists no project.")).toBeTruthy();
  });

  it("Project: no flows and no legacy rounds is said", async () => {
    mount("/p/demo", {
      "/api/v1/projects/demo/integrity": () => failure("INTERNAL", "integrity down"),
      "/api/v1/projects/demo/activity": () => json(200, { api_version: 1, project: "demo", activity: [] }),
      "/api/v1/projects": () => json(200, { api_version: 1, projects: [card("demo")] }),
    });
    expect(await screen.findByText("No flows and no legacy rounds.")).toBeTruthy();
    expect(await screen.findByText("no rows yet")).toBeTruthy();
  });

  it("Project: a name the API does not list is named as such", async () => {
    mount("/p/ghost", {
      "/api/v1/projects/ghost/integrity": () => failure("NOT_FOUND", "no project ghost"),
      "/api/v1/projects/ghost/activity": () => failure("NOT_FOUND", "no project ghost"),
      "/api/v1/projects": () => json(200, { api_version: 1, projects: [card("demo")] }),
    });
    expect(await screen.findByText("the API's project list does not name this project")).toBeTruthy();
  });

  it("Flow: a failed overview is a named error, not a blank page", async () => {
    mount("/p/demo/f/f1", { "/overview": () => failure("LEDGER_CORRUPT", "claims.jsonl line 9") });
    expect(await screen.findByText("LEDGER_CORRUPT")).toBeTruthy();
    expect(screen.getByText("claims.jsonl line 9")).toBeTruthy();
  });

  it("Claim: a failed lineage is a named error and the heading stays", async () => {
    mount("/p/demo/f/f1/claim/c1", { "/claims/": () => failure("INTERNAL", "lineage unreadable") });
    expect(await screen.findByText("lineage unreadable")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("c1");
  });

  it("Source: a failed dossier is a named error and the heading stays", async () => {
    mount("/p/demo/f/f1/source/k1", { "/sources/": () => failure("INTERNAL", "dossier unreadable") });
    expect(await screen.findByText("dossier unreadable")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("k1");
  });
});
