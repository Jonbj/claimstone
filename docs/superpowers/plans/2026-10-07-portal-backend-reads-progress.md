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
| **BR** | two read-only routes: `GET …/questions/{qid}/profiles` and `GET …/flows/{flow_id}/exports`; schema, fixtures, web types | BR's listed tests pass; all checks pass | DONE |

## Log entries

### BR — DONE

- [x] BR.1 payload builders in the read model: `stored_profiles` (every `profiles.jsonl` row of
      one question inside the flow's selector via `synthesize._scope`, deduped by
      `profile_sha256` last-appended-wins, newest first, `current` on exactly the
      `latest_profiles` row) and `flow_exports` (`export.EXPORTS_LEDGER` rows of the flow,
      newest first, `export_id`/`created_at`/`actor` only — never the server-side `path`)
      (files: `claimstone/portal_state.py`)
- [x] BR.2 the two routes, GET-only: `GET …/flows/{flow_id}/questions/{qid}/profiles`
      (empty scope → `{"profiles": []}`; unknown question → 404) and
      `GET …/flows/{flow_id}/exports` (no rows → `{"exports": []}`), with both payloads
      declared in `api_schema.py` (files: `claimstone/api.py`, `claimstone/api_schema.py`,
      `docs/contracts/portal-api.schema.json`)
- [x] BR.3 tests through the real server: two builds with different hashes → two entries,
      newest first, one `current`; a same-hash rebuild → one entry; another round's row
      excluded; empty scope → `[]`; unknown question → 404; two flows' exports kept apart;
      no `path` key; empty → `[]`; both routes GET-only and in the A1/A2 lists
      (files: `tests/test_api_reads.py` (new), `tests/test_api.py`,
      `tests/test_api_contract.py`)
- [x] BR.4 fixtures regenerated, `cd web && npm run gen:types` committed, the B10 note in
      `docs/contracts/control_api.md`, every check green, step marked DONE
      (files: `tools/build_portal_fixtures.py` (only if the route list needs it),
      `web/tests/fixtures/**`, `web/src/lib/api-types.ts`, `docs/contracts/control_api.md`)

Checks (final, run in the worktree at the BR.4 code state — identical bytes to the step's
final commit, which adds only this log):

```
$ PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m pytest -q
1196 passed, 13 skipped in 50.95s
$ PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m claimstone.cli validate --all-projects
OK   example-news-and-returns: 16 topics, 20 questions (registry v2, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), registry 85e5fcc44ddc
OK   pilot-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 28 manifest rows, registry 82007de2b569
OK   pmc-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 40 manifest rows, registry 82007de2b569
$ PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python tools/check_instrument_versions.py
30 instrument version(s) acknowledged in the design record
$ cd web && npm ci && npm run gen:types && npm run typecheck && npm test && npm run build
Test Files  15 passed (15)
      Tests  72 passed (72)
✓ built in 4.25s
check-csp: ok (no inline script, no style attribute)
```

1196 = the 1187 baseline plus this step's 9 tests (`tests/test_api_reads.py`). The schema
file's route count is 16 (was 14); the contract parity test enforces it.

Decisions (spec silent):
- **The house route spelling, again** (B6's first decision, applied to both routes):
  `/api/v1/projects/{p}/flows/{flow_id}/questions/{qid}/profiles` and
  `/api/v1/projects/{p}/flows/{flow_id}/exports`, not the control-spec `p/…/q/…` form. The
  profiles route serves `unbound/{slug}` selectors too, like its sibling
  `questions/{qid}` tails and `latest_profiles`' own scope; the exports route is
  flows-only — an unbound selector has no flow id to key rows by — and
  `/unbound/{slug}/exports` is a 404.
- **"Newest first" is ledger append order, reversed**, for both routes: `built_at` and
  `created_at` have second resolution and two appends can share a second, while the
  position of the last appending row is tie-free and is the same quantity the collapse
  rule uses ("the last appended").
- **The build timestamp field is `built_at`**, read from the row (`synthesize.build`
  stamps it); recorded here because the prompt asked the row, not a guess, to name it.
- **The usable-result count is `len(row["results"])`, served as `usable_results`**: the
  profile's own `results` list holds exactly the claims whose review said USABLE
  (`evidence.profile`), so the count is the row's, never recounted here. An operational
  question's `LITERATURE_VERDICT_NOT_APPLICABLE` row records no `results`, so it lists 0
  with `provisional: false`.
- **Context keys beside the list key**: `project`/`selector`/`id` (profiles) and
  `project`/`flow_id` (exports), like every sibling payload (question detail, profile
  diff, summary). The spec's `{"profiles": []}` names the empty list; `api_version` is
  added by the transport whatever the payload.
- **`actor` appears only when the row records one** — the prompt's literal wording; the
  schema keeps `export_id`/`created_at` required and `actor` optional under
  `additionalProperties: false`, so json2ts generates it as `actor?: string`.
- **No `API_VERSION` bump and no new version constant**: both routes are new payloads and
  no existing payload changed shape, so nothing a v1 consumer reads moved; and BR adds no
  instrument or record type for `check_instrument_versions.py` to acknowledge.
- **Hand-appended scope fixtures in the tests**: another round's profile row and another
  flow's export row are appended by hand (`r2` sits below the floor, so the engine's own
  build refuses it). They pin the scope filter, exactly like `build_workspace`'s own
  hand-written rows; every profile *generation* the route lists still comes from the real
  stage 5 and stage 6.

Deviations:
- **`tools/build_portal_fixtures.py` edited** (not in the scope list): the
  `Q02.profiles.json` fixture needed the same `_fixture_name` special case B6 added for
  `Q02.profile-diff`, so the question's fixture never becomes a `Q02/` directory beside
  the `Q02.json` file that extends it. The same file B6 touched for the same reason.
- `tests/test_api_contract.py` gained the two `_schema_for` mappings (inside the scope
  limit's `tests/test_api*.py`; named here for the merge).

NOT DONE: (none — BR complete)
