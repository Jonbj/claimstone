// The control client: the ONLY module allowed to send a non-GET request (spec v2.1 §1 rule 5,
// enforced by tests/writes.test.ts). The control API (`/control/v1`, claimstone/control.py) has
// no JSON schema, so the types below are written by hand from `docs/contracts/control_api.md`
// and the Python handlers; where a row is the ledger's own and the portal only renders it, it
// is typed as an open record rather than a guessed shape.
//
// Every POST carries `credentials: "same-origin"`, `X-CSRF-Token`, `Content-Type:
// application/json` (the file upload sends `application/pdf`) and an `Idempotency-Key` from
// `crypto.randomUUID()` — except login, logout and the file upload. The CSRF token lives in
// this module's memory only, never in storage: a reload asks `GET /session` for it again.
//
// Errors are the read API's envelope, `{"error": {"code", "message"}}`, mapped to
// `ControlError(status, code, message)`. A reply that is not the envelope becomes a plain
// `Error`, as in api.ts. A 401 on any route but the login itself tells the session provider the
// operator is signed out.

import type { MandateStatus, PolicyStatus, ScheduleStatus, SchedulerIndex } from "./scheduler";

const PREFIX = "/control/v1";

export interface FieldProblem {
  path: string;
  message: string;
}

export class ControlError extends Error {
  readonly status: number;
  readonly code: string;
  readonly message: string;
  /** Field paths of a 422, or an empty list. */
  readonly details: FieldProblem[];

  constructor(status: number, code: string, message: string, details: FieldProblem[] = []) {
    super(`[${code}] ${message}`);
    this.name = "ControlError";
    this.status = status;
    this.code = code;
    this.message = message;
    this.details = details;
  }
}

// --- types, by route ------------------------------------------------------------------------

export type Row = Record<string, unknown>;

export interface Operator {
  id: string;
  name: string;
  role: "operator" | "admin";
  must_change_password: boolean;
}

/** `GET /account`. `google_linked` is sent by the server but the portal does not use it
 *  (Google sign-in is deferred). */
export interface Account extends Operator {
  email: string | null;
  google_linked: boolean;
}

export interface SessionRow {
  session_id: string;
  created_at: string;
  last_seen: string;
  method: string;
  current: boolean;
}

export interface Person {
  id: string;
  name: string;
  role: "operator" | "admin";
  email: string | null;
  enabled: boolean;
  google_linked: boolean;
}

export type PersonAction = "password" | "disable" | "enable" | "email" | "role";

export interface NewPersonBody {
  password: string;
  id: string;
  name: string;
  email: string;
  role: string;
  temporary_password: string;
}

export interface SessionInfo {
  operator: Operator;
  csrf_token: string;
}

export const VERDICTS = [
  "SUPPORTED",
  "CONTRADICTED",
  "CONTESTED_IN_LITERATURE",
  "UNANSWERED_IN_LITERATURE",
  "NEVER_ASKED",
] as const;
export type Verdict = (typeof VERDICTS)[number];

export interface AdjudicateBody {
  verdict: Verdict;
  rationale: string;
  profile_sha256: string;
  attest: true;
}

export interface Draft {
  draft: Row | null;
  /** null when there is no draft to compare. */
  current: boolean | null;
  current_profile_sha256: string | null;
}

// today (B9; claimstone/today.py)
export interface TodayChanged {
  counts: Record<string, number>;
  undated_rows: number;
  newest: Array<{ when: string; stage: string; row: Row }>;
}
export interface NeedsYouRequired {
  flow_id: string;
  type: string;
  subject: string;
  cause: string;
}
export interface NeedsYouOptional {
  flow_id: string;
  type: string;
  subject: string;
  id: string;
}
export interface OperationSummary {
  operation_id: string;
  stage: string | null;
  state: string;
  state_note: string;
  limits: {
    network_requests: number | null;
    model_calls: number | null;
    spend_usd: number | null;
  };
  spent_usd: number;
  units_with_unknown_cost: number;
  remaining_usd: number | null;
  units_completed: number;
  planned_at: string | null;
  last_event: string;
  last_event_at: string | null;
  authorized_by: Row | null;
  worker_last_seen: string | null;
  worker_note: string;
}
export type TodayProject =
  | {
      project: string;
      since: string | null;
      first_visit: boolean;
      changed: TodayChanged;
      needs_you: { required: NeedsYouRequired[]; optional: NeedsYouOptional[] };
      continues_without_you: OperationSummary[] | null;
      error?: undefined;
    }
  | { project: string; error: string };
