// Builders and a fetch stub shared by the scheduler page tests. Shapes follow
// web/src/lib/scheduler.ts, which was checked against claimstone/control.py.
import { vi } from "vitest";
import type {
  MandateStatus, PolicyStatus, ScheduleStatus, SchedulerIndex, Worker,
} from "@/lib/scheduler";

export const SID = "a".repeat(64);
export const OTHER = "b".repeat(64);

export function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}

export const err = (status: number, code: string, message: string) =>
  json(status, { error: { code, message } });

export const ME = { id: "ada", name: "Ada Lovelace", role: "operator", must_change_password: false };

export function entry(n: number, window: [string, string]) {
  return {
    batch_id: `b${n}`, operation_ids: [`o${n}`], flow_id: `flow${n}`, stage: "discover",
    units: [{}, {}, {}], max_total_requests: 240, not_before: window[0], expires_at: window[1],
  };
}

export const PAST: [string, string][] = [
  ["2025-01-01T00:00:00+00:00", "2025-01-31T00:00:00+00:00"],
  ["2025-02-01T00:00:00+00:00", "2025-02-28T00:00:00+00:00"],
];
export const FUTURE: [string, string][] = [
  ["2099-01-01T00:00:00+00:00", "2099-01-31T00:00:00+00:00"],
  ["2099-02-01T00:00:00+00:00", "2099-02-28T00:00:00+00:00"],
];

export function schedule(state: string, over: Partial<ScheduleStatus> = {}, windows = PAST,
                         id = SID): ScheduleStatus {
  return {
    schedule_id: id, state: state as ScheduleStatus["state"],
    plan: { version: 1, project: "news", max_total_requests: 480,
            entries: windows.map((w, i) => entry(i + 1, w)) },
    events: [], ...over,
  };
}

export const authorized = (name = "Bea Operator") => ({
  event: "authorized", at: "2026-10-01T09:30:00+00:00",
  identity: { signer_auth: "password", operator: "bea", name },
});

export function policy(state: string, scheduleId = SID, over: Partial<PolicyStatus> = {}): PolicyStatus {
  return {
    policy_id: "p".repeat(64), state: state as PolicyStatus["state"],
    policy: { project: "news", schedule_id: scheduleId, flow_ids: ["flow1", "flow2"],
      allowed_hosts: ["europepmc.org", "arxiv.org"], source_classes: ["ACADEMIC", "PREPRINT"],
      max_candidates: 10, max_requests_each: 3, max_total_requests: 30,
      not_before: "2025-01-01T00:00:00+00:00", expires_at: "2025-03-01T00:00:00+00:00" },
    reserved_candidates: 2, remaining_candidates: 8, reserved_requests: 4, events: [], ...over,
  };
}

export function mandate(state: string, scheduleId: string | null = SID,
                        over: Partial<MandateStatus> = {}): MandateStatus {
  return {
    mandate_id: "m".repeat(64), state: state as MandateStatus["state"], flow_id: "flow1",
    flow_ids: ["flow1", "flow2"], disabled_by: null, reserved_local_calls: 5,
    remaining_local_calls: 95, pending_batches: [],
    mandate: { ...(scheduleId ? { schedule_id: scheduleId } : {}), extract_model: "qwen-extract",
               review_model: "qwen-review", max_total_local_calls: 100 },
    ...over,
  };
}

export const worker = (key: string, state: string, over: Partial<Worker> = {}): Worker => ({
  worker_key: key, state: state as Worker["state"], last_seen_at: "2026-10-12T10:00:00+00:00",
  phase: "IDLE", age_seconds: 4, ...over,
});

export function indexPage(over: Partial<SchedulerIndex> = {}, nextCursor: string | null = null,
                          offset = 0): SchedulerIndex {
  return {
    project: "news", schedules: [], copy_policies: [], local_mandates: [],
    workers: { supervisor: worker("supervisor", "ALIVE"), operations: worker("operations", "ALIVE"),
               mandates: {} },
    archive: { limit: 25, offset, revision: "rev", next_cursor: nextCursor,
               total: { schedules: 0, copy_policies: 0, local_mandates: 0 } },
    ...over,
  };
}

