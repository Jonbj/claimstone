# Research portal: implementation spec (phases P0–P2b)

**Status:** ready for implementation. Nothing in this spec is implemented yet.
**Date:** 2026-10-06.
**Derived from:** `2026-10-06-research-portal-design.md`, as corrected by
`2026-10-06-research-portal-review.md`. Finding numbers (F1…F22) refer to that review.
**Audience:** an implementing model with no prior context. Follow this document literally. When it is
silent, choose the smallest change that keeps every existing test passing, and write down the choice in
the D82 entry (§9).

---

## 0. Read this first: rules for the implementer

### 0.1 What you are building

1. **P0:** a canonical scope module, plus fixes to `round_state.py` so a figure shown for one round
   never includes another round's data, and a damaged ledger never shows as zero.
2. **P1:** an append-only `flows.jsonl` ledger and three CLI commands (`flow create`, `flow list`,
   `flow check`) that bind a round selector to a digest of the project's protocol and detect drift.
3. **P2:** a **read-only**, multi-project, multi-flow web portal (`claimstone portal`) built on the
   standard library, like `claimstone/dashboard.py`.
4. **P2b:** `claimstone export` and `claimstone export-verify`: a consistent, verifiable snapshot of one
   flow.

### 0.2 What you must NOT do. Each of these is a defect, not a shortcut.

- Do not add any route that writes, any button or form that starts work, or any HTTP method other than
  GET. The portal in this spec is read-only. Every write in this spec happens through the CLI.
- Do not modify `claimstone/admissibility.py`, `claimstone/synthesize.py`, `claimstone/evidence.py`,
  `claimstone/claimgate.py`, `claimstone/fulltext.py`, `claimstone/net.py`, `claimstone/acquire.py`,
  `claimstone/normalize.py`, `claimstone/extract.py` or `claimstone/review.py`. They are scientific
  instruments, and changing them requires a measured decision this spec does not contain.
- Do not modify `claimstone/dashboard.py` except as stated in §3.4.
- Do not change any existing ledger row, and do not rewrite or delete any file under `store/`. Tests use
  `tmp_path` stores only.
- Do not make network requests, run model backends or run `acquire`, `discover`, `normalize`,
  `extract`, `review`, `synthesize` or `adjudicate` against the real `store/`.
- Do not add dependencies. Use only the stdlib plus what `pyproject.toml` already has. No web
  framework, no template engine, no JS library, no CDN.
- Do not add a cache for computed state. Every request re-reads the ledgers.
- Do not display any secret value, its length or its prefix. Display presence only (`set` / `not set`).
- Do not compute anything from the values stored in a flow's binding: floor, registry and population
  are always read from the live project, and the binding is only **compared** against them (F4).
- Do not label HTTP 403 as a paywall or as a purchasable offer anywhere in the UI (F19).
- Do not order, filter or rank acquisition or intake cards using claims, reviews, stances, results or
  profiles (F13).
- Do not convert `AI_PROVISIONAL` screening rows into anything else. Do not show them as inclusions,
  exclusions or admissions. Show them only as "advisory, AI provisional".
- Do not sign verdicts, and do not prefill a verdict choice. The portal may show the `adjudicate`
  **command text** with the profile hash filled in. The verdict and the rationale remain placeholders
  the person must replace.
- Do not commit anything under `projects/` or `store/`.

### 0.3 Commands that must pass after every milestone

```bash
.venv/bin/pytest -q
.venv/bin/claimstone validate --all-projects
.venv/bin/python tools/check_instrument_versions.py
```

If pytest has socket-related errors in your sandbox for server tests, follow the existing pattern in
`tests/test_dashboard.py` (look at how it creates servers and whether it skips). Do not delete tests.

### 0.4 Code style

Match `claimstone/round_state.py` and `claimstone/dashboard.py`:

- `from __future__ import annotations`
- frozen dataclasses for state
- module docstrings that explain *why*
- `int | None` where None means "not knowable" and 0 means "counted zero"
- `html.escape` on every interpolated value
- no `except Exception` that turns an error into a number

---

## 1. Background you need (verified facts)

- Ledgers are append-only JSONL under `store/<project>/`. `Store.read(name)` yields rows. It skips a torn
  final line (no trailing newline) and records it in `store.torn_tail`, and it raises
  `store.LedgerCorrupt` on damage anywhere else. `Store.latest_by(name, key)` keeps the last row per
  key.
- A **round selector** today is the pair `(round_name: str | None, manifest_only: bool)`:
  - `round_name=None` means the whole store.
  - A candidate is in scope when `(round_name is None or row.get("round") == round_name) and (not
    manifest_only or row.get("source_id"))`. This is the predicate in `admissibility.rate`
    (`admissibility.py:80-89`) and `profile_inputs.population` (`profile_inputs.py:15-21`).
  - `round_state._stage_discover` uses a different predicate (`or "routine"`). This is F3, fixed in P0.
- A source's identity in downstream ledgers is `str(candidate.get("source_id") or candidate_key)`
  (see `profile_inputs.population`). Claims, documents and chunks carry `source_id`.
- `synthesize.verdicts(store, project=, round_name=, manifest_only=)` returns `{"rows": [...],
  "adjudicated", "stale", "awaiting_adjudication", "no_controlled_error_rate_across"}`. Each row has
  `profile`, `verdict`, `stale`, `stored_profile_stale` and `unavailable`. It is correctly scoped. **Use
  it for everything about profiles and verdicts.**
- `admissibility.admit(project, store, round_name=, manifest_only=)` returns the floor result with
  `found`, `obtained`, `confirmed`, `rate`, `basis`, `floor`, `by_class` (each bucket has `found`,
  `obtained`, `confirmed`, `awaiting_normalize`, `rate`, `basis`, `floor`, `meets_floor`), `blocking`,
  `final`, `status`, `failures_by_class`, `failures_by_host`, `not_a_document` and
  `orphan_acquisitions`. **Use it, and do not change it.** It has two known project-wide reads
  (`confirmations`, `ledger_repairs`, F1). Leave them alone and disclose them in the UI (§4.6).
