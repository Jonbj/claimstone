// The scheduler's write routes (claimstone/control.py): exact URL, method and body, the CSRF header,
// and a 409 that is an error and not a sign-out. Only control.ts sends these.
import { afterEach, beforeEach, describe, expect, expectTypeOf, it, vi } from "vitest";
import type { MandateStatus } from "@/lib/scheduler";
import { control, ControlError, setCsrfToken, setUnauthorizedHandler } from "@/lib/control";

interface Call { url: string; method: string; body: unknown; headers: Record<string, string> }
let calls: Call[];
let reply: () => Response;
beforeEach(() => {
  setCsrfToken("tok");
  calls = [];
  reply = () => new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } });
  vi.stubGlobal("fetch", (url: string, init: RequestInit = {}) => {
    calls.push({ url, method: init.method ?? "GET", body: init.body ? JSON.parse(String(init.body)) : null,
                 headers: (init.headers ?? {}) as Record<string, string> });
    return Promise.resolve(reply());
  });
});
afterEach(() => { vi.unstubAllGlobals(); setCsrfToken(null); setUnauthorizedHandler(null); });

const SHA = "a".repeat(64);
const plan = {
  source_flow_id: "flow1",
  rounds: [{ round: "update-2026-11", title: "Update 2026-11", not_before: "2026-11-01T00:00:00Z", expires_at: "2026-12-01T00:00:00Z" }],
  apis: ["openalex"], allowed_hosts: ["api.openalex.org"], max_units_each: 8, max_requests_each: 3, per_query: 25,
};

describe("scheduler write methods", () => {
  it.each([
    ["planPeriodic", () => control.planPeriodic("news", plan), "/control/v1/p/news/periodic-plans", plan],
    ["authorizeSchedule", () => control.authorizeSchedule("news", SHA, { plan_sha256: SHA, max_total_requests: 480 }),
      `/control/v1/p/news/schedules/${SHA}/authorize`, { plan_sha256: SHA, max_total_requests: 480 }],
    ["revokeSchedule", () => control.revokeSchedule("news", SHA, SHA), `/control/v1/p/news/schedules/${SHA}/revoke`, { plan_sha256: SHA }],
    ["planCopyPolicy", () => control.planCopyPolicy("news", { schedule_id: SHA, allowed_hosts: ["h"], source_classes: ["ACA"], max_candidates: 10, max_requests_each: 3, not_before: "a", expires_at: "b" }),
      "/control/v1/p/news/copy-policies", { schedule_id: SHA, allowed_hosts: ["h"], source_classes: ["ACA"], max_candidates: 10, max_requests_each: 3, not_before: "a", expires_at: "b" }],
    ["authorizeCopyPolicy", () => control.authorizeCopyPolicy("news", SHA, { policy_sha256: SHA, max_candidates: 10, max_requests_each: 3, max_total_requests: 30 }),
      `/control/v1/p/news/copy-policies/${SHA}/authorize`, { policy_sha256: SHA, max_candidates: 10, max_requests_each: 3, max_total_requests: 30 }],
    ["revokeCopyPolicy", () => control.revokeCopyPolicy("news", SHA, SHA), `/control/v1/p/news/copy-policies/${SHA}/revoke`, { policy_sha256: SHA }],
    ["enableSeriesMandate", () => control.enableSeriesMandate("news", { schedule_id: SHA, flow_ids: ["f1", "f2"], extract_model: "a", review_model: "b", max_total_local_calls: 100 }),
      "/control/v1/p/news/local-mandates/series", { schedule_id: SHA, flow_ids: ["f1", "f2"], extract_model: "a", review_model: "b", max_total_local_calls: 100 }],
    ["disableMandate", () => control.disableMandate("news", SHA), `/control/v1/p/news/local-mandates/${SHA}/disable`, { mandate_id: SHA }],
    ["createPeriodicExport", () => control.createPeriodicExport("news", SHA, "d".repeat(64)),
      `/control/v1/p/news/schedules/${SHA}/export`, { dossier_id: "d".repeat(64) }],
    ["verifyPeriodicExport", () => control.verifyPeriodicExport("news", "e".repeat(64)),
      `/control/v1/p/news/periodic-exports/${"e".repeat(64)}/verify`, {}],
  ])("%s posts the exact body with the CSRF token and an idempotency key", async (_name, call, url, body) => {
    await call();
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({ url, method: "POST", body });
    expect(calls[0].headers["X-CSRF-Token"]).toBe("tok");
    expect(calls[0].headers["Idempotency-Key"]).toBeTruthy();
  });

  it("percent-encodes the project and the ids", async () => {
    await control.revokeSchedule("a b", "x/y", "z");
    expect(calls[0].url).toBe("/control/v1/p/a%20b/schedules/x%2Fy/revoke");
  });

  it("a 409 PLAN_DIFFERS is a ControlError with its details, not a sign-out", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    reply = () => new Response(JSON.stringify({ error: { code: "PLAN_DIFFERS", message: "schedule hash or request ceiling changed",
      details: [{ path: "max_total_requests", message: "changed" }] } }), { status: 409, headers: { "Content-Type": "application/json" } });
    const error = await control.authorizeSchedule("news", SHA, { plan_sha256: SHA, max_total_requests: 1 }).catch((e) => e);
    expect(error).toBeInstanceOf(ControlError);
    expect(error).toMatchObject({ status: 409, code: "PLAN_DIFFERS", message: "schedule hash or request ceiling changed" });
    expect(error.details).toEqual([{ path: "max_total_requests", message: "changed" }]);
    expect(handler).not.toHaveBeenCalled();
  });

  it("a 409 REFUSED carries the engine's sentence", async () => {
    reply = () => new Response(JSON.stringify({ error: { code: "REFUSED", message: "round cap must cover every frozen discovery query" } }),
      { status: 409, headers: { "Content-Type": "application/json" } });
    const error = await control.planPeriodic("news", plan).catch((e) => e);
    expect(error).toMatchObject({ code: "REFUSED", message: "round cap must cover every frozen discovery query" });
  });

  it("the download is a path for a browser navigation, never a request", () => {
    expect(control.periodicExportDownloadPath("news", "abc")).toBe("/control/v1/p/news/periodic-exports/abc/download");
    expect(calls).toHaveLength(0);
  });

  it("types the answers of the mandate routes as the server sends them", () => {
    // autopilot.enable_series returns {mandate_id, mandate}; autopilot.disable returns {mandate_id, state}
    type Enabled = Awaited<ReturnType<typeof control.enableSeriesMandate>>;
    type Disabled = Awaited<ReturnType<typeof control.disableMandate>>;
    expectTypeOf<Enabled>().toEqualTypeOf<{ mandate_id: string; mandate: MandateStatus["mandate"] }>();
    expectTypeOf<Disabled>().toEqualTypeOf<{ mandate_id: string; state: string }>();
  });
});
