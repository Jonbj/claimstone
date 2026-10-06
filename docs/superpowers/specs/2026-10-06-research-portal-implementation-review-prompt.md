# Prompt for Claude Code: research portal implementation review

An implementation of `docs/superpowers/specs/2026-10-06-research-portal-implementation-spec.md`
(phases P0, P1, P2, P2b, plus §6 instrument registration, §7 documentation and the D82 entry)
has just been completed by another agent, autonomously, from
`2026-10-06-research-portal-opencode-prompt.md`. Your job is an independent, adversarial review
of that work. You are reviewing, not fixing: report findings, do not repair them.

## Read first, in this order

1. `CLAUDE.md` (the seven invariants — non-negotiable) and `AGENTS.md`.
2. The implementation spec, in full: `docs/superpowers/specs/2026-10-06-research-portal-implementation-spec.md`.
3. `docs/superpowers/specs/2026-10-06-research-portal-review.md` — the design review whose
   findings F1–F22 the spec incorporates. The spec cites finding numbers constantly; you need them.
4. The progress log: `docs/superpowers/plans/2026-10-06-research-portal-progress.md`. It records
   the baseline, every decision made where the spec was silent, and every deviation. **Challenge
   each of those decisions and deviations explicitly** — they were made without a human in the loop.
5. The code under review: `claimstone/scope.py`, `claimstone/round_state.py`,
   `claimstone/dashboard.py`, `claimstone/flows.py`, `claimstone/portal_state.py`,
   `claimstone/portal.py`, `claimstone/export.py`, `claimstone/profile_inputs.py`,
   `claimstone/cli.py`, `tools/check_instrument_versions.py`, and the new tests
   `tests/test_scope.py`, `tests/test_flows.py`, `tests/test_portal_state.py`,
   `tests/test_portal.py`, `tests/test_export.py`, plus the additions to
   `tests/test_round_state.py` and `tests/test_dashboard.py`.
6. The documentation it wrote: `docs/contracts/flows.md`, `docs/contracts/exports.md`,
   the `requests.md` correction, the D82 entry, the `HANDOFF.md` paragraph, `docs/README.md`.

## Facts you may rely on (recorded at the end of the run)

- `.venv/bin/pytest -q` → **1180 passed, 7 skipped** (baseline before the work: 1132 passed,
  7 skipped; the 7 skips are pre-existing: 1 in `tests/test_chunk.py`, 3+3 gated behind
  `CLAIMSTONE_LIVE=1`).
- `.venv/bin/claimstone validate --all-projects` → exit 0.
- `.venv/bin/python tools/check_instrument_versions.py` → exit 0,
  `26 instrument version(s) acknowledged`.
- Nothing was committed. Nothing under `projects/` or `store/` was modified, except one
  read-only HTTP GET against a portal started on loopback for D82's page-time measurement.
- Other uncommitted work by other people was in the tree before this run
  (`docs/SCHEDULER_BACKLOG.md`, `tools/build_source_selection_dossier.py`,
  `tools/preview_source_selection_queue.py`, `tools/record_l02_*.py`, and the spec/prompt files
  themselves). It must be untouched; it is not part of this review.

## Hard constraints. These override any instinct to be helpful.

- Do not commit, branch, stash or reset anything. Leave the working tree as you found it.
- Never write to, repair or delete anything under `store/`. Tests and any portal you start must
  use `tmp_path` or a directory under `/tmp` only. Never modify `projects/`.
- No network requests to the outside world, no model backends. Never run `acquire`, `discover`,
  `normalize`, `extract`, `review`, `synthesize`, `adjudicate`, `model-run` or `./claimstone.sh`.
- `claimstone portal` may be started on `127.0.0.1` with a high port against a **tmp** store
  only (build one from the test fixtures, e.g. `tests.test_portal_state.build_workspace`), and
  must be stopped afterwards. The one exception, as in the implemented run: a read-only GET
  against the real store for re-measuring D82's page time is permitted.
- Do not modify any test, the spec, the progress log or the implementation to make a finding go
  away. You are the reviewer: findings are the deliverable.

## What to review, specifically

1. **Spec conformance, test by test.** Walk the tables in §2.4, §3.7, §4.13 and §5.4 and check
   each test exists **and asserts what the spec's row says it asserts**. A test that passes while
   proving something weaker than its spec row is a finding (name the gap). Check the spec's own
   acceptance probes are honest: e.g. does I-T3 really make stance-flipping unobservable, does
   H-T6 really cover every route, does E-T3 really damage bytes inside the recorded prefix.
2. **The seven invariants against the new code.** No portal route writes or starts work (check
   the handler's full reachable surface, including `__getattr__` and error paths); no verdict is
   signed or prefilled anywhere in the UI (placeholders must stay placeholders); `AI_PROVISIONAL`
   rows are advisory only; per-class counts precede pooled ones; the five verdict states never
   collapse (`NO_VERIFIED_CLAIM` is never shown as `UNANSWERED_IN_LITERATURE` or `NEVER_ASKED`).
3. **The review findings the spec claims to fix are actually fixed.** F1/F3 (scope leaks and the
   `or "routine"` predicate), F2 (errors as zeros), F4 (bindings compared, never used to compute),
   F9 (per-request project reload), F13 (ordering independence), F17 (mtime fallback in scoped
   reads), F19 (PAYWALL_403 display). For each: cite the code that fixes it and the test that
   demonstrates it, or report it as not fixed.
4. **Export semantics.** Is the prefix cut correct (torn tails, `exports.jsonl` exclusion — the
   progress log records that decision; is it right)? Is recomputation deterministic across
   machines and time (timestamps, dict order, git identity)? Can `export-verify` pass on an
   export whose outputs are quietly wrong, or fail on one that is right?
5. **Security of the transport.** Host allowlist and Origin check bypasses, path-parameter
   handling (`unquote` once — what about encoded slashes or `%2e%2e`?), header handling on error
   paths, the 500 handler, information leaks in `admin_state` (values, lengths, prefixes).
6. **Docs and figures.** Every number in D82, `HANDOFF.md` and the progress log must match
   command output you actually ran (re-run them). Do the two new contracts describe the code as
   written, including the lock and identity rules? Is the D82 page-time claim reproducible?
7. **Hygiene.** `git status --short` / `git diff --stat` must show only files the spec requires
   plus the pre-existing third-party work listed above. Nothing under `projects/` or `store/`.
   The modules in spec §0.2 must be unmodified except the two named exceptions
   (`profile_inputs.population` as a pure refactor, `check()` in
   `tools/check_instrument_versions.py`).

## Labels

Use the review's convention: **[CODE]** verified by reading the cited code, **[RUN]** verified by
running something (name the command), **[INFER]** design inference, **[UNRESOLVED]** depends on
data or intent you cannot see. Never present an inference as a verified defect.

## Deliverable

Write `docs/superpowers/specs/2026-10-06-research-portal-implementation-review.md` in the style
of `2026-10-06-research-portal-review.md`:

1. Findings ordered by severity (critical / high / medium / low), each labelled, each citing
   exact file and line, each naming the minimal remedy — but not applying it.
2. A conformance table: spec test id → test function → verdict (proves it / proves less / absent).
3. A verdict on each recorded decision and deviation in the progress log: endorse or reject, with
   the reason.
4. The exact output lines of the three commands as you ran them, and D82's page time as you
   measured it.
5. A closing statement of what is safe to keep as-is and what must be reworked before the next
   phase (P3) may start.

Keep the review under one page per section. Do not claim anything you did not verify by running
or reading it.