- `admissibility.collapse(store)` gives one acquisition row per `candidate_key`.
- `chunk_sets.current(store)` gives active chunks keyed by `chunk_id`, and may raise `ValueError` on an
  inconsistent chunk set. `claim_records.current(store)` returns `(claims_by_claim_id,
  rejections_by_claim_id)`. `review.current(store)` returns reviews keyed by `claim_id`.
- `config.load_project(path)` returns a `Project` dataclass. `config.check_registry_drift(project,
  store, record=False)` raises `config.RegistryDrift` without writing. `config.discover_projects(dir)`
  lists project directories.
- Project input files are `topics.yaml`, `questions.yaml`, `sources.yaml` and optionally `manifest.tsv`.
  `manifest.tsv` may be a symlink; read its resolved bytes.
- `populations.jsonl` holds one row per round with `policy_sha256` (`population.py:64-83`).
- `cli.BACKENDS` lists the backend names. `claimstone/runners/__init__.py` has `available()`.
  `claimstone/grobid.py` has the pinned `IMAGE`.
- `tools/check_instrument_versions.py` requires every `*_VERSION` constant listed in its `INSTRUMENTS`
  tuple to be mentioned in `docs/DESIGN_DECISIONS.md` as `<phrase> <value>` (read the script to confirm
  the exact pattern before writing D82).

---

## 2. P0: canonical scope, and honest errors in `round_state`

### 2.1 New file `claimstone/scope.py`

```python
"""One selector, one predicate: which rows belong to a round.

Every reader that shows a figure "for a round" must use these functions, so a portal page and
`report` can never count two different populations under one name (review F1, F3).
"""
SCOPE_VERSION = 1

@dataclass(frozen=True)
class Selector:
    round: str | None        # None = the whole store
    manifest_only: bool = False

    @property
    def whole_store(self) -> bool:
        return self.round is None and not self.manifest_only

    def as_dict(self) -> dict[str, Any]: ...   # {"round": ..., "manifest_only": ...}

def candidate_in_scope(row: Mapping[str, Any], selector: Selector) -> bool
def candidates(store: Store, selector: Selector) -> dict[str, dict[str, Any]]
    # latest_by("candidates.jsonl", "candidate_key") filtered by candidate_in_scope
def source_ids(store: Store, selector: Selector) -> set[str]
    # {str(row.get("source_id") or key) for key, row in candidates(...).items()}
def row_in_scope(ledger: str, row: Mapping[str, Any], *, selector: Selector,
                 keys: set[str], sources: set[str], claim_sources: Mapping[str, str]) -> bool
```

Rules for `row_in_scope`, which `activity` and last-write use:

| ledger | in scope when |
|---|---|
| `candidates.jsonl`, `acquisitions.jsonl` | `row["candidate_key"] in keys` |
| `documents.jsonl`, `chunks.jsonl`, `claims.jsonl`, `rejections.jsonl` | `str(row.get("source_id")) in sources` |
| `reviews.jsonl` | `claim_sources.get(str(row.get("claim_id"))) in sources` |
| `profiles.jsonl`, `adjudications.jsonl` | `row.get("round") == selector.round and bool(row.get("manifest_only")) == selector.manifest_only` |
| anything else | `False` |

When `selector.whole_store` is true, `row_in_scope` returns True for every row of those nine ledgers.

**Change `profile_inputs.population`** so that its body is `return scope.source_ids(store,
Selector(round_name, manifest_only))`. This must be a pure refactor, and a test (2.4, T6) proves it.

### 2.2 Changes to `claimstone/round_state.py`

1. **F3:** in `_stage_discover`, replace `str(row.get("round") or "routine") == round_name` with
   `scope.candidate_in_scope(row, selector)`.
2. **F1:** build `selector = Selector(round_name, manifest_only)` in `state()`. When
   `selector.whole_store` is false:
   - Filter `claims` and `rejections` (from `claim_records.current`) to rows whose `source_id` is in
     `scope.source_ids`.
   - Filter `reviews` to `claim_id`s of the filtered claims.
   - Filter `chunk_count` to chunks whose `source_id` is in scope.
   - In `_stage_normalize`, count `documents` and `acquired` only for scoped sources and keys.
   - `_question_spine` must receive the filtered claims as a parameter instead of reading
     `claim_records.current` itself.
   - `rejections_by_reason` uses the filtered rejections.

   When `selector.whole_store` is true, behavior must be byte-identical to today. The existing tests
   prove this.
3. **`_last_write`**: add a `selector`-aware variant. For a non-whole-store selector, return the maximum
   row timestamp (keys `_ROW_TIMES`) over rows where `row_in_scope` is true, or `None` if there is none.
   **Never** fall back to file mtime for a scoped selector. Whole store keeps today's mtime behavior.
4. **`activity(store, limit, selector=None)`**: when a non-whole-store selector is given, keep only rows
   where `row_in_scope` is true. Rows without a timestamp key are excluded from the scoped activity
   (they have no trustworthy time). The default `selector=None` keeps today's behavior.
5. **F2, errors are not zeros:**
   - Add `errors: tuple[str, ...] = ()` as the **last** field of `RoundState`.
   - Remove `except Exception` in `_stage_acquire`, `_stage_normalize` and `_profiles_for_spine`.
     Replace each with:
     - `except LedgerCorrupt as exc:` → append `f"LEDGER_CORRUPT: {exc}"` to errors and set the
       affected stage's `inputs`, `outputs` and `rejected` to `None`, with `detail="ledger damaged:
       figures withheld"`.
     - `except ValueError as exc` **only** around `chunk_sets.current` → `f"CHUNK_SET_INVALID: {exc}"`,
       same treatment for the normalize and extract stages.
   - In `state()`, the `try` around `synthesize.verdicts` must catch only `synthesize.NotAdmissible`,
     `config.RegistryDrift` (a subclass of `config.ConfigError`) and `LedgerCorrupt`. The first
     two set `unavailable` as today. `LedgerCorrupt` sets `unavailable` **and** appends to errors. Any
     other exception propagates.
   - Thread errors through with a small mutable list passed into the helpers, or return tuples. Keep it
     simple.
6. `cheap_state` is unchanged.

### 2.3 Changes to `claimstone/dashboard.py` (P0 only)

- If `state.errors` is non-empty, render a section at the top of `<main>` titled "ledger integrity". It
  shows each error escaped, in a red chip, and the sentence: "Figures that depend on a damaged ledger are
  withheld, not zero."