// The values admissibility.py really produces: `basis` is "confirmed" once normalisation has started
// and "obtained" before; `blocking` holds codes such as awaiting_discovery, awaiting_classification,
// awaiting_acquire, normalize_not_started, awaiting_normalize, orphan_acquisitions, ledger_repairs;
// `final` is `not blocking`.
export function admission(over: Record<string, unknown> = {}) {
  return { round: "r1", found: 8, classified: 8, attempted: 8, obtained: 4, confirmed: 3,
    awaiting_normalize: 1, blocking: ["awaiting_normalize"], final: false, basis: "confirmed", rate: 0.375,
    rate_upper: 0.5, by_class: {}, classes_below_floor: [], class_floors: {},
    status: "INSUFFICIENT_ACQUISITION", floor: 0.8, floor_version: 1, ...over };
}

export function dossier(over: Record<string, unknown> = {}, rounds?: unknown[]) {
  return {
    api_version: 1, schedule_id: SID, state: "WAITING_FOR_SCHEDULE",
    blockers: ["SCHEDULE_OR_ROUND_INCOMPLETE"], profiles: [], human_decisions: [],
    snapshot_sha256: "s".repeat(64), finalized_dossier_id: null, finalized_at: null,
    snapshot_stale: false, needs_finalization: false, history_count: 0, verdict: null,
    audit: { schedule_id: SID, schedule_state: "PLANNED", ancestor_rounds: [],
      rounds: rounds ?? [
        { round: "Round one", flow_id: "flow1", binding_state: "CURRENT",
          not_before: PAST[0][0], expires_at: PAST[0][1], operations: { COMPLETED: 3 },
          successful_queries: 2, planned_queries: 3, admission: admission() },
        { round: "Round two", flow_id: "flow2", binding_state: "CURRENT",
          not_before: PAST[1][0], expires_at: PAST[1][1], operations: {},
          successful_queries: 0, planned_queries: 3, admission: admission({ found: 0, confirmed: 0, rate: null }) },
      ],
      cumulative_admission: admission(), ready_for_evidence_review: false, verdict: null },
    ...over,
  };
}

export const SHA = (c: string) => c.repeat(64);

/** A cumulative profile row as `synthesize.preview` sends it (only the fields the page shows). */
// `state` is null for a profile with results and NO_VERIFIED_CLAIM for one without (evidence.py);
// `coverage.sources` counts the sources that speak to the question, out of `examined`.
export function profile(questionId: string, over: Record<string, unknown> = {}) {
  return { question_id: questionId, profile_sha256: SHA("c"), state: null, provisional: false, blocking: [],
    direction_count: { yes: 4, no: 1 }, coverage: { sources: 10, examined: 12 }, ...over };
}

/** A human-decision row: `verdict` is null until a person has signed. */
export function decision(questionId: string, over: Record<string, unknown> = {}) {
  return { question_id: questionId, verdict: null, stale: false, stored_profile_stale: false,
    unavailable: "", ...over };
}

/** A dossier whose audit and question rows are given by the caller. */
export function resultDossier(over: Record<string, unknown> = {}, audit: Record<string, unknown> = {}) {
  const base = dossier();
  return { ...base, ...over, audit: { ...base.audit, ...audit } };
}

export interface Routes {
  signedIn?: boolean;
  /** Index answers, in order; the last repeats. */
  index?: Array<() => Promise<Response>>;
  /** Answers the index by URL instead of by order; wins over `index`. */
  indexFor?: (url: string) => Promise<Response>;
  schedule?: () => Promise<Response>;
  dossier?: () => Promise<Response>;
  /** Single-object reads (`GET …/copy-policies/{id}`, `…/local-mandates/{id}`); 404 when absent. */
  policyRead?: (id: string) => Promise<Response>;
  mandateRead?: (id: string) => Promise<Response>;
  /** `unbound_selectors` slugs of the project `news` in the project list. */
  unbound?: string[];
  /** Bound flows of the project in the project list (flow_id and selector; the rest is defaulted). */
  flows?: Array<{ flow_id: string; selector: { round: string | null; manifest_only: boolean };
                  title?: string | null; selector_label?: string; binding_state?: string }>;
  /** Unbound round selectors of the project (their rounds already have candidates). */
  unboundRounds?: string[];
  /** `GET …/flows/{id}/overview`: the journey's topics are all the new-series page reads. */
  overview?: (flowId: string) => Promise<Response>;
  /** Any POST, by URL and parsed body; 404 when absent. */
  post?: (url: string, body: unknown) => Promise<Response>;
}

