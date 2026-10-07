You are implementing **step B6** of the portal backend, in a **parallel** session. Another session
builds the other steps on `research-portal` at the same time.

**Amendment (2026-10-07, operator):** B2 was implemented on the main line by the scheduler session
(writer lock in `store.py`, persistent host budget and URL guard in `net.py`, `FETCH_VERSION` 5 —
committed on `research-portal`). **B2 is no longer this session's work. Do not redo it.**

**STOP RULE: do exactly one step per session: B6 only. When it is DONE,
reply "parallel step complete" and do nothing else.** Do not ask questions. When something is unspecified,
make the smallest decision that keeps every existing test passing and the seven invariants in `CLAUDE.md`
intact. Record it in the log.

## Where you work

- **Directory:** `/home/stefano/Documents/Projects/claimstone-parallel`, a git worktree.
- **Branch:** `portal-backend-parallel`. `git branch --show-current` must print it. If not, stop and report.
  Never switch branch, merge, rebase, push, amend, reset or stash. The reviewer merges.
- **Never touch** `/home/stefano/Documents/Projects/claimstone` (the main checkout). Read nothing from it and
  write nothing to it.
- **Progress log:** `docs/superpowers/plans/2026-10-07-portal-backend-parallel-progress.md`, in the worktree.
  It is not the main log.

## The work

All of the following are in the worktree:
- the main prompt `docs/superpowers/specs/2026-10-07-portal-backend-glm-prompt.md`. Follow its "Working method
  inside a step", "Hard constraints", "Log format" and "Report" sections exactly, with the log path above.
  Ignore its step table and its "Start of every session";
- the spec `docs/superpowers/specs/2026-10-07-portal-backend-spec.md`. Read §1, §3, and the section of your
  step.

| step | spec | done when |
|---|---|---|
| ~~B2~~ | done on the main line (see amendment above) — not this session's work | — |
| **B6** | `profile-diff` route in the read API; `api_schema.py`; regenerated schema and fixtures | spec B6 tests pass; checks pass |

Scope limits, because the other session edits other files at the same time:
- B6 touches only `claimstone/api.py`, `claimstone/api_schema.py`, the generated schema and fixtures, and
  their tests.
- Do not edit `cli.py`, `synthesize.py`, `acquire.py` or `DESIGN_DECISIONS.md`.
- Do not register new version constants. Record "to register at merge: …" in the log instead.

## Start of every session

1. `cd /home/stefano/Documents/Projects/claimstone-parallel` and check the branch.
2. Read `CLAUDE.md` and the progress log. If the log does not exist, create it:
   - add a table with B6 `TODO` (B2 is done on the main line);
   - run the checks and record their output as the baseline;
   - commit it alone.
3. `git status --short`: uncommitted files here can only be from an interrupted session of yours. Finish or
   discard them as the main prompt says.

## Checks (this worktree has no virtualenv of its own: use these exact commands)

```bash
PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m pytest -q
PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m claimstone.cli validate --all-projects
PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python tools/check_instrument_versions.py
```

`PYTHONPATH=$PWD` is required, so that the worktree's code is imported and not the main checkout's. For B6,
also run `cd web && npm ci && npm run typecheck && npm test`. `npm ci` is the only network access allowed,
to the npm registry.