- Pass the selector into `round_state.activity(...)` when the server has a round or `manifest_only`.
- Wrap the body of `do_GET` so that an unexpected exception returns HTTP 500 with `text/plain` body
  `500: <ExceptionClassName>` (no traceback, no message). Never return a page with zeros.

### 2.4 Tests: new file `tests/test_scope.py`, plus additions to `tests/test_round_state.py`

Build fixtures with `Store("fixture", base=tmp_path)` and the example project
`projects/example-news-and-returns`, as the existing tests do. Use two rounds, `"r1"` and `"r2"`, with
distinct candidate keys and source ids (`S01`/`S02` in r1, `S03` in r2). For r2, write a document,
chunks, two claims, one rejection and one review. For r1, write one claim.

| id | name | asserts |
|---|---|---|
| T1 | `test_candidate_predicate_matches_admissibility` | for rows with and without `round`/`source_id`, `candidate_in_scope` equals the inline predicate from `admissibility.rate` |
| T2 | `test_round_state_claims_do_not_leak_between_rounds` | `state(..., round_name="r1")`: extract outputs, `rejections_by_reason` and every `QuestionRow.claims` count only r1 rows; same check for r2 |
| T3 | `test_round_state_review_and_chunks_scoped` | review progress denominator and extract inputs count only the selected round |
| T4 | `test_scoped_activity_and_last_write_exclude_other_round` | `activity(store, 50, Selector("r1"))` contains no row with `S03` or r2's candidate key; scoped `last_write` is None for a stage with no r1 rows even though r2 wrote that ledger |
| T5 | `test_whole_store_state_unchanged` | with `round_name=None`, `state(...).as_dict()` equals the result computed by a copy of the pre-change logic. Simplest approach: assert the same concrete numbers the fixture implies |
| T6 | `test_profile_population_refactor_is_identical` | `profile_inputs.population` returns the same set as before for whole store, r1, r2 and manifest_only |
| T7 | `test_corrupt_acquisitions_is_an_error_not_zero` | write a valid row, then a line `{bad`, then a valid row into `acquisitions.jsonl`. `state()` has an `errors` entry starting with `LEDGER_CORRUPT`, and the acquire and normalize stages have `outputs is None` and `inputs is None` (not 0) |
| T8 | `test_round_less_candidate_is_not_routine` | a candidate without `round` is not in scope for `Selector("routine")` |
| T9 | `test_dashboard_renders_integrity_section` | `render_page` with a state carrying errors contains "ledger integrity" and the escaped error text |

---

## 3. P1: flows (`claimstone/flows.py`, CLI `flow`)

### 3.1 Concepts

- A **flow** binds `(project, selector)` to digests of the protocol at binding time. It is identified by
  `flow_id`, the sha256 hex of the canonical JSON of its binding (defined below), so creating the same
  binding twice yields the same id (idempotent).
- A flow never supplies values to a computation. It is compared against the live project to produce a
  **binding state**.
- A round that has candidates but no flow is shown as **legacy: protocol not verified**.

### 3.2 Protocol digest

```python
FLOW_VERSION = 1

def input_file_digests(project_root: Path) -> dict[str, str | None]
    # for name in ("topics.yaml", "questions.yaml", "sources.yaml", "manifest.tsv"):
    #   sha256 of Path.read_bytes() (follows symlinks), or None if the file is absent

def protocol_digest(project: Project) -> str
    # sha256 of canonical JSON of the semantic protocol, built from the loaded Project:
    # {
    #   "classes": [dataclasses.asdict(c) for c in project.classes],
    #   "acquisition_floor": project.acquisition_floor,
    #   "floor_version": project.floor_version, "floor_set_at": project.floor_set_at,
    #   "excluded_hosts": sorted(project.excluded_hosts),
    #   "topics": [dataclasses.asdict(t) for t in project.topics],
    #   "registry_version": project.registry_version, "registry_sha256": project.registry_sha256,
    #   "manifest": [dataclasses.asdict(m) for m in project.manifest],
    #   "gate_thresholds": project.gate_thresholds, "gate_policy": project.gate_policy,
    #   "normalize_thresholds": project.normalize_thresholds,
    #   "extraction": project.extraction, "citation_channel": project.citation_channel,
    #   "population": project.population,
    # }
    # canonical JSON = json.dumps(obj, sort_keys=True, ensure_ascii=False,
    #                             separators=(",", ":"), default=str)
```

The semantic digest decides drift. File digests are recorded for information only, because a whitespace
edit must not read as drift. This is the reasoning in `config.registry_digest`'s docstring. Before
using `asdict`, check that each element is a dataclass. If one is not, convert it explicitly and say so in
D82.

### 3.3 Ledger `store/<project>/flows.jsonl` (append-only)

Event `created`:

```json
{
  "event": "created",
  "flow_version": 1,
  "flow_id": "<64 hex>",
  "binding": {
    "project": "pmc-screen-time",
    "selector": {"round": "pmc-oa-v1", "manifest_only": false},
    "registry_version": 3,
    "registry_sha256": "<hex>",
    "protocol_sha256": "<hex>",
    "population_sha256": "<hex or null>",
    "derived_from": null,
    "relation": null
  },
  "input_files": {"topics.yaml": "<hex>", "questions.yaml": "<hex>", "sources.yaml": "<hex>", "manifest.tsv": null},
  "bound_after_data": true,
  "candidates_at_binding": 40,
  "title": "PMC screen time, OA deposits",
  "created_at": "2026-10-06T12:00:00+00:00",
  "created_by": "<os user from getpass.getuser()>",
  "code_revision": "<git rev-parse HEAD or null>",
  "code_dirty": true
}
```

Field rules:

- `flow_id = sha256(canonical_json(binding))`. **Only `binding` is hashed**, so the title, the time and
  the creator never change identity.
- `population_sha256` is `store.latest_by("populations.jsonl", "round").get(round)["policy_sha256"]` if
  present, else null. For `round: null`, it is null.
- `relation` is one of `null`, `"supersedes"` or `"derived_from"`. If `derived_from` is set, `relation`
  must be non-null, and `derived_from` must be an existing flow id in the same ledger.
