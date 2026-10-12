# Scheduler in the portal — plans, authorizations, workers, cumulative result: design

Status: proposed, 2026-10-12. Backend: D123–D130 (done, deployed). This document designs the
**frontend only**; no server route is added. Read first: `docs/design/portal/SCHEDULER_FRONTEND_HANDOFF.md`
(the backend's own hand-off), and the contracts it names: `docs/contracts/control_api.md` (§Finite
periodic scheduler controls D128, §Worker observation D129), `network_schedules.md`, `copy_policies.md`,
`local_mandates.md`, `periodic_dossiers.md`, `periodic_exports.md`, `worker_runtime.md`,
`scheduler_operations.md`.

## Why

The backend can plan finite dated discovery rounds, take three separate human authorizations (the
calendar, a future-copy policy, a local-model mandate), run them under one supervisor and build a
whole-corpus evidence dossier. None of it is reachable from the portal: today the only scheduler UI is
`OperationsPanel` ("Right now": list operations and batches, authorize the planned ones). Everything
else is a CLI command. The portal must let a person **create** a periodic plan, **read** exactly what
each authorization permits and may spend, **grant and revoke** it, **see** whether the machinery is
alive, and **read the cumulative result** before signing — without ever turning a plan into a run, a
completed operation into a completed research round, or a ready dossier into a verdict.

## Decisions taken with the user (2026-10-12)

- **Scope of the first version:** show and authorize what the scheduler already does, **and** create
  periodic plans from the portal.
- **Placement: a "Scheduler" tab per project**, next to the flows. Not inside each flow (a series has
  several child flows and one policy/mandate/dossier for all of them), not a global menu entry.
- **A series page is a stepped path**: round timeline on top, then Plan → Calendar → Future copies →
  Local model → Cumulative result, one step under another, each saying what it permits, what it does
  not permit and what it can spend.
- **Creating a series** uses a **cadence** (every month / week / N days, start date, number of rounds)
  that generates an editable list of rounds.
- **The cumulative result** has its own page: state and blockers first, then thresholds, questions,
  downloads. No verdict is ever preselected.
- **Roles:** every operator may do all of this; an admin differs only in managing people
  (decision D131). Each authorization records the signed-in operator.
- Italian and English from the start, on the wizard's i18n infrastructure.

## Principles (from the hand-off and `CLAUDE.md`)

1. **Server values are facts.** The UI never derives a state from counts. `COMPLETED` on an
   operation means its finite unit ended; it is not a research round or a question completed.
   `READY_FOR_HUMAN_READING` means the dossier gates passed; it is not a verdict.
2. **A plan is `planned`, never `running`.** Before authorization the UI says no request is
   permitted. UTC start and expiry are always explicit.
3. **Process liveness and scientific progress live in different places.** A stale or stopped worker
   is an operational alert; it never erases the last ledger event and never implies a failed search.
4. **No optimistic approval.** Every write is followed by a re-read; a `409` re-reads and asks the
   person again. An authorization repeats exactly the hash and limits the page showed.
5. **A `403` is an access refusal, not proof of a paywall.** No purchase call-to-action exists
   without a verified offer, which this feature never creates.
6. **Whole-corpus dossier ≠ last round.** The cumulative result is a project-level object linked
   from every update flow. Per-class floors sit beside the overall rate.

## Pages and navigation

