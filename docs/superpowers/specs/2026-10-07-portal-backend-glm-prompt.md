You are implementing **one step** of a multi-step feature in the Claimstone repository.

**STOP RULE: do exactly one step, the first one not marked DONE (or BLOCKED) in the progress log. Then
write the report and end the session. Do not start the next step, even if you have budget left.** Do not
ask me questions. When something is unspecified, make the smallest decision that keeps every existing test
passing and the seven invariants in `CLAUDE.md` intact. Record it in the log and continue.

Your budget may run out at any moment, without warning. The working method below is designed so that an
interruption loses at most one small sub-task. Follow it exactly.

## The work

The specification is `docs/superpowers/specs/2026-10-07-portal-backend-spec.md`. It is the authority. Read
§1 (always applies), §3, and the section of your step. The design it serves is
`docs/design/portal/v2/README.md`; read it only for context and never copy its illustrative figures into
code.

Background you will need:
- `docs/contracts/scheduler_operations.md`: the lock and resume rules;
- `docs/superpowers/specs/2026-10-06-research-portal-review.md`: findings F5, F6, F13–F17;
- `claimstone/transport.py` and `claimstone/api.py`: the existing read API, which must stay read-only.

## Start of every session (in this order)

1. Check you are on the right branch: `git branch --show-current` must print `research-portal`. If it does
   not, run `git switch research-portal`. Never work on `main`.
2. Read `CLAUDE.md`, then the progress log `docs/superpowers/plans/2026-10-07-portal-backend-progress.md`.
   If the log does not exist:
   - create it with the step table below, all steps `TODO`;
   - run the checks and record their output as the baseline;
   - commit the log alone (`docs: start portal backend progress log`).
3. Run `git status --short`. Another session works on this branch in parallel (the scheduler track), so
   uncommitted files may not be yours.
   - Uncommitted changes to files **named in your step's `IN PROGRESS` sub-tasks** mean a previous session
     of yours was interrupted. Inspect them, then either finish that sub-task or discard **only those
     files** with `git restore`/`git clean` on the named paths.
   - Any other uncommitted file belongs to someone else: do not edit, stage, restore or delete it.
4. Pick the step: the one marked `IN PROGRESS`, or else the first in the table that is `TODO`. Steps marked
   `PARALLEL` are never yours (see "Parallel steps" below).

## Working method inside a step

1. **Before writing any code**, append the step's section to the log:
   - mark it `IN PROGRESS`;
   - add a checklist of 3–6 small sub-tasks (`- [ ] B3.1 …`), each completable and checkable on its own;
   - list the files each sub-task will touch.

   Commit the log: `docs: plan B<n>`.
2. For each sub-task:
   - implement it, test first where the spec lists tests;
   - run the checks;
   - tick it (`- [x]`) in the log;
   - commit the code and the log together: `wip(B<n>.<k>): <what>`.

   Stage files **by explicit path**; never `git add -A` or `git add .`. Commit only when the checks pass. If
   they fail, fix before moving on.
3. When every sub-task is ticked and the step's "done when" (or its listed tests) holds:
   - change the marker to `DONE`;
   - record the final check lines, decisions and deviations;
   - commit: `feat(portal-backend): B<n> <title>`, or `docs(portal-backend): B0 …`.
4. Write the report (below) and **end the session**.

Each commit message ends with the line `Co-Authored-By: GLM via opencode`. Commit with `git commit` on
`research-portal` only. Never push, rebase, amend, reset, stash, or switch to another branch.

## Steps

| step | content (spec section) | done when |
|---|---|---|
| **B0** | Decision entry (next free `D` number at the time you write it) and `docs/contracts/control_api.md` | files exist; checks pass; no code changed |
| **B1** | Project writer lock adopted by every writer; re-read under the lock in acquire and adjudicate (F5) | spec B1 tests pass; checks pass |
| **B2** | Host failure budget rebuilt from `requests.jsonl`; `urlguard.py`; manual redirects checked per hop (F6, F15) | spec B2 tests pass; checks pass |
| **B3** | `adjudication_version 2`, `signer_auth`, `actor`; required parameters; read API field, schema, fixtures (F16) | spec B3 tests pass; checks pass |
| **B4** | `claimstone control`, `claimstone operator add/disable`, sessions, CSRF, rate limit | spec B4 tests pass, including the "every POST refuses anonymous" test |
| **B5** | Web signing and drafts | spec B5 tests pass |
| **B6** | Profile diff route in the read API; schema and fixtures | spec B6 tests pass |
| **B7a** | Intake of DOIs, URLs and references; cohort routing; single explicit fetch | spec B7a tests pass |
| **B7b** | File intake, quarantine, engine gates, `operator-supplied` acquisition row, `supplied_copies` policy (F14) | spec B7b tests pass; existing admissibility tests unchanged and passing |
| **B8** | Identity resolution, retry-campaign record and preview, purchase offers and stages, defer/decline, F13 ordering test | spec B8 tests pass |
| **B9** | Seen markers and `/control/v1/today` | spec B9 tests pass |
| **B10** | Export create and verify from the control API; exports list in the read API; PDF licence rule | spec B10 tests pass |
| **B11** | Reachability checks, write-only credentials, 501 for the paid test call | spec B11 tests pass |
| **B12** | Scheduler-facing routes, **only if** the operations ledger module exists; otherwise mark `BLOCKED` with the reason and end the session | as spec B12, or `BLOCKED` recorded |
| **B13** | `control` service in compose and nginx, version registrations, decision entry completed, `HANDOFF.md` | checks pass; `docker compose config` validates; `api` service unchanged |

