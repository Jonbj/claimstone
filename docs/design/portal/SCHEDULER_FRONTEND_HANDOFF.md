# Frontend handoff: Claimstone scheduler and periodic research

Read this before adapting `web/` to the scheduler. This is an implementation
handoff, not a visual redesign. The current portal design under
`docs/design/portal/` remains the visual source; `CLAUDE.md`, the contracts and
the server determine scientific and authorization meaning. This document
describes the backend after D126. No frontend file was changed for D123–D126.

## What the operator is doing

The operator creates a frozen research protocol, authorizes finite work, then
watches Claimstone find sources, acquire legal copies, normalize them, extract
quoted claims, obtain independent reviews and build evidence profiles. A
dated update is a new flow linked to the previous one. Its final dossier
describes the **whole corpus across all rounds**. The person reads each
question profile and signs a verdict; there is no automatic verdict.

The interface should answer four questions at a glance:

1. What is running now, and under which exact authorization?
2. What needs my action, and what will that action permit or spend?
3. What stopped, why, and what can safely happen next?
4. Is the whole-corpus result current, ready for my reading, or superseded?

Use server values as facts. `COMPLETED` on an operation means its finite unit
ended; it does **not** mean a research round or a question is scientifically
complete. `READY_FOR_HUMAN_READING` means the dossier gates passed; it is not
a verdict. A 403 is an access refusal, not proof of a paywall. A planned batch
has no permission to make a request.

## The UI model

Keep the existing project → flow → question hierarchy. Add a *Scheduler*
section to each flow journey, with compact cards for discovery, copies,
normalization, extraction, review, profile and human reading. Each card shows
state, count or remaining work, latest activity and a drill-down to the
underlying evidence or operation. Use the existing activity feed for actual
events; a plan is labelled `planned`, never `running`.

For a dated series, show the linked flows as a timeline: protocol source flow,
each UTC window, planned/successful queries, acquisition per round and the
whole-corpus floor. The dossier belongs at the project level or a separate
"Cumulative result" tab linked from every update flow; it is not the profile
of the last round. Show per-class floors beside the overall acquisition rate.

The dossier view should open with its state and blockers, then list questions.
For each scientific question, show profile state, provisional blockers,
profile hash, current human verdict if any, and a visible stale marker.
Operational questions show "No literature verdict applies". The detailed
question reader and signature panel already exist: link to them, do not
invent an automatic "approve result" control. When evidence changes, keep
the previous signed verdict visible as history but mark it stale.

## Read APIs available now

The read service uses `/api/v1` and is unauthenticated on local/VPN deployment;
it never writes. `GET /api/v1/projects` lists project and flow identities.
The existing flow routes provide `summary`, `overview`, `inbox`, activity,
question detail, historical profiles and profile diffs. The new route is:

```
GET /api/v1/projects/{project}/periodic-dossiers/{schedule_id}
```

It returns the live report from
[`periodic_dossiers.md`](../../contracts/periodic_dossiers.md). Key fields:

| Field | Display rule |
|---|---|
| `state`, `blockers` | Primary dossier status and actionable reason. Use these enum values, not a client inference from counts. |
| `audit.schedule_state`, `audit.rounds`, `audit.ancestor_rounds` | Timeline, UTC windows, query and operation progress, per-round gates. |
| `audit.cumulative_admission` | Overall and per-class acquisition denominator, numerator, floor, finality and block reasons. |
| `profiles` | Live full-corpus stage-6 profiles. Empty below floor. Preserve exact five verdict semantics separately. |
| `human_decisions` | Current signatures and stale flags. A missing signature is `null`. |
| `snapshot_sha256`, `finalized_dossier_id`, `snapshot_stale` | Current evidence identity, last saved dossier identity and whether that saved dossier is superseded. |
| `needs_finalization`, `history_count` | Local persistence status. Do not turn this into a scientific decision. |
| `verdict` | Always `null` for the dossier. Verdicts live per question and require a person's signature. |

The endpoint recomputes on every GET. Poll at the same modest rate as the
existing flow journey, then back off when hidden. It may be expensive on a
large corpus. Its response is valid JSON for export; a browser download can
save the payload. Handle an unknown schedule as 404 and registry drift or
ledger integrity errors as named blocking states, not an empty result.

The authenticated control service uses `/control/v1`. Existing routes:

```
GET  /control/v1/p/{project}/flows/{flow_id}/operations
GET  /control/v1/p/{project}/flows/{flow_id}/batches
POST /control/v1/p/{project}/flows/{flow_id}/batches/{batch_id}/authorize
POST /control/v1/p/{project}/flows/{flow_id}/operations/{operation_id}/authorize
```

The batch POST repeats `operation_ids` and `max_total_requests` exactly as
shown by its GET. The operation POST repeats its `limits` object. A mismatch
is a 409 and should prompt a fresh read. `web/src/lib/control.ts` is the only
frontend module allowed to send non-GET requests; keep CSRF and session
handling there. `pause` and `resume` currently return 501, so leave them
disabled with the server's reason.

