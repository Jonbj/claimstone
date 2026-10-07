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
| **B6** | `profile-diff` route in the read API; `api_schema.py`; regenerated schema and fixtures | spec B6 tests pass; checks pass; web checks pass | DONE |

## Log entries

### B6 — DONE

- [x] B6.1 `profile_diff` payload in the read model: both hashes looked up in `profiles.jsonl`, results
      added/removed/changed keyed by stable result id, reason when the rows record one, per-relation and
      per-class counts before and after (files: `claimstone/portal_state.py`)
- [x] B6.2 the route in `api.py` (`GET …/questions/{qid}/profile-diff?from=…&to=…`, read-only; a hash not
      in the ledger → 404; a missing end → 400) + schema in `api_schema.py`, generated schema regenerated
      (files: `claimstone/api.py`, `claimstone/api_schema.py`, `docs/contracts/portal-api.schema.json`)
- [x] B6.3 tests: identical hashes → empty diff; a result losing its review → removed with its reason;
      added and changed relations; 404 and 400 refusals — the later profile generations built by the real
      stage 5 (`review.build`, answered call, `review.harvest`) and the real stage 6, never hand-written
      profile rows
      (files: `tests/test_api_profile_diff.py` (new), `tests/test_api.py`, `tests/test_api_contract.py`)
- [x] B6.4 fixtures regenerated; all checks and web checks pass; step marked DONE
      (files: `tools/build_portal_fixtures.py`, `web/tests/fixtures/**`, `web/src/lib/api-types.ts`)

Checks (final, run in the worktree at the B6.4 code state — identical bytes to the step's final
commit, which adds only this log):

```
$ PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m pytest -q
1173 passed, 13 skipped in 42.70s
$ PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m claimstone.cli validate --all-projects
OK   example-news-and-returns: 16 topics, 20 questions (registry v2, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), registry 85e5fcc44ddc
OK   pilot-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 28 manifest rows, registry 82007de2b569
OK   pmc-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 40 manifest rows, registry 82007de2b569
$ PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python tools/check_instrument_versions.py
29 instrument version(s) acknowledged in the design record
$ cd web && npm run typecheck && npm test
13 test files passed, 55 tests passed
```

1173 = the 1166 baseline plus this step's 7 tests (`tests/test_api_profile_diff.py`). The web
figures were run after `npm ci` (the only network access) and `npm run gen:types` against the
regenerated schema.

Decisions (spec silent):
- **The route follows the house convention**, `/api/v1/projects/{p}/flows/{flow_id}/questions/{qid}/profile-diff?from=…&to=…`,
  not the spec's `/p/{project}/…/q/{question_id}` spelling: every other route in `api.py` uses the
  long form, and a route spelled differently from its siblings would be a second convention.
- **No round scope on the hash lookup.** The sha is content-addressed, so comparing a question's
  profile across rounds is a legitimate question and the lookup searches all of that question's
  `profiles.jsonl` rows. When more than one row holds the same sha, the last one wins (rebuilds
  append).
- **The stable result id is `claim_id`.** One claim has exactly one review and one result row per
  profile, and no annotation id travels with a result row; the spec's "annotation id, or claim id
  plus review id" has no second carrier to read.
- **Reasons surface only when the rows record one.** A removed result carries the latest
  `reviews.jsonl` row for its claim (verdict and reason; `latest_by`, so a re-review supersedes),
  or `no review recorded` — never an invented narrative. The diff level carries `reason` when an
  instrument version changed (`claim_gate_version 4 → 5`), because that is a change of rules, not
  of the literature. Added and changed results carry `reason: null`: no row records one.
- **`from==to` is a valid empty comparison**, not an error: the spec's first test names it.
- **A missing `from` or `to` is 400 `BAD_REQUEST`** (a malformed query parameter, the caller's
  error, matching `_limit`'s convention), not 404.

Deviations:
- **`profile_diff` lives in `portal_state.py`**, which the parallel prompt's scope list did not
  name (it named `api.py`, `api_schema.py`, the generated schema and fixtures, and their tests).
  The house layering is strict — `api.py` only routes and `portal_state.py` holds the payload
  builders — and putting the diff logic in the router would break it. The file is otherwise
  untouched by the other session's steps, so the collision risk the scope list exists to manage
  is unchanged.
- `_routes()` in `tests/test_api.py` gained an optional stored-hash parameter so the diff route
  joins the A1 and A2 route lists and the fixtures (the builder's own docstring: the fixtures walk
  "the same §3.2 list tests A1 and A2 walk"). `test_api.py` was not in the scope list either; the
  change is additive and every existing route string is byte-identical.
- The diff fixture is named `Q02.profile-diff.*` beside `Q02.json` rather than `Q02/profile-diff.*`
  (`_fixture_name` special case), so the question's fixture never becomes a directory beside the
  file that extends it.

To register at merge: nothing — B6 adds no version constant. The schema file's route count is
14 (was 13); the contract test enforces the parity.

NOT DONE: (none — B6 complete; B2 was done on the main line)