export interface Today {
  operator: string;
  projects: TodayProject[];
}
export interface SeenBody {
  project?: string;
  until?: string;
}

// intake (B7a/B7b; docs/contracts/intake.md)
export type IntakeKind = "doi" | "url" | "reference";
export interface IntakeBody {
  kind: IntakeKind;
  value: string;
  note?: string;
}
export interface IntakeList {
  flow_id: string;
  items: Row[];
}
export const IDENTITY_ANSWERS = ["same_work", "version_of", "different", "not_sure"] as const;
export type IdentityAnswer = (typeof IDENTITY_ANSWERS)[number];

// decisions (B8; docs/contracts/decisions.md)
export interface OpenDecision {
  type: string;
  required: boolean;
  id: string;
  candidate_key: string;
  recorded_at: string | null;
  item: Row;
}
export interface Decisions {
  flow_id: string;
  open: OpenDecision[];
  decided_recently: Row[];
}
export interface RetryPreview {
  candidates: Array<{
    candidate_key: string;
    source_id: string | null;
    source_class: string | null;
    last_failure: string;
    hosts: string[];
  }>;
  hosts: string[];
  refused_hosts: Record<string, string>;
  robots: string;
  max_requests_cap: number;
  executes: string;
}
export interface RetryBody {
  candidate_ids: string[];
  campaign: string;
  max_requests: number;
}
export interface DecisionStateBody {
  state: "deferred" | "declined";
  until?: string;
  reason: string;
}
export interface OfferBody {
  candidate_id: string;
  work_version: string;
  vendor: string;
  price: string;
  currency: string;
  tax_status?: string;
  terms_url: string;
  verified_at: string;
  resolves: string;
}
export type OfferStage = "approved" | "bought_externally" | "declined";

// scheduler writes (claimstone/control.py: `_periodic_plan`, `_schedule_*`, `_copy_policy_*`,
// `_local_mandate_*`, `_periodic_export_*`). The bodies carry exactly the keys the server accepts.
export interface PeriodicPlanBody {
  source_flow_id: string;
  rounds: Array<{ round: string; title: string; not_before: string; expires_at: string }>;
  apis: string[];
  allowed_hosts: string[];
  max_units_each: number;
  max_requests_each: number;
  per_query: number;
}
export interface PeriodicPlanResult {
  rounds: Array<{ round: string; flow_id: string; not_before: string; expires_at: string; batch_id: string }>;
  schedule_id: string;
  schedule_state: string;
  max_total_requests: number;
}
export interface PolicyPlanBody {
  schedule_id: string;
  allowed_hosts: string[];
  source_classes: string[];
  max_candidates: number;
  max_requests_each: number;
  not_before: string;
  expires_at: string;
}
export interface SeriesMandateBody {
  schedule_id: string;
  flow_ids: string[];
  extract_model: string;
  review_model: string;
  max_total_local_calls: number;
}
export interface FlowMandateBody {
  flow_id: string;
  extract_model: string;
  review_model: string;
  max_total_local_calls: number;
  /** D135: `ollama-cloud` makes the calls metered; all four ceilings are then required, in cents (prices per million tokens). */
  backend?: "llamacpp" | "ollama-cloud";
  budget_cents?: number;
  max_call_cents?: number;
  price_in_cents?: number;
  price_out_cents?: number;
}
/** What `autopilot.enable_series` answers: the new mandate's id and its frozen terms, not a status. */
export interface SeriesMandateEnabled { mandate_id: string; mandate: MandateStatus["mandate"] }
/** What `autopilot.disable` answers. */
export interface MandateDisabled { mandate_id: string; state: string }
export interface PeriodicExportCreated {
  export_id: string;
  schedule_id: string;
  dossier_id: string;
  created_now: boolean;
  download: string;
}

