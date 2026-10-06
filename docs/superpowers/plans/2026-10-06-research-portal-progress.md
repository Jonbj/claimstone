# Research portal: implementation progress log

Started 2026-10-06, from `2026-10-06-research-portal-opencode-prompt.md`. Spec:
`docs/superpowers/specs/2026-10-06-research-portal-implementation-spec.md`.

## Baseline (before any edit)

- `.venv/bin/pytest -q` → **1132 passed, 7 skipped in 16.03s**.
  Skips (pre-existing, not failures):
  - `tests/test_chunk.py:241` figures were measured on 14 documents, store has 44 (1)
  - `tests/test_live.py:25` set CLAIMSTONE_LIVE=1 and CLAIMSTONE_CONTACT_EMAIL to run (3)
  - `tests/test_live_runners.py:27` set CLAIMSTONE_LIVE=1 to run (3)
  No failures, no errors.
- `.venv/bin/claimstone validate --all-projects` → exit 0; six projects OK
  (alembic-s4, alembic-s4-breve, alembic-s4-lungo, example-news-and-returns,
  pilot-screen-time, pmc-screen-time).
- `.venv/bin/python tools/check_instrument_versions.py` → exit 0;
  `23 instrument version(s) acknowledged in the design record`.

## Checkpoints

### P0 — scope + honest errors in round_state (checkpoint name: `fix: scope round state per selector and surface ledger damage`)

Files added/changed:
- added `claimstone/scope.py` (SCOPE_VERSION 1, Selector, candidate_in_scope, candidates,
  source_ids, row_in_scope).
- `claimstone/profile_inputs.py`: `population` is now a one-line delegation to
  `scope.source_ids` (pure refactor, T6 proves equality against the pre-refactor body).
- `claimstone/round_state.py`: F3 (`_stage_discover` uses `scope.candidate_in_scope`), F1
  (claims/reviews/chunks/documents/acquired filtered per selector; `_question_spine` receives
  claims instead of re-reading; scoped `_last_write` from row timestamps only, never mtime;
  `activity(store, limit, selector=None)`), F2 (`errors` tuple on RoundState; `except
  LedgerCorrupt` replaces `except Exception` in `_stage_acquire`/`_stage_normalize`/
  `_profiles_for_spine`; `except ValueError` only around `chunk_sets.current` →
  CHUNK_SET_INVALID; `state()`'s verdicts try catches only NotAdmissible, RegistryDrift,
  LedgerCorrupt).
- `claimstone/dashboard.py`: "ledger integrity" section when `state.errors`, selector-aware
  activity call, `do_GET` wrapped → `500: <ExceptionClassName>` (`_fail`).
- tests: `tests/test_scope.py` (T1, T6, T8 + selector/row_in_scope coverage), additions to
  `tests/test_round_state.py` (T2–T5, T7), `tests/test_dashboard.py` (T9).

Commands after P0:
- `.venv/bin/pytest -q` → **1144 passed, 7 skipped** (baseline was 1132 passed; +12 tests).
- `.venv/bin/claimstone validate --all-projects` → exit 0.
- `.venv/bin/python tools/check_instrument_versions.py` → exit 0, 23 acknowledged.

Fixture note (discovered while writing tests): a claim/rejection whose `source_id` has a
document must carry a `chunk_id` present in the active chunk set, or `claim_records.current`
drops it — the two-round fixtures therefore give the r2 rejection a `chunk_id`.

Decisions (spec silent):
- T9 lives in `tests/test_dashboard.py` (it tests `dashboard.render_page`), not
  `test_round_state.py`; the spec's §2.4 table lists it without naming a file.
- `errors` in `round_state` are de-duplicated in first-seen order (two stages reading the same
  damaged ledger name the same error; the page should carry it once).

### P1 — flows (checkpoint name: `feat: bind round selectors to protocol digests (flows)`)

Files added/changed:
- added `claimstone/flows.py` (FLOW_VERSION 1): `input_file_digests`, `protocol_digest`,
  `flows`, `binding_state`, `legacy_selectors`, `set_title`, `create`; writes under an exclusive
  `flock` on `.flows.lock`, rereading the ledger under it.
- `claimstone/cli.py`: `flow create|list|check|title` subcommands. None of them record the
  registry: create delegates to `flows.create` (which checks with `record=False`), and
  list/check open the store with `check_registry_drift(..., record=False)` and report
  `RegistryDrift` as a state.