**Parallel steps.** B2 and B6 are built by another session on the branch `portal-backend-parallel` and merged
into `research-portal` by the reviewer. On this branch, treat them as `PARALLEL`: never pick them, and record
them in the log table as `PARALLEL (portal-backend-parallel)`. B7a needs `claimstone/urlguard.py` from B2. If
that file is absent when B7a starts, mark B7a `BLOCKED (waiting for B2 merge)` and end the session.

## Checks

Always run:

```bash
.venv/bin/pytest -q
.venv/bin/claimstone validate --all-projects
.venv/bin/python tools/check_instrument_versions.py
```

When a step changes `api_schema.py`, also regenerate and commit
`docs/contracts/portal-api.schema.json` and `web/tests/fixtures/*.json` with the existing tools, then run
`cd web && npm run typecheck && npm test`. Do not change any frontend source.

## Hard constraints. These override any instinct to be helpful.

- **The real data is untouchable.**
  - Never write to, repair or delete anything under `store/`, and never modify `projects/`.
  - Tests use `tmp_path` and build their own project and store.
  - Any server you start by hand for a check runs against a tmp store (for example from
    `tests.test_portal_state.build_workspace`) and a tmp state dir, and you stop it afterwards.
- **No network.**
  - No scholarly API, publisher, model backend, npm or Docker Hub.
  - Every test that exercises a fetch uses a fake resolver or a local stub server on 127.0.0.1, enabled
    only through an explicit test hook.
  - Never run `acquire`, `discover`, `normalize`, `extract`, `review`, `synthesize`, `adjudicate`,
    `model-run`, `./claimstone.sh` or `./portal.sh` against anything real.
- **No new dependency.** Python stdlib plus what is already in `pyproject.toml`. Passwords use
  `hashlib.scrypt`; sessions use `secrets`.
- **The read API stays read-only.** Do not add a non-GET path to `transport.BaseHandler` or `api.py`. Writes
  live in `claimstone/control.py` only.
- **No scientific decisions in code.**
  - Never preselect, suggest or default a verdict.
  - Never let a provisional profile, an operational question or a stale hash be signed.
  - Never rank intake or offers by anything derived from claims, reviews or stances.
  - Never change the floor denominator.
  - Never merge two works.
- **Secrets.**
  - Never print, log, return or commit a password, a session token or a credential value.
  - Never commit `.env`, `.claimstone/` or anything under `store/` or `projects/`. Add `.claimstone/` to
    `.gitignore` in B4.
- **Do not build the scheduler.** If a step seems to need an operations ledger or an executor, it is B12's
  precondition: record it and stop.
- Never weaken, skip, delete or rewrite an existing test to make it pass. If an existing test fails because
  of your change, the change is wrong. The only allowed edits to existing tests are the call sites of
  `synthesize.adjudicate`, which gain the new required keywords in B3.
- Never invent figures. Every number in docs or in the log is copied from output you ran.
- If the same failure survives three distinct fix attempts:
  - re-read the spec section and choose the simplest design that satisfies its purpose, then record the
    deviation;
  - if something is truly impossible, record it as **NOT DONE** in the step, with the reason;
  - mark the step `DONE (with NOT DONE items)` only if the rest holds; otherwise leave it `IN PROGRESS` and
    say what blocks it.

## Log format, per step

```
### B<n> — IN PROGRESS | DONE | BLOCKED
- [x] B<n>.1 … (files: …)
- [ ] B<n>.2 … (files: …)
Checks: <exact final lines of each command, at DONE>
Decisions (spec silent): …
Deviations: …
NOT DONE: …
```

## Report, then end the session

Reply with:
- the step you worked on and its final marker;
- the sub-tasks completed this session;
- the final check lines;
- the commits made (`git log --oneline` since the session started);
- the decisions and deviations;
- the next step.

Keep it under half a page. Then stop: do not begin the next step.
