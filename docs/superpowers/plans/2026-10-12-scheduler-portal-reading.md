# Scheduler in the portal — reading half (plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A project gets a "Scheduler" tab: an index of its series and processes, a stepped series page, and the cumulative-result page — all read-only, bilingual, and faithful to the server's words. Plan 2 (`2026-10-12-scheduler-portal-writing.md`) adds creating series, the authorizations and the exports.

**Architecture:** Typed read methods (`control.ts` for the authenticated scheduler index and reads, `api.ts` for the dossier), a small `ProjectTabs` component on the project pages, four routes under `/p/:project/scheduler`, and presentational step components that take server rows and render them. No state is derived from counts. No new backend route.

**Tech Stack:** React 19, react-router 7, Tailwind 4, Vitest + Testing Library; the wizard's i18n (`web/src/lib/i18n.tsx`, `web/src/messages/{en,it}.json`, `t()` with literal keys only).

Spec: `docs/superpowers/specs/2026-10-12-scheduler-portal-design.md` — read it first (principles, pages, error handling). Hand-off: `docs/design/portal/SCHEDULER_FRONTEND_HANDOFF.md`.

## Conventions every task follows

- Work in a worktree on branch `scheduler-portal` (the spec is committed there). `.venv` and `web/node_modules` are symlinks to the main tree's. From `web/`: `npx vitest run <file>`, `npm run typecheck`; at the end of each task also `npm test`; at the end of the plan `npm run build` (runs `check-csp`: **no inline `style`, no inline script**).
- Only `src/lib/control.ts` calls `fetch` with a non-GET. Reads of evidence go through `api.ts`; authenticated reads through `control.ts`.
- Every visible string is `t("literal.key")` with the key in **both** `en.json` and `it.json` (the catalog test fails otherwise). Italian follows the wizard's register: plain, second person.
- Server values are facts: state words (`PLANNED`, `AUTHORIZED`, `REVOKED`, `ENABLED`, `DISABLED`, `ALIVE`, `STALE`, `STOPPED`, `NOT_STARTED`, `UNKNOWN`, dossier `state`) are rendered through a lookup table that **only translates the label**; an unknown value is shown verbatim, never mapped to a default.
- Commit trailer, every commit:
  ```
  Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE
  ```
- Test style: copy `web/tests/people.test.tsx` / `account.test.tsx` (declarative `MemoryRouter`, `fetch` stubbed by URL with `vi.stubGlobal`, `setCsrfToken("tok")`, `LocaleProvider` + `SessionProvider`).

## The server shapes (copied from the code; plan against these)

`GET /control/v1/p/{p}/scheduler[?limit=&cursor=]`:
```
{ project, schedules: ScheduleStatus[], copy_policies: PolicyStatus[], local_mandates: MandateStatus[],
  workers: { supervisor: Worker, operations: Worker, mandates: { [mandate_id]: Worker } },
  archive: { limit, offset, total: {schedules, copy_policies, local_mandates}, revision, next_cursor: string|null } }
```
`ScheduleStatus` = `{schedule_id, state: "PLANNED"|"AUTHORIZED"|"REVOKED", plan: {version, project, max_total_requests, entries: [{batch_id, operation_ids, flow_id, stage, units, max_total_requests, not_before, expires_at}]}, events: [{event, at, identity: {signer_auth, operator, name}, …}]}` (events after the first; `identity` of the authorizing/revoking operator).
`PolicyStatus` = `{policy_id, state, policy: {project, schedule_id, flow_ids, allowed_hosts, source_classes, max_candidates, max_requests_each, max_total_requests, not_before, expires_at, …}, reserved_candidates, remaining_candidates, reserved_requests, events}`.
`MandateStatus` = `{mandate_id, state: "ENABLED"|"DISABLED", flow_id, flow_ids, disabled_by, reserved_local_calls, remaining_local_calls, pending_batches: [{batch_id, stage, awaiting_approval, max_total_requests}], mandate: {schedule_id?, extract_model, review_model, max_total_local_calls, …}}`.
`Worker` = `{worker_key, state: "ALIVE"|"STALE"|"STOPPED"|"NOT_STARTED"|"UNKNOWN", last_seen_at: string|null, phase: "IDLE"|"DRIVING"|"STOPPED"|null, age_seconds: number|null}`.
`GET /api/v1/projects/{p}/periodic-dossiers/{schedule}` = `PeriodicCumulativeDossier` (already in `web/src/lib/api-types.ts`): `state`, `blockers`, `audit`, `profiles`, `human_decisions`, `snapshot_sha256`, `finalized_dossier_id`, `finalized_at`, `snapshot_stale`, `needs_finalization`, `history_count`, `verdict: null`. `audit` (typed loosely there) is `{schedule_id, schedule_state, ancestor_rounds: [...], rounds: [{round, flow_id, binding_state, not_before, expires_at, operations: {STATE: n}, successful_queries, planned_queries, admission}], cumulative_admission, ready_for_evidence_review, verdict: null}` and every `admission` is `{round, found, classified, attempted, obtained, confirmed, awaiting_normalize, blocking: string[], final: boolean, basis, rate: number|null, rate_upper, by_class: {[class]: {rate, floor, meets_floor, …}}, classes_below_floor: string[], class_floors, status: "OK"|"INSUFFICIENT_ACQUISITION", floor, floor_version, …}`.

