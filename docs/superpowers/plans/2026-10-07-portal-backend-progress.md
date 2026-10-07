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
| **B0** | Decision entry (next free `D` number at the time you write it) and `docs/contracts/control_api.md` | files exist; checks pass; no code changed | TODO |
| **B1** | Project writer lock adopted by every writer; re-read under the lock in acquire and adjudicate (F5) | spec B1 tests pass; checks pass | TODO |
| **B2** | Host failure budget rebuilt from `requests.jsonl`; `urlguard.py`; manual redirects checked per hop (F6, F15) | spec B2 tests pass; checks pass | TODO |
| **B3** | `adjudication_version 2`, `signer_auth`, `actor`; required parameters; read API field, schema, fixtures (F16) | spec B3 tests pass; checks pass | TODO |
| **B4** | `claimstone control`, `claimstone operator add/disable`, sessions, CSRF, rate limit | spec B4 tests pass, including the "every POST refuses anonymous" test | TODO |
| **B5** | Web signing and drafts | spec B5 tests pass | TODO |
| **B6** | Profile diff route in the read API; schema and fixtures | spec B6 tests pass | TODO |
| **B7a** | Intake of DOIs, URLs and references; cohort routing; single explicit fetch | spec B7a tests pass | TODO |
| **B7b** | File intake, quarantine, engine gates, `operator-supplied` acquisition row, `supplied_copies` policy (F14) | spec B7b tests pass; existing admissibility tests unchanged and passing | TODO |
| **B8** | Identity resolution, retry-campaign record and preview, purchase offers and stages, defer/decline, F13 ordering test | spec B8 tests pass | TODO |
| **B9** | Seen markers and `/control/v1/today` | spec B9 tests pass | TODO |
| **B10** | Export create and verify from the control API; exports list in the read API; PDF licence rule | spec B10 tests pass | TODO |
| **B11** | Reachability checks, write-only credentials, 501 for the paid test call | spec B11 tests pass | TODO |
| **B12** | Scheduler-facing routes, **only if** the operations ledger module exists; otherwise mark `BLOCKED` with the reason and end the session | as spec B12, or `BLOCKED` recorded | TODO |
| **B13** | `control` service in compose and nginx, version registrations, decision entry completed, `HANDOFF.md` | checks pass; `docker compose config` validates; `api` service unchanged | TODO |

## Log entries
