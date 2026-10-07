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

### BR — IN PROGRESS

- [ ] BR.1 payload builders in the read model: `stored_profiles` (every `profiles.jsonl` row of
      one question inside the flow's selector via `synthesize._scope`, deduped by
      `profile_sha256` last-appended-wins, newest first, `current` on exactly the
      `latest_profiles` row) and `flow_exports` (`export.EXPORTS_LEDGER` rows of the flow,
      newest first, `export_id`/`created_at`/`actor` only — never the server-side `path`)
      (files: `claimstone/portal_state.py`)
- [ ] BR.2 the two routes, GET-only: `GET …/flows/{flow_id}/questions/{qid}/profiles`
      (empty scope → `{"profiles": []}`; unknown question → 404) and
      `GET …/flows/{flow_id}/exports` (no rows → `{"exports": []}`), with both payloads
      declared in `api_schema.py` (files: `claimstone/api.py`, `claimstone/api_schema.py`,
      `docs/contracts/portal-api.schema.json`)
- [ ] BR.3 tests through the real server: two builds with different hashes → two entries,
      newest first, one `current`; a same-hash rebuild → one entry; another round's row
      excluded; empty scope → `[]`; unknown question → 404; two flows' exports kept apart;
      no `path` key; empty → `[]`; both routes GET-only and in the A1/A2 lists
      (files: `tests/test_api_reads.py` (new), `tests/test_api.py`)
- [ ] BR.4 fixtures regenerated, `cd web && npm run gen:types` committed, the B10 note in
      `docs/contracts/control_api.md`, every check green, step marked DONE
      (files: `tools/build_portal_fixtures.py` (only if the route list needs it),
      `web/tests/fixtures/**`, `web/src/lib/api-types.ts`, `docs/contracts/control_api.md`)