## File structure

- Create `web/src/lib/scheduler.ts` — types for the shapes above + the pure helpers (`stateLabelKey`, `workerAlert`, `seriesOverview`). (T1)
- Modify `web/src/lib/control.ts` — `schedulerIndex`, `schedule`, `copyPolicy`, `localMandate`. (T1)
- Modify `web/src/lib/api.ts` — `periodicDossier`. (T1)
- Create `web/src/components/ProjectTabs.tsx`; modify `ProjectPage.tsx`, `FlowOverviewPage.tsx`, `App.tsx`. (T2)
- Create `web/src/pages/SchedulerPage.tsx` (index). (T3)
- Create `web/src/pages/SeriesPage.tsx` and `web/src/components/scheduler/{RoundTimeline,StepCard,PlanStep,CalendarStep,PolicyStep,MandateStep,ResultStep}.tsx`. (T4)
- Create `web/src/pages/CumulativeResultPage.tsx`. (T5)
- Modify `web/src/messages/{en,it}.json` throughout (`sched.*`).
- Tests: `tests/scheduler-lib.test.ts`, `tests/schedulertabs.test.tsx`, `tests/schedulerindex.test.tsx`, `tests/seriespage.test.tsx`, `tests/cumulativeresult.test.tsx`.

---

### Task 1: Types, read methods, pure helpers

**Files:** create `web/src/lib/scheduler.ts`, `web/tests/scheduler-lib.test.ts`; modify `web/src/lib/control.ts`, `web/src/lib/api.ts`, `web/tests/controlauth.test.ts` (or a new `tests/controlscheduler.test.ts`).

- [ ] **Step 1: Failing tests** — `tests/scheduler-lib.test.ts`

```ts
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
```
Run → FAIL.

- [ ] **Step 2: Implement `web/src/lib/scheduler.ts`**

```ts
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
  disabled_by: string | null;
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
```
Add to `api.ts` (imports `PeriodicCumulativeDossier` from `./api-types`):
```ts
  periodicDossier: (project: string, scheduleId: string) =>
    get<PeriodicCumulativeDossier>(
      `/projects/${encodeURIComponent(project)}/periodic-dossiers/${encodeURIComponent(scheduleId)}`),
```
Add to `control.ts` (`enc` exists; imports the shapes from `./scheduler`):
```ts
  schedulerIndex: (project: string, cursor?: string | null, limit = 25) =>
    get<SchedulerIndex>(`/p/${enc(project)}/scheduler?limit=${limit}${cursor ? `&cursor=${enc(cursor)}` : ""}`),
  schedule: (project: string, id: string) => get<ScheduleStatus>(`/p/${enc(project)}/schedules/${enc(id)}`),
  copyPolicy: (project: string, id: string) => get<PolicyStatus>(`/p/${enc(project)}/copy-policies/${enc(id)}`),
  localMandate: (project: string, id: string) => get<MandateStatus>(`/p/${enc(project)}/local-mandates/${enc(id)}`),
```
Tests for the methods in `tests/controlscheduler.test.ts` (fetch stub): URLs `/control/v1/p/news/scheduler?limit=25`, with a cursor `&cursor=abc%3D`, `…/schedules/<id>`, `…/copy-policies/<id>`, `…/local-mandates/<id>`; and `api.periodicDossier` → `/api/v1/projects/news/periodic-dossiers/<id>`; a `409` body `{error:{code:"ARCHIVE_CHANGED",message}}` from `schedulerIndex` rejects with `ControlError` whose `code` is `ARCHIVE_CHANGED` and does **not** sign the user out.