// exports (B10)
export interface ExportCreated {
  export_id: string;
  created_now: boolean;
  copies: unknown;
}
export interface ExportVerified {
  export_id: string;
  holds: boolean;
  problems: unknown[];
}

// administration (B11)
export const CHECK_TARGETS = ["llamacpp", "ollama-cloud", "grobid"] as const;
export type CheckTarget = (typeof CHECK_TARGETS)[number];
export interface AdminCheckRow {
  kind: "reachability";
  target: string;
  url: string;
  ok: boolean;
  status: number | null;
  detail: string;
  latency_ms: number | null;
  actor: string;
  recorded_at: string;
}
export interface ControlAdmin {
  credentials: Record<string, boolean>;
  backends: { configured: string[]; available: string[] };
  backends_note: string;
  instruments: Record<string, unknown>;
  key_rotation_note: string;
  checks: Record<string, AdminCheckRow>;
  check_targets: Record<string, string>;
}
export interface CredentialBody {
  name: string;
  value: string;
  password: string;
}

// operations (B12)
export interface OperationsList {
  flow_id: string;
  operations: OperationSummary[];
}
export interface StartFlowBody { title: string; round: string }
export interface StartFlowResult { flow_id: string; created: boolean; title: string; round: string }
export interface PlanBatchBody {
  stage: "discover" | "acquire";
  apis: string[];
  allowed_hosts: string[];
  max_units: number;
  max_requests_each: number;
  per_query: number;
  /** acquire only: also ask the Unpaywall and OpenAlex APIs for open-access locations */
  use_apis?: boolean;
  retry_classes?: string[];
  retry_reason?: string;
}
export interface PlannedBatch {
  batch_id: string;
  operation_ids: string[];
  units: Array<{
    operation_id: string; subject: unknown; direct_url: string | null;
    allowed_hosts: string[]; allowed_schemes: string[]; max_requests: number;
    use_apis: boolean; retry_classes: string[];
  }>;
  selected: number;
  skipped: Array<{ subject: string; reason: string }>;
  max_total_requests: number;
  remaining_unplanned: number;
  stage: "discover" | "acquire";
  flow_id: string;
  project: string;
  batch_version: number;
}
export type BatchUnit = PlannedBatch["units"][number] & { state: string };
export interface BatchSummary {
  batch_id: string;
  stage: "discover" | "acquire";
  created_at: string;
  operation_ids: string[];
  units: BatchUnit[];
  max_total_requests: number;
  selected: number;
  remaining_unplanned: number;
  skipped: Array<{ subject: string; reason: string }>;
  awaiting_approval: number;
}
export interface BatchesList {
  flow_id: string;
  batches: BatchSummary[];
}
export interface AuthorizeBatchBody {
  operation_ids: string[];
  max_total_requests: number;
}
export interface AuthorizedBatch extends BatchSummary {
  authorized_now: number;
}
export interface AcquireHosts {
  pending_candidates: number;
  candidate_hosts: Array<{ host: string; candidates: number }>;
  refused_hosts: Array<{ host: string; candidates: number; sources?: string[]; open_access_candidates?: number }>;
  retryable_classes: Array<{ failure_class: string; candidates: number }>;
  plain_http_candidates: number;
  suggested_max_requests_each: number;
}
export type OperationLimits = OperationSummary["limits"];