## Scheduler commands and what they mean

The CLI is authoritative for behavior until matching control endpoints exist.

| Action | Current command | Network or model call? |
|---|---|---|
| Inspect one flow | `scheduler-preview PROJECT FLOW_ID` | None |
| Start/revisit bounded local work | `scheduler auto-enable`, `auto-once`, `auto-worker`, `auto-status`, `auto-disable` | Local calls under the mandate's lifetime cap; already authorized network operations may run. |
| Plan dated updates | `scheduler periodic-plan PROJECT SOURCE_FLOW_ID --rounds-file ...` | None; writes flow and operation plans. |
| Approve finite query windows | `scheduler schedule-authorize PROJECT SCHEDULE_ID` | Authorization only; worker later makes bounded requests. |
| Permit future matching copies | `scheduler copy-policy-plan`, then `copy-policy-authorize`; `copy-policy-revoke` stops later starts. | Planning/approval only; each actual copy remains subject to robots and transport gates. |
| Inspect round and cumulative acquisition | `scheduler periodic-audit PROJECT SCHEDULE_ID` | None |
| Inspect live cumulative evidence | `scheduler periodic-dossier PROJECT SCHEDULE_ID` | None |
| Persist eligible handoff | `scheduler periodic-finalize PROJECT SCHEDULE_ID` | None; appends profiles and a dossier only after all gates pass. |

A local mandate on a scheduled child flow calls periodic finalization after
its local pass. **Creating the child flow does not yet create its local
mandate.** Until that backend gap is closed, the operator or a separate
orchestrator must authorize bounded local mandates for child flows. The
current control API does not yet expose the schedule or copy-policy commands.
Do not place enabled buttons for them that pretend a control route exists.

## Backend work needed for a fully interactive scheduler UI

1. Authenticated read and write routes for finite network schedules and copy
   policies. GET must return the frozen plan, hosts, classes, UTC windows,
   lifetime request/candidate ceilings, authorizing actor and current state.
   POST authorization must echo the exact hash and limits shown; revocation
   should stop future starts without deleting history.
2. Authenticated read and action routes for local mandates, including the
   lifetime model-call cap and remaining reservations. The operator must see
   the two distinct models and approved flow before enabling one.
3. A project-level scheduler index listing periodic schedules, their child
   flows, copy policies, local mandates and dossier IDs. Today the new read
   route requires a known `schedule_id`.
4. A bounded policy for inheriting local work to future child flows, or an
   explicit operator action per child. Until then, the interface should say
   "scheduled discovery approved; local reading mandate needed" where true.
5. A server event/heartbeat read model for real-time status. Current activity
   and operation ledgers support polling; they do not prove a live worker is
   healthy. Never derive "scheduler on" from a Docker container icon alone.
6. If the browser needs a packaged downloadable dossier rather than the live
   JSON, add an authenticated export action that snapshots the whole corpus
   and returns a verifiable artifact. The existing export action is flow
   scoped; `periodic-dossier` is a live JSON handoff.

Implement the backend routes before wiring their buttons. Keep server enums
and block reasons as the single source of meaning; a frontend type must not
create a new interpretation of `COMPLETED`, admission or staleness.

## Acceptance walkthrough for the frontend session

- A project with a planned future update shows a timeline and an approval
  action only where a control endpoint exists. Before approval, the UI says
  no request is permitted. UTC start and expiry are explicit.
- A query completed with `ok: false`, or an empty update without a completed
  query, never shows the dossier as ready. A candidate found but without an
  obtained copy remains in the cumulative denominator.
- A copy policy displays exact hosts/classes and both lifetime caps. A 403
  has no purchase CTA until a verified offer exists.
- Below the floor, `profiles` is empty and the blocker is prominent. Above
  the floor with pending extraction or review, profiles are provisional.
- Once the gates pass, the full-corpus dossier appears. No verdict is
  preselected. A later evidence change marks the saved dossier or signed
  question stale; the previous record remains inspectable.
- Every write uses `control.ts` and an authenticated session. A changed plan
  yields a 409 and a re-read, with no optimistic "approved" state.
- The browser can save the live dossier JSON. It labels this a live report
  unless a matching `finalized_dossier_id` is present and `snapshot_stale` is
  false.

## Where to read next

- [`scheduler_operations.md`](../../contracts/scheduler_operations.md),
  [`network_schedules.md`](../../contracts/network_schedules.md),
  [`copy_policies.md`](../../contracts/copy_policies.md),
  [`periodic_dossiers.md`](../../contracts/periodic_dossiers.md).
- `claimstone/periodic.py`, `claimstone/periodic_dossier.py`,
  `claimstone/autopilot.py`, `claimstone/api.py`, `claimstone/control.py`.
- `web/src/components/OperationsPanel.tsx`, `web/src/lib/control.ts`,
  `web/src/pages/FlowOverviewPage.tsx`.
- D123–D126 in `docs/DESIGN_DECISIONS.md`; `docs/HANDOFF.md` for live state.