- [ ] **Step 3:** tests + `npm run typecheck` pass. **Step 4: Commit** `portal: scheduler shapes, read methods and the series overview`.

---

### Task 2: The Scheduler tab and routes

**Files:** create `web/src/components/ProjectTabs.tsx`, `web/tests/schedulertabs.test.tsx`; modify `ProjectPage.tsx`, `FlowOverviewPage.tsx`, `App.tsx`, catalogs.

`ProjectPage` redirects to the journey when a project has one flow (or one `CURRENT` flow), so the tabs must also render on the flow overview, or the Scheduler tab would be unreachable.

- [ ] **Step 1: Catalog keys** (`sched.tabs.flows/scheduler`, `sched.title`, plus the ones used later; add a key the moment a task needs it, in both languages). English: `Flows`, `Scheduler`. Italian: `Flussi`, `Scheduler`.
- [ ] **Step 2: Failing tests** (`tests/schedulertabs.test.tsx`): `ProjectTabs project="news"` renders two links, `Flows` → `/p/news` ... **careful:** `/p/news` redirects to the journey for a single-flow project; give the Flows link `?details=1` only when the current page is the project page, otherwise plain `/p/news`; the Scheduler link → `/p/news/scheduler` with `aria-current="page"` when on `/p/news/scheduler*`; Italian labels; project names are percent-encoded.
- [ ] **Step 3: Implement**

```tsx
import { Link, useLocation } from "react-router";
import { useLocale } from "@/lib/i18n";

// Two tabs under a project's breadcrumb. The flows tab is the project page (or, for a single-flow
// project, the flow's journey it redirects to); the scheduler tab is the series of dated updates.
export default function ProjectTabs({ project }: { project: string }) {
  const { t } = useLocale();
  const { pathname } = useLocation();
  const base = `/p/${encodeURIComponent(project)}`;
  const onScheduler = pathname.startsWith(`${base}/scheduler`);
  const link = "inline-flex min-h-11 items-center rounded-lg px-3 text-sm";
  return (
    <nav aria-label={t("sched.tabs.label")} className="flex gap-1 border-b border-border">
      <Link to={`${base}?details=1`} aria-current={onScheduler ? undefined : "page"}
            className={`${link} ${onScheduler ? "text-muted-foreground" : "bg-card font-semibold"}`}>
        {t("sched.tabs.flows")}
      </Link>
      <Link to={`${base}/scheduler`} aria-current={onScheduler ? "page" : undefined}
            className={`${link} ${onScheduler ? "bg-card font-semibold" : "text-muted-foreground"}`}>
        {t("sched.tabs.scheduler")}
      </Link>
    </nav>
  );
}
```
Render `<ProjectTabs project={project} />` in `ProjectPage` under the header and in `FlowOverviewPage` under its breadcrumb. In `App.tsx` add children routes `{ path: "p/:project/scheduler", element: <SchedulerPage /> }`, `…/scheduler/new` (plan 2), `…/scheduler/s/:schedule` → `SeriesPage`, `…/scheduler/s/:schedule/result` → `CumulativeResultPage` (create the three pages as stubs rendering their title so the routes resolve; Tasks 3–5 fill them). Existing page tests that count links or snapshot headings (`grep -rn "Breadcrumb\|getByRole(\"link\"" tests/flowpage.test.tsx tests/project*.test.tsx`) must be updated for the extra nav, nothing else.
- [ ] **Step 4:** tests, typecheck. **Step 5: Commit** `portal: a Scheduler tab on the project pages`.

---

### Task 3: The scheduler index

**Files:** create `web/src/pages/SchedulerPage.tsx`, `web/src/components/scheduler/WorkersStrip.tsx`, `web/tests/schedulerindex.test.tsx`; catalogs.

