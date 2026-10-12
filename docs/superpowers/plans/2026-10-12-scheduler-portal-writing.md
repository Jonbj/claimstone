# Scheduler in the portal — writing half (plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From the portal a person can create a series of dated updates from a cadence, grant and revoke the three separate authorizations (calendar, future copies, local model), and package the verified cumulative dossier — each action showing exactly what it permits and repeating exactly what the server showed.

**Architecture:** Typed write methods in `control.ts` (the only module allowed to send a non-GET), two pure modules (`cadence.ts`, `figures.ts`), one form page for a new series, and action panels added to the read-only step components of plan 1. No optimistic state: every write is followed by a re-read; a `409` re-reads and asks again.

**Tech Stack:** as plan 1. **Do not start before plan 1 (`2026-10-12-scheduler-portal-reading.md`) is merged**: this plan edits its components.

Spec: `docs/superpowers/specs/2026-10-12-scheduler-portal-design.md`. Hand-off: `docs/design/portal/SCHEDULER_FRONTEND_HANDOFF.md`. Conventions: identical to plan 1 ("Conventions every task follows") — worktree, catalogs in both languages, server words verbatim, trailer, test style. Additional rule for this plan: **no write control is ever enabled while a request is in flight, and nothing is retried automatically after a `409`.**

## The write contract (copied from `claimstone/control.py`)

All under `/control/v1/p/{p}`; session + Origin + CSRF as for every POST; an operator may use all of them (D131); each records `{signer_auth: "portal-session", operator, name}` as the actor.

