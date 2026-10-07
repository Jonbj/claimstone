// The typed fetch wrapper: every request is GET, every error is the §3.3 envelope
// mapped to ApiError(code, message) — the frontend renders a named state, never an
// empty table (design §4.1, §4.2 rule 1).
import type {
  Activity,
  Admin,
  Error as ApiErrorPayload,
  Inbox,
  Integrity,
  Lineage,
  Meta,
  Overview,
  Poll,
  ProfileDiff,
  Projects,
  QuestionDetail,
  SourceDossier,
  Summary,
} from "./api-types";

export class ApiError extends Error {
  readonly code: ApiErrorPayload["error"]["code"];
  readonly message: string;

  constructor(code: ApiErrorPayload["error"]["code"], message: string) {
    super(`[${code}] ${message}`);
    this.name = "ApiError";
    this.code = code;
    this.message = message;
  }
}

const PREFIX = "/api/v1";

type Payload = { api_version: number; error?: { code: string; message: string } };

async function get<T extends Payload>(path: string): Promise<T> {
  const response = await fetch(`${PREFIX}${path}`, { method: "GET" });
  let body: T;
  try {
    body = (await response.json()) as T;
  } catch {
    // A proxy error page or a dead API is not an envelope: name it, never render it as data.
    throw new Error(`HTTP ${response.status}: the API did not answer with JSON`);
  }
  if (!response.ok && !body?.error) {
    throw new Error(`HTTP ${response.status}: an error without the API's envelope`);
  }
  if (body?.error) {
    throw new ApiError(body.error.code as ApiErrorPayload["error"]["code"],
                       body.error.message);
  }
  return body;
}

type Selector = { round: string | null; manifest_only: boolean };

function selectorPath(kind: "f" | "u", sel: string): string {
  return kind === "f" ? `flows/${encodeURIComponent(sel)}` : `unbound/${encodeURIComponent(sel)}`;
}

export const api = {
  meta: () => get<Meta>("/meta"),
  projects: () => get<Projects>("/projects"),
  admin: () => get<Admin>("/admin"),
  integrity: (project: string) =>
    get<Integrity>(`/projects/${encodeURIComponent(project)}/integrity`),
  activity: (project: string, limit = 50) =>
    get<Activity>(`/projects/${encodeURIComponent(project)}/activity?limit=${limit}`),
  poll: (project: string) => get<Poll>(`/projects/${encodeURIComponent(project)}/poll`),
  summary: (project: string, kind: "f" | "u", sel: string) =>
    get<Summary>(`/projects/${encodeURIComponent(project)}/${selectorPath(kind, sel)}/summary`),
  overview: (project: string, kind: "f" | "u", sel: string) =>
    get<Overview>(`/projects/${encodeURIComponent(project)}/${selectorPath(kind, sel)}/overview`),
  inbox: (project: string, kind: "f" | "u", sel: string) =>
    get<Inbox>(`/projects/${encodeURIComponent(project)}/${selectorPath(kind, sel)}/inbox`),
  question: (project: string, kind: "f" | "u", sel: string, qid: string) =>
    get<QuestionDetail>(
      `/projects/${encodeURIComponent(project)}/${selectorPath(kind, sel)}/questions/${encodeURIComponent(qid)}`),
  profileDiff: (project: string, kind: "f" | "u", sel: string, qid: string,
                fromSha: string, toSha: string) =>
    get<ProfileDiff>(
      `/projects/${encodeURIComponent(project)}/${selectorPath(kind, sel)}` +
      `/questions/${encodeURIComponent(qid)}/profile-diff` +
      `?from=${encodeURIComponent(fromSha)}&to=${encodeURIComponent(toSha)}`),
  claim: (project: string, kind: "f" | "u", sel: string, claimId: string) =>
    get<Lineage>(
      `/projects/${encodeURIComponent(project)}/${selectorPath(kind, sel)}/claims/${encodeURIComponent(claimId)}`),
  source: (project: string, kind: "f" | "u", sel: string, candidateKey: string) =>
    get<SourceDossier>(
      `/projects/${encodeURIComponent(project)}/${selectorPath(kind, sel)}/sources/${encodeURIComponent(candidateKey)}`),
};

export type { Selector };