- tests: `tests/test_flows.py` (F-T1…F-T8).
- docs: `docs/contracts/flows.md`.

Commands after P1:
- `.venv/bin/pytest -q` → **1152 passed, 7 skipped** (+8).
- `validate --all-projects` → exit 0. `check_instrument_versions.py` → exit 0, 23 acknowledged.

Decisions (spec silent):
- `flow title` takes an optional `--by` (default `getpass.getuser()`); the spec named the
  `by` field of the event but no CLI flag for it.
- In `flow check`, a `RegistryDrift` raised while opening the store is printed as
  `registry drift: …` and makes the exit 4 (not a crash, and not CURRENT).
- `flow create`'s bound-after-data warning goes to stdout (it is output, not an error).
- F-T3's question-text edit marker is "An edited variant — " (an "EDITED:" prefix is invalid
  in a YAML plain scalar — colon+space).

### P2 — read-only portal (checkpoint name: `feat: read-only research portal`)

Files added/changed:
- added `claimstone/portal_state.py`: pure functions — `index`, `inbox_cards` + `Card` +
  `CATEGORY_ORDER`, `work_cards` (the F13-pinned builder), `floor_panel`, `integrity`,
  `admin_state`, `instrument_check`/`instrument_versions`, `question_matrix`, `flow_overview`,
  `question_detail`, `lineage`, `source_dossier`, `NotFound`.
- added `claimstone/portal.py`: transport and rendering — ThreadingHTTPServer, GET-only with the
  `__getattr__` refusal, Host allowlist (421) + Origin check (403), CSP/nosniff/no-store headers,
  lookup-never-path parameters, per-request `load_project` + `check_registry_drift(record=False)`
  with ConfigError/RegistryDrift as named states, 3 s polling on scoped pages, admin/index/inbox
  pages, reuses `dashboard._STYLE/_esc/_chip/_frac` by import.
- `claimstone/cli.py`: `claimstone portal [--projects-dir] [--store] [--host] [--port]`.
- `tools/check_instrument_versions.py`: `main` refactored to call a new `check() -> list[str]`
  (behaviour and exit codes unchanged); the three new instruments registered (§6).
- `docs/DESIGN_DECISIONS.md`: D82 written at this milestone, not last, because
  `check_instrument_versions.py` refuses to pass until the record names `scope_version 1`,
  `flow_version 1`, `export_version 1` — that refusal is the feature. The page-time figure was
  filled in after the manual check below.
- tests: `tests/test_portal_state.py` (P-T1..3, I-T1..5, L-T1..2, A-T1, G-T1, F-T9),
  `tests/test_portal.py` (H-T1..6).

Commands after P2:
- `.venv/bin/pytest -q` → **1173 passed, 7 skipped** (+21).
- `validate --all-projects` → exit 0.
- `check_instrument_versions.py` → exit 0, **26** instrument version(s) acknowledged.

Manual loopback check (spec §8): a tmp store built from the test fixture workspace, portal on
127.0.0.1:8791 — all 17 routes answered 200 (`/`, `/inbox`, `/admin`, project, flow, question,
claim lineage, source dossier, the legacy equivalents, and the five API routes). D82's timing
against the real store (one read-only GET): **15.43 s** (15.38 s, 15.66 s on repeats).

Decisions (spec silent):
- `work_cards` builds the three F13 categories with `scope=""`; `inbox_cards` fills the scope
  label afterwards via `dataclasses.replace`, because the pinned signature carries no flow id.
- `make_server` sets the handler's `bind_port` after binding, so the Host allowlist works with
  port 0.
- The portal's integrity panel computes code identity itself when not handed the server's
  values; the page header shows the server-start value, labelled "at server start".
- The dashboard's `_STYLE`/`_esc`/`_chip`/`_frac` are imported from `claimstone.dashboard`, as
  §4.1 requires (no copying).