- `bound_after_data` is true when the selector already has at least one candidate at binding time.
  `candidates_at_binding` is that count. The UI must then say: "bound after data existed: rows written
  before binding are not verified against this protocol."
- `code_revision` and `code_dirty` come from `git rev-parse HEAD` and `git status --porcelain` (non-empty
  means dirty), run with `subprocess.run(..., timeout=5, capture_output=True)`. On any failure, record
  null, never guess.

Event `title`: `{"event": "title", "flow_id": "...", "title": "...", "at": "...", "by": "..."}`. Titles are
display metadata only.

Writes must take an exclusive `fcntl.flock` on `store/<project>/.flows.lock`, reread the ledger under the
lock and only then append. Use the pattern from `source_selection._writer_lock`.

### 3.4 Binding state

```python
def binding_state(project: Project, store: Store, flow: dict) -> dict
# returns {"state": one of
#   "CURRENT"            — registry_sha256, protocol_sha256, population_sha256 all equal live values
#   "REGISTRY_DRIFTED"   — registry_sha256 or registry_version differs (checked first)
#   "PROTOCOL_DRIFTED"   — protocol_sha256 differs
#   "POPULATION_DRIFTED" — population_sha256 differs
#  , "differences": [names of differing components], "bound_after_data": bool}
```

### 3.5 Functions

```python
def flows(store) -> dict[str, dict]           # flow_id -> created row, latest title merged as "title"
def create(project, store, *, selector, title, derived_from=None, relation=None) -> tuple[dict, bool]
    # returns (row, created_now). Calls check_registry_drift(project, store, record=False) first and
    # lets RegistryDrift propagate. Idempotent: an existing identical binding returns (existing, False).
def legacy_selectors(store, flow_rows) -> list[Selector]
    # every distinct candidates.jsonl `round` value (string) with no flow whose selector.round equals
    # it, as Selector(round, False), sorted
def set_title(store, flow_id, title, by) -> dict
```

### 3.6 CLI (`claimstone/cli.py`)

Add a `flow` subcommand with sub-subcommands. Follow existing argparse style, and use `_checked_store`
except where noted.

| command | behavior | exit |
|---|---|---|
| `claimstone flow create PROJECT --title T [--round R] [--manifest] [--derived-from ID --relation supersedes\|derived_from]` | prints `created <flow_id>` or `exists <flow_id>`; prints the bound-after-data warning when applicable | 0; 2 on bad args or unknown `--derived-from` |
| `claimstone flow list PROJECT [--json]` | one line per flow: id[:12], selector, title, binding state; then the legacy selectors | 0 |
| `claimstone flow check PROJECT FLOW_ID` | prints the state and its differences | 0 if CURRENT, 4 otherwise, 2 if unknown id |
| `claimstone flow title PROJECT FLOW_ID --title T` | appends a title event | 0 |

`flow list` and `flow check` must **not** record anything. Open the store without `_checked_store`
recording: use `Store(...)` plus `check_registry_drift(..., record=False)`, and report `RegistryDrift` as
a state, not a crash.

### 3.7 Tests: `tests/test_flows.py`

| id | asserts |
|---|---|
| F-T1 | create twice gives the same `flow_id`, one ledger row, and `created_now` is False the second time |
| F-T2 | a title change does not change `flow_id` |
| F-T3 | editing whitespace or comments in a copied `questions.yaml` keeps CURRENT; changing a question text under the same version gives `REGISTRY_DRIFTED`; changing `acquisition_floor` gives `PROTOCOL_DRIFTED` (use a copied project in `tmp_path`) |
| F-T4 | `bound_after_data` is true when candidates exist for the round, and false otherwise |
| F-T5 | `legacy_selectors` lists r2 when only r1 has a flow |
| F-T6 | `--derived-from` with an unknown id exits 2 and writes nothing |
| F-T7 | `flow check` exit codes 0 / 4 / 2 |
| F-T8 | `flow list` and `flow check` leave every file under the store byte-identical (hash before/after) |

---

## 4. P2: read-only portal (`claimstone/portal_state.py`, `claimstone/portal.py`)

### 4.1 Architecture

- `portal_state.py` holds pure functions only: ledgers in, plain dicts and dataclasses out. No HTTP, no
  HTML. This makes every view testable without sockets.
- `portal.py` holds transport and rendering: `http.server.ThreadingHTTPServer`, a handler class with GET
  routing, HTML rendering functions and JSON responses. Reuse `dashboard._STYLE`, `_esc`, `_chip` and
  `_frac` by importing them, not by copying.
- One server serves **all** projects under `--projects-dir` (default `projects`) with stores under
  `--store` (default `store`).
- **Every request** calls `config.load_project(path)` again (F9) and
  `check_registry_drift(project, store, record=False)`. `ConfigError` and `RegistryDrift` are rendered as
  named states on the page, never as a crash.

### 4.2 CLI

`claimstone portal [--projects-dir projects] [--store store] [--host 127.0.0.1] [--port 8788]`

- Uses `dashboard.host_warning` for non-loopback binds, exactly like `_serve`.
- Prints `claimstone portal — http://HOST:PORT/  (read-only; Ctrl-C to stop)`.

### 4.3 Request security (all routes)

1. **Host header allowlist:** accept only `127.0.0.1:PORT`, `localhost:PORT`, `[::1]:PORT`, and
   `HOST:PORT` when `--host` was given explicitly. Otherwise return 421 with a plain body. This is the
   DNS-rebinding defense.
2. If the request carries an `Origin` header, it must equal `http://` + an allowed Host. Otherwise
   return 403.
3. Only GET. Every other verb answers 405, using the same `__getattr__` trick as `dashboard._Handler`.
   HEAD answers 405 without a body.
4. Response headers on every response:
   - `Cache-Control: no-store`
   - `X-Content-Type-Options: nosniff`
   - `Referrer-Policy: no-referrer`
   - `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline';
     connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`
5. Path parameters are **looked up, never used as paths**:
   - `project` must be the name of a directory returned by `discover_projects`.
   - `flow_id` must match `^[0-9a-f]{64}$` and exist in that project's `flows.jsonl`.
   - `question` must be an id in the loaded registry.
   - `claim_id` and `candidate_key` must exist as keys in the respective current maps.
   - Anything else returns 404 with a plain body. Use `urllib.parse.unquote` once on segments.