The project page (`/p/:project`) gets tabs **Flows** (today's content) and **Scheduler**. A flow that
belongs to a series shows a chip "Series … · round …" linking to its series page (the relation comes
from the schedule's entries).

| Route | Page |
|---|---|
| `/p/:project/scheduler` | Index |
| `/p/:project/scheduler/new` | New series |
| `/p/:project/scheduler/s/:schedule` | The series (stepped path) |
| `/p/:project/scheduler/s/:schedule/result` | Cumulative result |

**Index.** A strip with the supervisor and process state (`workers.supervisor`, then per-mandate on
the page): `ALIVE` / `STALE` / `STOPPED` / `NOT_STARTED` / `UNKNOWN`, each with its meaning; `STALE`,
`UNKNOWN` and `STOPPED` are operational alerts. Below it the series, paged with `?limit=25` and
`archive.next_cursor`; `409 ARCHIVE_CHANGED` restarts at page one. Mandates attached to a single flow
(not a series) are listed separately. Each series row shows its state, rounds done / total, the
authorization state of its three grants and the cumulative state.

**New series** — one page form, no server draft (planning appends only a frozen local plan and
starts nothing):
1. *Starting flow* — a non-manifest flow of the project (a manifest-only flow is refused by the
   server; do not offer it).
2. *When* — cadence (monthly, weekly, every N days), start date, number of rounds (1–32) generate an
   editable list `{round, title, not_before, expires_at}`: names `[A-Za-z0-9_-]+` unique and not
   already a round with candidates, windows future, ordered, non-overlapping, ending within 366 days
   of planning. The client checks these for early messages; the server's refusal wins and is shown
   under the field it names.
3. *Where and how much* — sources (OpenAlex, Crossref, arXiv) with exact hosts filled in
   (`api.openalex.org`, `api.crossref.org`, `export.arxiv.org`), and under *Advanced options* the
   hosts, `per_query`, `max_units_each`, `max_requests_each`, defaulted so the round cap covers every
   frozen query.
Beside the form, live figures: searches per round = (terms of all topics) × (distinct sources); the
round cap must be at least that; lifetime ceiling = searches × requests each × rounds. These are
a preview; the response's `max_total_requests` is the truth. On success the person lands on the
series page, with nothing authorized.

**The series.** The round timeline (UTC windows, planned vs successful queries, acquisition per
round, whole-corpus floor) above these steps:
1. *Plan* — read-only: rounds, windows, exact query units, the summed request cap, `plan_sha256`.
2. *Calendar* — what it permits (only these frozen discovery queries, in these windows, up to this
   request ceiling), what it does not (copies, the local model, a verdict), what it may spend.
   *Authorize* posts the displayed `plan_sha256` and `max_total_requests`; *Revoke* posts the hash and
   stops later starts (a unit already running finishes). The actor and time come from `events`.
3. *Future copies* — a form: exact hosts, source classes, UTC window, `max_candidates`,
   `max_requests_each` (their product is the lifetime ceiling, shown); then authorize with
   `policy_sha256` and the three limits repeated from the GET. States that robots, redirects,
   non-global-address refusal and the per-domain failure budgets still apply, that a candidate
   without a matching successful hit stays for operator review, and that a copy is not an admission.
4. *Local model* — two distinct model names (extraction, review) and one lifetime call cap over the
   exact ordered child flows; shows reservations and remaining calls; *Disable* stops later passes.
   States that this authorizes no network request.
5. *Cumulative result* — the state and blocker, link to the page.

**Cumulative result.** (Layout approved on the mockup.) State and blockers in a banner; acquisition
(overall and per class, floor and rate); save status (`finalized_dossier_id`, `snapshot_stale`,
`history_count`); the questions with profile state, provisional blockers, profile hash, the current
signature (`null` = none) with a visible **stale** marker, and a link to the existing question reader
and signature panel — there is no "approve result" control; operational questions say no literature
verdict applies; downloads: the live JSON (labelled "live report" unless a matching, non-stale
`finalized_dossier_id` exists) and the verified package (`POST …/export` with the current
`finalized_dossier_id`, then the authenticated download and `POST …/verify`, showing `holds` and any
named problem), enabled only when `state` is `READY_FOR_HUMAN_READING`, a finalized id exists and
`snapshot_stale` is false.

## Data flow, freshness, errors

- Reads of the evidence (`GET /api/v1/projects/{p}/periodic-dossiers/{schedule}`, flows) go through
  `api.ts`; everything authenticated — the scheduler index, schedule/policy/mandate reads, plan,
  authorize, revoke, disable, export — goes through `control.ts`, the only module allowed to send a
  non-GET. Types follow the contracts; a type may not give a state a meaning the server does not.
- Polling at the rate of the existing flow journey, slower when the tab is hidden; the dossier read
  recomputes on every GET and may be costly, so it is fetched only on the series and result pages and
  never in a list.
- `404` → "not found"; registry drift or ledger integrity errors → a named blocking state, never an
  empty result; `409 PLAN_DIFFERS` / `REFUSED` → show the server's sentence, re-read the plan, ask for a
  new action; `409 ARCHIVE_CHANGED` → restart paging; `501` on pause/resume → controls disabled with the
  server's reason; `429` / `403` as given.
- Authorization buttons are disabled while a request is in flight. After any `409` nothing is retried
  automatically: a changed plan or limit always needs a fresh human action.

## Language

Italian and English from the start, using the wizard's catalog and `t("literal.key")` rule. Fixed
explanatory text (what each step permits / does not / may spend) plus figures computed by the server;
an unknown figure is shown as "—". The Italian copy follows the wizard's register and is reviewed by
the owner before release.

## Tests

- Component tests with a stubbed `fetch`, one per item of the hand-off's acceptance walkthrough:
  a planned future round shows a timeline and no permission; a query with `ok: false` or an empty
  update never shows the dossier as ready; a candidate without an obtained copy stays in the
  denominator; a copy policy shows hosts, classes and both caps; a `403` has no purchase action;
  below the floor `profiles` is empty and the blocker is prominent; once ready no verdict is
  preselected; a later evidence change marks the saved dossier and the signature stale and keeps the
  previous record visible; a changed plan yields `409` and a re-read with no "approved" state; the live
  JSON is labelled live unless final and current; the verified package needs ready + finalized +
  not stale; a stale worker heartbeat does not hide the last ledger event.
- Form tests for the cadence generator (months with 28–31 days, ordering, the 366-day limit, window in
  the past) and for the live figures.
- Catalog test: every key in both languages. Typecheck, the existing suite, build and `check-csp`.
- A real-browser run against the real control and read servers with an example project (as for the
  wizard), in Italian and English, at 420 px: create a series, read its steps, authorize the calendar,
  create a policy and a mandate, open the cumulative result, download the live JSON.

## Out of scope

Pause and resume (the server answers `501`), a real-time event stream, a cheap server-side summary
endpoint, any new backend route, and translating the rest of the portal. Opening the portal beyond
this computer remains a separate piece of work (D131).