Behaviour (from the spec):
- Signed out → a line with a Sign-in link (the control API needs a session); no request.
- A **workers strip**: `workers.supervisor` first (label "Automatic scanning"), then `operations`. Each shows the server's state word (translated label), `last_seen_at`, `phase` and `age_seconds`. A `workerAlert` state is an *operational* alert (role `status`, wording: "the process that runs approved work is not running — approved work waits; nothing has failed scientifically"), and says in one sentence that `ALIVE` means the process is scanning, not that anything advanced. The strip never mentions a research outcome.
- **Series list**: one row per schedule (`overviewOfSeries`), newest first by the first entry's `not_before`: state word, `rounds`, window start → end (UTC, explicit), the three grants as small chips (Calendar: the schedule state; Copies: policy state or "not decided"; Local model: mandate state or "not decided"), the `max_total_requests`, link to `/p/:project/scheduler/s/:id`. The **"New series"** button → `/p/:project/scheduler/new`.
- **Paging**: "Load more" calls `schedulerIndex(project, next_cursor)` and appends; a `409 ARCHIVE_CHANGED` clears the list and reloads page one with a one-line notice ("The list changed while you were reading it; starting again from the first page.").
- **Mandates on a single flow** (those whose `mandate.schedule_id` is absent), listed separately with their state and remaining calls.
- Empty state: "No series yet" + the New series button.

- [ ] **Step 1: Failing tests** — stubbed `fetch` by URL (`/control/v1/p/news/scheduler?limit=25`):
  1. renders two series newest-first, with state words verbatim and the UTC window; a policy/mandate attached by `schedule_id` shows in the right row, an unattached mandate in the separate list;
  2. an `ALIVE` supervisor shows no alert; `STALE` shows the alert text and the last-seen time, and the series list is still shown (liveness never hides evidence);
  3. paging: first answer has `next_cursor: "c1"`; clicking "Load more" requests `…&cursor=c1` and appends; a `409 ARCHIVE_CHANGED` on that request restarts at page one and shows the notice;
  4. signed out → no `/scheduler` request, a sign-in link;
  5. Italian rendering of the labels (state words stay as the server sent them, e.g. `AUTHORIZED` is shown through the label table "Autorizzato" **and** the raw word is available as `title`/visually hidden text — pick one convention and apply it everywhere: **label translated, raw word in a `title` attribute**).
- [ ] **Step 2: Implement** with `useApi(() => control.schedulerIndex(project), [project])` for page one, local state for appended pages, `usePoll` (the project poll already exists) calling `reload()`; hidden-tab pause is inherited from `usePoll`. The label table lives in one module, `web/src/components/scheduler/labels.ts`, exporting `stateLabelKey(word: string): string | null` returning a catalog key for known words and `null` for an unknown one (shown verbatim); keys `sched.state.PLANNED|AUTHORIZED|REVOKED|ENABLED|DISABLED|ALIVE|STALE|STOPPED|NOT_STARTED|UNKNOWN|IDLE|DRIVING`, both languages.
- [ ] **Step 3:** tests, typecheck. **Step 4: Commit** `portal: the project's Scheduler index`.

---

### Task 4: The series page (read-only)

**Files:** create `web/src/pages/SeriesPage.tsx`, `web/src/components/scheduler/{RoundTimeline,StepCard,PlanStep,CalendarStep,PolicyStep,MandateStep,ResultStep}.tsx`, `web/tests/seriespage.test.tsx`; catalogs.

Data: `control.schedule(project, id)` (the plan and its events); `api.periodicDossier(project, id)` (rounds, admission, dossier state; may be slow — fetched on this page and the result page only); the index (for the policies and mandates of this schedule: `control.schedulerIndex(project)` then `overviewOfSeries`; if the schedule is not on the first page the page walks the cursor up to a bounded number of pages, 10, and then shows "grants not loaded" rather than guessing). A `404` on the schedule → "series not found"; registry drift / ledger errors from the dossier → a named blocking banner in place of the timeline, the plan step still shown.

`RoundTimeline`: one cell per entry, in window order: round name (from `audit.rounds[i].round`; fall back to the flow id), UTC `not_before → expires_at`, the operation counts verbatim (`{COMPLETED: 12}`), `successful_queries / planned_queries`, acquisition `confirmed / found` and `rate` (— when null) with the round's `admission.status` word, and a **"planned"** label when the schedule is not `AUTHORIZED` or the window has not opened. A round whose `admission.found === 0` says "no candidates found yet" (not a failure).

