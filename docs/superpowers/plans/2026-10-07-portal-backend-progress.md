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
| **B1** | Project writer lock adopted by every writer; re-read under the lock in acquire and adjudicate (F5) | spec B1 tests pass; checks pass | IN PROGRESS (triaged 2026-10-07: lock primitive already on the main line; the re-read scope is the step) |
| **B2** | Host failure budget rebuilt from `requests.jsonl`; `urlguard.py`; manual redirects checked per hop (F6, F15) | spec B2 tests pass; checks pass | DONE (main line, scheduler session `67ca0a4` — substance in `store.py`/`net.py`, form deviation: no `locks.py`/`urlguard.py`) |
| **B3** | `adjudication_version 2`, `signer_auth`, `actor`; required parameters; read API field, schema, fixtures (F16) | spec B3 tests pass; checks pass | TODO |
| **B4** | `claimstone control`, `claimstone operator add/disable`, sessions, CSRF, rate limit | spec B4 tests pass, including the "every POST refuses anonymous" test | TODO |
| **B5** | Web signing and drafts | spec B5 tests pass | TODO |
| **B6** | Profile diff route in the read API; schema and fixtures | spec B6 tests pass | DONE (portal-backend-parallel, merged `3045aa2` 2026-10-07; decisions in the parallel log) |
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

Checks (final, run in the main checkout at commit e525382; the scheduler session's parallel
work-in-progress on the same branch is uncommitted and moving under us — see Deviations):

```
$ .venv/bin/pytest -q
1244 passed, 7 skipped in 40.36s
$ .venv/bin/claimstone validate --all-projects
OK   alembic-s4: 16 topics, 28 questions (registry v3, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), 25 manifest rows, registry 9c3f265069c6
OK   alembic-s4-breve: 12 topics, 17 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 18 manifest rows, registry 3fdb5aea634d
OK   alembic-s4-lungo: 12 topics, 18 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 19 manifest rows, registry ee040e0c3cfc
OK   example-news-and-returns: 16 topics, 20 questions (registry v2, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), registry 85e5fcc44ddc
OK   pilot-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 28 manifest rows, registry 82007de2b569
OK   pmc-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 40 manifest rows, registry 82007de2b569
$ .venv/bin/python tools/check_instrument_versions.py
29 instrument version(s) acknowledged in the design record
```

