# Portal backend (reads) — progress log

Step BR of `docs/superpowers/specs/2026-10-07-portal-backend-spec.md` (§1 and B10), built on the
branch `portal-backend-reads` per `docs/superpowers/specs/2026-10-07-portal-backend-reads-prompt.md`.
The working method, hard constraints, log format and report shape live in
`docs/superpowers/specs/2026-10-07-portal-backend-glm-prompt.md`; they are not restated here.
The precedent is B6 (`docs/superpowers/plans/2026-10-07-portal-backend-parallel-progress.md`).

## Baseline (recorded 2026-10-07, before BR, at `1b608a6`)

```
$ PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m pytest -q
1187 passed, 13 skipped in 46.52s
$ PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m claimstone.cli validate --all-projects
OK   example-news-and-returns: 16 topics, 20 questions (registry v2, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), registry 85e5fcc44ddc
OK   pilot-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 28 manifest rows, registry 82007de2b569
OK   pmc-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 40 manifest rows, registry 82007de2b569
$ PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python tools/check_instrument_versions.py
30 instrument version(s) acknowledged in the design record
$ cd web && npm ci && npm run gen:types && npm run typecheck && npm test && npm run build
Test Files  15 passed (15)
      Tests  72 passed (72)
✓ built in 4.24s
check-csp: ok (no inline script, no style attribute)
```

As in the parallel worktree: only the tracked project instances live here, which is why
`validate` reads three project lines and pytest skips 13 tests that read real data.

## Step table

| step | content (spec section) | done when | marker |
|---|---|---|---|
| **BR** | two read-only routes: `GET …/questions/{qid}/profiles` and `GET …/flows/{flow_id}/exports`; schema, fixtures, web types | BR's listed tests pass; all checks pass | TODO |

## Log entries

(none yet — BR starts at the next session action)