6. Never serve raw bytes from `store/raw`. Show `stored_path` as text only.
7. Unexpected exceptions return 500 with `500: <ExceptionClassName>`.

### 4.4 Routes

All HTML pages share a header showing:
- breadcrumb
- "read-only derived view"
- code revision and dirty flag, computed once at server start, labelled "at server start"

| route | content (functions in `portal_state`) |
|---|---|
| `GET /` | **Index** (`index(projects_dir, store_dir)`): one card per project. Each card shows config status (OK / `ConfigError` text), registry version and short sha, registry drift state, flows (title, selector, binding state, floor status from `admit`, verdict counts from `verdicts`), legacy selectors labelled "legacy: protocol not verified", and the open inbox count by category |
| `GET /inbox` | **Cross-project inbox**: the cards from §4.5 for every flow and legacy selector, grouped by project then category |
| `GET /admin` | **Admin (read-only)**: see §4.8 |
| `GET /p/<project>/` | **Project page**: integrity panel (§4.7), flows table, legacy selectors, project-wide activity (`round_state.activity(store, 50)`) |
| `GET /p/<project>/f/<flow_id>/` | **Flow overview** (`flow_overview`): binding state banner; stage strip from `round_state.state(..., round_name, manifest_only)` (now scoped); floor and deficit panel (§4.6); question matrix (§4.9); this flow's inbox; scoped activity |
| `GET /p/<project>/legacy/<round>/` | same page for a legacy selector, banner "legacy: protocol not verified", no binding comparison |
| `GET /p/<project>/f/<flow_id>/q/<qid>` | **Question detail** (`question_detail`): profile fields (state, provisional, blocking, coverage, `direction_count` labelled "a count, not a strength", `gate_rejected`, `reviewed_not_usable`, `awaiting_review`, linkage, extraction completion, `profile_sha256`, `stored_profile_stale`, `unavailable`); results table with a link per `claim_id` to lineage; recorded verdict and staleness |
| `GET /p/<project>/f/<flow_id>/claim/<claim_id>` | **Lineage** (`lineage`, §4.10) |
| `GET /p/<project>/f/<flow_id>/source/<candidate_key>` | **Source dossier** (`source_dossier`, §4.11) |
| legacy equivalents | `/p/<project>/legacy/<round>/q/<qid>`, `/claim/<id>`, `/source/<key>` |
| `GET /api/index`, `/api/p/<project>/f/<flow_id>`, `/api/p/<project>/f/<flow_id>/q/<qid>`, `/api/inbox` | the same dicts as JSON (`json.dumps(..., default=str, ensure_ascii=False)`) |
| `GET /api/poll?project=<p>` | `round_state.cheap_state(store)` for that project. The page polls every 3 s and reloads when the ledgers signature changes, as the dashboard does |

### 4.5 Inbox cards (`inbox_cards(project, store, selector, flow_row | None) -> list[Card]`)

```python
@dataclass(frozen=True)
class Card:
    category: str        # one of CATEGORY_ORDER
    scope: str           # "flow <id12>" or "legacy <round>" or "project"
    subject: str         # candidate_key, question id, ledger name, ...
    cause: str           # one sentence naming the rows
    command: str | None  # exact CLI text, or None
    note: str            # constraint the operator must know
```

`CATEGORY_ORDER = ("INTEGRITY", "PROTOCOL", "ACQUISITION", "CLASSIFICATION", "NORMALIZE", "EXTRACT",
"REVIEW", "ADJUDICATION", "ADVISORY")`. Cards sort by `(CATEGORY_ORDER.index(category), subject)`. That
is the **only** ordering rule.

| category | source of truth | cause / command / note |
|---|---|---|
| INTEGRITY | `RoundState.errors`, `store.torn_tail`, `ledger_repairs.jsonl` rows, `admit()["orphan_acquisitions"]` | command `None` for corruption ("inspect by hand; never repair interior damage"); `claimstone report <project path>` for orphans |
| PROTOCOL | `binding_state` not CURRENT; `RegistryDrift` | note: "a protocol change is a new flow: `claimstone flow create ... --derived-from <id> --relation supersedes`" |
| ACQUISITION | one card per failed candidate in scope: `admissibility.collapse` row with `acquired` false, or candidate with no row (NOT_ATTEMPTED) | if failure class is transient or NOT_ATTEMPTED: `claimstone acquire <path> --round <r>` (+ `--manifest` if selected); if terminal: `claimstone acquire <path> --round <r> --retry-class <CLASS> --campaign <campaign-name>`, note "terminal: retry only in a named campaign the operator authorizes (AGENTS.md)". For `PAYWALL_403`, cause text is exactly `HTTP 403 — access refused (stored as PAYWALL_403; not proof of a paywall or of a purchasable copy)` |
| CLASSIFICATION | candidates in scope without `source_class` | `claimstone discover <path> --reclassify` (verify the flag exists in `build_parser`; if it does not, `command=None`) |
| NORMALIZE | `admit()["awaiting_normalize"] > 0`; `not_a_document` entries | `./claimstone.sh normalize <path>`, note "runs in the container; the image is rebuilt first (D42)" / `claimstone gate-audit <path> --show-rejected` |
| EXTRACT | each live profile's `extraction` counts `unanswered`, `unharvested`, `unregated` > 0 (from `verdicts`) | `command=None`, cause names the counts per kind, note "see docs/GUIDE.md, stage 4; extraction is not round-scoped and builds work for the whole project (review F7)" |
| REVIEW | `awaiting_review` > 0 in a live profile | `command=None`, same note style |
| ADJUDICATION | rows from `verdicts` that are not provisional, have no `unavailable`, are not NOT_APPLICABLE, and have no verdict or a stale one | command: `claimstone adjudicate <path> --question <Q> --round <r> --profile-sha256 <full hash> --verdict <ONE_OF_FIVE> --rationale-file <file> --by <name>` (+ `--manifest-only` if selected). Careful: `acquire`, `report` and `gate-audit` spell this flag
`--manifest`, while `synthesize`, `verdicts` and `adjudicate` spell it `--manifest-only`. Verify every
flag against `build_parser`. Note: "a person reads the profile and signs; an agent does not". Leave `<ONE_OF_FIVE>` and the others as literal placeholders |
| ADVISORY | `source_screening.jsonl` / `source_identity.jsonl` latest rows whose `candidate_key` is in scope: counts by role and status | `command=None`, note "AI_PROVISIONAL: advisory only; changes no admission, denominator or reference (D79–D81)" |

