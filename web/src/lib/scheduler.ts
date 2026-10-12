// The scheduler's server shapes (docs/contracts/control_api.md D128–D130) and the few pure helpers the
// pages share. A state word is the server's: it is passed through unchanged; the pages only translate
// the label they show for it.

export type ScheduleState = "PLANNED" | "AUTHORIZED" | "REVOKED";
export type PolicyState = "PLANNED" | "AUTHORIZED" | "REVOKED";
export type MandateState = "ENABLED" | "DISABLED";
export type WorkerState = "ALIVE" | "STALE" | "STOPPED" | "NOT_STARTED" | "UNKNOWN";

export interface GrantEvent {
  event: string;
  at: string;
  identity?: { signer_auth?: string; operator?: string; name?: string };
  [key: string]: unknown;
}

export interface ScheduleEntry {
  batch_id: string;
  operation_ids: string[];
  flow_id: string;
  stage: string;
  units: unknown[];
  max_total_requests: number;
  not_before: string;
  expires_at: string;
}

export interface ScheduleStatus {
  schedule_id: string;
  state: ScheduleState;
  plan: { version: number; project: string; max_total_requests: number; entries: ScheduleEntry[] };
  events: GrantEvent[];
}

export interface PolicyStatus {
  policy_id: string;
  state: PolicyState;
  policy: {
    project: string; schedule_id: string; flow_ids: string[]; allowed_hosts: string[];
    source_classes: string[]; max_candidates: number; max_requests_each: number;
    max_total_requests: number; not_before: string; expires_at: string;
  };
  reserved_candidates: number;
  remaining_candidates: number;
  reserved_requests: number;
  events: GrantEvent[];
}

export interface MandateStatus {
  mandate_id: string;
  state: MandateState;
  flow_id: string;
  flow_ids: string[];
  disabled_by: GrantEvent["identity"] | null;
  reserved_local_calls: number;
  remaining_local_calls: number;
  pending_batches: Array<{ batch_id: string; stage: string; awaiting_approval: number; max_total_requests: number }>;
  mandate: { schedule_id?: string; extract_model: string; review_model: string; max_total_local_calls: number };
}

export interface Worker {
  worker_key: string;
  state: WorkerState;
  last_seen_at: string | null;
  phase: "IDLE" | "DRIVING" | "STOPPED" | null;
  age_seconds: number | null;
}

export interface SchedulerIndex {
  project: string;
  schedules: ScheduleStatus[];
  copy_policies: PolicyStatus[];
  local_mandates: MandateStatus[];
  workers: { supervisor: Worker; operations: Worker; mandates: Record<string, Worker> };
  archive: {
    limit: number; offset: number; revision: string; next_cursor: string | null;
    total: { schedules: number; copy_policies: number; local_mandates: number };
  };
}

export interface SeriesOverview {
  schedule: ScheduleStatus;
  state: string;
  rounds: number;
  windowStart: string;
  windowEnd: string;
  policies: PolicyStatus[];
  mandates: MandateStatus[];
}

/** What belongs to one schedule. A policy or mandate belongs to it only by its own `schedule_id`. */
export function overviewOfSeries(
  schedule: ScheduleStatus, policies: PolicyStatus[], mandates: MandateStatus[],
): SeriesOverview {
  const entries = schedule.plan.entries;
  return {
    schedule,
    state: schedule.state,
    rounds: entries.length,
    windowStart: entries[0]?.not_before ?? "",
    windowEnd: entries[entries.length - 1]?.expires_at ?? "",
    policies: policies.filter((p) => p.policy.schedule_id === schedule.schedule_id),
    mandates: mandates.filter((m) => m.mandate.schedule_id === schedule.schedule_id),
  };
}

/** An operational alert: anything but a recently heard-from process. Never a scientific failure. */
export function workerAlert(worker: Worker): boolean {
  return worker.state !== "ALIVE";
}

/** One acquisition summary of a round (`admission` in the dossier's audit), as the server sends it. */
export interface Admission {
  found: number;
  confirmed: number;
  obtained: number;
  rate: number | null;
  status: string;
  [key: string]: unknown;
}

/** One round of the dossier's audit. Only the fields the series page shows are typed. */
export interface AuditRound {
  round?: string;
  flow_id?: string;
  not_before?: string;
  expires_at?: string;
  operations?: Record<string, number>;
  successful_queries?: number;
  planned_queries?: number;
  admission?: Admission;
  [key: string]: unknown;
}

/** `audit.rounds` of a dossier; the audit is typed loosely upstream, so anything else is no rounds. */
export function roundsOf(audit: unknown): AuditRound[] {
  const rounds = (audit as { rounds?: unknown } | null)?.rounds;
  return Array.isArray(rounds) ? (rounds as AuditRound[]) : [];
}

/** `audit.cumulative_admission`, or null when the audit does not carry one in the expected shape. */
export function cumulativeOf(audit: unknown): Admission | null {
  const row = (audit as { cumulative_admission?: unknown } | null | undefined)?.cumulative_admission;
  if (!row || typeof row !== "object") return null;
  const a = row as Record<string, unknown>;
  return typeof a.found === "number" && typeof a.confirmed === "number" ? (row as Admission) : null;
}

/** A cumulative profile row; operational questions carry `state` only. */
export interface ProfileRow {
  question_id: string;
  profile_sha256?: string;
  state?: string;
  provisional?: boolean;
  direction_count?: Record<string, number>;
  coverage?: { sources?: number; examined?: number };
  [key: string]: unknown;
}

export interface DecisionRow {
  question_id: string;
  verdict: { verdict?: unknown; [key: string]: unknown } | null;
  stale?: boolean;
  stored_profile_stale?: boolean;
  unavailable?: string;
}

export interface QuestionRow {
  questionId: string;
  profile: ProfileRow | null;
  decision: DecisionRow | null;
}

const hasId = (row: unknown): row is { question_id: string } =>
  !!row && typeof row === "object" && typeof (row as { question_id?: unknown }).question_id === "string";

/** Profiles and human decisions joined by `question_id`. A row on one side only still shows. */
export function questionRowsOf(profiles: unknown, decisions: unknown): QuestionRow[] {
  const byId = new Map<string, QuestionRow>();
  const slot = (id: string) => {
    if (!byId.has(id)) byId.set(id, { questionId: id, profile: null, decision: null });
    return byId.get(id)!;
  };
  for (const row of Array.isArray(profiles) ? profiles : []) {
    if (hasId(row)) slot(row.question_id).profile = row as ProfileRow;
  }
  for (const row of Array.isArray(decisions) ? decisions : []) {
    if (hasId(row)) slot(row.question_id).decision = row as DecisionRow;
  }
  return [...byId.values()].sort((a, b) => (a.questionId < b.questionId ? -1 : a.questionId > b.questionId ? 1 : 0));
}