Deviations:
- The ADJUDICATION card's command uses the question as a **positional** argument
  (`adjudicate <path> <Q> …`), not the spec's literal `--question <Q>`: `build_parser` accepts
  no `--question` flag there, and I-T4 requires every command string to parse against it.
  (Spec's own working-loop rule 4 — verify flags against `build_parser` — resolves this.)

### P2b — export (checkpoint name: `feat: verifiable flow export`)

Files added/changed:
- added `claimstone/export.py` (EXPORT_VERSION 1): `snapshot` (prefix cut at last newline under
  `.flows.lock`, torn tails recorded and excluded), `_compute_outputs` (profiles/floor/questions/
  claims/rejections/acquisition CSVs + report.md, all derived from the frozen prefix rebuilt in a
  temp dir), `export` (idempotent on `sha256(canonical({"flow_id","selector","prefixes}))`,
  appends `exports.jsonl` under the lock), `verify` (PREFIX_CHANGED + OUTPUT_DIFFERS, exit
  semantics in the CLI).
- `claimstone/cli.py`: `claimstone export PROJECT FLOW_ID [--store]` and `claimstone
  export-verify DIR [--projects-dir]` (exit 0 / 5).
- tests: `tests/test_export.py` (E-T1…E-T7).
- docs: `docs/contracts/exports.md`.

Commands after P2b:
- `.venv/bin/pytest -q` → **1180 passed, 7 skipped** (+7).

Decisions (spec silent):
- `exports.jsonl` is excluded from the snapshot (the spec's globs name only `audits/` and
  `exports/` directories): it is bookkeeping about exports, not evidence, and including it would
  give every export a new identity however unchanged the ledgers — E-T5 forces this reading.
- `export-verify` takes `--projects-dir` (default `projects`): recomputation needs the live
  project, and the spec fixed only `export-verify DIR` without saying where the project comes
  from. A project it cannot find reports `PROJECT_NOT_FOUND` and exits 5.
- CSV adds two columns for the document parser versions (`html_parser_version`,
  `jats_parser_version`) rather than one combined field.

### Docs + D82 (checkpoint name: `docs: record D82 and portal contracts`)

- `docs/contracts/flows.md` (written at P1), `docs/contracts/exports.md` (P2b).
- `docs/contracts/requests.md`: `fetch_version` corrected from "currently 2" to 3 (F18).
- `docs/superpowers/specs/2026-10-06-research-portal-design.md`: status line added naming the
  review and the implementation spec.
- `docs/HANDOFF.md`: dated paragraph at the top of "Where the work stands" (test count from
  pytest's own output; no ledger, request or model call happened).
- `docs/README.md` (the map): portal command + D82 entry, the two new contracts, and the
  research-portal bullet updated from "not implemented" to P0–P2b implemented.
- `docs/DESIGN_DECISIONS.md`: D82 (see the P2 note on why it was written early); the measured
  page time was filled in after the loopback check.

### Final results (definition of done, §11, adapted for "no commits")

- `.venv/bin/pytest -q` → **1180 passed, 7 skipped in 23.86s** (baseline 1132 passed, 7 skipped;
  +48 tests, no pre-existing failure worsened — there were none).
- `.venv/bin/claimstone validate --all-projects` → exit 0.
- `.venv/bin/python tools/check_instrument_versions.py` → exit 0,
  `26 instrument version(s) acknowledged in the design record`.
- `claimstone flow` (create/list/check/title), `claimstone portal`, `claimstone export`,
  `claimstone export-verify` all exercised on a tmp workspace; portal routes also verified with
  curl on loopback (17 routes, all 200).
- `git status --short` / `git diff --stat`: only files this spec requires, plus pre-existing
  uncommitted work by others (`docs/SCHEDULER_BACKLOG.md`, `tools/build_source_selection_dossier.py`,
  `tools/preview_source_selection_queue.py`, `tools/record_l02_*.py`, and the spec/prompt files
  themselves) left exactly as found. Nothing under `projects/` or `store/` changed.

## NOT DONE

Nothing from the spec's §11 checklist. P3 and P4 are out of scope by the spec's own §10 and were
not started.


## Implementation review (2026-10-06, Claude Code)

Reviewed and corrected in place: see
`docs/superpowers/specs/2026-10-06-research-portal-implementation-review.md` (findings I1–I15,
regression tests R1–R10). The main corrections:

- Q04's whole-store profile is now visible at `/p/<project>/legacy/-/`.
- One `compute()` per selector per request; the flow page went from 15.2 s to 3.9 s.
- The adjudication card no longer proposes a signature the engine refuses.
- The export id includes instruments and the live protocol.
- Invalid flow rows are excluded.
- `--allow-host` added.

Final: `.venv/bin/pytest -q` → 1191 passed, 7 skipped. The next phase (separate frontend and
containers) is specified in `docs/superpowers/specs/2026-10-06-portal-frontend-docker-design.md`.
