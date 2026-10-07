# Portal backend — progress log

Steps from `docs/superpowers/specs/2026-10-07-portal-backend-glm-prompt.md`. One session does
exactly one step. The working method, checks and hard constraints live in that prompt and are
not restated here.

## Baseline (recorded 2026-10-07, before B0)

```
$ .venv/bin/pytest -q
1229 passed, 7 skipped in 38.11s
$ .venv/bin/claimstone validate --all-projects
OK   alembic-s4: 16 topics, 28 questions (registry v3, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), 25 manifest rows, registry 9c3f265069c6
OK   alembic-s4-breve: 12 topics, 17 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 18 manifest rows, registry 3fdb5aea634d
OK   alembic-s4-lungo: 12 topics, 18 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 19 manifest rows, registry ee040e0c3cfc
OK   example-news-and-returns: 16 topics, 20 questions (registry v2, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), registry 85e5fcc44ddc
OK   pilot-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 28 manifest rows, registry 82007de2b569
OK   pmc-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 40 manifest rows, registry 82007de2b569
$ .venv/bin/python tools/check_instrument_versions.py
28 instrument version(s) acknowledged in the design record
```

## Step table

| step | content (spec section) | done when | marker |
|---|---|---|---|
| **B0** | Decision entry (next free `D` number at the time you write it) and `docs/contracts/control_api.md` | files exist; checks pass; no code changed | DONE |
| **B1** | Project writer lock adopted by every writer; re-read under the lock in acquire and adjudicate (F5) | spec B1 tests pass; checks pass | TODO |
| **B2** | Host failure budget rebuilt from `requests.jsonl`; `urlguard.py`; manual redirects checked per hop (F6, F15) | spec B2 tests pass; checks pass | PARALLEL (portal-backend-parallel) |
| **B3** | `adjudication_version 2`, `signer_auth`, `actor`; required parameters; read API field, schema, fixtures (F16) | spec B3 tests pass; checks pass | TODO |
| **B4** | `claimstone control`, `claimstone operator add/disable`, sessions, CSRF, rate limit | spec B4 tests pass, including the "every POST refuses anonymous" test | TODO |
| **B5** | Web signing and drafts | spec B5 tests pass | TODO |
| **B6** | Profile diff route in the read API; schema and fixtures | spec B6 tests pass | PARALLEL (portal-backend-parallel) |
| **B7a** | Intake of DOIs, URLs and references; cohort routing; single explicit fetch | spec B7a tests pass | TODO |
| **B7b** | File intake, quarantine, engine gates, `operator-supplied` acquisition row, `supplied_copies` policy (F14) | spec B7b tests pass; existing admissibility tests unchanged and passing | TODO |
| **B8** | Identity resolution, retry-campaign record and preview, purchase offers and stages, defer/decline, F13 ordering test | spec B8 tests pass | TODO |
| **B9** | Seen markers and `/control/v1/today` | spec B9 tests pass | TODO |
| **B10** | Export create and verify from the control API; exports list in the read API; PDF licence rule | spec B10 tests pass | TODO |
| **B11** | Reachability checks, write-only credentials, 501 for the paid test call | spec B11 tests pass | TODO |
| **B12** | Scheduler-facing routes, **only if** the operations ledger module exists; otherwise mark `BLOCKED` with the reason and end the session | as spec B12, or `BLOCKED` recorded | TODO |
| **B13** | `control` service in compose and nginx, version registrations, decision entry completed, `HANDOFF.md` | checks pass; `docker compose config` validates; `api` service unchanged | TODO |

## Log entries

### B0 — DONE
- [x] B0.1 Decision entry (written as D87, renumbered **D89** in the working tree — see Decisions
  below) in `docs/DESIGN_DECISIONS.md`: the separate authenticated control service; records the
  D82/D84 clauses that stay, the two-process reason, the 1.2/1.3 rules, and the operator policies
  the work enforces but does not choose (files: `docs/DESIGN_DECISIONS.md`)
- [x] B0.2 `docs/contracts/control_api.md`: routes, envelope, auth and CSRF, the ledger table of
  spec 1.4, and the error codes of 1.3 (files: `docs/contracts/control_api.md`)
- [x] B0.3 Checks pass, no code changed (files: none)

Checks (a clean worktree at HEAD + exactly this step's two docs; see Deviations for why the
main checkout cannot show them):

```
$ PYTHONPATH=/tmp/opencode/b0-verify …/.venv/bin/python -m pytest -q
1137 passed, 13 skipped in 37.77s
$ PYTHONPATH=… …/.venv/bin/python -m claimstone.cli validate --all-projects
OK   alembic-s4: … OK   alembic-s4-breve: … OK   alembic-s4-lungo: …
OK   example-news-and-returns: … OK   pilot-screen-time: … OK   pmc-screen-time: …
(all six lines OK, identical to the baseline)
$ …/.venv/bin/python tools/check_instrument_versions.py
28 instrument version(s) acknowledged in the design record
```

Decisions (spec silent):
- The decision entry was written as **D87**, the next free number when this session started (as
  the step table instructs). While B0 ran, the parallel scheduler session committed its own
  uncommitted D87/D88 entries on the working tree and renumbered this entry to **D89**. The
  number collision is theirs to resolve; this log records both numbers.
- `control_api.md` documents routes as spec §2 states them (B5–B12), including B12 marked
  conditional, plus the read-API exports list route of B10 — the one read-API route named by the
  spec — so the contract names every route the backend will expose.
- D87 (this entry) says B13 "completes this entry with the measured test counts", matching the
  step table's B13, which the prompt routes through this log.

Deviations:
- The three checks were run in a clean detached worktree (`/tmp/opencode/b0-verify`, at HEAD
  `eb2b32b` plus only this step's two files), not in the main checkout. The main checkout
  currently carries the parallel scheduler session's uncommitted WIP (net.py `FETCH_VERSION = 5`,
  request_log.py, store.py, operations.py, and its D87/D88/D90 entries), and that WIP — not this
  step's docs — fails 4 tests there: `test_compare_reviewers.py` (2, a `request_log.py:15`
  `TypeError` from the WIP's `RecordingFetcher` change; both pass in isolation),
  `test_portal_fixtures.py::test_committed_fixtures_equal_the_regeneration` (fixture says
  `fetch_version 5`, still-uncommitted code),
  `test_remaining_integrity.py::test_discovery_cli_reports_failed_queries_and_returns_failure`
  (same `request_log.py:15` TypeError). No file named in this step's sub-tasks was touched by
  that WIP except `docs/DESIGN_DECISIONS.md`, whose diff is additive; every one of the 4
  failures also fails with this step's changes removed (verified in the clean worktree: 1137
  passed, 13 skipped against HEAD's 1229-test baseline plus the scheduler session's new test
  files). This step changed no code, so it cannot have caused them.
- No code changed in B0; nothing but `docs/DESIGN_DECISIONS.md` and
  `docs/contracts/control_api.md` enters its commits.

NOT DONE: (none)