**Ordering-independence rule (F13):** the function that builds ACQUISITION, CLASSIFICATION and NORMALIZE
cards takes **only** `(project, admitted, scoped_candidates, collapsed_acquisitions, selector)` as
arguments. It must not receive the store, claims, reviews or profiles. Test I-T3 enforces this.

Every `command` string must start with a subcommand that exists in `cli.build_parser()`. The exception is
`./claimstone.sh normalize`, for which the check is `normalize`. Test I-T4 enforces this.

### 4.6 Floor and deficit panel (`floor_panel(admitted) -> dict`)

From `admit()` only:

- Overall: `basis` count / `found`, `rate` (2 decimals), `floor`, `floor_version`, `floor_set_at`,
  `status`, `final`, `blocking`.
- Per class (from `by_class`): `found`, the basis count, `awaiting_normalize`, `floor`, `meets_floor`,
  and **`needed = max(0, ceil(floor * found - 1e-9) - basis_count)`**.
- Sentence per class with `needed > 0`: `"{class}: {needed} more of the {found - basis_count} not yet
  confirmed would be needed to reach its floor. This says nothing about which are obtainable, and
  selecting them by expected result is not allowed."`
- Fixed disclosure under the panel: "Admission currently reads document confirmations and ledger repairs
  across the whole project (review F1). A round with no normalized documents may show the confirmed
  basis because another round has documents."
- No "simulate" control and no hypothetical rates.

### 4.7 Integrity panel (`integrity(project_path, store) -> dict`)

| check | how |
|---|---|
| config | `load_project` OK or the `ConfigError` text |
| registry drift | `check_registry_drift(record=False)` OK or the `RegistryDrift` text |
| ledgers | for each `*.jsonl` directly under `store/<project>/`: rows read, torn tail yes/no, or `LedgerCorrupt` text. Read with `Store.read`. **Never call `repair`** |
| ledger repairs | count of `ledger_repairs.jsonl` rows |
| orphans | `admit(project, store)["orphan_acquisitions"]` length (whole store) |
| instruments | call a new function `check() -> list[str]` in `tools/check_instrument_versions.py` (refactor `main` to call it; `main` behavior and exit codes unchanged), imported with `importlib.util.spec_from_file_location`. Empty list means OK |
| code | `code_revision`, `code_dirty` at server start; `grobid.IMAGE` |

### 4.8 Admin page (`admin_state(root) -> dict`)

- Credentials. For `CLAIMSTONE_CONTACT_EMAIL`, `OLLAMA_API_KEY` and `OPENALEX_API_KEY`, show `set` or
  `not set`. A name is `set` if `os.environ` has a non-empty value, **or** if `.env` in the repository
  root has a line `NAME=<non-empty>`. Parse `.env` by splitting on the first `=`. Never store, return or
  render the value. The JSON response contains booleans only.
- Backends: `cli.BACKENDS` and `sorted(runners.available())`. Label: "configured names; not health-checked.
  A health probe would be a request and is never a side effect of GET."
- Instruments: the module constants listed in `tools/check_instrument_versions.py` `INSTRUMENTS` (read the
  values with its `declared()` helper), `scope_version`, `flow_version`, `export_version`.
- A fixed note: "Key rotation is done by editing `.env` outside the portal. Containers read `.env` when
  `./claimstone.sh` starts them."

### 4.9 Question matrix (`question_matrix(project, store, selector) -> list[dict]`)

One row per registry question, in registry order. Columns:

- id, kind, text
- per-class claim counts (scoped, from `RoundState.questions[i].claims_by_class`) shown **before** the
  total (invariant 6)
- coverage `sources / examined`
- direction count, labelled "count"
- gate rejected total
- awaiting review
- profile state, `provisional`, `blocking`
- verdict or stale

Vocabulary rules:

- `kind: operational` shows `LITERATURE_VERDICT_NOT_APPLICABLE` and an empty verdict cell. Never a sixth
  verdict.
- `NO_VERIFIED_CLAIM` is shown dashed with the dashboard's note text. It is never shown as
  `UNANSWERED_IN_LITERATURE` or `NEVER_ASKED`.
- When `unavailable` is non-empty (inadmissible), show the stored profiles as **historical** with that
  text, as `cli._verdicts` does.

### 4.10 Lineage (`lineage(project, store, selector, claim_id) -> dict`)

Build each step from current maps:

1. `claim`: the row from `claim_records.current(store)[0]`. It must be in scope by `source_id`, else 404.
   Show `claim`, `stance`, `question_id`, `evidence_quote`, `claim_gate_version`, `gate_revision`,
   `backend`, `model`, `harness_version`, `call_id`, `source_class`.
2. `review`: `review.current(store).get(claim_id)`. Show verdict, reason, reviewer, `review_version`, or
   "awaiting review".
3. `chunk`: `chunk_sets.current(store)[claim["chunk_id"]]`. Show `chunk_id`, `generation_sha256`,
   `text_sha256` and the text, with the quote highlighted by escaping first and then wrapping the
   **first** occurrence in `<mark>`. Recheck in the view: `quote_found = evidence_quote in chunk text`.
   If false, render a red banner "invariant 1 check fails on current data". Do not hide the claim.
4. `document`: `latest_by("documents.jsonl","source_id")[source_id]`. Show `fulltext_confirmed`,
   `html_parser_version`, `jats_parser_version`, `generation_sha256`, chunks/references/body_chars, and
   `grobid.IMAGE` when the document is a PDF.
5. `acquisition`: find `candidate_key` where `str(row.get("source_id") or key) == source_id` among
   scoped candidates, then `admissibility.collapse(store)[candidate_key]`. Show `sha256`, `stored_path`,
   `url`, `provenance`, `licence`, `oa_status`, `campaign`, `fetched_at`, and the `attempts` table
   (url, `http_status`, `failure_class` displayed per F19, `fetch_version`).
6. `candidate`: `source_class`, round, channel, title fields present in the row.

A missing step renders "not found in current ledgers" for that step, and the remaining steps still
render.

