import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import OperationsPanel from "@/components/OperationsPanel";
import { SessionProvider } from "@/lib/session";

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status,
    headers: { "Content-Type": "application/json" } }));
}

describe("network batch planning", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("uses the checked API hosts, shows the ceiling, refreshes PLANNED and never authorizes", async () => {
    let reads = 0;
    const writes: Array<{ url: string; body: unknown }> = [];
    let release: (response: Response) => void = () => {};
    const gate = new Promise<Response>((resolve) => { release = resolve; });
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      if (url === "/control/v1/session") return json(200, { operator: {
        id: "o", name: "Operator", role: "admin", must_change_password: false }, csrf_token: "tok" });
      if (url.endsWith("/operations")) {
        reads += 1;
        return json(200, { flow_id: "f1", operations: reads > 1 ? [{
          operation_id: "op1", stage: "discover", state: "PLANNED", state_note: "waiting",
          limits: { network_requests: 3, model_calls: null, spend_usd: null },
          spent_usd: 0, units_with_unknown_cost: 0, remaining_usd: null,
          units_completed: 0, planned_at: null, last_event: "planned", last_event_at: null,
          authorized_by: null, worker_last_seen: null, worker_note: "idle",
        }] : [] });
      }
      if (init?.method === "POST") {
        writes.push({ url, body: JSON.parse(String(init.body)) });
        return gate;
      }
      return json(404, { error: { code: "NOT_FOUND", message: "unknown" } });
    });
    render(<MemoryRouter><SessionProvider><OperationsPanel project="demo" flowId="f1"
      namedRound hasCandidates /></SessionProvider></MemoryRouter>);
    await screen.findByRole("button", { name: "Plan batch" });
    expect(screen.getByText("At most 15 requests, to: api.openalex.org")).toBeTruthy();
    fireEvent.click(screen.getByRole("checkbox", { name: "crossref" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "openalex" }));
    expect(screen.getByText("At most 15 requests, to: api.crossref.org")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Plan batch" }));
    await waitFor(() => expect(writes.length).toBe(1));
    expect(writes[0]).toEqual({ url: "/control/v1/p/demo/flows/f1/batches", body: {
      stage: "discover", apis: ["crossref"], allowed_hosts: ["api.crossref.org"],
      max_units: 5, max_requests_each: 3, per_query: 10,
    } });
    expect((screen.getByRole("button", { name: "Planning…" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Planning…" }));
    expect(writes).toHaveLength(1);
    release(await json(201, { batch_id: "b1", operation_ids: ["op1"], units: [], selected: 1,
      max_total_requests: 3 }));
    await waitFor(() => expect(reads).toBe(2));
    expect(await screen.findByRole("button", { name: "Authorize" })).toBeTruthy();
    expect(writes).toHaveLength(1);
  });

  it("accepts exact acquisition hosts, refuses wildcards, and shows server refusal", async () => {
    const writes: unknown[] = [];
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      if (url === "/control/v1/session") return json(200, { operator: {
        id: "o", name: "Operator", role: "admin", must_change_password: false }, csrf_token: "tok" });
      if (url.endsWith("/operations")) return json(200, { flow_id: "f1", operations: [] });
      if (init?.method === "POST") {
        writes.push(JSON.parse(String(init.body)));
        return json(409, { error: { code: "REFUSED", message: "the candidates changed" } });
      }
      return json(404, { error: { code: "NOT_FOUND", message: "unknown" } });
    });
    render(<MemoryRouter><SessionProvider><OperationsPanel project="demo" flowId="f1"
      namedRound hasCandidates /></SessionProvider></MemoryRouter>);
    await screen.findByRole("button", { name: "Plan batch" });
    fireEvent.change(screen.getByLabelText("Stage"), { target: { value: "acquire" } });
    fireEvent.change(screen.getByLabelText("Exact hosts, one per line"), {
      target: { value: "*.example.org" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Plan batch" }));
    expect(writes).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Exact hosts, one per line"), {
      target: { value: "example.org\nrepo.example.org" },
    });
    expect(screen.getByText("At most 15 requests, to: example.org, repo.example.org")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Plan batch" }));
    expect(await screen.findByText("the candidates changed")).toBeTruthy();
    expect(writes).toEqual([{ stage: "acquire", apis: [],
      allowed_hosts: ["example.org", "repo.example.org"], max_units: 5,
      max_requests_each: 3, per_query: 25 }]);
  });
});