// retry policies (D134; docs/contracts/retry_policies.md, control_api.md). The policy is the
// frozen ledger row; the portal renders its own fields and sends them back verbatim.
export interface RetryPolicyBody {
  allowed_hosts: string[];
  max_retries: number;
  max_attempts_each: number;
  max_requests_each: number;
  use_apis: boolean;
  base_delay_hours: number;
  max_delay_hours: number;
  expires_at: string;
}
export type RetryPolicyState = "PLANNED" | "AUTHORIZED" | "REVOKED";
export interface RetryPolicy {
  version: number;
  project: string;
  flow_id: string;
  selector: unknown;
  allowed_hosts: string[];
  max_retries: number;
  max_attempts_each: number;
  max_requests_each: number;
  max_total_requests: number;
  use_apis: boolean;
  base_delay_hours: number;
  max_delay_hours: number;
  not_before: string;
  expires_at: string;
  code_sha256: string;
  protocol_sha256: string;
}
export interface RetryPolicyStatus {
  policy_id: string;
  state: RetryPolicyState;
  policy: RetryPolicy;
  reserved_retries: number;
  remaining_retries: number;
  reserved_requests: number;
  events: unknown[];
}
export interface RetryPoliciesList {
  flow_id: string;
  policies: RetryPolicyStatus[];
}
export interface AuthorizeRetryPolicyBody {
  policy_sha256: string;
  max_retries: number;
  max_requests_each: number;
  max_total_requests: number;
}

// new project (plan 1; docs/contracts/new_project.md)
export type Figures = Record<string, unknown>;

export interface WizardTemplateSummary {
  id: string;
  label: string;
  description: string;
}

export interface WizardTemplate {
  id: string;
  label: string;
  default_floor: number;
  classes: Array<{ id: string; name: string; weight_hint: string; notes: string }>;
  excluded_hosts: string[];
  notation_presets: Array<{ id: string; label: string }>;
}

export interface DraftSummary {
  draft_id: string;
  status: "open" | "discarded" | "created";
  revision: number;
  steps_saved: number[];
  project_name: string | null;
  project: string | null;
  updated_at: string;
}

export interface DraftState {
  draft_id: string;
  revision: number;
  status: "open" | "discarded" | "created";
  steps: Record<string, { data: Row; revision: number }>;
  advanced: Record<string, string>;
  figures: Record<string, Figures>;
  project: string | null;
  last_failure: string | null;
  started_at: string;
  updated_at: string;
}

export interface StepSaved {
  revision: number;
  data: Row;
  figures: Figures;
}

export interface Preview {
  figures: Figures;
  protocol_sha256: string;
  files: Record<string, string>;
  revision: number;
}

export interface Created {
  project: string;
  protocol_sha256: string;
  files: Record<string, string>;
  frozen: { registry_version: number; frozen_at: string; floor_version: number };
}

// --- transport ------------------------------------------------------------------------------

// The token is held here and nowhere else; `setCsrfToken(null)` is a sign-out.
let csrfToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

/** The session provider registers here so a 401 from any route signs the UI out. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

type Envelope = { error?: { code?: string; message?: string; details?: FieldProblem[] } };

async function parse<T>(response: Response, auth: boolean): Promise<T> {
  let body: (T & Envelope) | null;
  try {
    body = (await response.json()) as T & Envelope;
  } catch {
    // A proxy error page or a dead server is not an envelope: name it, never render it as data.
    throw new Error(`HTTP ${response.status}: the control API did not answer with JSON`);
  }
  if (body?.error) {
    if (response.status === 401 && auth) {
      csrfToken = null;
      onUnauthorized?.();
    }
    throw new ControlError(response.status, String(body.error.code ?? "UNKNOWN"),
                           String(body.error.message ?? ""),
                           Array.isArray(body.error.details) ? body.error.details : []);
  }
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: an error without the control API's envelope`);
  }
  return body as T;
}

function uuid(): string {
  return crypto.randomUUID();
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${PREFIX}${path}`, {
    method: "GET",
    credentials: "same-origin",
  });
  // The session probe answers 401 when nobody is signed in; that is its answer, not a sign-out.
  return parse<T>(response, path !== "/session");
}

interface PostOptions {
  /** Login and logout carry no Idempotency-Key and, for the login, no CSRF token yet. */
  idempotent?: boolean;
  csrf?: boolean;
  /** A wrong password is a 401 that does not mean the session ended. */
  auth?: boolean;
  /** A caller-chosen key for a write whose retry must replay the first answer. */
  idempotencyKey?: string;
}

