import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import RetryPolicyPanel from "@/components/RetryPolicyPanel";
import { control, setCsrfToken } from "@/lib/control";

const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), {
  status, headers: { "Content-Type": "application/json" },
}));

const emptyHosts = { pending_candidates: 0, candidate_hosts: [], refused_hosts: [],
  retryable_classes: [], plain_http_candidates: 0, suggested_max_requests_each: 3 };

function policy(state: "PLANNED" | "AUTHORIZED" | "REVOKED" = "PLANNED") {
  return {
    policy_id: "p1", state,
    policy: {
      version: 1, project: "demo", flow_id: "f1", selector: null,
      allowed_hosts: ["a.example", "b.example"], max_retries: 20, max_attempts_each: 3,
      max_requests_each: 10, max_total_requests: 200, use_apis: true, base_delay_hours: 6,
      max_delay_hours: 48, not_before: "2026-10-17T00:00:00Z", expires_at: "2026-11-16T23:59:59Z",
      code_sha256: "c".repeat(64), protocol_sha256: "p".repeat(64),
    },
    reserved_retries: 2, remaining_retries: 18, reserved_requests: 40, events: [],
  };
}

describe("retry policy control methods", () => {
  beforeEach(() => setCsrfToken("tok"));
  afterEach(() => { vi.unstubAllGlobals(); setCsrfToken(null); });

  it("posts the exact request shapes for the four methods", async () => {
    const calls: Array<{ url: string; method: string; body: unknown }> = [];
    vi.stubGlobal("fetch", (url: string, init: RequestInit = {}) => {
      calls.push({ url, method: init.method ?? "GET", body: init.body ? JSON.parse(String(init.body)) : null });
      return init.method === "GET" ? json(200, { flow_id: "f1", policies: [] }) : json(201, {});
    });
    const body = { allowed_hosts: ["a.example"], max_retries: 20, max_attempts_each: 3,
      max_requests_each: 10, use_apis: false, base_delay_hours: 6, max_delay_hours: 48,
      expires_at: "2026-11-16T23:59:59Z" };
    await control.planRetryPolicy("demo", "f1", body);
    await control.retryPolicies("demo", "f1");
    await control.authorizeRetryPolicy("demo", "p1", { policy_sha256: "p1", max_retries: 20, max_requests_each: 10, max_total_requests: 200 });
    await control.revokeRetryPolicy("demo", "p1");
    expect(calls.map((c) => [c.method, c.url])).toEqual([
      ["POST", "/control/v1/p/demo/flows/f1/retry-policies"],
      ["GET", "/control/v1/p/demo/flows/f1/retry-policies"],
      ["POST", "/control/v1/p/demo/retry-policies/p1/authorize"],
      ["POST", "/control/v1/p/demo/retry-policies/p1/revoke"],
    ]);
    expect(calls[0].body).toEqual(body);
    expect(calls[2].body).toEqual({ policy_sha256: "p1", max_retries: 20, max_requests_each: 10, max_total_requests: 200 });
    expect(calls[3].body).toEqual({ policy_sha256: "p1" });
  });
});