`StepCard` is the wrapper: a numbered heading, the server state chip, and three fixed text blocks **What it permits / What it does not permit / What it can spend** (catalog text per step, plus figures from props). Steps:
1. **PlanStep** — the entries table (flow, window, `units.length` searches, `max_total_requests`), the summed `plan.max_total_requests`, `schedule_id` (the plan hash) in monospace with a copy button.
2. **CalendarStep** — state word; if `PLANNED`: "No request is permitted yet." This plan renders the read-only version (no button; plan 2 adds Authorize and Revoke). Show the `events` (who, when) verbatim once authorized or revoked.
3. **PolicyStep** — if none: "Not decided" and what deciding would permit. Otherwise state, hosts, source classes, UTC window, `max_candidates × max_requests_each = max_total_requests`, `reserved_candidates/max_candidates`, `reserved_requests`, events. Always the sentence that robots, redirects, non-global-address refusal and per-domain failure budgets still apply, and that a candidate without a matching successful hit stays for operator review.
4. **MandateStep** — if none: "Not decided"; otherwise state, the two models, `reserved_local_calls / max_total_local_calls`, `remaining_local_calls`, `pending_batches` (awaiting approval, shown as such), `disabled_by`, the worker for this mandate (`workers.mandates[id]`) beside it in its own "process" line, never inside the scientific state.
5. **ResultStep** — the dossier `state` word and the first blocker, and a link to `…/result`.
Never render an "Authorize" or "Create" control in this plan.

- [ ] **Step 1: Failing tests** (`tests/seriespage.test.tsx`), `fetch` stubbed by URL, fixtures built with helpers like Task 1's:
  1. a `PLANNED` schedule shows every round as "planned", the calendar step says no request is permitted, UTC windows are printed with `UTC`;
  2. an `AUTHORIZED` one shows the authorizing operator's name and time from `events`;
  3. a round with `successful_queries: 2, planned_queries: 3` and operations `{COMPLETED: 3}` shows `2 / 3` and the dossier banner is **not** "ready" (the dossier `state` word is shown verbatim: `WAITING_FOR_SCHEDULE`);
  4. a round with `admission.found: 8, confirmed: 3` keeps `3 / 8` in the denominator (candidates found without an obtained copy are shown);
  5. a copy policy attached by `schedule_id` shows hosts, classes, both caps and the product; no purchase/pay text anywhere on the page (a negative text assertion for "buy|purchase|pay|acquista|compra|paga" on the whole rendered text);
  6. a `STALE` mandate worker shows an operational "process" line while the mandate state and the last ledger event stay visible;
  7. `404` on the schedule → "series not found"; a dossier request failing with `REGISTRY_DRIFT` → a named blocking banner and the plan step still rendered; a failing dossier read does not blank the other steps;
  8. Italian rendering.
- [ ] **Step 2: Implement** the page and components. Keep each component under ~120 lines; shared formatting (`utcRange(a, b)`, `requestsLine(each, count, total)`) goes in `web/src/components/scheduler/format.ts` with its own tests.
- [ ] **Step 3:** tests, typecheck, `npm test`. **Step 4: Commit** `portal: the series page — plan, grants, rounds and processes`.

---

### Task 5: The cumulative result page (read-only)

**Files:** create `web/src/pages/CumulativeResultPage.tsx`, `web/src/components/scheduler/{ResultBanner,AcquisitionPanel,QuestionRows}.tsx`, `web/tests/cumulativeresult.test.tsx`; catalogs.