async function post<T>(path: string, body: unknown, options: PostOptions = {}): Promise<T> {
  const { idempotent = true, csrf = true, auth = true, idempotencyKey } = options;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (csrf) {
    if (csrfToken === null) {
      throw new ControlError(401, "UNAUTHORIZED", "not signed in: there is no session token");
    }
    headers["X-CSRF-Token"] = csrfToken;
  }
  if (idempotent) headers["Idempotency-Key"] = idempotencyKey ?? uuid();
  const response = await fetch(`${PREFIX}${path}`, {
    method: "POST",
    credentials: "same-origin",
    headers,
    body: JSON.stringify(body),
  });
  return parse<T>(response, auth);
}

const enc = encodeURIComponent;
function flowBase(project: string, flowId: string): string {
  return `/p/${enc(project)}/flows/${enc(flowId)}`;
}

export const control = {
  startFlow: (project: string, body: StartFlowBody) =>
    post<StartFlowResult>(`/p/${enc(project)}/flows`, body),
  planBatch: (project: string, flowId: string, body: PlanBatchBody) =>
    post<PlannedBatch>(`${flowBase(project, flowId)}/batches`, body),
  batches: (project: string, flowId: string) =>
    get<BatchesList>(`${flowBase(project, flowId)}/batches`),
  authorizeBatch: (project: string, flowId: string, batchId: string, body: AuthorizeBatchBody) =>
    post<{ batch: AuthorizedBatch }>(`${flowBase(project, flowId)}/batches/${enc(batchId)}/authorize`, body),
  // session
  /** Signing in stores the CSRF token in memory; the cookie is the server's HttpOnly one. */
  async signIn(id: string, password: string): Promise<SessionInfo> {
    const info = await post<SessionInfo>("/session", { id, password },
                                         { idempotent: false, csrf: false, auth: false });
    csrfToken = info.csrf_token;
    return info;
  },
  // scheduler (reads; claimstone/control.py `_scheduler_index` and the per-object reads)
  schedulerIndex: (project: string, cursor?: string | null, limit = 25) =>
    get<SchedulerIndex>(`/p/${enc(project)}/scheduler?limit=${limit}${cursor ? `&cursor=${enc(cursor)}` : ""}`),
  schedule: (project: string, id: string) => get<ScheduleStatus>(`/p/${enc(project)}/schedules/${enc(id)}`),
  copyPolicy: (project: string, id: string) => get<PolicyStatus>(`/p/${enc(project)}/copy-policies/${enc(id)}`),
  localMandate: (project: string, id: string) => get<MandateStatus>(`/p/${enc(project)}/local-mandates/${enc(id)}`),
  async session(): Promise<SessionInfo> {
    const info = await get<SessionInfo>("/session");
    csrfToken = info.csrf_token;
    return info;
  },
  async signOut(): Promise<void> {
    try {
      await post<{ ended: boolean }>("/session/end", {}, { idempotent: false });
    } finally {
      // Whatever the server said, this tab no longer holds a token.
      csrfToken = null;
    }
  },

  // account and people. A call that carries a password sends no Idempotency-Key: the server
  // ignores it for them, and a retry must not replay a password check.
  account: () => get<{ operator: Account }>("/account"),
  changePassword: (current: string, next: string) =>
    post<{ changed: boolean }>("/account/password", { current, new: next }, { idempotent: false }),
  accountSessions: () => get<{ sessions: SessionRow[] }>("/account/sessions"),
  endOtherSessions: () =>
    post<{ ended: number }>("/account/sessions/end-others", {}, { idempotent: false }),
  people: () => get<{ people: Person[] }>("/people"),
  createPerson: (body: NewPersonBody) =>
    post<{ person: Person }>("/people", body, { idempotent: false }),
  personAct: (id: string, action: PersonAction, body: Record<string, string>) =>
    post<{ person?: Person; changed?: boolean }>(`/people/${enc(id)}/${action}`, body,
                                                 { idempotent: false }),

  // today
  today: () => get<Today>("/today"),
  seen: (body: SeenBody) => post<{ seen: Row }>("/seen", body),

  // signing and drafts
  adjudicate: (project: string, flowId: string, qid: string, body: AdjudicateBody) =>
    post<{ adjudication: Row }>(`${flowBase(project, flowId)}/q/${enc(qid)}/adjudicate`, body),
  saveDraft: (project: string, flowId: string, qid: string,
              body: { rationale: string; profile_sha256: string }) =>
    post<Draft>(`${flowBase(project, flowId)}/q/${enc(qid)}/draft`, body),
  draft: (project: string, flowId: string, qid: string) =>
    get<Draft>(`${flowBase(project, flowId)}/q/${enc(qid)}/draft`),

  // intake
  intake: (project: string, flowId: string) =>
    get<IntakeList>(`${flowBase(project, flowId)}/intake`),
  submitIntake: (project: string, flowId: string, body: IntakeBody) =>
    post<{ intake: Row }>(`${flowBase(project, flowId)}/intake`, body),
  resolveIntake: (project: string, flowId: string, intakeId: string,
                  body: { answer: IdentityAnswer; reason?: string }) =>
    post<{ decision: Row; intake: Row }>(
      `${flowBase(project, flowId)}/intake/${enc(intakeId)}/resolve`, body),

  // new project
  newTemplates: () => get<{ templates: WizardTemplateSummary[] }>("/new-templates"),
  newTemplate: (id: string) => get<WizardTemplate>(`/new-templates/${enc(id)}`),
  newDrafts: () => get<{ drafts: DraftSummary[] }>("/new"),
  newStart: () => post<{ draft_id: string; revision: number }>("/new", {}),
  newRead: (id: string) => get<DraftState>(`/new/${enc(id)}`),
  newSaveStep: (id: string, step: number, baseRevision: number, data: unknown) =>
    post<StepSaved>(`/new/${enc(id)}/steps/${step}`, { base_revision: baseRevision, data }),
  newSaveAdvanced: (id: string, baseRevision: number, files: Record<string, string>) =>
    post<{ revision: number }>(`/new/${enc(id)}/advanced`, { base_revision: baseRevision, files }),
  newPreview: (id: string) => get<Preview>(`/new/${enc(id)}/preview`),
  newDiscard: (id: string, baseRevision: number) =>
    post<{ revision: number; status: string }>(`/new/${enc(id)}/discard`, { base_revision: baseRevision }),
  newCreate: (id: string, protocolSha256: string) =>
    // The key is the draft and the digest: a retry after a lost answer replays the first answer
    // instead of creating twice, and a different digest is a different request.
    post<Created>(`/new/${enc(id)}/create`, { confirm: true, protocol_sha256: protocolSha256 },
                  { idempotencyKey: `create-${id}-${protocolSha256.slice(0, 16)}` }),

  // decisions
  decisions: (project: string, flowId: string) =>
    get<Decisions>(`${flowBase(project, flowId)}/decisions`),
  retryPreview: (project: string, flowId: string, candidateIds: string[]) =>
    get<RetryPreview>(
      `${flowBase(project, flowId)}/decisions/retry-campaign/preview` +
      `?candidate_ids=${enc(candidateIds.join(","))}`),
  approveRetry: (project: string, flowId: string, body: RetryBody) =>
    post<{ decision: Row }>(`${flowBase(project, flowId)}/decisions/retry-campaign`, body),
  setDecisionState: (project: string, flowId: string, decisionId: string,
                     body: DecisionStateBody) =>
    post<{ decision: Row }>(
      `${flowBase(project, flowId)}/decisions/${enc(decisionId)}/state`, body),

  // offers
  recordOffer: (project: string, flowId: string, body: OfferBody) =>
    post<{ offer: Row }>(`${flowBase(project, flowId)}/offers`, body),
  stageOffer: (project: string, flowId: string, offerId: string, stage: OfferStage) =>
    post<{ offer: Row }>(`${flowBase(project, flowId)}/offers/${enc(offerId)}/stage`,
                         { stage }),

  // exports (the list is the read API's)
  createExport: (project: string, flowId: string, includeCopies: boolean) =>
    post<ExportCreated>(`${flowBase(project, flowId)}/exports`,
                        { include_copies: includeCopies }),
  verifyExport: (project: string, flowId: string, exportId: string) =>
    post<ExportVerified>(`${flowBase(project, flowId)}/exports/${enc(exportId)}/verify`, {}),

  // scheduler writes
  planPeriodic: (p: string, body: PeriodicPlanBody) => post<PeriodicPlanResult>(`/p/${enc(p)}/periodic-plans`, body),
  authorizeSchedule: (p: string, id: string, body: { plan_sha256: string; max_total_requests: number }) =>
    post<ScheduleStatus>(`/p/${enc(p)}/schedules/${enc(id)}/authorize`, body),
  revokeSchedule: (p: string, id: string, planSha: string) =>
    post<ScheduleStatus>(`/p/${enc(p)}/schedules/${enc(id)}/revoke`, { plan_sha256: planSha }),
  planCopyPolicy: (p: string, body: PolicyPlanBody) => post<PolicyStatus>(`/p/${enc(p)}/copy-policies`, body),
  authorizeCopyPolicy: (p: string, id: string, body: { policy_sha256: string; max_candidates: number; max_requests_each: number; max_total_requests: number }) =>
    post<PolicyStatus>(`/p/${enc(p)}/copy-policies/${enc(id)}/authorize`, body),
  revokeCopyPolicy: (p: string, id: string, sha: string) =>
    post<PolicyStatus>(`/p/${enc(p)}/copy-policies/${enc(id)}/revoke`, { policy_sha256: sha }),
  enableSeriesMandate: (p: string, body: SeriesMandateBody) => post<SeriesMandateEnabled>(`/p/${enc(p)}/local-mandates/series`, body),
  enableFlowMandate: (project: string, flowId: string, body: FlowMandateBody) =>
    post<SeriesMandateEnabled>(`${flowBase(project, flowId)}/local-mandates`, body),
  disableMandate: (p: string, id: string) =>
    post<MandateDisabled>(`/p/${enc(p)}/local-mandates/${enc(id)}/disable`, { mandate_id: id }),
  createPeriodicExport: (p: string, scheduleId: string, dossierId: string) =>
    post<PeriodicExportCreated>(`/p/${enc(p)}/schedules/${enc(scheduleId)}/export`, { dossier_id: dossierId }),
  verifyPeriodicExport: (p: string, exportId: string) =>
    post<{ export_id: string; holds: boolean; problems: string[] }>(`/p/${enc(p)}/periodic-exports/${enc(exportId)}/verify`, {}),
  /** A path for a browser navigation with the session cookie; a download is never a `fetch`. */
  periodicExportDownloadPath: (p: string, exportId: string) => `${PREFIX}/p/${enc(p)}/periodic-exports/${enc(exportId)}/download`,

  // administration
  admin: () => get<ControlAdmin>("/admin"),
  checkTarget: (target: CheckTarget) => post<{ check: AdminCheckRow }>("/admin/check", { target }),
  setCredential: (body: CredentialBody) =>
    post<{ credential: { name: string; set: boolean; note: string } }>("/admin/credential", body),
  /** Always answers 501 today; the portal shows the reason and never calls it. */
  paidTest: () => post<never>("/admin/paid-test", {}),

  // operations
  acquireHosts: (project: string, flowId: string) =>
    get<AcquireHosts>(`${flowBase(project, flowId)}/acquire-hosts`),
  // retry policies (D134). The policy_id is the policy's own digest, so it is sent back as the
  // `policy_sha256` on authorize and revoke, exactly as the list returned it.
  planRetryPolicy: (project: string, flowId: string, body: RetryPolicyBody) =>
    post<RetryPolicyStatus>(`${flowBase(project, flowId)}/retry-policies`, body),
  retryPolicies: (project: string, flowId: string) =>
    get<RetryPoliciesList>(`${flowBase(project, flowId)}/retry-policies`),
  authorizeRetryPolicy: (project: string, policyId: string, body: AuthorizeRetryPolicyBody) =>
    post<RetryPolicyStatus>(`/p/${enc(project)}/retry-policies/${enc(policyId)}/authorize`, body),
  revokeRetryPolicy: (project: string, policyId: string) =>
    post<RetryPolicyStatus>(`/p/${enc(project)}/retry-policies/${enc(policyId)}/revoke`,
                           { policy_sha256: policyId }),
  operations: (project: string, flowId: string) =>
    get<OperationsList>(`${flowBase(project, flowId)}/operations`),
  authorizeOperation: (project: string, flowId: string, operationId: string,
                       limits: OperationLimits) =>
    post<{ authorized: Row; already_authorized: boolean }>(
      `${flowBase(project, flowId)}/operations/${enc(operationId)}/authorize`, { limits }),
  /** 501 today: the scheduler's ledger has no `stopping` event. */
  pauseOperation: (project: string, flowId: string, operationId: string) =>
    post<never>(`${flowBase(project, flowId)}/operations/${enc(operationId)}/pause`, {}),
  resumeOperation: (project: string, flowId: string, operationId: string) =>
    post<never>(`${flowBase(project, flowId)}/operations/${enc(operationId)}/resume`, {}),
};