describe("retry policy plan form", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); setCsrfToken(null); });

  it("shows the defaults and pre-fills hosts from the record only", async () => {
    setCsrfToken("tok");
    vi.stubGlobal("fetch", (url: string) => {
      if (url.endsWith("/retry-policies")) return json(200, { flow_id: "f1", policies: [] });
      if (url.endsWith("/acquire-hosts")) return json(200, {
        pending_candidates: 2, candidate_hosts: [{ host: "example.org", candidates: 2 }],
        refused_hosts: [{ host: "used.example", candidates: 1 }], retryable_classes: [],
        plain_http_candidates: 0, suggested_max_requests_each: 3,
      });
      return json(404, {});
    });
    render(<RetryPolicyPanel project="demo" flowId="f1" />);
    await screen.findByRole("button", { name: "Plan retries" });
    expect((screen.getByLabelText("Max retries") as HTMLInputElement).value).toBe("20");
    expect((screen.getByLabelText("Attempts per candidate") as HTMLInputElement).value).toBe("3");
    expect((screen.getByLabelText("Requests each") as HTMLInputElement).value).toBe("10");
    expect((screen.getByLabelText("First wait (hours)") as HTMLInputElement).value).toBe("6");
    expect((screen.getByLabelText("Longest wait (hours)") as HTMLInputElement).value).toBe("48");
    expect((screen.getByLabelText("Expires on") as HTMLInputElement).value).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    await waitFor(() => expect((screen.getByLabelText("Exact hosts, one per line") as HTMLTextAreaElement).value).toBe("example.org\nused.example"));
    expect(screen.getByText(/never longer than 48 h/)).toBeTruthy();
  });

  it("refuses an empty host list before any POST", async () => {
    setCsrfToken("tok");
    const posts: string[] = [];
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      if (init?.method === "POST") { posts.push(url); return json(201, {}); }
      if (url.endsWith("/retry-policies")) return json(200, { flow_id: "f1", policies: [] });
      if (url.endsWith("/acquire-hosts")) return json(200, emptyHosts);
      return json(404, {});
    });
    render(<RetryPolicyPanel project="demo" flowId="f1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Plan retries" }));
    expect(screen.getByRole("alert").textContent).toContain("Enter at least one exact host");
    expect(posts).toHaveLength(0);
  });

  it("adds the resolver hosts when the API lookups are ticked and sends one POST", async () => {
    setCsrfToken("tok");
    const writes: Array<Record<string, unknown>> = [];
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      if (init?.method === "POST") { writes.push(JSON.parse(String(init.body))); return json(201, {}); }
      if (url.endsWith("/retry-policies")) return json(200, { flow_id: "f1", policies: [] });
      if (url.endsWith("/acquire-hosts")) return json(200, emptyHosts);
      return json(404, {});
    });
    render(<RetryPolicyPanel project="demo" flowId="f1" />);
    fireEvent.change(await screen.findByLabelText("Exact hosts, one per line"), { target: { value: "example.org" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Also ask the Unpaywall and OpenAlex APIs" }));
    fireEvent.click(screen.getByRole("button", { name: "Plan retries" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({
      allowed_hosts: ["example.org", "api.unpaywall.org", "api.openalex.org"],
      use_apis: true, max_retries: 20, max_attempts_each: 3, max_requests_each: 10,
      base_delay_hours: 6, max_delay_hours: 48,
    });
    expect(writes[0]).toHaveProperty("expires_at");
  });

  it("shows a busy state and sends exactly one POST on submit", async () => {
    setCsrfToken("tok");
    let posts = 0;
    let finish: (r: Response) => void = () => {};
    const gate = new Promise<Response>((resolve) => { finish = resolve; });
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      if (init?.method === "POST") { posts += 1; return gate; }
      if (url.endsWith("/retry-policies")) return json(200, { flow_id: "f1", policies: [] });
      if (url.endsWith("/acquire-hosts")) return json(200, {
        pending_candidates: 1, candidate_hosts: [{ host: "example.org", candidates: 1 }],
        refused_hosts: [], retryable_classes: [], plain_http_candidates: 0, suggested_max_requests_each: 3,
      });
      return json(404, {});
    });
    render(<RetryPolicyPanel project="demo" flowId="f1" />);
    await screen.findByRole("button", { name: "Plan retries" });
    await waitFor(() => expect((screen.getByLabelText("Exact hosts, one per line") as HTMLTextAreaElement).value).toBe("example.org"));
    fireEvent.click(screen.getByRole("button", { name: "Plan retries" }));
    const busyButton = await screen.findByRole("button", { name: "Planning…" }) as HTMLButtonElement;
    expect(busyButton.disabled).toBe(true);
    fireEvent.click(busyButton);
    expect(posts).toBe(1);
    finish(await json(201, {}));
    await screen.findByRole("button", { name: "Plan retries" });
    expect(posts).toBe(1);
  });

  it("shows the server's refusal verbatim and does not retry", async () => {
    setCsrfToken("tok");
    let posts = 0;
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      if (init?.method === "POST") { posts += 1; return json(409, { error: { code: "REFUSED", message: "host in excluded_hosts" } }); }
      if (url.endsWith("/retry-policies")) return json(200, { flow_id: "f1", policies: [] });
      if (url.endsWith("/acquire-hosts")) return json(200, {
        pending_candidates: 1, candidate_hosts: [{ host: "example.org", candidates: 1 }],
        refused_hosts: [], retryable_classes: [], plain_http_candidates: 0, suggested_max_requests_each: 3,
      });
      return json(404, {});
    });
    render(<RetryPolicyPanel project="demo" flowId="f1" />);
    await waitFor(() => expect((screen.getByLabelText("Exact hosts, one per line") as HTMLTextAreaElement).value).toBe("example.org"));
    fireEvent.click(screen.getByRole("button", { name: "Plan retries" }));
    expect(await screen.findByText("host in excluded_hosts")).toBeTruthy();
    expect(posts).toBe(1);
  });
});

