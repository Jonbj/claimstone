// F3: the flow page. Header links, the operations panel for flows only, no write control on
// an unbound selector, and none for a signed-out visitor.
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/control";
import { SessionProvider } from "@/lib/session";
import FlowOverviewPage from "@/pages/FlowOverviewPage";
import flowOverview from "./fixtures/projects/example-news-and-returns/flows/0df548e3743689e1a0dd099da697aee4842e8a573f1225a8da13fec128a248cd/overview.json";
import unboundOverview from "./fixtures/projects/example-news-and-returns/unbound/-/overview.json";

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}

const flowId = String((flowOverview.flow as { flow_id: string }).flow_id);
let requested: string[];

function mount(path: string, signedIn: boolean) {
  requested = [];
  vi.stubGlobal("fetch", (url: string) => {
    requested.push(url);
    if (url.startsWith("/control/v1/session")) {
      return signedIn
        ? json(200, { operator: { id: "o1", name: "Ada" }, csrf_token: "t" })
        : json(401, { error: { code: "UNAUTHORIZED", message: "no session" } });
    }
    if (url.endsWith("/operations")) return json(200, { flow_id: flowId, operations: [] });
    if (url.includes("/overview")) {
      return json(200, url.includes("/unbound/") || url.includes("/u/") ? unboundOverview : flowOverview);
    }
    if (url.includes("/poll")) return json(200, { api_version: 1, signature: "s" });
    return json(404, { error: { code: "NOT_FOUND", message: "x" } });
  });
  render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider>
        <Routes>
          <Route path="/p/:project/f/:sel" element={<FlowOverviewPage kind="f" />} />
          <Route path="/p/:project/u/:sel" element={<FlowOverviewPage kind="u" />} />
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  );
}

describe("F3: flow journey page", () => {
  beforeEach(() => {
    setCsrfToken(null);
    // recharts' ResponsiveContainer needs it; jsdom has none.
    vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("links Add material, Decisions, Export and Activity, and shows Right now", async () => {
    mount("/p/demo/f/sel1", true);
    const href = async (name: string) =>
      (await screen.findByRole("link", { name })).getAttribute("href");
    expect(await href("Add material")).toBe("/p/demo/f/sel1/material");
    expect(await href("Decisions")).toBe("/p/demo/f/sel1/decisions");
    expect(await href("Export")).toBe("/p/demo/f/sel1/export");
    expect(await href("Activity")).toBe("/p/demo#activity");
    expect(await screen.findByText("No operation is planned for this flow.")).toBeTruthy();
  });

  it("signed out: the panel asks for a session and offers no button", async () => {
    mount("/p/demo/f/sel1", false);
    expect(await screen.findByText("Sign in to see and authorize operations")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Authorize|Pause|Resume/ })).toBeNull();
    expect(requested.some((u) => u.endsWith("/operations"))).toBe(false);
  });

  it("an unbound selector has no operations panel, no write link and no operations request", async () => {
    mount("/p/demo/u/-", true);
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByText("Right now")).toBeNull();
    expect(screen.queryByRole("link", { name: /Add material|Decisions|Export/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Authorize|Pause|Resume/ })).toBeNull();
    expect(requested.some((u) => u.includes("/operations"))).toBe(false);
  });
});
