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

const PREFIX = "/control/v1";

export class ControlError extends Error {
  readonly status: number;
  readonly code: string;
  readonly message: string;

  constructor(status: number, code: string, message: string) {
    super(`[${code}] ${message}`);
    this.name = "ControlError";
    this.status = status;
    this.code = code;
    this.message = message;
  }
}

// --- types, by route ------------------------------------------------------------------------

export type Row = Record<string, unknown>;

export interface Operator {
  id: string;
  name: string;
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
export type OperationLimits = OperationSummary["limits"];

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

type Envelope = { error?: { code?: string; message?: string } };

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
                           String(body.error.message ?? ""));
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
}

async function post<T>(path: string, body: unknown, options: PostOptions = {}): Promise<T> {
  const { idempotent = true, csrf = true, auth = true } = options;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (csrf) {
    if (csrfToken === null) {
      throw new ControlError(401, "UNAUTHORIZED", "not signed in: there is no session token");
    }
    headers["X-CSRF-Token"] = csrfToken;
  }
  if (idempotent) headers["Idempotency-Key"] = uuid();
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
  // session
  /** Signing in stores the CSRF token in memory; the cookie is the server's HttpOnly one. */
  async signIn(id: string, password: string): Promise<SessionInfo> {
    const info = await post<SessionInfo>("/session", { id, password },
                                         { idempotent: false, csrf: false, auth: false });
    csrfToken = info.csrf_token;
    return info;
  },
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

  // administration
  admin: () => get<ControlAdmin>("/admin"),
  checkTarget: (target: CheckTarget) => post<{ check: AdminCheckRow }>("/admin/check", { target }),
  setCredential: (body: CredentialBody) =>
    post<{ credential: { name: string; set: boolean; note: string } }>("/admin/credential", body),
  /** Always answers 501 today; the portal shows the reason and never calls it. */
  paidTest: () => post<never>("/admin/paid-test", {}),

  // operations
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