export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

/** The file upload (B7b): the body is the PDF itself, so it carries no Idempotency-Key and its
 *  Content-Type is application/pdf. XMLHttpRequest is used for its upload progress events;
 *  `fetch` cannot report them. The client refuses over 50 MiB; the server stays the authority. */
export function uploadIntakeFile(
  project: string, flowId: string, target: string, file: File,
  onProgress?: (loaded: number, total: number) => void,
): Promise<{ intake: Row }> {
  return new Promise((resolve, reject) => {
    if (file.size > MAX_UPLOAD_BYTES) {
      reject(new ControlError(413, "TOO_LARGE", "a file must be at most 50 MiB"));
      return;
    }
    if (csrfToken === null) {
      reject(new ControlError(401, "UNAUTHORIZED", "not signed in: there is no session token"));
      return;
    }
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${PREFIX}${flowBase(project, flowId)}/intake/file?target=${enc(target)}`);
    xhr.withCredentials = false; // same-origin requests carry the cookie regardless
    xhr.setRequestHeader("Content-Type", "application/pdf");
    xhr.setRequestHeader("X-CSRF-Token", csrfToken);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded, event.total);
    };
    xhr.onerror = () => reject(new Error("the upload did not reach the control API"));
    xhr.onload = () => {
      let body: ({ intake: Row } & Envelope) | null = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        reject(new Error(`HTTP ${xhr.status}: the control API did not answer with JSON`));
        return;
      }
      if (body?.error) {
        if (xhr.status === 401) {
          csrfToken = null;
          onUnauthorized?.();
        }
        reject(new ControlError(xhr.status, String(body.error.code ?? "UNKNOWN"),
                                String(body.error.message ?? "")));
      } else if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(`HTTP ${xhr.status}: an error without the control API's envelope`));
      } else {
        resolve(body as { intake: Row });
      }
    };
    xhr.send(file);
  });
}