Layout (approved on the mockup): banner → acquisition → save status → questions → downloads.
- **Banner**: the dossier `state` word (translated label, raw word in `title`) and every entry of `blockers` verbatim. Fixed text: "Ready for human reading is not a verdict." Wording per state is *only* an explanation of the word the server sent.
- **Acquisition**: from `audit.cumulative_admission`: `rate` / `floor`, `status` word, `classes_below_floor` highlighted, a row per `by_class` entry with its `rate` and its own `floor` and `meets_floor`; below it the same for each round in `audit.rounds` (compact). `rate: null` → "—".
- **Save status**: `finalized_dossier_id` (or "not saved"), `finalized_at`, `history_count`, and **"superseded"** when `snapshot_stale`; `needs_finalization` shown as a plain fact, not as a decision.
- **Questions**: for each `profiles[i]` and each `human_decisions[i]` (match by `question_id`; a decision without a profile is still shown): question id, profile state (provisional if the dossier state is not ready), `profile_sha256` shortened with a copy button, the current signature (`verdict` object's word, or "no signature"), a **stale** marker when `human_decisions[i].stale` or `stored_profile_stale`, and the `unavailable` reason string verbatim if present. Operational questions (`unavailable === "LITERATURE_VERDICT_NOT_APPLICABLE"` or the field naming it) say "no literature verdict applies". The link goes to `/p/:project/u/-/q/:qid` — the whole-store reader (slug `-`) — **only when that selector exists**; if the reader answers 404 the row shows the id without a link. Fixed note under the table: "Signing in the portal is done per flow, on that flow's own profile; this page only shows the whole-corpus profiles and signatures that exist." (A known limit of the current server: the sign route is per flow. Raise it with the owner in the final report.)
- **Downloads** (this plan: the live JSON only): button "Download the live report (JSON)" builds a `Blob` of the exact payload already fetched and saves it as `periodic-dossier-<schedule 12>.json` via an `<a download>` (no network request, nothing leaves the page). The label says **"live report"** unless `finalized_dossier_id` is present **and** `snapshot_stale` is false, in which case it says "current saved dossier". The verified package arrives with plan 2.

- [ ] **Step 1: Failing tests:**
  1. `INSUFFICIENT_ACQUISITION` with empty `profiles`: the blocker is in the banner, no question has a profile hash, the questions table says "no current profile";
  2. `WAITING_FOR_EVIDENCE`: profiles shown as provisional; `READY_FOR_HUMAN_READING`: the banner adds "not a verdict" and **no signature is preselected** (every unsigned question reads "no signature");
  3. a stale saved dossier (`snapshot_stale: true`) shows "superseded" and the previous signature stays visible with its stale marker;
  4. a class below its own floor is highlighted and named; `rate: null` renders "—";
  5. the live JSON button creates a Blob whose text equals `JSON.stringify(payload)` (spy on `URL.createObjectURL`), makes no `fetch` call, and its label is "live report" unless final and current;
  6. `REGISTRY_DRIFT`/ledger error from the API → a named blocking state, never an empty page; `404` unknown schedule → "series not found";
  7. the page makes **one** dossier request on load and re-reads on the project poll only (assert the call count after one poll tick via `vi.useFakeTimers`);
  8. Italian rendering.
- [ ] **Step 2: Implement.** **Step 3:** tests, typecheck, `npm test`, `npm run build`. **Step 4: Commit** `portal: the cumulative result page`.

---

### Task 6: Browser check (controller, with the owner)

Not delegated. Create a throwaway workspace with the example project plus a hand-made frozen schedule (use `claimstone scheduler periodic-plan` from the CLI on `projects/example-news-and-returns` against a scratch `store/`, with a rounds file whose windows start tomorrow), run `claimstone control` and `claimstone api` on scratch ports with `--allow-host localhost:5173`, start Vite from the worktree (proxy ports are in `web/vite.config.ts`: 8788 read API, 8790 control), sign in, and walk: the tab on a single-flow project (reachable from the journey), the index with its workers strip (start and stop `claimstone scheduler supervise` to see `ALIVE` → `STOPPED`/`STALE`), the series page before and after `claimstone scheduler schedule-authorize`, the cumulative page, the live JSON download; in Italian and English and at 420 px (no horizontal overflow). Report anything odd to the owner; do not merge or push without their word.

---

## Self-review (done)

- **Spec coverage:** tab + routes → T2; index, workers strip, paging, single-flow mandates → T3; series page with timeline and the five steps' read side → T4; cumulative result (banner, acquisition, save status, questions, live JSON) → T5; principles (server words, planned≠running, liveness apart, no verdict, no paywall CTA) → asserted in T3–T5 tests; bilingual → every task. Creation, authorizations, revocations, exports, verified package → plan 2.
- **Open item to raise with the owner:** the portal's sign route is per flow (`/control/v1/p/{p}/flows/{flow}/q/{q}/adjudicate`), while a cumulative dossier's profiles are whole-store; the page links to the read-only whole-store reader and says so. If the owner wants signing a cumulative profile from the portal, that is a backend decision first.
- **Placeholders:** none; test fixtures use the shapes copied from the code above. Catalog texts are written by the implementer in both languages from the fixed wording given in each task, and reviewed by the owner at T6.
