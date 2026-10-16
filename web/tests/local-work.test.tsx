import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import PlanBatchForm from "@/components/PlanBatchForm";
import WorkLocallyPanel from "@/components/WorkLocallyPanel";
import { setCsrfToken } from "@/lib/control";

const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), {
  status, headers: { "Content-Type": "application/json" },
}));

describe("second acquisition plan", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); setCsrfToken(null); });

  it("prefills the suggested ceiling, requires a retry reason, and sends retry keys only when selected", async () => {
    setCsrfToken("tok");
    const writes: Array<Record<string, unknown>> = [];
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      if (url.endsWith("/acquire-hosts")) return json(200, {
        pending_candidates: 2, candidate_hosts: [{ host: "example.org", candidates: 2 }],
        refused_hosts: [], retryable_classes: [{ failure_class: "REQUEST_LIMIT_REACHED", candidates: 1 }],
        plain_http_candidates: 1, suggested_max_requests_each: 5,
      });
      if (init?.method === "POST") {
        writes.push(JSON.parse(String(init.body)));
        return json(201, { batch_id: "b1", operation_ids: [], units: [] });
      }
      return json(404, {});
    });
    render(<PlanBatchForm project="demo" flowId="f1" hasCandidates onPlanned={() => {}} />);
    fireEvent.change(screen.getByLabelText("Stage"), { target: { value: "acquire" } });
    await screen.findByText(/candidate URLs start with http/);
    await waitFor(() => expect((screen.getByLabelText("Max requests each") as HTMLInputElement).value).toBe("5"));
    fireEvent.click(screen.getByRole("button", { name: "Plan batch" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).not.toHaveProperty("retry_classes");
    expect(writes[0]).not.toHaveProperty("retry_reason");
    fireEvent.click(screen.getByRole("checkbox", { name: "REQUEST_LIMIT_REACHED (1)" }));
    fireEvent.click(screen.getByRole("button", { name: "Plan batch" }));
    expect(writes).toHaveLength(1);
    expect(screen.getByRole("alert").textContent).toContain("Give a reason");
    fireEvent.change(screen.getByLabelText("Why"), { target: { value: "Second attempt after raising the cap" } });
    fireEvent.click(screen.getByRole("button", { name: "Plan batch" }));
    await waitFor(() => expect(writes).toHaveLength(2));
    expect(writes[1]).toMatchObject({ max_requests_each: 5,
      retry_classes: ["REQUEST_LIMIT_REACHED"], retry_reason: "Second attempt after raising the cap" });
  });

  it("keeps a person's request ceiling when the suggestion arrives", async () => {
    let resolve: (value: Response) => void = () => {};
    vi.stubGlobal("fetch", () => new Promise<Response>((done) => { resolve = done; }));
    render(<PlanBatchForm project="demo" flowId="f1" hasCandidates onPlanned={() => {}} />);
    fireEvent.change(screen.getByLabelText("Stage"), { target: { value: "acquire" } });
    fireEvent.change(screen.getByLabelText("Max requests each"), { target: { value: "7" } });
    resolve(await json(200, { pending_candidates: 1, candidate_hosts: [], refused_hosts: [],
      retryable_classes: [], plain_http_candidates: 1, suggested_max_requests_each: 5 }));
    await screen.findByText(/candidate URLs start with http/);
    expect((screen.getByLabelText("Max requests each") as HTMLInputElement).value).toBe("7");
  });
});

describe("one-flow local mandate", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); setCsrfToken(null); });

  it("confirms exact terms, sends one POST with transport headers, and shows refusal", async () => {
    setCsrfToken("tok");
    const writes: Array<{ url: string; init: RequestInit }> = [];
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      if (url.includes("/scheduler?")) return json(200, { local_mandates: [], archive: {
        revision: "r", next_cursor: null } });
      if (init?.method === "POST") {
        writes.push({ url, init });
        return json(409, { error: { code: "REFUSED", message: "flow preview blocked" } });
      }
      return json(404, {});
    });
    render(<WorkLocallyPanel project="demo" flowId="f1" />);
    await screen.findByRole("button", { name: "Enable local work" });
    expect((screen.getByLabelText("Max local model calls") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Max local model calls") as HTMLInputElement).placeholder).toBe("100");
    fireEvent.change(screen.getByLabelText("Extraction model"), { target: { value: "model-a" } });
    fireEvent.change(screen.getByLabelText("Review model"), { target: { value: "model-a" } });
    expect(screen.getByText("The extraction and review models must differ.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Review model"), { target: { value: "model-b" } });
    fireEvent.change(screen.getByLabelText("Max local model calls"), { target: { value: "25" } });
    fireEvent.click(screen.getByRole("button", { name: "Enable local work" }));
    expect(writes).toHaveLength(0);
    const dialog = screen.getByRole("dialog", { name: "Confirm local mandate" });
    expect(within(dialog).getByText("Extraction model: model-a")).toBeTruthy();
    expect(within(dialog).getByText("Review model: model-b")).toBeTruthy();
    expect(within(dialog).getByText("Max local model calls: 25")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText("flow preview blocked")).toBeTruthy();
    expect(writes).toHaveLength(1);
    expect(writes[0].url).toBe("/control/v1/p/demo/flows/f1/local-mandates");
    expect(JSON.parse(String(writes[0].init.body))).toEqual({ flow_id: "f1", extract_model: "model-a",
      review_model: "model-b", max_total_local_calls: 25 });
    expect(writes[0].init.headers).toMatchObject({ "X-CSRF-Token": "tok",
      "Content-Type": "application/json", "Idempotency-Key": expect.any(String) });
  });

  it("reads all scheduler pages, shows an active mandate, and confirms disable", async () => {
    setCsrfToken("tok");
    const writes: Array<{ url: string; body: unknown }> = [];
    const mandate = { mandate_id: "m1", state: "ENABLED", flow_id: "f1", flow_ids: ["f1"],
      reserved_local_calls: 3, remaining_local_calls: 97, pending_batches: [], disabled_by: null,
      mandate: { extract_model: "a", review_model: "b", max_total_local_calls: 100 } };
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      if (url.includes("/scheduler?")) return json(200, { local_mandates: url.includes("cursor=") ? [mandate] : [],
        archive: { revision: "r", next_cursor: url.includes("cursor=") ? null : "next" } });
      if (init?.method === "POST") {
        writes.push({ url, body: JSON.parse(String(init.body)) });
        return json(200, { mandate_id: "m1", state: "DISABLED" });
      }
      return json(404, {});
    });
    render(<WorkLocallyPanel project="demo" flowId="f1" />);
    expect(await screen.findByText("Mandate state: ENABLED · m1")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Enable local work" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Disable" }));
    expect(writes).toHaveLength(0);
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toEqual({ url: "/control/v1/p/demo/local-mandates/m1/disable",
      body: { mandate_id: "m1" } });
  });
});