### 4.11 Source dossier (`source_dossier(project, store, selector, candidate_key) -> dict`)

- The candidate row.
- **All** acquisition rows for that key, in ledger order. This is not the collapsed view. Label the
  collapsed one "counted".
- The document row.
- The active chunk count.
- Advisory screening and identity rows for that key across scopes, each labelled with
  `assessment_status` and the D79–D81 advisory note.
- Claim count by question.

### 4.12 Live updates

Copy the dashboard's polling approach: poll `/api/poll?project=<p>` every 3 s, and reload when the
ledgers signature changed and the page is visible. Do not add SSE or WebSockets. The index page polls
nothing.

### 4.13 Tests: `tests/test_portal_state.py`, `tests/test_portal.py`

Pure-function tests (no sockets):

| id | asserts |
|---|---|
| P-T1 | `index` on a tmp projects dir (copy of the example project plus a store with r1 flow and r2 legacy) lists the flow and the legacy selector, with "legacy: protocol not verified" |
| P-T2 | flow overview for r1 contains no r2 source id anywhere in its JSON (`json.dumps(...)` substring check) |
| P-T3 | `PROTOCOL_DRIFTED` banner after changing the floor in the copied project, and the floor panel shows the **live** floor |
| I-T1 | the PAYWALL_403 card cause text equals the exact sentence in §4.5 and the word "paywall" appears only inside "not proof of a paywall" |
| I-T2 | categories sort by `CATEGORY_ORDER` and then subject |
| I-T3 | `inspect.signature` of the acquisition-card builder has exactly the parameters in §4.5; and building cards with claims whose stances are all flipped yields identical ACQUISITION cards |
| I-T4 | every non-None `command` parses with `cli.build_parser()` after replacing placeholders with dummy values (`./claimstone.sh` stripped) |
| I-T5 | ADJUDICATION card contains the full profile hash and literal `<ONE_OF_FIVE>`; no card contains a concrete verdict word as the `--verdict` value |
| L-T1 | lineage shows all six steps for a complete fixture; a fixture with a quote not in the chunk shows `quote_found` False |
| L-T2 | lineage for a claim of r2 requested under the r1 selector raises the not-found path |
| A-T1 | `admin_state` with `OLLAMA_API_KEY=secret-value-123` in env: `json.dumps(result)` does not contain `secret-value-123`, `secret` or `15` (the length) |
| G-T1 | `integrity` reports `LedgerCorrupt` for a corrupt ledger and does not modify the file (hash before/after) |
| F-T9 | floor panel `needed` arithmetic: found 12, confirmed 2, floor 0.8 → needed 8; found 5, floor 0.8, confirmed 4 → 0 |

Handler tests (`tests/test_portal.py`, create the server with port 0 and follow the dashboard tests'
socket handling):

| id | asserts |
|---|---|
| H-T1 | POST, PUT, DELETE, PATCH, OPTIONS and HEAD give 405; HEAD has an empty body |
| H-T2 | `Host: evil.example:PORT` gives 421; `Origin: http://evil.example` gives 403 |
| H-T3 | CSP, nosniff and no-store headers present on HTML and JSON |
| H-T4 | `/p/../etc/` and `/p/unknown/` give 404; a flow id of 63 chars gives 404 |
| H-T5 | a question text containing `<script>alert(1)</script>` (copied project) renders escaped |
| H-T6 | after serving every route once, all files under the tmp store are byte-identical |

---

## 5. P2b: export (`claimstone/export.py`, CLI `export`, `export-verify`)

### 5.1 Snapshot capture

1. Take `fcntl.flock` on `store/<project>/.flows.lock`. This is the only lock that exists today; it
   prevents a concurrent `flow create` and **does not** stop other writers. That is why step 2 cuts at a
   newline and the verifier checks prefixes.
2. For every file matching `store/<project>/*.jsonl` and `store/<project>/calls/**/*.jsonl` (not
   `audits/`, not `exports/`), read bytes, cut at the last `\n` (exclude a torn tail and record it), and
   record `{path, bytes, rows, sha256}` of the prefix.
3. Release the lock.
4. Write the prefixes into a temporary directory laid out as a store
   (`tempfile.TemporaryDirectory()/<project>/...`).
5. Compute every output from `Store(project, base=tmpdir)`, never from the live store.

### 5.2 Outputs (directory `store/<project>/exports/<export_id>/`)

| file | content |
|---|---|
| `manifest.json` | `export_version: 1`, `flow` (the created row), `binding_state`, `selector`, `prefixes` (list from 5.1, sorted by path), `torn_tails` (list), `code_revision`, `code_dirty`, instrument versions (as on the admin page), `created_at`, `created_by` |
| `profiles.json` | `synthesize.verdicts(...)` for the selector, `json.dumps(sort_keys=True, indent=1, default=str)` |
| `floor.json` | `admissibility.admit(...)` for the selector |
| `questions.csv` | the question matrix rows |
| `claims.csv` | scoped current claims: `claim_id`, `question_id`, `source_id`, `source_class`, `stance`, `evidence_quote`, `chunk_id`, `generation_sha256`, `document parser versions`, `acquisition sha256`, `licence`, `review verdict`, `quote_found` |
| `rejections.csv` | scoped current rejections: `claim_id`, `source_id`, `failure`, `detail` |
| `acquisition.csv` | one row per scoped candidate: key, `source_id`, class, counted acquired, `failure_class` (raw stored code) and display text, provenance, licence |
| `report.md` | human summary: binding state, floor panel text, question matrix as a table, the fixed disclosures (no verdict unless signed, `NO_VERIFIED_CLAIM` ≠ `NEVER_ASKED`, F1 disclosure, "no controlled family-wise error rate across N questions") |

Rules:

- CSV: `csv` module, `lineterminator="\n"`, rows sorted by their first column, then by the second.
  UTF-8.
- No raw bytes, no PDFs, no receipts, nothing from `audits/`.
- `export_id = sha256(canonical_json({"flow_id", "selector", "prefixes"}))`. If the directory already
  exists, print `exists <export_id>` and write nothing.
- `created_at` and `created_by` are excluded from the id and from verification.
- After writing, append `{"export_id", "flow_id", "path", "created_at"}` to
  `store/<project>/exports.jsonl` under the same lock.