describe("retry policy list and authorization", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); setCsrfToken(null); });

  it("lists a planned policy with its reservations", async () => {
    setCsrfToken("tok");
    vi.stubGlobal("fetch", (url: string) => {
      if (url.endsWith("/retry-policies")) return json(200, { flow_id: "f1", policies: [policy()] });
      if (url.endsWith("/acquire-hosts")) return json(200, emptyHosts);
      return json(404, {});
    });
    render(<RetryPolicyPanel project="demo" flowId="f1" />);
    expect(await screen.findByText("State: PLANNED · p1")).toBeTruthy();
    expect(screen.getByText("Hosts: a.example, b.example")).toBeTruthy();
    expect(screen.getByText("Retries: 18 / 20")).toBeTruthy();
    expect(screen.getByText("Requests reserved: 40 / 200")).toBeTruthy();
    expect(screen.getByText("First wait: 6 h")).toBeTruthy();
    expect(screen.getByText("Longest wait: 48 h")).toBeTruthy();
    expect(screen.getByText("Attempts per candidate: 3")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Authorize" })).toBeTruthy();
  });

  it("authorizes with the as-read values after confirming the exact terms", async () => {
    setCsrfToken("tok");
    const writes: Array<{ url: string; body: Record<string, unknown> }> = [];
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      if (url.endsWith("/retry-policies")) return json(200, { flow_id: "f1", policies: [policy()] });
      if (url.endsWith("/acquire-hosts")) return json(200, emptyHosts);
      if (init?.method === "POST") { writes.push({ url, body: JSON.parse(String(init.body)) }); return json(201, {}); }
      return json(404, {});
    });
    render(<RetryPolicyPanel project="demo" flowId="f1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Authorize" }));
    const dialog = screen.getByRole("dialog", { name: "Authorize this retry policy?" });
    expect(within(dialog).getByText("Hosts: a.example, b.example")).toBeTruthy();
    expect(within(dialog).getByText("Max retries: 20")).toBeTruthy();
    expect(within(dialog).getByText("Requests each: 10")).toBeTruthy();
    expect(within(dialog).getByText("Total request ceiling: 200")).toBeTruthy();
    expect(within(dialog).getByText("Attempts per candidate: 3")).toBeTruthy();
    expect(within(dialog).getByText("First wait: 6 h")).toBeTruthy();
    expect(within(dialog).getByText("Longest wait: 48 h")).toBeTruthy();
    expect(within(dialog).getByText("API lookups: on")).toBeTruthy();
    expect(writes).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0].url).toBe("/control/v1/p/demo/retry-policies/p1/authorize");
    expect(writes[0].body).toEqual({ policy_sha256: "p1", max_retries: 20, max_requests_each: 10, max_total_requests: 200 });
  });

  it("rereads on PLAN_DIFFERS and does not resend", async () => {
    setCsrfToken("tok");
    let reads = 0;
    let posts = 0;
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      if (url.endsWith("/retry-policies")) { reads += 1; return json(200, { flow_id: "f1", policies: [policy()] }); }
      if (url.endsWith("/acquire-hosts")) return json(200, emptyHosts);
      if (init?.method === "POST") { posts += 1; return json(409, { error: { code: "PLAN_DIFFERS", message: "read it again" } }); }
      return json(404, {});
    });
    render(<RetryPolicyPanel project="demo" flowId="f1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Authorize" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Confirm" }));
    await screen.findByText("The retry policy plan changed. Review the refreshed plan before authorizing it.");
    await waitFor(() => expect(reads).toBe(2));
    expect(posts).toBe(1);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("revokes an authorized policy after confirming, and hides the plan form", async () => {
    setCsrfToken("tok");
    const writes: Array<{ url: string; body: unknown }> = [];
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      if (url.endsWith("/retry-policies")) return json(200, { flow_id: "f1", policies: [policy("AUTHORIZED")] });
      if (url.endsWith("/acquire-hosts")) return json(200, emptyHosts);
      if (init?.method === "POST") { writes.push({ url, body: JSON.parse(String(init.body)) }); return json(200, {}); }
      return json(404, {});
    });
    render(<RetryPolicyPanel project="demo" flowId="f1" />);
    await screen.findByRole("button", { name: "Revoke" });
    expect(screen.queryByRole("button", { name: "Plan retries" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));
    fireEvent.click(within(screen.getByRole("dialog", { name: "Revoke this retry policy?" })).getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toEqual({ url: "/control/v1/p/demo/retry-policies/p1/revoke", body: { policy_sha256: "p1" } });
  });

  it("planning never authorizes: the only POST is the plan", async () => {
    setCsrfToken("tok");
    let policies: unknown[] = [];
    const writes: Array<{ url: string }> = [];
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        writes.push({ url });
        policies = [policy("PLANNED")];
        return json(201, {});
      }
      if (url.endsWith("/retry-policies")) return json(200, { flow_id: "f1", policies });
      if (url.endsWith("/acquire-hosts")) return json(200, {
        pending_candidates: 1, candidate_hosts: [{ host: "example.org", candidates: 1 }],
        refused_hosts: [], retryable_classes: [], plain_http_candidates: 0, suggested_max_requests_each: 3,
      });
      return json(404, {});
    });
    render(<RetryPolicyPanel project="demo" flowId="f1" />);
    await waitFor(() => expect((screen.getByLabelText("Exact hosts, one per line") as HTMLTextAreaElement).value).toBe("example.org"));
    fireEvent.click(screen.getByRole("button", { name: "Plan retries" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0].url).toBe("/control/v1/p/demo/flows/f1/retry-policies");
    expect(writes.map((w) => w.url)).not.toContain("/authorize");
  });
});
