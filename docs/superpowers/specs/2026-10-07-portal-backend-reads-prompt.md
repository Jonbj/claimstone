You are implementing **step BR** of the portal backend, in a **parallel** session. Another session builds
B4 (the control server) on `research-portal` at the same time.

**STOP RULE: do exactly step BR. When it is DONE, write the report and end the session. Do nothing else.**
Do not ask questions. When something is unspecified, make the smallest decision that keeps every existing
test passing and the seven invariants in `CLAUDE.md` intact, and record it in the log.

## Where you work

- **Directory:** `/home/stefano/Documents/Projects/claimstone-reads`, a git worktree.
- **Branch:** `portal-backend-reads`. `git branch --show-current` must print it. If not, stop and report.
  Never switch branch, merge, rebase, push, amend, reset or stash. The reviewer merges.
- **Never touch** `/home/stefano/Documents/Projects/claimstone`, the main checkout.
- **Progress log:** `docs/superpowers/plans/2026-10-07-portal-backend-reads-progress.md`, in the worktree.
  It is not the main log.

## Method

Follow the "Working method inside a step", "Hard constraints", "Log format" and "Report" sections of
`docs/superpowers/specs/2026-10-07-portal-backend-glm-prompt.md` exactly, with the log path above. Ignore that
prompt's step table and its "Start of every session". The spec for context is
`docs/superpowers/specs/2026-10-07-portal-backend-spec.md`: §1 and B10.

**Precedent to follow:** B6, the `profile-diff` route. Read its decisions and deviations in
`docs/superpowers/plans/2026-10-07-portal-backend-parallel-progress.md`, and keep its conventions:
- long route spelling `/api/v1/projects/{p}/flows/{flow_id}/…`;
- payload builders in `portal_state.py`, routing only in `api.py`;
- schema in `api_schema.py`, regenerated contract and fixtures;
- the route joins the A1/A2 route lists in `tests/test_api.py`.

## Step BR — two read-only routes

1. **Stored profiles of one question.** `GET /api/v1/projects/{p}/flows/{flow_id}/questions/{qid}/profiles`.
   - Every `profiles.jsonl` row for that question **within the flow's selector**, using the same scope rule
     as `synthesize.latest_profiles` / `_scope`.
   - Newest first. Rows with the same `profile_sha256` are collapsed to one entry, the last appended.
   - Each entry: `profile_sha256`, the row's build timestamp field as it is recorded (read the row to find
     its name; do not invent one), `provisional`, `state`, the usable-result count as the profile records
     it, and `current: true` for exactly the one that `latest_profiles` returns.
   - No profile for that question in this scope → `{"profiles": []}`, not 404.
   - An unknown question id → 404, as the question route does.

   Purpose: the question page's profile-diff panel can offer a list instead of asking the operator to paste
   hashes (follow-up recorded in `docs/superpowers/plans/2026-10-06-portal-frontend-progress.md`).
2. **Exports of one flow.** `GET /api/v1/projects/{p}/flows/{flow_id}/exports`.
   - The `exports.jsonl` rows (`export.EXPORTS_LEDGER`) whose `flow_id` equals this flow, newest first.
   - Each entry: `export_id`, `created_at`, plus `actor` when the row has one (later portal-made exports
     will). Never the server-side `path`: the response must not reveal filesystem paths.
   - No exports → `{"exports": []}`.
   - It never runs `export.verify`: verifying is an explicit action (B10, control API).

**Tests:**
- `profiles`: two builds with different hashes → two entries, newest first, one `current`; a rebuild with
  the same hash → one entry; a row of another round is excluded; an empty scope → `[]`; an unknown question →
  404.
- `exports`: two flows' exports are kept apart; no `path` key in any entry; empty → `[]`.
- Both routes are GET-only and appear in the A1/A2 lists.

Then regenerate `docs/contracts/portal-api.schema.json` and `web/tests/fixtures/*.json` with the existing
tools, and `cd web && npm run gen:types`. Commit the regenerated `web/src/lib/api-types.ts` (or wherever
`gen:types` writes). **Do not edit any other frontend source.** No `API_VERSION` bump unless an existing
payload changes; record the reasoning either way. No new version constant.

**Scope limit.** Touch only these files:
- `claimstone/api.py`, `claimstone/api_schema.py`, `claimstone/portal_state.py`;
- `docs/contracts/portal-api.schema.json`;
- the regenerated fixtures and generated web types;
- `tests/test_api*.py`, `tests/test_portal_state*.py`, or a new `tests/test_api_reads.py`;
- `docs/contracts/control_api.md` (only to note that the B10 read route now exists);
- your log.

The other session edits `cli.py`, `control.py`, `.gitignore` and their tests.

## Start of session

1. `cd /home/stefano/Documents/Projects/claimstone-reads` and check the branch.
2. Read `CLAUDE.md`, then the log. If the log does not exist:
   - create it with a table holding BR `TODO`;
   - run the checks and record their output as the baseline;
   - commit the log alone.
3. `git status --short`: uncommitted files can only be from an interrupted session of yours.

## Checks (no virtualenv in this worktree: use these exact commands)

```bash
PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m pytest -q
PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m claimstone.cli validate --all-projects
PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python tools/check_instrument_versions.py
cd web && npm ci && npm run gen:types && npm run typecheck && npm test && npm run build
```

`npm ci` is the only network access allowed, to the npm registry. Commit trailer:
`Co-Authored-By: glm-5.3:cloud`.