| Route | Body (exact keys; unknown keys are refused) | Answers |
|---|---|---|
| `POST /periodic-plans` | `{source_flow_id: string, rounds: [{round, title, not_before, expires_at}], apis: string[], allowed_hosts: string[], max_units_each: int, max_requests_each: int, per_query: int}` | `201 {rounds: [{round, flow_id, not_before, expires_at, batch_id}], schedule_id, schedule_state, max_total_requests}`; `409 REFUSED` with the engine's sentence |
| `POST /schedules/{id}/authorize` | `{plan_sha256, max_total_requests}` (the ids/limits **as GET showed**) | `201` first time / `200` repeat, the schedule status; `409 PLAN_DIFFERS` if either differs; `409 REFUSED` |
| `POST /schedules/{id}/revoke` | `{plan_sha256}` | `200` status; `409 PLAN_DIFFERS` |
| `POST /copy-policies` | `{schedule_id, allowed_hosts, source_classes, max_candidates, max_requests_each, not_before, expires_at}` | `201` policy status (state `PLANNED`); `409 REFUSED` |
| `POST /copy-policies/{id}/authorize` | `{policy_sha256, max_candidates, max_requests_each, max_total_requests}` | `201`/`200`; `409 PLAN_DIFFERS` |
| `POST /copy-policies/{id}/revoke` | `{policy_sha256}` | `200`; `409 PLAN_DIFFERS` |
| `POST /local-mandates/series` | `{schedule_id, flow_ids, extract_model, review_model, max_total_local_calls}`; `flow_ids` must equal the schedule's entries' flow ids in order | `201` mandate status; `409 PLAN_DIFFERS` if flows changed; `409 REFUSED` |
| `POST /local-mandates/{id}/disable` | `{mandate_id}` | `200`; `409 PLAN_DIFFERS` |
| `POST /schedules/{id}/export` | `{dossier_id}` (= the dossier's current `finalized_dossier_id`) | `201 {export_id, schedule_id, dossier_id, created_now, download}` / `200` identical repeat; `409` stale or unfinished |
| `POST /periodic-exports/{id}/verify` | `{}` | `200 {export_id, holds: boolean, problems: string[]}` |
| `GET /periodic-exports/{id}/download` | — | `application/zip` attachment (four files, no copies); `409 EXPORT_INVALID` if verification fails |

Plan rules the server enforces (so the client may pre-check for early messages but must show the server's refusal verbatim): round names `[A-Za-z0-9_-]{1,80}`, unique, and not the name of a round that already has candidates; each window UTC, `start > now`, `start < end`, `end <= now + 366 days`, ordered by start and non-overlapping (`start >= previous end`), 1–32 rounds; `apis ⊆ {openalex, crossref, arxiv}`, non-empty; hosts exact lowercase names without ports/wildcards, non-empty, none in the project's excluded hosts; `max_units_each ≥ (all topic terms) × (distinct apis)`; all caps positive integers; the source flow must not be manifest-only. Query count per round = `(sum of terms over all topics) × (number of distinct apis)`; `max_total_requests = query_count × max_requests_each × rounds`.

Suggested defaults (from `docs/GUIDE.md` and `docs/LOCAL_COMPOSE_TRIAL.md`): `per_query = 25`, `max_requests_each = 3`, `max_units_each = query_count`; hosts by API: `openalex → api.openalex.org`, `crossref → api.crossref.org`, `arxiv → export.arxiv.org`. They are *suggestions the person sees and can edit under Advanced options*, never hidden.

## File structure

- Modify `web/src/lib/control.ts` — write methods + types. (W1)
- Create `web/src/lib/cadence.ts`, `web/src/lib/figures.ts` — pure. (W2)
- Create `web/src/pages/NewSeriesPage.tsx`, `web/src/components/scheduler/{RoundsEditor,FiguresPanel}.tsx`; modify `App.tsx`. (W3)
- Modify `web/src/components/scheduler/{CalendarStep,PolicyStep,MandateStep}.tsx`; create `GrantPanel.tsx`, `PolicyForm.tsx`, `MandateForm.tsx`. (W4–W5)
- Modify `web/src/pages/CumulativeResultPage.tsx`; create `web/src/components/scheduler/ExportPanel.tsx`. (W6)
- Tests: `tests/controlschedulerwrite.test.ts`, `tests/cadence.test.ts`, `tests/figures.test.ts`, `tests/newseries.test.tsx`, `tests/grants.test.tsx`, `tests/schedulerexport.test.tsx`.

---

### Task W1: Write methods

**Files:** modify `web/src/lib/control.ts`; create `web/tests/controlschedulerwrite.test.ts`.

- [ ] **Step 1: Failing tests** — one per route of the table: assert the URL (project and ids percent-encoded), method, exact JSON body, and that the CSRF header is set; additionally: a `409` body `{error:{code:"PLAN_DIFFERS",message}}` rejects with a `ControlError` whose `code` is `PLAN_DIFFERS`, does **not** call the unauthorized handler, and `details` is preserved; `periodicExportDownloadPath("news","abc")` returns `/control/v1/p/news/periodic-exports/abc/download` (a path only: downloads are a browser navigation with the session cookie, never a `fetch`).
- [ ] **Step 2: Implement** next to the plan-1 read methods (idempotency keys stay the default — these routes are idempotent server-side and a network retry must replay the first answer):

```ts
export interface PeriodicPlanBody {
  source_flow_id: string;
  rounds: Array<{ round: string; title: string; not_before: string; expires_at: string }>;
  apis: string[]; allowed_hosts: string[];
  max_units_each: number; max_requests_each: number; per_query: number;
}
export interface PeriodicPlanResult {
  rounds: Array<{ round: string; flow_id: string; not_before: string; expires_at: string; batch_id: string }>;
  schedule_id: string; schedule_state: string; max_total_requests: number;
}
export interface PolicyPlanBody {
  schedule_id: string; allowed_hosts: string[]; source_classes: string[];
  max_candidates: number; max_requests_each: number; not_before: string; expires_at: string;
}
export interface SeriesMandateBody {
  schedule_id: string; flow_ids: string[]; extract_model: string; review_model: string;
  max_total_local_calls: number;
}
export interface ExportCreated {   // (rename if `ExportCreated` already exists for flow exports: PeriodicExportCreated)
  export_id: string; schedule_id: string; dossier_id: string; created_now: boolean; download: string;
}
// in `control`:
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
  enableSeriesMandate: (p: string, body: SeriesMandateBody) => post<MandateStatus>(`/p/${enc(p)}/local-mandates/series`, body),
  disableMandate: (p: string, id: string) => post<MandateStatus>(`/p/${enc(p)}/local-mandates/${enc(id)}/disable`, { mandate_id: id }),
  createPeriodicExport: (p: string, scheduleId: string, dossierId: string) =>
    post<PeriodicExportCreated>(`/p/${enc(p)}/schedules/${enc(scheduleId)}/export`, { dossier_id: dossierId }),
  verifyPeriodicExport: (p: string, exportId: string) =>
    post<{ export_id: string; holds: boolean; problems: string[] }>(`/p/${enc(p)}/periodic-exports/${enc(exportId)}/verify`, {}),
  periodicExportDownloadPath: (p: string, exportId: string) => `${PREFIX}/p/${enc(p)}/periodic-exports/${enc(exportId)}/download`,
```
- [ ] **Step 3:** tests, typecheck. **Step 4: Commit** `portal: scheduler write methods`.

---

### Task W2: Cadence and figures (pure)

**Files:** create `web/src/lib/cadence.ts`, `web/src/lib/figures.ts`, `web/tests/cadence.test.ts`, `web/tests/figures.test.ts`.

- [ ] **Step 1: Failing tests**

```ts
// tests/cadence.test.ts
import { describe, expect, it } from "vitest";
import { checkRounds, generateRounds } from "@/lib/cadence";

const NOW = new Date("2026-10-12T10:00:00Z");

describe("generateRounds", () => {
  it("monthly: four windows from the start date, each ending where the next begins", () => {
    const r = generateRounds({ kind: "monthly", start: "2026-11-01", count: 4 }, "Update");
    expect(r.map((x) => x.round)).toEqual(["update-2026-11", "update-2026-12", "update-2027-01", "update-2027-02"]);
    expect(r[0]).toMatchObject({ not_before: "2026-11-01T00:00:00Z", expires_at: "2026-12-01T00:00:00Z", title: "Update 2026-11" });
    expect(r[3].expires_at).toBe("2027-03-01T00:00:00Z");
  });
  it("monthly from the 31st clamps to short months and never goes backwards", () => {
    const r = generateRounds({ kind: "monthly", start: "2026-12-31", count: 3 }, "Update");
    expect(r.map((x) => x.not_before)).toEqual(["2026-12-31T00:00:00Z", "2027-01-31T00:00:00Z", "2027-02-28T00:00:00Z"]);
    expect(r[2].expires_at).toBe("2027-03-31T00:00:00Z");
  });
  it("weekly and every-N-days step by whole days", () => {
    const w = generateRounds({ kind: "weekly", start: "2026-11-02", count: 2 }, "Update");
    expect(w[1].not_before).toBe("2026-11-09T00:00:00Z");
    const d = generateRounds({ kind: "days", start: "2026-11-02", every: 10, count: 2 }, "Update");
    expect(d[1].not_before).toBe("2026-11-12T00:00:00Z");
    expect(d[0].round).toBe("update-2026-11-02");
  });
  it("names are URL-safe whatever the title prefix", () => {
    const r = generateRounds({ kind: "weekly", start: "2026-11-02", count: 1 }, "Aggiornamento città");
    expect(r[0].round).toMatch(/^[A-Za-z0-9_-]+$/);
  });
});

describe("checkRounds (early messages; the server stays the authority)", () => {
  const ok = generateRounds({ kind: "monthly", start: "2026-11-01", count: 2 }, "Update");
  it("accepts a clean list", () => expect(checkRounds(ok, new Set(), NOW)).toEqual([]));
  it("flags a start in the past", () => {
    const bad = generateRounds({ kind: "monthly", start: "2026-10-01", count: 1 }, "Update");
    expect(checkRounds(bad, new Set(), NOW).map((p) => p.code)).toContain("PAST");
  });
  it("flags overlap, disorder, duplicate and known round names, and the 366-day limit", () => {
    const a = { round: "r1", title: "t", not_before: "2026-11-01T00:00:00Z", expires_at: "2026-12-01T00:00:00Z" };
    const b = { round: "r1", title: "t", not_before: "2026-11-15T00:00:00Z", expires_at: "2026-12-15T00:00:00Z" };
    const codes = checkRounds([a, b], new Set(["r9"]), NOW).map((p) => p.code);
    expect(codes).toEqual(expect.arrayContaining(["OVERLAP", "DUPLICATE"]));
    expect(checkRounds([{ ...a, round: "r9" }], new Set(["r9"]), NOW).map((p) => p.code)).toContain("KNOWN");
    const far = { round: "far", title: "t", not_before: "2027-09-01T00:00:00Z", expires_at: "2027-11-15T00:00:00Z" };
    expect(checkRounds([far], new Set(), NOW).map((p) => p.code)).toContain("TOO_FAR");
  });
  it("flags 0 or more than 32 rounds, a bad name and an empty title", () => {
    expect(checkRounds([], new Set(), NOW).map((p) => p.code)).toContain("COUNT");
    const bad = { round: "has space", title: " ", not_before: "2026-11-01T00:00:00Z", expires_at: "2026-12-01T00:00:00Z" };
    expect(checkRounds([bad], new Set(), NOW).map((p) => p.code)).toEqual(expect.arrayContaining(["NAME", "TITLE"]));
  });
});
```
```ts
// tests/figures.test.ts
import { describe, expect, it } from "vitest";
import { figures, hostsFor, queryCount } from "@/lib/figures";

describe("figures", () => {
  const topics = [{ terms: ["a", "b", "c"] }, { terms: ["d"] }];
  it("query count is every term of every topic times the distinct sources", () => {
    expect(queryCount(topics, ["openalex", "crossref", "openalex"])).toBe(8);
    expect(queryCount([], ["openalex"])).toBe(0);
  });
  it("the ceiling is searches x requests each x rounds", () => {
    expect(figures({ topics, apis: ["openalex", "crossref"], maxRequestsEach: 3, rounds: 4 })).toEqual({
      searchesPerRound: 8, searchesTotal: 32, requestsPerRound: 24, requestsTotal: 96, minUnitsEach: 8 });
  });
  it("hosts follow the sources, sorted and unique", () => {
    expect(hostsFor(["crossref", "openalex", "openalex"])).toEqual(["api.crossref.org", "api.openalex.org"]);
  });
});
```
Run → FAIL.

- [ ] **Step 2: Implement `cadence.ts`**

```ts
// Rounds from a cadence, and the early checks the server repeats. All times are UTC midnight.
export type Cadence =
  | { kind: "monthly"; start: string; count: number }
  | { kind: "weekly"; start: string; count: number }
  | { kind: "days"; start: string; every: number; count: number };

export interface RoundDraft { round: string; title: string; not_before: string; expires_at: string }
export interface RoundProblem { index: number; code: "COUNT" | "NAME" | "TITLE" | "PAST" | "ORDER" | "OVERLAP" | "DUPLICATE" | "KNOWN" | "TOO_FAR" | "WINDOW"; }

const DAY = 86_400_000;
const iso = (d: Date) => `${d.toISOString().slice(0, 19)}Z`;
const parseDay = (s: string) => new Date(`${s}T00:00:00Z`);

function addMonths(start: Date, months: number): Date {
  const y = start.getUTCFullYear(), m = start.getUTCMonth() + months, day = start.getUTCDate();
  const last = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();   // last day of the target month
  return new Date(Date.UTC(y, m, Math.min(day, last)));
}

function boundaries(c: Cadence): Date[] {
  const start = parseDay(c.start);
  const out: Date[] = [];
  for (let i = 0; i <= c.count; i += 1) {
    out.push(c.kind === "monthly" ? addMonths(start, i)
      : new Date(start.getTime() + i * (c.kind === "weekly" ? 7 : c.every) * DAY));
  }
  return out;
}

const slug = (text: string) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
  .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "round";

/** One window per step, each ending exactly where the next begins (the server allows end == next start). */
export function generateRounds(c: Cadence, titlePrefix: string): RoundDraft[] {
  const b = boundaries(c);
  const unit = c.kind === "monthly" ? 7 : 10;                  // YYYY-MM or YYYY-MM-DD
  return b.slice(0, c.count).map((from, i) => {
    const label = iso(from).slice(0, unit);
    return { round: `${slug(titlePrefix)}-${label}`, title: `${titlePrefix} ${label}`,
             not_before: iso(from), expires_at: iso(b[i + 1]) };
  });
}

/** Early messages only. The server's refusal is shown verbatim when it differs. */
export function checkRounds(rounds: RoundDraft[], knownRounds: Set<string>, now: Date): RoundProblem[] {
  const problems: RoundProblem[] = [];
  if (rounds.length < 1 || rounds.length > 32) problems.push({ index: -1, code: "COUNT" });
  const seen = new Set<string>();
  let lastStart = -Infinity, lastEnd = -Infinity;
  rounds.forEach((r, index) => {
    if (!/^[A-Za-z0-9_-]{1,80}$/.test(r.round)) problems.push({ index, code: "NAME" });
    if (seen.has(r.round)) problems.push({ index, code: "DUPLICATE" });
    if (knownRounds.has(r.round)) problems.push({ index, code: "KNOWN" });
    seen.add(r.round);
    if (!r.title.trim()) problems.push({ index, code: "TITLE" });
    const start = Date.parse(r.not_before), end = Date.parse(r.expires_at);
    if (!(start < end)) problems.push({ index, code: "WINDOW" });
    if (start <= now.getTime()) problems.push({ index, code: "PAST" });
    if (end > now.getTime() + 366 * DAY) problems.push({ index, code: "TOO_FAR" });
    if (start <= lastStart) problems.push({ index, code: "ORDER" });
    else if (start < lastEnd) problems.push({ index, code: "OVERLAP" });
    lastStart = start; lastEnd = end;
  });
  return problems;
}
```
and **`figures.ts`**:
```ts
export const HOST_FOR: Record<string, string> = {
  openalex: "api.openalex.org", crossref: "api.crossref.org", arxiv: "export.arxiv.org" };
export const SOURCES = ["openalex", "crossref", "arxiv"] as const;

export const queryCount = (topics: Array<{ terms: string[] }>, apis: string[]): number =>
  topics.reduce((n, t) => n + t.terms.length, 0) * new Set(apis).size;

export const hostsFor = (apis: string[]): string[] =>
  [...new Set(apis.map((a) => HOST_FOR[a]).filter(Boolean))].sort();

export function figures(i: { topics: Array<{ terms: string[] }>; apis: string[]; maxRequestsEach: number; rounds: number }) {
  const searchesPerRound = queryCount(i.topics, i.apis);
  return { searchesPerRound, searchesTotal: searchesPerRound * i.rounds,
           requestsPerRound: searchesPerRound * i.maxRequestsEach,
           requestsTotal: searchesPerRound * i.maxRequestsEach * i.rounds,
           minUnitsEach: searchesPerRound };
}
```
- [ ] **Step 3:** tests pass (fix the test expectations only if you can show the server rule says otherwise — they encode `end == next start` allowed and clamping). **Step 4: Commit** `portal: cadence and request-figure helpers`.

---

### Task W3: "New series"

**Files:** create `web/src/pages/NewSeriesPage.tsx`, `web/src/components/scheduler/{RoundsEditor,FiguresPanel}.tsx`, `web/tests/newseries.test.tsx`; modify `App.tsx` (route `p/:project/scheduler/new`), catalogs (`sched.new.*`).

Page behaviour: signed out → sign-in line. Loads `api.projects()` (the project's flows: offer those with `selector.manifest_only === false`; show `selector_label`/title; default the newest `CURRENT`), and `api.overview(project, "f", flowId)` for `journey.topics` (term counts) of the chosen flow. `knownRounds` = every flow's `selector.round` plus the labels of unbound round selectors (they have candidates). Form state: flow, cadence (`monthly` default / `weekly` / `days` + `every`), start date (default the first of next month, UTC), count (default 3), rounds (the editable list from `generateRounds`, regenerated when cadence inputs change **unless the person has edited a row**, in which case ask "Regenerate and lose your edits?" with an inline confirm — no `window.confirm`), sources (checkboxes OpenAlex/Crossref/arXiv, none ticked by default → the submit stays disabled with the reason), and *Advanced options*: hosts (textarea, prefilled by `hostsFor`), `per_query` (25), `max_requests_each` (3), `max_units_each` (= `minUnitsEach`, must be ≥). `FiguresPanel` shows the preview from `figures()`: searches per round, searches in all, requests per round, **ceiling in all**; it says these are a preview and the server's `max_total_requests` is the figure that counts. Early problems from `checkRounds` appear under the rounds editor with catalog sentences (`sched.new.problem.<CODE>`). Fixed explanation block "What Claimstone will do after you save": it freezes one flow and one set of exact searches per round, writes only a plan on disk, makes **no request**, authorizes nothing; the next step is the series page where the calendar is approved separately. Submit → `control.planPeriodic`; on success `navigate` to `/p/:project/scheduler/s/:schedule_id`; on `409 REFUSED` / `422` show the server's sentence in a `role="alert"` above the button (with `details` mapped to fields when present) and keep every field; busy → disabled. Reuse `useLeaveWarning` from `components/wizard` for unsaved edits (tab close/reload).

- [ ] **Step 1: Failing tests** (`tests/newseries.test.tsx`, fetch stubbed by URL; reuse the project/overview fixtures of `flowpage` tests):
  1. renders the flows (manifest-only excluded), the figures update live when a source is ticked / `max_requests_each` changes (e.g. 2 topics × 3 terms … assert exact numbers);
  2. submit disabled with no source and with a past start, with the early sentence shown;
  3. the submit body is exactly `{source_flow_id, rounds, apis, allowed_hosts, max_units_each, max_requests_each, per_query}` with the generated rounds, hosts from the ticked sources, `apis` sorted, caps as numbers;
  4. editing a row then changing the count asks before regenerating (inline confirm), keeping the edit if declined;
  5. success navigates to the series page route (assert via a `Where` probe); the page never claims anything is authorized;
  6. `409 REFUSED {message: "round cap must cover every frozen discovery query"}` shows that sentence and keeps the form values; a second submit is blocked while busy;
  7. Italian rendering of labels and the explanation block.
- [ ] **Step 2: Implement.** **Step 3:** tests, typecheck, `npm test`. **Step 4: Commit** `portal: create a series of dated updates from a cadence`.

---

### Task W4: Grant the calendar

**Files:** create `web/src/components/scheduler/GrantPanel.tsx`; modify `CalendarStep.tsx`; create `web/tests/grants.test.tsx` (extended in W5); catalogs (`sched.calendar.*`).

`GrantPanel` is the one confirmation pattern for all three grants. Props: `{ title: string; explanation: ReactNode; confirmLabel: string; actionLabel: string; danger?: boolean; onConfirm: () => Promise<unknown>; onDone: () => void; onDiffers: () => void }` — `onConfirm` calls the matching `control.*` method with the values the parent displays, `onDone` re-reads the parent's data after success, `onDiffers` re-reads after a `PLAN_DIFFERS` (the panel itself clears its checkbox and shows the sentence). It keeps no copy of the server's state.

The pattern: a labelled checkbox ("I have read what this permits and its limits") that enables the primary button; the button sends exactly the values currently shown on the page; while busy everything is disabled; afterwards the parent **re-reads** (calls its `reload()`), no local "approved" flag exists. States:
- Schedule `PLANNED` → the permits / does-not-permit / may-spend text with the figures (`rounds`, UTC windows, `units.length` searches in total, `max_total_requests`) and **Authorize** (`control.authorizeSchedule(project, id, {plan_sha256: schedule_id, max_total_requests: plan.max_total_requests})`).
- `AUTHORIZED` → who and when from `events` (verbatim), and **Revoke** (an inline sentence: "Stops later starts. A search already running finishes.") → `control.revokeSchedule(project, id, schedule_id)`.
- `REVOKED` → who and when; no action (the server refuses re-authorizing a revoked schedule; say so).
Errors: `409 PLAN_DIFFERS` → "The plan changed after you opened this page. Reloaded below; read it again before deciding." and trigger `reload()`, clear the checkbox; `409 REFUSED` → the sentence verbatim; `403`/`429` as given.

- [ ] **Step 1: Failing tests:** (a) `PLANNED`: the button is disabled until the box is ticked; ticking and clicking posts exactly `{plan_sha256, max_total_requests}` as displayed, then `GET` schedule is requested again (assert order); (b) a `PLAN_DIFFERS` answer clears the checkbox, shows the sentence, triggers a re-read and no automatic retry (assert the POST was sent once); (c) `AUTHORIZED` shows the operator name from `events` and Revoke posts `{plan_sha256}`; (d) `REVOKED` shows no action and the refusal note; (e) double click sends one request; (f) Italian.
- [ ] **Step 2: Implement.** **Step 3:** tests, typecheck. **Step 4: Commit** `portal: authorize and revoke the calendar`.

---

### Task W5: Future copies and the local model

**Files:** create `PolicyForm.tsx`, `MandateForm.tsx`; modify `PolicyStep.tsx`, `MandateStep.tsx`; extend `tests/grants.test.tsx`; catalogs (`sched.policy.*`, `sched.mandate.*`).

**Copy policy.** If the series has none and the schedule is `AUTHORIZED` or `PLANNED`: `PolicyForm` — hosts (textarea, one exact HTTPS host per line, lowercase, **no default**: the person names the hosts copies may come from), source classes (checkbox list suggested from `api.overview(project,"f",firstFlow).floor_panel.by_class` keys, plus a free-text field for other declared class ids; the server refuses undeclared ones — show its sentence), UTC window (defaults: schedule's first `not_before` → last `expires_at`; editable; shown in UTC), `max_candidates`, `max_requests_each`; live product line `max_candidates × max_requests_each = ceiling`. Submit → `control.planCopyPolicy` (state `PLANNED`, nothing permitted); the step then shows the frozen policy and **Authorize** via `GrantPanel` with `{policy_sha256: policy_id, max_candidates, max_requests_each, max_total_requests}` read from `policy`; `AUTHORIZED` shows reservations (`reserved_candidates/max_candidates`, `reserved_requests`) and **Revoke** `{policy_sha256}`. The fixed text says: it permits requests only for new candidates that match a successful hit of this schedule's queries, on these hosts and classes and in this window; robots, redirects, non-global-address refusal and per-domain failure budgets still apply; it admits no source scientifically, buys nothing, signs nothing; later unknown candidates must still match these limits.

**Local model.** If none: `MandateForm` — two **distinct** model names (text inputs; the server validates), one lifetime call cap (positive integer); the `flow_ids` sent are `schedule.plan.entries.map(e => e.flow_id)` read from the displayed schedule (never typed). Submit → `control.enableSeriesMandate`; `409 PLAN_DIFFERS` (flows changed) re-reads. Existing mandate: state, models, `reserved_local_calls / max_total_local_calls`, remaining, pending batches, and **Disable** (`control.disableMandate`) through `GrantPanel`. Text: it permits local model calls (extraction and review) up to the cap and **no network request**; disabling stops later passes, an unfinished call is not undone.

- [ ] **Step 1: Failing tests:** (a) policy form posts exactly the seven keys with hosts split on lines/trimmed/lowercased, classes sorted, caps as numbers, window as sent; product line updates; (b) after planning, the step shows the frozen policy and Authorize posts `{policy_sha256, max_candidates, max_requests_each, max_total_requests}` equal to the displayed policy's; `PLAN_DIFFERS` re-reads; (c) revoke posts `{policy_sha256}`; (d) the server's `REFUSED "copy policy needs declared source classes"` is shown verbatim and the form keeps its values; (e) mandate form posts `flow_ids` equal to the schedule's entries in order, equal model names are flagged before sending; (f) disable posts `{mandate_id}`; (g) no purchase wording anywhere on these steps (negative text assertion); (h) the steps hide their forms while the schedule is `REVOKED`; (i) Italian.
- [ ] **Step 2: Implement.** **Step 3:** tests, typecheck, `npm test`. **Step 4: Commit** `portal: future-copy policy and local-model mandate`.

---

### Task W6: The verified package

**Files:** create `ExportPanel.tsx`; modify `CumulativeResultPage.tsx`; create `web/tests/schedulerexport.test.tsx`; catalogs (`sched.export.*`).

`ExportPanel` (on the result page, below the live-JSON button): the package button is **enabled only when** `state === "READY_FOR_HUMAN_READING"`, `finalized_dossier_id` is a string and `snapshot_stale === false`; otherwise it is disabled and names the first unmet condition. Click → `control.createPeriodicExport(project, schedule, finalized_dossier_id)`; on success show `export_id`, "created now" or "already existed", then automatically `control.verifyPeriodicExport` and display `holds` (✓/✗) and every `problems` entry verbatim; when `holds` is true show a download link `<a href={periodicExportDownloadPath} download>` (a navigation, not a `fetch`). A `409` (stale or unfinished) → "The evidence changed; the page was re-read" and re-read the dossier; a stale package from before stays listed as historical only if the page has its id (this plan keeps the id in component state for the session; no listing endpoint exists).

- [ ] **Step 1: Failing tests:** disabled in each of the four states with the right reason (not ready / not saved / superseded / ready+saved+current → enabled); click posts `{dossier_id}` equal to `finalized_dossier_id`, then verify, then shows `holds: true` and the download link with the exact path; `holds: false` shows the named problems and **no** download link; `409` re-reads the dossier (assert a second GET) and shows the sentence; no purchase wording; one POST per click; Italian.
- [ ] **Step 2: Implement.** **Step 3:** tests, typecheck, `npm test`, `npm run build`. **Step 4: Commit** `portal: package and verify the cumulative dossier`.

---

### Task W7: Browser run, handoff note (controller, with the owner)

Not delegated. In the throwaway workspace of plan 1 Task 6: create a series from the cadence form (tomorrow, 3 monthly rounds, OpenAlex only), read the series page (nothing authorized), authorize the calendar, create and authorize a copy policy, create a series mandate, watch the supervisor pick the rounds up (start `claimstone scheduler supervise` in the scratch workspace), revoke, disable; open the result page; if the scratch corpus can reach `READY_FOR_HUMAN_READING` (use the offline fixtures of `tests/test_periodic_dossier*.py` to build one) create and verify the package. English and Italian, 420 px. Then add a short "Frontend: done" status line at the top of `docs/design/portal/SCHEDULER_FRONTEND_HANDOFF.md` listing what the portal now covers and what remains (pause/resume 501, event stream, summary endpoint, signing whole-corpus profiles). Report to the owner; merge, push and redeploy only on their word (`./portal.sh up` rebuilds `web`).

---

## Self-review (done)

- **Spec coverage:** creation from a cadence with generated editable rounds, sources with exact hosts, caps, live figures, no server draft, early + server messages → W2–W3; the three grants with "permits / does not permit / may spend" text, exact echo of hashes and limits, re-read on `409`, no optimistic state, revoke/disable → W4–W5; verified package and verification result → W6; roles (all operators) → no role checks; i18n → every task; no purchase CTA → negative assertions in W5/W6 and plan 1.
- **Placeholders:** none. The two judgement items are explicit: the suggested defaults (`per_query 25`, `max_requests_each 3`, hosts by source) are labelled as suggestions from the repository's own guide, visible and editable; copy-policy source classes are suggested from the overview and otherwise free text because no read route lists a project's declared classes.
- **Type consistency:** `ScheduleStatus`/`PolicyStatus`/`MandateStatus`/`Worker`/`SchedulerIndex` come from plan 1's `lib/scheduler.ts`; write bodies match the table above; `GrantPanel` takes `{ project, kind, onDone }`-style props defined in W4 and reused in W5.
