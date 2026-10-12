import { describe, expect, it } from "vitest";
import { overviewOfSeries, workerAlert } from "@/lib/scheduler";
import type { MandateStatus, PolicyStatus, ScheduleStatus, Worker } from "@/lib/scheduler";

const schedule = (state: string, over: Partial<ScheduleStatus> = {}): ScheduleStatus => ({
  schedule_id: "s".repeat(64), state: state as ScheduleStatus["state"],
  plan: { version: 1, project: "p", max_total_requests: 480, entries: [
    { batch_id: "b1", operation_ids: ["o1"], flow_id: "f1", stage: "discover", units: [], max_total_requests: 240, not_before: "2026-11-01T00:00:00+00:00", expires_at: "2026-11-30T00:00:00+00:00" },
    { batch_id: "b2", operation_ids: ["o2"], flow_id: "f2", stage: "discover", units: [], max_total_requests: 240, not_before: "2026-12-01T00:00:00+00:00", expires_at: "2026-12-31T00:00:00+00:00" }] },
  events: [], ...over });
const policy = (state: string, scheduleId: string): PolicyStatus => ({
  policy_id: "p".repeat(64), state: state as PolicyStatus["state"],
  policy: { project: "p", schedule_id: scheduleId, flow_ids: ["f1", "f2"], allowed_hosts: ["h"], source_classes: ["ACA"], max_candidates: 10, max_requests_each: 3, max_total_requests: 30, not_before: "a", expires_at: "b" },
  reserved_candidates: 0, remaining_candidates: 10, reserved_requests: 0, events: [] });
const mandate = (state: string, scheduleId: string | null): MandateStatus => ({
  mandate_id: "m".repeat(64), state: state as MandateStatus["state"], flow_id: "f1", flow_ids: ["f1", "f2"],
  disabled_by: null, reserved_local_calls: 0, remaining_local_calls: 100, pending_batches: [],
  mandate: { schedule_id: scheduleId ?? undefined, extract_model: "a", review_model: "b", max_total_local_calls: 100 } });

describe("overviewOfSeries", () => {
  it("attaches a policy and a mandate to their schedule by schedule_id and nothing else", () => {
    const s = schedule("AUTHORIZED");
    const view = overviewOfSeries(s, [policy("AUTHORIZED", s.schedule_id), policy("PLANNED", "x")],
      [mandate("ENABLED", s.schedule_id), mandate("ENABLED", null)]);
    expect(view.policies.map((p) => p.state)).toEqual(["AUTHORIZED"]);
    expect(view.mandates).toHaveLength(1);
    expect(view.rounds).toBe(2);
    expect(view.windowStart).toBe("2026-11-01T00:00:00+00:00");
    expect(view.windowEnd).toBe("2026-12-31T00:00:00+00:00");
  });
  it("keeps the server's state word untouched", () => {
    expect(overviewOfSeries(schedule("SOMETHING_NEW"), [], []).state).toBe("SOMETHING_NEW");
  });
});

describe("workerAlert", () => {
  const w = (state: string): Worker => ({ worker_key: "supervisor", state: state as Worker["state"], last_seen_at: null, phase: null, age_seconds: null });
  it.each([["STALE", true], ["UNKNOWN", true], ["STOPPED", true], ["NOT_STARTED", true], ["ALIVE", false]])(
    "%s -> alert %s", (state, alert) => expect(workerAlert(w(state))).toBe(alert));
});
