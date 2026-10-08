# Portal journey — progress log

Spec: `docs/superpowers/specs/2026-10-08-portal-journey-spec.md`. Branch `research-portal`.
Precedent for payload and schema work: `docs/superpowers/plans/2026-10-07-portal-backend-reads-progress.md` (BR).

## Step table

| step | content | done when | marker |
|---|---|---|---|
| **J1** | `journey` block in the flow overview, computed on the server; schema, fixtures, types, contract doc | J1's listed tests pass; all checks pass | DONE |
| **J2** | the flow page rendered as the journey | J2's tests pass; all checks pass | DONE |
| **J3** | journey page polish (screenshot defects on real data) | J3's tests pass; all checks pass | IN PROGRESS |

## Log entries

### J1 — DONE

- [x] J1.1 `claimstone/journey.py` (eight step rules, fixed templates, topics, question counts,
      `needs_you`, `running`) wired into `portal_state.flow_overview` from the same `computed` and
      cards; schema in `api_schema.py`; contract schema, web fixtures and `api-types.ts`
      regenerated in the same commit because the contract and fixture tests compare them
      (files: `claimstone/journey.py`, `claimstone/portal_state.py`, `claimstone/api_schema.py`,
      `docs/contracts/portal-api.schema.json`, `web/tests/fixtures/**`, `web/src/lib/api-types.ts`)
- [x] J1.2 `JOURNEY_VERSION` registered in `tools/check_instrument_versions.py` with a dated D entry,
      `docs/contracts/journey.md` (files: `tools/check_instrument_versions.py`,
      `docs/DESIGN_DECISIONS.md`, `docs/contracts/journey.md`)
- [x] J1.3 `tests/test_journey.py`: each status rule, nulls, legacy, running operation, route, F13
      (files: `tests/test_journey.py`)
- [x] J1.4 real-project read-only sanity check, all checks, J1 marked DONE (files: this log)

The sub-task split changed from the plan: schema and regenerated artifacts moved into J1.1 because
the contract and fixture tests fail on any overview payload change until they are regenerated.

Checks (final, at the code state of the closing commit):

```
$ .venv/bin/pytest -q
1449 passed, 7 skipped in 121.51s (0:02:01)
$ .venv/bin/claimstone validate --all-projects
OK   alembic-s4-lungo: 12 topics, 18 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 19 manifest rows, registry ee040e0c3cfc
OK   example-news-and-returns: 16 topics, 20 questions (registry v2, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), registry 85e5fcc44ddc
OK   pilot-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 28 manifest rows, registry 82007de2b569
OK   pmc-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 40 manifest rows, registry 82007de2b569
$ .venv/bin/python tools/check_instrument_versions.py
37 instrument version(s) acknowledged in the design record
$ cd web && npm run gen:types && npm run typecheck && npm test && npm run build
 Test Files  31 passed (31)
      Tests  176 passed (176)
✓ built in 4.04s
check-csp: ok (no inline script, no style attribute)
```

Read-only sanity check (`portal_state.flow_overview` on real projects, no write, no stage command).
Steps 1..8 statuses:

- pmc-screen-time, whole store (legacy): not_applicable, done, done, done, partial, partial, partial,
  waits_for_you (ready_to_sign 1)
- pmc-screen-time, round pmc-oa-v1 (legacy): not_applicable, done, done, done, not_started, partial,
  not_started, not_started
- alembic-s4-lungo, flow s4-l02-repository-copies-2026-10-06-v2 (bound): done, not_started x7;
  needs_you required 0, optional 0
- alembic-s4-lungo, whole store (legacy): not_applicable, partial, partial, done, not_started, done,
  not_started, not_started
- alembic-s4-lungo, round s4-l02-search-2026-09-29-v1 (legacy): not_applicable, done, blocked (below
  floor), done, not_started x4
- alembic-s4-lungo, round s4-open-copies-v1 (legacy): not_applicable, partial, partial, done,
  not_started, done, not_started, not_started

No operation was running on either project (`running: []`). Observation: on the whole-store views
step 6 reads `done`/`partial` while step 5 reads `not_started`/`partial`, because review progress
counts all accepted claims in the store and extract progress counts live profile readings; the steps
report what each stage's own ledger says and do not reconcile them.

Decisions (the reading that never claims more progress than the ledgers show):
- Step 7 is also `blocked` when any verdict row carries a per-row `unavailable` text (stored profiles
  of a round that no longer clears admission), with that text verbatim. `rs.unavailable` alone was
  empty in that case and counting the historical profiles would have shown `partial`.
- Step 7: a literature question with no profile is not final; profile counts exclude operational.
- Step 2 and 4: unreadable admission gives `partial`, never `done`. Step 4: no prepared document is
  `not_started` even if copies were obtained.
- "Running" uses the scheduler's continuing set as the spec says, so an `AUTHORIZED` operation (still
  waiting for the worker) sets its step to `running`; its `state` in `running` says AUTHORIZED. I also
  mapped the `-build` and `-harvest` variants (`extract-build`, `extract-harvest`, `review-build`,
  `review-harvest`) to their lane's step; the spec named only extract-build/drain and review-drain.
- `running` is filtered with `operations_view.for_flow` narrowed to the continuing events, because the
  summary row carries no flow id; same replay, one `_events` pass.
- Added `running_note` (string or null) to the block: the spec asks for a named note on a damaged
  operations ledger but gave the shape no field for it.
- `rejected` stays `null` ("—") where a stage records none, following the round state's convention.
- Sub-task split changed: schema, fixtures and types went into J1.1 (contract tests compare them).

Deviations: `running_note` field added to the spec's shape; sub-task split as above.

