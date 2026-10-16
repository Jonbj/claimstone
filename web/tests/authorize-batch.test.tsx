import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import OperationsPanel from "@/components/OperationsPanel";
import { SessionProvider } from "@/lib/session";

function json(status: number, body: unknown): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}

function batch(ceiling = 7, awaiting = 2) {
  return {
    batch_id: "b1", stage: "acquire", created_at: "2026-10-16T00:00:00Z",
    operation_ids: ["op2", "op1"], max_total_requests: ceiling,
    selected: 2, remaining_unplanned: 0, awaiting_approval: awaiting,
    skipped: [{ subject: "candidate-3", reason: "outside declared hosts" }],
    units: [
      { operation_id: "op2", subject: "candidate-2", direct_url: null,
        allowed_hosts: ["z.example", "a.example"], allowed_schemes: ["https"],
        max_requests: 4, use_apis: true, retry_classes: [], state: "PLANNED" },
      { operation_id: "op1", subject: "candidate-1", direct_url: null,
        allowed_hosts: ["a.example"], allowed_schemes: ["https"],
        max_requests: 3, use_apis: false, retry_classes: [], state: "PLANNED" },
    ],
  };
}

function panel() {
  return render(<MemoryRouter><SessionProvider>
    <OperationsPanel project="demo" flowId="f1" />
  </SessionProvider></MemoryRouter>);
}

describe("whole batch authorization", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("hides the block when signed out and makes no batch read", async () => {
    const fetched: string[] = [];
    vi.stubGlobal("fetch", (url: string) => {
      fetched.push(url);
      return json(401, { error: { code: "UNAUTHORIZED", message: "sign in" } });
    });
    panel();
    await screen.findByText("Sign in to see and authorize operations");
    expect(screen.queryByRole("region", { name: "Batches awaiting your authorization" })).toBeNull();
    expect(fetched).toEqual(["/control/v1/session"]);
  });

  it("hides the block when no batch awaits approval", async () => {
    let reads = 0;
    vi.stubGlobal("fetch", (url: string) => {
      if (url.endsWith("/session")) return json(200, { operator: {
        id: "o", name: "Operator", role: "admin", must_change_password: false }, csrf_token: "tok" });
      if (url.endsWith("/operations")) return json(200, { flow_id: "f1", operations: [] });
      if (url.endsWith("/batches")) {
        reads += 1;
        return json(200, { flow_id: "f1", batches: [batch(7, 0)] });
      }
      throw new Error(`unexpected ${url}`);
    });
    panel();
    await waitFor(() => expect(reads).toBe(1));
    expect(screen.queryByRole("region", { name: "Batches awaiting your authorization" })).toBeNull();
  });

  it("shows the read plan, confirms it once, and refreshes batches and operations", async () => {
    let batchReads = 0;
    let operationReads = 0;
    const posts: Array<{ url: string; body: unknown; headers: Record<string, string> }> = [];
    let finish: (response: Response) => void = () => {};
    const gate = new Promise<Response>((resolve) => { finish = resolve; });
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      if (url.endsWith("/session")) return json(200, { operator: {
        id: "o", name: "Operator", role: "admin", must_change_password: false }, csrf_token: "tok" });
      if (url.endsWith("/operations")) {
        operationReads += 1;
        return json(200, { flow_id: "f1", operations: [] });
      }
      if (url.endsWith("/batches")) {
        batchReads += 1;
        return json(200, { flow_id: "f1", batches: [batch(7, batchReads === 1 ? 2 : 0)] });
      }
      if (init?.method === "POST") {
        posts.push({ url, body: JSON.parse(String(init.body)), headers: init.headers as Record<string, string> });
        return gate;
      }
      throw new Error(`unexpected ${url}`);
    });
    panel();
    const open = await screen.findByRole("button", { name: "Authorize this batch" });
    const region = screen.getByRole("region", { name: "Batches awaiting your authorization" });
    expect(within(region).getByText("2 of 2 operations await authorization")).toBeTruthy();
    expect(within(region).getByText("at most 7 network requests")).toBeTruthy();
    expect(within(region).getByText("Exact hosts: a.example, z.example")).toBeTruthy();
    expect(within(region).getByText("Uses the open-access lookup APIs")).toBeTruthy();
    fireEvent.click(within(region).getByText("Skipped: 1 (show reasons)"));
    expect(within(region).getByText("candidate-3: outside declared hosts")).toBeTruthy();
    expect(posts).toHaveLength(0);
    fireEvent.click(open);
    const dialog = screen.getByRole("dialog", { name: "Authorize batch" });
    expect(within(dialog).getByText("operations: 2")).toBeTruthy();
    expect(within(dialog).getByText("at most 7 network requests")).toBeTruthy();
    expect(within(dialog).getByText("Exact hosts: a.example, z.example")).toBeTruthy();
    expect(posts).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm authorization" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].url).toBe("/control/v1/p/demo/flows/f1/batches/b1/authorize");
    expect(posts[0].body).toEqual({ operation_ids: ["op2", "op1"], max_total_requests: 7 });
    expect(posts[0].headers["X-CSRF-Token"]).toBe("tok");
    expect(posts[0].headers["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
    const busy = within(dialog).getByRole("button", { name: "Authorizing…" }) as HTMLButtonElement;
    expect(busy.disabled).toBe(true);
    fireEvent.click(busy);
    expect(posts).toHaveLength(1);
    finish(await json(201, { batch: { ...batch(7, 0), authorized_now: 2 } }));
    await waitFor(() => expect(batchReads).toBe(2));
    await waitFor(() => expect(operationReads).toBe(2));
    expect(screen.queryByRole("dialog", { name: "Authorize batch" })).toBeNull();
    expect(posts).toHaveLength(1);
  });

  it("rereads a changed plan and does not resend it", async () => {
    let batchReads = 0;
    let posts = 0;
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      if (url.endsWith("/session")) return json(200, { operator: {
        id: "o", name: "Operator", role: "admin", must_change_password: false }, csrf_token: "tok" });
      if (url.endsWith("/operations")) return json(200, { flow_id: "f1", operations: [] });
      if (url.endsWith("/batches")) {
        batchReads += 1;
        return json(200, { flow_id: "f1", batches: [batch(batchReads === 1 ? 7 : 8)] });
      }
      if (init?.method === "POST") {
        posts += 1;
        return json(409, { error: { code: "PLAN_DIFFERS", message: "read it again" } });
      }
      throw new Error(`unexpected ${url}`);
    });
    panel();
    fireEvent.click(await screen.findByRole("button", { name: "Authorize this batch" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Confirm authorization" }));
    await screen.findByText("The batch plan changed. Review the refreshed plan before authorizing it.");
    await waitFor(() => expect(batchReads).toBe(2));
    expect(posts).toBe(1);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(await screen.findByText("at most 8 network requests")).toBeTruthy();
  });
});
