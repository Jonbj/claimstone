You are implementing a fully specified feature in the Claimstone repository, working autonomously from
start to finish. **Do not ask me any questions and do not stop for confirmation.** I will not answer
until you are done. When the spec does not cover something, make the smallest decision that keeps every
existing test passing and the seven invariants in `CLAUDE.md` intact. Record each such decision in the
progress log (see below) and continue.

## What to implement

Implement **all** of `docs/superpowers/specs/2026-10-06-research-portal-implementation-spec.md`: phases
P0, P1, P2 and P2b, the documentation in §7 and the D82 entry in §9. That spec is the authority. Follow
its §0 rules literally. Read the spec in full before writing any code.

## Read first, in this order

1. `CLAUDE.md` (invariants: non-negotiable)
2. `AGENTS.md`
3. the implementation spec above, in full
4. `docs/superpowers/specs/2026-10-06-research-portal-review.md`. It explains why each requirement
   exists; the finding numbers F1–F22 are cited in the spec.
5. The code the spec names before you change or call it: `claimstone/round_state.py`,
   `claimstone/dashboard.py`, `claimstone/store.py`, `claimstone/admissibility.py`,
   `claimstone/profile_inputs.py`, `claimstone/synthesize.py`, `claimstone/population.py`,
   `claimstone/source_selection.py`, `claimstone/config.py`, `claimstone/cli.py`,
   `tools/check_instrument_versions.py`, and the existing tests `tests/test_round_state.py` and
   `tests/test_dashboard.py` for fixture patterns.

## Hard constraints. These override any instinct to be helpful.

- **No git commits, no branches, no stash, no reset, no checkout of files.** The working tree contains
  substantial uncommitted work by other people, including untracked files such as
  `claimstone/round_state.py` and `claimstone/dashboard.py`. Committing or stashing would mix or lose it.
  Ignore the "Commit:" lines in the spec's §8 and use them as checkpoint names in the progress log
  instead. Leave all changes uncommitted.
- Never read from, write to, repair or delete anything under `store/`. The one exception is the timing
  measurement in the spec's §9, which is a read-only HTTP GET against a portal you start on loopback.
  Never modify `projects/`. Tests use `tmp_path` only. For a project copy in tests, copy
  `projects/example-news-and-returns` into `tmp_path`.
- No network requests to the outside world, no model backends. Never run `acquire`, `discover`,
  `normalize`, `extract`, `review`, `synthesize`, `adjudicate`, `model-run` or `./claimstone.sh`.
- No new dependencies, no web framework, no CDN, no JS library.
- Do not modify the modules listed in the spec's §0.2, except the two named exceptions:
  `profile_inputs.population` as a pure refactor, and extracting `check()` in
  `tools/check_instrument_versions.py`.
- Never weaken, skip, delete or rewrite an existing test to make it pass. If an existing test fails
  because of your change, your change is wrong: fix the change.
- Never invent figures. Any number you write in docs (test counts, timings) must be copied from command
  output you actually ran.

## Working loop

1. **Baseline, before any edit.** Run:
   ```bash
   .venv/bin/pytest -q
   .venv/bin/claimstone validate --all-projects
   .venv/bin/python tools/check_instrument_versions.py
   ```
   Record the exact results in the progress log, including any failures or errors that already exist
   (for example socket-denied server tests). Pre-existing failures are not yours to fix; they must
   simply not get worse.
2. Implement the milestones in the order of the spec's §8: P0 → P1 → P2 → P2b → docs/D82. For each
   milestone:
   - Write its tests from the spec's tables first (test ids T1…, F-T…, P-T…, I-T…, L-T…, A-T…, G-T…,
     H-T…, E-T…). Use the spec's test ids in the test function docstrings.
   - Implement until those tests pass.
   - Run the three baseline commands. The suite must be green except for exactly the pre-existing
     failures recorded at baseline.
   - Append a checkpoint entry to the progress log.
3. If a test fails, diagnose from the actual error output, fix, and rerun. If the same failure survives
   three distinct fix attempts, re-read the relevant spec section and the code it names, choose the
   simplest design that satisfies the spec's stated purpose, record the deviation in the log, and
   continue. Never stop the whole job for one stuck item. If something is truly impossible, leave it
   documented as **NOT DONE** with the reason, finish everything else, and report it at the end.
4. Before verifying the flag names that appear in CLI command strings, check them against
   `cli.build_parser()`. Note that `acquire`, `report` and `gate-audit` use `--manifest`, while
   `synthesize`, `verdicts` and `adjudicate` use `--manifest-only`.
5. For P2's manual check, start the portal on `127.0.0.1` with a high port and point `--store` at a
   **tmp copy** you build from test fixtures, never at `store/`. Fetch each route with `curl`, then stop
   the server. For D82's timing, the spec asks for one GET on
   `/p/pmc-screen-time/legacy/pmc-oa-v1/` against the real store. That is a read only and it is
   permitted. If it fails or takes more than 120 s, record "not measured: <reason>" in D82 instead.

## Progress log

Create and maintain `docs/superpowers/plans/2026-10-06-research-portal-progress.md`. It holds:

- the baseline results
- one checkpoint per milestone: files added or changed, tests added, the three commands' output
  summaries
- every decision you made where the spec was silent
- every deviation from the spec, with its reason
- anything NOT DONE

Update it as you go, not only at the end, so that an interrupted run can be resumed from it. If the
file already exists when you start, read it and resume from the last completed checkpoint rather than
starting over.

## Definition of done

Done means the spec's §11 checklist is satisfied, adapted for "no commits": instead of commits,
`git status` shows your changes as uncommitted, and nothing under `projects/` or `store/` is changed.
Concretely:

- All spec tests exist and pass; the full suite has no failures beyond the baseline ones.
- `validate --all-projects` and `check_instrument_versions.py` exit 0.
- `claimstone flow`, `claimstone portal`, `claimstone export` and `claimstone export-verify` work.
- `docs/contracts/flows.md`, `docs/contracts/exports.md`, the `requests.md` correction, the design-spec
  status line, the HANDOFF paragraph, the docs map links and D82 are written.
- `git diff --stat` (tracked files) and `git status --short` (untracked) show only files this spec
  requires.

## Final message

When finished, reply with:

1. the per-milestone summary
2. the final output lines of the three commands
3. the list of created and modified files
4. the decisions and deviations from the progress log
5. anything NOT DONE

Keep the whole message under one page. Do not claim anything you did not verify by running it.
