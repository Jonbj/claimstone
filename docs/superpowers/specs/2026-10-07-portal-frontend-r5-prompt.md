You are implementing **step R5** of the portal frontend — the profile-diff panel — in a
**parallel** session on a git worktree. The backend route it consumes (B6) is already merged.

**STOP RULE: do exactly one step — R5. When it is DONE, write the report and end the session.
Do not start anything else.** Do not ask questions: when something is unspecified, make the
smallest decision that keeps every existing test passing and the seven invariants in
`CLAUDE.md` intact, and record it in the log.

## Where you work

- **Directory:** `/home/stefano/Documents/Projects/claimstone-r5`, a git worktree.
- **Branch:** `portal-frontend-r5`. `git branch --show-current` must print it. If not, stop
  and report. Never switch branch, merge, rebase, push, amend, reset or stash. The reviewer
  merges.
- **Never touch** `/home/stefano/Documents/Projects/claimstone` (the main checkout).
- **Progress log:** create `docs/superpowers/plans/2026-10-07-portal-frontend-r5-progress.md`
  in the worktree. It is yours alone; do not edit the main frontend progress log — the
  reviewer folds the markers in at merge.

## What already exists (read before writing code)

- The route: `GET /api/v1/projects/{p}/flows/{flow_id}/questions/{qid}/profile-diff?from={sha}&to={sha}`
  — read-only; a missing `from` or `to` → 400 `BAD_REQUEST`; an unknown hash or question →
  404 `NOT_FOUND`; `from==to` → a valid empty diff. See `claimstone/portal_state.py`
  (`profile_diff`) and `tests/test_api_profile_diff.py` for the payload's exact semantics.
- The types: `ProfileDiff` in `web/src/lib/api-types.ts` (generated from the contract —
  do not regenerate or edit it). Its entries: `from`/`to` (each with `profile_sha256`,
  `built_at`, `claim_gate_version`, `decision_contract_version`, `registry_version`),
  `reason` (string | null), `summary` (`added`/`removed`/`changed`), three arrays
  `added`/`removed`/`changed` (keyed by `result_id` = the claim id; `removed` carries the
  recorded review reason; `changed` carries per-field `from`/`to`), and `counts.from`/`counts.to`
  (`by_class` and `direction_count`).
- A committed fixture for the empty diff:
  `web/tests/fixtures/projects/example-news-and-returns/flows/…/questions/Q02.profile-diff.from-….json`
  (from==to).
- The house patterns: `api.ts` (one typed function per route, `ApiError` from the §3.3
  envelope), `hooks/useApi`, `pages/QuestionPage.tsx` (where the panel lands),
  `components/ErrorState`, `components/CommandBlock` (verbatim text blocks), `lib/vocabulary`.

## The work

One panel on the question page: compare two stored profiles of this question, result by
result. It is an **audit view**, and it concludes nothing.

- **R5.1** `api.profileDiff(project, kind, sel, qid, fromSha, toSha)` in `web/src/lib/api.ts`,
  following the existing function shapes exactly.
- **R5.2** `web/src/components/ProfileDiffPanel.tsx`: two inputs for the hashes (the `from`
  input prefilled with the question's current `profile_sha256` when the page holds one), a
  compare action, and the rendering:
  - `summary` as three labelled counts; the diff-level `reason` verbatim when present;
  - each added/removed/changed entry with `result_id`, the claim text, the `evidence_quote`
    **verbatim**, the stance label from `vocabulary`, the source class, and a link to the
    entry's lineage page (the existing claim route);
  - a removed entry's `reason` verbatim — it is what the ledger recorded, never a narrative;
  - a changed entry's per-field `from` → `to` values verbatim;
  - `counts.from`/`counts.to` (`by_class` per relation, `direction_count`) labelled as a
    **count, not a strength** — the same wording the question page already uses;
  - **no verdict word anywhere**: the diff carries none, and the panel adds none;
  - error states through `ErrorState`: the 400/404 envelope message verbatim, the code named.
- **R5.3** wire the panel into `pages/QuestionPage.tsx` (a collapsed section is fine; the page's
  existing behaviour unchanged).
- **R5.4** tests, in the style of the existing `web/tests/*.test.tsx`: the panel with inline
  payloads covering added+removed+changed+diff-reason, the empty diff (the committed fixture),
  and the 404/400 refusals; plus a `useApi`/`api.ts` test for the new function.

Scope limits, because other sessions work in parallel:
- **You touch only `web/src/**` and `web/tests/**`** (plus your own new progress log file).
- Do not touch `claimstone/**`, `docs/contracts/**`, `web/tests/fixtures/**`,
  `web/src/lib/api-types.ts`, or any progress log other than your own.
- Do not install dependencies; do not change `package.json`.

## A deviation to record, not to fix

The read API has **no route listing a question's stored profile hashes**, so the panel cannot
offer a picker of real hashes: the operator pastes them (the `from` prefill is the one hash
the page already shows). Adding a hash-list route is backend work outside this step — record
it in the log as the follow-up, do not implement it.

## Start of session

1. `cd /home/stefano/Documents/Projects/claimstone-r5` and check the branch.
2. Read `CLAUDE.md`. Create your progress log: a step table with R5 `IN PROGRESS`, a checklist
   of the sub-tasks above with the files each touches, the baseline check output, and commit
   it alone (`docs: plan R5`).
3. `git status --short` must be clean apart from your own work.

## Checks (the worktree has no virtualenv of its own)

```bash
PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m pytest -q
PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m claimstone.cli validate --all-projects
PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python tools/check_instrument_versions.py
cd web && npm ci && npm run typecheck && npm test && npm run build
```

`PYTHONPATH=$PWD` is required so the worktree's code is imported, not the main checkout's.
The python checks are a gate (your change touches none of that code); the web checks are
where your work is. `npm ci` is the only network access allowed, to the npm registry.
`npm run build` includes `scripts/check-csp.mjs` — record its verdict in the log.

## Log format, per step

```
### R5 — IN PROGRESS | DONE | BLOCKED
- [x] R5.1 … (files: …)
- [ ] R5.2 … (files: …)
Checks: <exact final lines of each command, at DONE>
Decisions (spec silent): …
Deviations: …
NOT DONE: …
```

Every commit message ends with the line `Co-Authored-By: glm-5.3:cloud`. Stage files by
explicit path; never `git add -A`. Commit only when the checks pass. Never invent figures:
every number in the log is copied from output you ran.

## Report, then end the session

Reply with: the step and its final marker; the sub-tasks completed; the final check lines;
the commits (`git log --oneline` since the session started); the decisions and deviations;
the follow-up for the reviewer. Under half a page. Then stop.