# Portal backend (parallel) — progress log

Steps from `docs/superpowers/specs/2026-10-07-portal-backend-parallel-prompt.md` (amended
2026-10-07: B2 was implemented on the main line by the scheduler session, so **this branch
carries B6 only**). One session does exactly one step. The working method, checks and hard
constraints live in the main prompt and the parallel prompt; they are not restated here.

## Baseline (recorded 2026-10-07, before B6, at `00d19b1`)

```
$ PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m pytest -q
1166 passed, 13 skipped in 39.36s
$ PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m claimstone.cli validate --all-projects
OK   example-news-and-returns: 16 topics, 20 questions (registry v2, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), registry 85e5fcc44ddc
OK   pilot-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 28 manifest rows, registry 82007de0b569
OK   pmc-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 40 manifest rows, registry 82007de0b569
$ PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python tools/check_instrument_versions.py
29 instrument version(s) acknowledged in the design record
```

Note: this worktree carries only the tracked project instances (no `alembic-*`), which is
why `validate` reads three project lines and pytest skips 13 tests that read real data.

## Step table

| step | content (spec section) | done when | marker |
|---|---|---|---|
| ~~B2~~ | done on the main line (scheduler session, `FETCH_VERSION` 5) — not this branch's work | — | DONE (elsewhere) |
| **B6** | `profile-diff` route in the read API; `api_schema.py`; regenerated schema and fixtures | spec B6 tests pass; checks pass; web checks pass | IN PROGRESS |

## Log entries

### B6 — IN PROGRESS
- [x] B6.1 `profile_diff` payload in the read model: both hashes looked up in `profiles.jsonl`, results
      added/removed/changed keyed by stable result id, reason when the rows record one, per-relation and
      per-class counts before and after (files: `claimstone/portal_state.py`)
- [x] B6.2 the route in `api.py` (`GET …/questions/{qid}/profile-diff?from=…&to=…`, read-only; a hash not
      in the ledger → 404; a missing end → 400) + schema in `api_schema.py`, generated schema regenerated
      (files: `claimstone/api.py`, `claimstone/api_schema.py`, `docs/contracts/portal-api.schema.json`)
- [ ] B6.3 tests: identical hashes → empty diff; a result losing its review → removed with its reason
- [ ] B6.4 fixtures regenerated; all checks and web checks pass; step marked DONE