NOT DONE: nothing of J1. The frontend (J2) is untouched.

### J1 review — 2026-10-08 (reviewer)
Accepted with one change: J1 let an `AUTHORIZED` operation set its step to `running`. An operation no
worker has started is not work in flight, and saying so is the claim D107 refuses for the heartbeat. Now
only `state == RUNNING_OR_LOCK_HELD` makes a step `running`. Authorized and interrupted operations stay
listed in `running` with their state. Tests: the authorized case asserts no step is running; a new test
simulates a held writer lock and asserts the step runs. The contract is updated. The step 5/6 mismatch on
whole-store views, where review counts every accepted claim and extract counts the live profiles'
readings, is accepted as recorded: each step reports its own ledger honestly.

### J2 — DONE

Plan (frontend only; `api-types.ts`, Python and fixtures do not change):

- [x] J2.1 `web/src/components/JourneySteps.tsx`: segment bar and the eight steps, status to colour/shape
      and word only, summary and actor verbatim, figures with "—" for null, step 3 floor line, step 8
      "Read and sign Qnn" buttons from matrix rows with `display_state == awaiting_a_person`
      (files: `web/src/components/JourneySteps.tsx`, `web/tests/journey.test.tsx`)
- [x] J2.2 right column: `JourneySide.tsx` (the topic, the questions compact, needs you with the null
      note) beside the kept `OperationsPanel` (files: `web/src/components/JourneySide.tsx`,
      `web/tests/journey.test.tsx`)
- [x] J2.3 restructure `FlowOverviewPage.tsx`: header with flow selector, journey left, side right,
      technical details in a collapsed `<details>`; legacy shows no write control
      (files: `web/src/pages/FlowOverviewPage.tsx`, `web/tests/flowpage.test.tsx`)
- [x] J2.4 `ProjectPage.tsx`: redirect to the single / single CURRENT flow, `?details=1` suppresses it,
      integrity and ledgers in a collapsed `<details>`; "Project details" link on the journey header
      (files: `web/src/pages/ProjectPage.tsx`, `web/tests/project.test.tsx`)
- [x] J2.5 all checks, J2 marked DONE (files: this log)

Checks (final, at the code state of the closing commit; `api-types.ts` unchanged by `gen:types`):

```
$ cd web && npm run gen:types && npm run typecheck && npm test && npm run build
 Test Files  32 passed (32)
      Tests  194 passed (194)
✓ built in 3.95s
check-csp: ok (no inline script, no style attribute)
$ .venv/bin/pytest -q tests/test_api_contract.py tests/test_portal_fixtures.py
7 passed in 3.73s
```

The full `pytest`, `validate --all-projects` and `check_instrument_versions.py` were not re-run: J2 touches
no Python.

Decisions:
- A step is shown `running` only if the server's `status` says so; the browser only maps status to a colour,
  shape and its word. "Ready to sign" buttons come from matrix rows with `display_state ==
  awaiting_a_person` (the state the KPI donut counts) and are absent on legacy selectors.
- Step 3's floor line is chosen from the server's `figures.status` (`OK` met, `INSUFFICIENT_ACQUISITION`
  below, anything else "floor —").
- Binding, ledger-integrity and corpus-unavailable notices stay visible above the journey; the full
  questions matrix, rejections card and inbox sit with KPIs, floor panel, source tracker and activity inside
  the collapsed details (invariant 6 per-class counts stay available).
- The header's research-flow selector comes from `GET /projects`; if unreadable it is omitted.
- Redirect uses the card's `binding_state`; `?details=1` suppresses it and opens the technical details.
  The header "Activity" link now points to `/p/:project?details=1#activity` (otherwise the redirect would
  swallow it); its test was updated. A collapsed details whose integrity read failed says so in its summary.
- Partial status is a half-filled gradient (done colour over grey).

Deviations: Activity link target as above; the existing project-page test now uses two drifted flows (one
flow would redirect). "Running" step statuses are not covered by a component test with a running fixture
beyond the generic status mapping.

NOT DONE: no browser/visual check against `V2Journey.html`; no Pause/Resume (unchanged, scheduler track).

### J3 — IN PROGRESS

Frontend only (`web/`); `api-types.ts`, Python and fixtures do not change.

- [x] J3.1 step 3 floor line only when status is not `not_started` and `figures.found` is a number > 0
      (files: `web/src/components/JourneySteps.tsx`, `web/tests/journey.test.tsx`)
- [ ] J3.2 step figures: drop figures that restate the status or are an empty `drifted_parts`; `note` as a
      muted sentence; no numeric figure dropped (files: `JourneySteps.tsx`, `journey.test.tsx`)
- [ ] J3.3 UTC date-time formatter `web/src/lib/datetime.ts`, applied to ISO figure values on the journey
      (files: `web/src/lib/datetime.ts`, `JourneySteps.tsx`, `web/tests/datetime.test.ts`, `journey.test.tsx`)
- [ ] J3.4 question state chips as human words via `vocabulary.ts`, code kept as `title`
      (files: `web/src/lib/vocabulary.ts`, `JourneySide.tsx`, `journey.test.tsx`)
- [ ] J3.5 topic card: first 4 expanded, "Show all N topics" toggle (files: `JourneySide.tsx`, `journey.test.tsx`)
- [ ] J3.6 binding: no review-finding jargon; CURRENT with no differences is one compact line beside the
      scope chips, drifted states keep the card (files: `web/src/pages/FlowOverviewPage.tsx`,
      `web/tests/flowpage.test.tsx`)
- [ ] J3.7 all checks, J3 marked DONE (files: this log)