The pytest run includes the scheduler session's in-flight tests (1244 = the 1229 baseline
plus their new test files, which were mid-write during this session); `check_instrument_versions`
prints 29 because their uncommitted `tools/check_instrument_versions.py` edit registered
`operations_version 1`. No figure here is this step's alone; this step changed no code.

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
- The scheduler session works uncommitted on this branch in parallel, and its tree moved under
  this step three times. (1) At this step's first check run its WIP failed 4 tests
  (`test_compare_reviewers.py` ×2 and `test_remaining_integrity.py` ×1, all a
  `request_log.py:15` TypeError from its own uncommitted `RecordingFetcher` change, and
  `test_portal_fixtures.py`'s fixture check against its uncommitted `FETCH_VERSION = 5`);
  this step's changes are two docs and cannot cause any of them — verified by running the same
  three checks in a clean detached worktree at HEAD plus exactly this step's two files
  (1137 passed, 13 skipped, all six validate lines OK, instruments 28). (2) It renumbered
  this step's decision entry in the working tree from D87 (as written) to D89, adding its own
  D87/D88/D90 around it; this step's commit stages only its own entry, additively over HEAD.
  (3) By the final check run its WIP had become green in the main checkout, which is why the
  final lines above are from the real checkout.
- The decision-entry number is the one the step table told this step to use ("next free `D`
  number at the time you write it"): **D87 as written, D89 as it stands in the working tree**
  after the scheduler session's renumbering. Both numbers are recorded here rather than
  resolved, because resolving the collision would mean editing another session's uncommitted
  files.

NOT DONE: (none)

### Merge and triage — 2026-10-07 (reviewer session)

B6 merged from `portal-backend-parallel` as `3045aa2` (`--no-ff`, no conflicts: the two
branches' changed-file lists were disjoint since base `00d19b1`). The parallel log
(`2026-10-07-portal-backend-parallel-progress.md`) moves with the merge and holds B6's
decisions and deviations. Nothing to register at merge.

Checks at the merge commit:

```
$ .venv/bin/pytest -q
1268 passed, 7 skipped in 44.72s
$ .venv/bin/claimstone validate --all-projects
OK   alembic-s4: 16 topics, 28 questions (registry v3, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), 25 manifest rows, registry 9c3f265069c6
OK   alembic-s4-breve: 12 topics, 17 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 18 manifest rows, registry 3fdb5aea634d
OK   alembic-s4-lungo: 12 topics, 18 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 19 manifest rows, registry ee040e0c3cfc
OK   example-news-and-returns: 16 topics, 20 questions (registry v2, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), registry 85e5fcc44ddc
OK   pilot-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 28 manifest rows, registry 82007de2b569
OK   pmc-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 40 manifest rows, registry 82007de2b569
$ .venv/bin/python tools/check_instrument_versions.py
29 instrument version(s) acknowledged in the design record
$ cd web && npm run typecheck && npm test
13 test files passed, 55 tests passed
```

**B1 triage** (the reviewer session read the spec against the main line, 2026-10-07):
already on the main line — the project-wide exclusive lock as `Store.writer_lock`
(`fcntl.flock` on `<store>/<project>/.writer.lock`, re-entrant per thread, serialized
per process, adopted **inside `store.append` itself** so every append is a critical
section, and held across read-modify-write in `flows`, `source_selection` and
`operations`). Still missing, and B1's remaining scope:
- `synthesize.adjudicate` checks the profile and appends **outside one hold**: the
  `latest_profiles` read, the `preview` comparison and the `store.append` (which takes
  the lock internally) are three windows. A synthesize racing the append can leave a
  signature on the old hash — exactly what F5 exists to prevent.
- `acquire` computes `attempt_no` from a prior read outside the lock
  (`acquire.py:67`, `acquire.py:376`): two concurrent writers can append duplicate
  attempt numbers.
- The spec's three tests (two-process append, adjudicate-races-synthesize, lock order)
  do not exist.
- Form deviation to carry into B1: the lock is `Store.writer_lock`, not the spec's
  `claimstone/locks.py::project_lock`; `flows._flows_lock` already delegates to it, so
  the order rule is satisfied by construction (one lock, no second to invert) —
  B1 should record that instead of building the module the spec names.

B2's table row is closed as DONE on the main line by the same triage: the host budget
rebuilt from `requests.jsonl`, the global-address URL guard and per-hop redirect checks
landed in `net.py`/`store.py` at `FETCH_VERSION` 5 (scheduler session), not as the
spec's `urlguard.py`. The spec's form may be amended at B13's cleanup or left recorded
here as the deviation it is.

Next: B1 (reduced scope above), then B3.

### B1 — IN PROGRESS (2026-10-07, reviewer session, after the triage above)

- [ ] B1.1 `synthesize.adjudicate` holds `store.writer_lock()` across the profile check and the
      append: `latest_profiles`, the `preview` comparison and the `store.append` become one
      transaction, so a profile change can no longer land between the check and the signature (F5)
      (files: `claimstone/synthesize.py`)
- [ ] B1.2 `acquire.run` and `acquire.reuse_cached` re-read the candidate's latest attempt under
      `store.writer_lock()` immediately before appending and assign `attempt_no` from that re-read;
      the fetch itself stays outside the lock (the spec's network rule)
      (files: `claimstone/acquire.py`)
- [ ] B1.3 the spec's three tests, deterministic: two processes appending through the writer →
      no duplicate ids and a clean tail; a concurrent acquisition landing between the prior read
      and the append → no duplicate `attempt_no`; adjudicate's check and append under one hold,
      a competing append provably cannot interleave; the flows lock is the project lock by
      construction (files: `tests/test_b1_writer_lock.py` (new))
- [ ] B1.4 checks pass; DONE recorded with the triage's form deviation (no `locks.py`:
      `Store.writer_lock` is the one lock, `flows._flows_lock` delegates to it, so the lock-order
      rule holds by construction — there is no second lock to invert)
