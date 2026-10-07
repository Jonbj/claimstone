// F3: the "Right now" panel. Authorize sends the limits it showed, only PLANNED has it, an
// unknown cost is never rendered as 0, signed out shows no write control.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import OperationsPanel from "@/components/OperationsPanel";
import { setCsrfToken } from "@/lib/control";
import { SessionProvider } from "@/lib/session";

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}

const LIMITS = { network_requests: 40, model_calls: null, spend_usd: 2.5 };
function op(over: Record<string, unknown>) {
  return {
    operation_id: "op1", stage: "extract", state: "PLANNED",
    state_note: "waiting for a person to authorize this exact plan",
    limits: LIMITS, spent_usd: 0, units_with_unknown_cost: 0, remaining_usd: 2.5,
    units_completed: 0, planned_at: "2026-10-07T10:00:00Z", last_event: "planned",
    last_event_at: "2026-10-07T10:00:00Z", authorized_by: null, worker_last_seen: null,
    worker_note: "the scheduler records no heartbeat yet", ...over,
  };
}

let posts: Array<{ url: string; body: unknown }>;
function mount(signedIn: boolean, operations: unknown[], authorize?: () => Promise<Response>) {
  posts = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    if (url.startsWith("/control/v1/session") && !url.includes("end")) {
      return signedIn
        ? json(200, { operator: { id: "o1", name: "Ada" }, csrf_token: "t" })
        : json(401, { error: { code: "UNAUTHORIZED", message: "no session" } });
    }
    if (url.endsWith("/operations")) return json(200, { flow_id: "f1", operations });
    if (url.endsWith("/authorize") && init?.method === "POST") {
      posts.push({ url, body: JSON.parse(String(init.body)) });
      return authorize ? authorize() : json(201, { authorized: {}, already_authorized: false });
    }
    return json(404, { error: { code: "NOT_FOUND", message: "x" } });
  });
  render(
    <MemoryRouter>
      <SessionProvider><OperationsPanel project="demo" flowId="f1" /></SessionProvider>
    </MemoryRouter>,
  );
}

describe("F3: operations panel", () => {
  beforeEach(() => setCsrfToken(null));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("signed out: says to sign in and offers no write control", async () => {
    mount(false, [op({})]);
    expect(await screen.findByText("Sign in to see and authorize operations")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("authorize posts the exact limits shown, once, then reloads", async () => {
    let release: (r: Response) => void = () => {};
    const gate = new Promise<Response>((resolve) => { release = resolve; });
    mount(true, [op({})], () => gate);
    fireEvent.click(await screen.findByRole("button", { name: "Authorize" }));
    expect(screen.getByRole("dialog").textContent).toContain("network requests: 40");
    const confirm = screen.getByRole("button", { name: "Confirm authorization" });
    fireEvent.click(confirm);
    await waitFor(() => expect(posts.length).toBe(1));
    expect((screen.getByRole("button", { name: "Authorizing…" }) as HTMLButtonElement).disabled).toBe(true);
    expect(posts[0].url).toContain("/operations/op1/authorize");
    expect(posts[0].body).toEqual({ limits: LIMITS });
    release(new Response(JSON.stringify({ authorized: {}, already_authorized: false }),
                         { status: 201, headers: { "Content-Type": "application/json" } }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("shows the server's 409 sentence as given", async () => {
    mount(true, [op({})], () => json(409, {
      error: { code: "PLAN_DIFFERS", message: "the limits sent are not this plan's limits" } }));
    fireEvent.click(await screen.findByRole("button", { name: "Authorize" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm authorization" }));
    expect(await screen.findByText("PLAN_DIFFERS")).toBeTruthy();
    expect(screen.getByText("the limits sent are not this plan's limits")).toBeTruthy();
  });

  it("offers Authorize only for PLANNED; Pause and Resume are disabled with a title", async () => {
    mount(true, [op({ state: "RUNNING_OR_LOCK_HELD", state_note: "a writer holds the project lock" })]);
    expect(await screen.findByText("a writer holds the project lock")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Authorize" })).toBeNull();
    for (const name of ["Pause", "Resume"]) {
      const button = screen.getByRole("button", { name }) as HTMLButtonElement;
      expect(button.disabled).toBe(true);
      expect(button.title).toContain("stopping event");
    }
  });

  it("describes an unknown cost as reserved, never as 0", async () => {
    mount(true, [op({ state: "COMPLETED", units_with_unknown_cost: 3, units_completed: 5, spent_usd: 0.4 })]);
    expect(await screen.findByText(/3 completed unit\(s\) did not report a cost: reserved/)).toBeTruthy();
    expect(screen.queryByText(/not counted as 0$/)).toBeTruthy();
    expect(screen.getByText("the scheduler records no heartbeat yet")).toBeTruthy();
  });
});
