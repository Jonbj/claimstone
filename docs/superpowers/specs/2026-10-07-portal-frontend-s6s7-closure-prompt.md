You are closing **steps S6 and S7** of the portal frontend plan — a verification and
documentation step, in a **parallel** session on a git worktree. Another session builds R5
elsewhere at the same time; your file sets do not overlap.

**STOP RULE: this session's one step is the S6/S7 closure. When it is DONE, write the report
and end the session.** Do not ask questions: when something is unspecified, make the smallest
decision that keeps every existing test passing and the seven invariants in `CLAUDE.md`
intact, and record it in the log.

## Where you work

- **Directory:** `/home/stefano/Documents/Projects/claimstone-s6s7`, a git worktree.
- **Branch:** `portal-frontend-s6s7`. `git branch --show-current` must print it. If not, stop
  and report. Never switch branch, merge, rebase, push, amend, reset or stash. The reviewer
  merges.
- **Never touch** `/home/stefano/Documents/Projects/claimstone` (the main checkout).
- **Progress log:** the main frontend log,
  `docs/superpowers/plans/2026-10-06-portal-frontend-progress.md` — it is yours alone in this
  window (the R5 session keeps its own separate log). Record the closure entries there.

## Background: why this is a closure, not a build

S6 and S7 were planned in `docs/superpowers/specs/2026-10-06-portal-frontend-glm-prompt.md`,
but their substance was built **outside the frontend plan** by another session (D84,
2026-10-06: `web/Dockerfile`, the `api`/`web`/`grobid` services in `compose.yaml`, `portal.sh`,
and later `trial.sh` and the scheduler service). Your job is the same triage the backend plan
already recorded for its absorbed steps: verify the substance exists, close the markers with
the deviation recorded, and implement only what is genuinely missing.

## The work

- **S6 — Dockerfile, compose services, `portal.sh`.**
  - Verify: `web/Dockerfile` exists and builds the frontend as served; `compose.yaml` carries
    the `api`, `web` and `grobid` services with the published listener on `127.0.0.1` only;
    `portal.sh` starts and stops them; D84 in `docs/DESIGN_DECISIONS.md` records the decision.
  - Check: `docker compose config -q` validates. **Validation only** — never `up`, `build`,
    `pull` or any other command that reaches Docker Hub or runs a container.
  - Read the plan's own review notes about S6 (the "Review of S5" entry's `memory: 2g` hint
    and the "Review of R4" entry) and confirm each named requirement is met or record it as
    a `NOT DONE` item with the reason.
  - Close S6 as `DONE (substance built by the scheduler session as D84 — form deviation:
    outside this plan; recorded 2026-10-07)` or leave it open with the precise gap.
- **S7 — parity check, D83, docs, instrument registration.**
  - Verify the parity check exists and runs: `tests/test_portal_fixtures.py` (committed
    fixtures equal the regeneration) — run it.
  - Verify D83 is recorded in `docs/DESIGN_DECISIONS.md`.
  - Verify the docs name the containers and the loopback-only listener: `README.md`,
    `docs/HANDOFF.md` (D84 paragraph), `docs/LOCAL_COMPOSE_TRIAL.md`.
  - Run `tools/check_instrument_versions.py`: if any instrument the frontend or the container
    stack introduced is unacknowledged, add the dated acknowledgment entries to
    `docs/DESIGN_DECISIONS.md` (append-only; use the next free `D` number only if the entry
    is a decision, not a mere acknowledgment — follow the file's own convention).
  - Close S7 as DONE, or `DONE (with NOT DONE items)` naming exactly what remains.

Scope limits:
- **You touch only `docs/**`** (the frontend progress log, `DESIGN_DECISIONS.md` append-only
  entries, README if a factual gap exists). No `claimstone/**` code, no `web/src/**`, no
  fixtures, no tests.
- If a gap is code, do not fix it: record it as `NOT DONE` with the reason. This session
  verifies and records; it does not build.

## Start of session

1. `cd /home/stefano/Documents/Projects/claimstone-s6s7` and check the branch.
2. Read `CLAUDE.md`, the frontend glm prompt (the S6/S7 rows), and the frontend progress log.
3. `git status --short` must be clean.

## Checks (the worktree has no virtualenv of its own)

```bash
PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m pytest -q
PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python -m claimstone.cli validate --all-projects
PYTHONPATH=$PWD /home/stefano/Documents/Projects/claimstone/.venv/bin/python tools/check_instrument_versions.py
docker compose config -q
cd web && npm run typecheck && npm test
```

`PYTHONPATH=$PWD` is required so the worktree's code is imported, not the main checkout's.
Your step changes no code, so every check must pass exactly as it did before you started —
record the baseline first and the final lines at DONE.

## Log format

Append one entry to the frontend progress log per closed step, in the file's own format
(checklist with `(files: …)`, exact check lines, decisions, deviations, `NOT DONE`). Every
commit message ends with the line `Co-Authored-By: glm-5.3:cloud`. Stage files by explicit
path. Commit only when the checks pass. Never invent figures: every number in the log is
copied from output you ran.

## Report, then end the session

Reply with: the two markers' final states; what was verified and what was found missing; the
final check lines; the commits; the decisions and deviations; what the reviewer must fold
into the log table at merge. Under half a page. Then stop.