- Exports are allowed only for flows. A legacy selector requires `flow create` first. An export of a
  non-CURRENT flow is allowed, and the state is written in manifest and report.

### 5.3 `claimstone export-verify DIR`

1. Load `manifest.json`.
2. For each prefix: the live file must exist, be at least `bytes` long, and its first `bytes` bytes must
   hash to `sha256`. Otherwise report `PREFIX_CHANGED <path>`. This detects rewritten history.
3. Rebuild the temp store from those prefixes, recompute every output file except `manifest.json`, and
   compare sha256 per file. Report `OUTPUT_DIFFERS <file>`.
4. Exit 0 when everything matches, 5 otherwise, and print one line per problem.

### 5.4 Tests: `tests/test_export.py`

| id | asserts |
|---|---|
| E-T1 | export then verify on an unchanged fixture gives exit 0 |
| E-T2 | append rows to `claims.jsonl` after export: verify still gives 0 (prefix unchanged), and a new export has a different `export_id` |
| E-T3 | rewrite an early byte in a ledger: verify reports `PREFIX_CHANGED` and exits 5 |
| E-T4 | a torn tail at export time is excluded from the prefix and listed in `torn_tails` |
| E-T5 | export twice without changes gives the same id and the second call writes nothing |
| E-T6 | no file in the export contains bytes read from `raw/` (write a sentinel string into a raw file and grep the export dir) |
| E-T7 | an r1 export contains no r2 `source_id` |

---

## 6. Instrument registration

Add to `INSTRUMENTS` in `tools/check_instrument_versions.py`:

```python
("claimstone/scope.py", "SCOPE_VERSION", "scope_version"),
("claimstone/flows.py", "FLOW_VERSION", "flow_version"),
("claimstone/export.py", "EXPORT_VERSION", "export_version"),
```

The D82 entry must mention `scope_version 1`, `flow_version 1` and `export_version 1`.

## 7. Documentation to add or update

1. `docs/contracts/flows.md`: every field of §3.3, the identity rule, the drift states and the lock.
2. `docs/contracts/exports.md`: §5 manifest fields, the id rule and the verify semantics.
3. `docs/contracts/requests.md`: correct "`fetch_version` currently 2" to 3 (F18). Doc fix only.
4. `docs/superpowers/specs/2026-10-06-research-portal-design.md`: add a line under Status:
   "Corrected by `2026-10-06-research-portal-review.md`; phases P0–P2b specified in
   `2026-10-06-research-portal-implementation-spec.md`."
5. `docs/HANDOFF.md`: one dated paragraph at the top of "Where the work stands" saying what was
   implemented, the test count **as printed by pytest**, and that no ledger, request or model call
   happened.
6. `docs/README.md` (the map): link the two new contracts and the portal command.

## 8. Order of work and checkpoints

1. P0: §2. Run the three commands. Commit: `fix: scope round state per selector and surface ledger damage`.
2. P1: §3 plus `contracts/flows.md`. Run the three commands. Commit: `feat: bind round selectors to
   protocol digests (flows)`.
3. P2: §4. Run the three commands. Then start `claimstone portal` locally on loopback and open `/`, one
   project page, one flow page (create a flow in a **tmp copy** of a store, never in the real store),
   `/inbox` and `/admin`. Commit: `feat: read-only research portal`.
4. P2b: §5 plus `contracts/exports.md`. Commit: `feat: verifiable flow export`.
5. D82, docs (§7, §9). Commit: `docs: record D82 and portal contracts`.

Before every commit, run `git status` and make sure nothing under `projects/` or `store/` is staged.

## 9. D82 entry: write it in `docs/DESIGN_DECISIONS.md`

Title: `## D82 — A read-only multi-flow portal over scoped reads (2026-10-06)`.

It must state, in this project's style (facts plus what measured them):

- Dashboard spec §13 ("no multi-project view") is superseded for the portal. §1 and §8 rule 7 (read-only,
  no button starts work) **still hold**. Any mutating route requires a later decision.
- The scope defects fixed (F1 list), with the test names that demonstrate them.
- That `admissibility` still reads confirmations and repairs project-wide, that this is disclosed in the
  UI and **not** changed, and that changing it is an `admission_version` decision.
- `scope_version 1`, `flow_version 1`, `export_version 1`.
- The measured page time for `/p/pmc-screen-time/legacy/pmc-oa-v1/` on this machine (time it with
  `curl -s -o /dev/null -w '%{time_total}'` against loopback). This is a read; it writes nothing.
- What is explicitly not built: intake, offers, purchase decisions, jobs, locking across stage writers,
  persistent host budget, URL guard, authenticated signing. Each is blocked by findings F5, F6, F7, F14,
  F15 and F16.

## 10. Out of scope (do not start; listed so nobody mistakes it for done)

These need the operator's decisions and a separate reviewed spec:

- **P3:** project-wide writer lock adopted by every stage writer (F5), persistent per-host failure budget
  derived from `requests.jsonl` (F6), non-global-address URL guard on every redirect hop (F15),
  round-scoped builders for normalize/extract/review (F7), and the contracts for `intake.jsonl`,
  `access_offers.jsonl` and `access_decisions.jsonl`. Also the **operator's declared policy** on whether
  operator-supplied copies count toward the floor (F14), and the blinded human-reference labelling
  ledger.
- **P4:** loopback session authentication, `operations.jsonl`, subprocess jobs with code-identity checks
  (F11), the signing workbench with `signer_auth` under a bumped `decision_contract_version` (F16), and a
  spending view.

## 11. Definition of done

- [ ] All tests in §2.4, §3.7, §4.13 and §5.4 exist and pass, and the full suite passes.
- [ ] `validate --all-projects` and `check_instrument_versions.py` exit 0.
- [ ] `claimstone portal` serves every route in §4.4 on loopback, and no route writes (H-T6).
- [ ] `export` / `export-verify` round-trip on a tmp copy of a store.
- [ ] D82, both contracts and the HANDOFF paragraph are written. The test count is copied from pytest's
      own output.
- [ ] `git diff --stat` shows no change under `projects/` or `store/`, and no change to the modules listed
      in §0.2 except `profile_inputs.population` (pure refactor) and the `check()` extraction in
      `tools/check_instrument_versions.py`.