/** Every request the stub has seen, with its method and parsed body. */
export const sent: Array<{ url: string; method: string; body: unknown }> = [];

export const topic = (id: string, terms: string[]) => ({ id, label: id, terms });
export const overviewOf = (topics: Array<{ id: string; label: string; terms: string[] }>,
                           byClass: Record<string, unknown> = {}) =>
  ({ api_version: 1, journey: { topics }, floor_panel: { by_class: byClass, disclosure: "", overall: {}, sentences: [] } });

/** Stubs fetch by URL and records every request's URL. */
export function stub(routes: Routes): string[] {
  const urls: string[] = [];
  let served = 0;
  sent.length = 0;
  vi.stubGlobal("fetch", (url: string, init: RequestInit = {}) => {
    urls.push(url);
    sent.push({ url, method: init.method ?? "GET", body: init.body ? JSON.parse(String(init.body)) : null });
    if (init.method === "POST" && !url.startsWith("/control/v1/session")) {
      return (routes.post ?? (() => err(404, "NOT_FOUND", "no")))(url, init.body ? JSON.parse(String(init.body)) : null);
    }
    if (url.startsWith("/control/v1/session")) {
      return routes.signedIn === false
        ? err(401, "UNAUTHORIZED", "not signed in")
        : json(200, { operator: ME, csrf_token: "t" });
    }
    if (url.startsWith("/control/v1/p/news/scheduler")) {
      if (routes.indexFor) return routes.indexFor(url);
      const list = routes.index ?? [() => json(200, indexPage())];
      return list[Math.min(served++, list.length - 1)]();
    }
    if (url.startsWith("/control/v1/p/news/copy-policies/")) {
      return (routes.policyRead ?? (() => err(404, "NOT_FOUND", "no such copy policy")))(url.split("/").pop()!);
    }
    if (url.startsWith("/control/v1/p/news/local-mandates/")) {
      return (routes.mandateRead ?? (() => err(404, "NOT_FOUND", "no such local mandate")))(url.split("/").pop()!);
    }
    if (url.startsWith("/control/v1/p/news/schedules/")) {
      return (routes.schedule ?? (() => err(404, "NOT_FOUND", "no such schedule")))();
    }
    if (url.startsWith("/api/v1/projects/news/periodic-dossiers/")) {
      return (routes.dossier ?? (() => json(200, dossier())))();
    }
    if (/^\/api\/v1\/projects\/news\/flows\/[^/]+\/overview$/.test(url)) {
      const flowId = decodeURIComponent(url.split("/")[6]);
      return (routes.overview ?? (() => json(200, overviewOf([topic("t1", ["a", "b", "c"]), topic("t2", ["d"])]))))(flowId);
    }
    if (url === "/api/v1/projects") {
      return json(200, { api_version: 1, projects: [{
        name: "news", config: "OK", config_error: null,
        flows: (routes.flows ?? []).map((f) => ({ title: null, selector_label: f.selector.round ? `round ${f.selector.round}` : "whole store",
          binding_state: "CURRENT", bound_after_data: false, ...f })),
        unbound_selectors: [
          ...(routes.unbound ?? []).map((slug) => ({ slug, label: slug, selector: { round: null, manifest_only: false } })),
          ...(routes.unboundRounds ?? []).map((round) => ({ slug: round, label: `round ${round}`, selector: { round, manifest_only: false } })),
        ],
      }] });
    }
    return err(404, "NOT_FOUND", "no");
  });
  return urls;
}
