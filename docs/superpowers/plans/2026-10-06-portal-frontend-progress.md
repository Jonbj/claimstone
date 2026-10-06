# Portal frontend progress log

Working document for `docs/superpowers/specs/2026-10-06-portal-frontend-glm-prompt.md`
(spec: `docs/superpowers/specs/2026-10-06-portal-frontend-docker-design.md`).
One step per session; markers below are the authority for "what is next".

| step | marker |
|---|---|
| S1 shared transport base class out of `claimstone/portal.py` | DONE |
| S2 `claimstone/api.py` + tests A1–A7 | DONE |
| S3 schema, validator, fixtures | DONE |
| S4 scaffold `web/` | DONE |
| S5 routes and components | DONE (SvelteKit; superseded by R2–R4) |
| R1 server fields for the React design (`question_state_counts`, `source_tracker`) | DONE |
| R2 React scaffold replaces the SvelteKit scaffold | DONE |
| R3 pages, part 1 (index, project, inbox, admin) | DONE |
| R4 pages, part 2 (flow overview, question, lineage, dossier) + CSP preview check | DONE |
| S6 Dockerfile, compose services, `portal.sh` | TODO |
| S7 parity check, D83, docs, instrument registration | TODO |

## Baseline (2026-10-06, before any work)

```
$ .venv/bin/pytest -q
1191 passed, 7 skipped in 26.13s
$ .venv/bin/claimstone validate --all-projects
OK   example-news-and-returns: 16 topics, 20 questions (registry v2, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), registry 85e5fcc44ddc
OK   pilot-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 28 manifest rows, registry 82007de2b569
OK   pmc-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 40 manifest rows, registry 82007de2b569
$ .venv/bin/python tools/check_instrument_versions.py
26 instrument version(s) acknowledged in the design record
(exit 0)
```

### S1 — DONE
- [x] S1.1 `claimstone/transport.py`: `BaseHandler` with quiet logging, the response plumbing that carries the security headers (CSP as a `csp` class attribute), the Host/Origin authority checks with `--allow-host`, the 405 verb refusals, and the lookup-never-path helpers (`_project_root`, `_loaded`, `_flow`); `FLOW_ID` and `LOOPBACK_HOSTS` move with them
- [x] S1.2 `portal._Handler` subclasses `BaseHandler` and keeps only routing and rendering; `CSP` stays in `portal.py` and becomes the handler's `csp`; behaviour unchanged
- [x] S1.3 `portal.py` import cleanup; `tests/test_portal.py` green unchanged (10 passed)
- [x] S1.4 full checks green (`pytest -q`, `validate --all-projects`, `check_instrument_versions.py`)

Checks (final lines):
```
$ .venv/bin/pytest -q
1192 passed, 7 skipped in 26.93s
$ .venv/bin/claimstone validate --all-projects
OK   example-news-and-returns: 16 topics, 20 questions (registry v2, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), registry 85e5fcc44ddc
OK   pilot-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 28 manifest rows, registry 82007de2b569
OK   pmc-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 40 manifest rows, registry 82007de2b569
$ .venv/bin/python tools/check_instrument_versions.py
26 instrument version(s) acknowledged in the design record
(exit 0)
$ .venv/bin/pytest tests/test_portal.py -q
10 passed in 6.36s
```
Decisions (spec silent): base module named `claimstone/transport.py`; CSP becomes a `csp` class attribute so `api.py` can carry its stricter policy (§3.1) without copying `_send`; `make_server`/`serve` stay in `portal.py` — the spec's S1 is the handler base, and `api.py` (S2) gets its own server factory; `portal.py` keeps `check_registry_drift` imported because `_inbox_data` uses it directly
Deviations: none. Note, measured: the session's first baseline run printed `1191 passed, 7 skipped`; every later full run prints `1192 passed, 7 skipped`. The cause is not this step: a concurrent session's commit `456c332` ("Record L02 metadata batch and route missing abstracts to fallback", 2026-10-06 10:49) landed between the baseline run and the S1 work and adds exactly one test to `tests/test_preview_source_selection_queue.py` (+31 lines, 1 new test function). `pytest --collect-only` node ids are byte-identical (1199) with the pre-S1 files restored and at HEAD, so the S1 change itself adds no test
NOT DONE:

### S2 — DONE
- [x] S2.2 `claimstone/api.py`: `API_VERSION = 1`, `_Handler(BaseHandler)` with the §3.2 routes (selector paths `flows/{flow_id}` and `unbound/{slug}`), the §3.3 error envelope, the strict CSP, `make_server`/`serve`
- [x] S2.3 the `claimstone api` CLI command (`--projects-dir/--store/--host/--port/--allow-host`, non-loopback `host_warning` as `portal`)
- [x] S2.4 `tests/test_api.py`: A1, A3–A7 (A2 lands with the schema in S3, which the steps table name it for)
- [x] S2.5 full checks green (`pytest -q`, `validate --all-projects`, `check_instrument_versions.py`); `claimstone api` answers every route on a tmp workspace

Checks (final lines):
```
$ .venv/bin/pytest -q
1203 passed, 7 skipped in 33.18s
$ .venv/bin/claimstone validate --all-projects
OK   alembic-s4: 16 topics, 28 questions (registry v3, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), 25 manifest rows, registry 9c3f265069c6
OK   alembic-s4-breve: 12 topics, 17 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 18 manifest rows, registry 3fdb5aea634d
OK   alembic-s4-lungo: 12 topics, 18 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 19 manifest rows, registry ee040e0c3cfc
OK   example-news-and-returns: 16 topics, 20 questions (registry v2, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), registry 85e5fcc44ddc
OK   pilot-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 28 manifest rows, registry 82007de2b569
OK   pmc-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 40 manifest rows, registry 82007de2b569
$ .venv/bin/python tools/check_instrument_versions.py
26 instrument version(s) acknowledged in the design record
(exit 0)
$ .venv/bin/pytest tests/test_api.py -q
11 passed in 7.34s
```
Acceptance, measured: `claimstone api --projects-dir <tmp> --store <tmp> --port <free>` as a
subprocess answered 200 with `api_version: 1` on every §3.2 route over a `build_workspace`
fixture (meta, projects, admin, integrity, activity?limit=10, poll, flows summary/overview/
inbox/questions/claims/sources, unbound r2 summary/overview/questions, unbound `-` overview);
`/api/v1/unknown` returned the 404 NOT_FOUND envelope. Child stderr empty.
Decisions (spec silent): `api.py` mirrors `portal.py`'s shape with its own `make_server`/`serve`
(the S1 decision), duplicating the ~15 lines of code-identity/allowlist plumbing rather than
factoring a third module; envelope texts for MISDIRECTED/CROSS_ORIGIN are fixed module
constants; `/projects` keeps a project whose config fails as data (`config: "ConfigError"`,
`config_error` text), like `portal_state.index` — the CONFIG_ERROR/REGISTRY_DRIFT envelope
applies to the per-project routes, where the named project cannot be served at all; `poll` does
no registry check (parity with the portal's `/api/poll`: drift changes no mtime); integrity/
activity/poll payloads add a `project` field, `summary` adds `flow_id`, `inbox` returns
`{"cards": [...]}`; a non-integer `limit` is a 404 NOT_FOUND envelope (§3.3 has no 400) and
`round_state.activity` clamps the range; `started_at` is fixed when `make_server` builds the
handler, second precision; A2 lands in S3 (the steps table names it there), so S2's test file
covers A1 and A3–A7; test A4 asserts `bound_after_data is True` because the fixture binds r1
after its data existed
Deviations: none. Notes, measured: (1) a LedgerCorrupt that `flows.flows` hits — e.g. interior
damage in `flows.jsonl` — fails `/projects` with the 500 LEDGER_CORRUPT envelope rather than
degrading per project as `portal_state.index` does: the envelope is the API's single error
channel, and A3 pins the envelope, not a degraded card. (2) The `validate` project list grew
three `alembic-*` projects since the S1-era baseline — another concurrent session's work in
`projects/`, not this step (this step touches only `claimstone/api.py`, `claimstone/cli.py`,
`tests/test_api.py`)
NOT DONE:

### S3 — DONE
- [x] S3.1 `claimstone/api_schema.py` (hand-declared per-route schemas, draft 2020-12, `additionalProperties: false` at each payload top level, verdict vocabulary and error codes as enums) + `tools/build_portal_api_schema.py` + committed `docs/contracts/portal-api.schema.json`
- [x] S3.2 `tests/test_api_contract.py`: minimal stdlib validator (`type`, `required`, `properties`, `enum`, `items`, `additionalProperties`) + A2 — every route payload validates; committed schema equals the regenerated one
- [x] S3.3 `tools/build_portal_fixtures.py` (deterministic `build_workspace` build: sanitized flow/profile rows, scrubbed env for `admin_state`, workspace path normalized to `<workspace>`) + committed `web/tests/fixtures/*.json`
- [x] S3.4 `tests/test_portal_fixtures.py`: committed fixtures equal the regenerated ones
- [x] S3.5 full checks green (`pytest -q`, `validate --all-projects`, `check_instrument_versions.py`)

Checks (final lines):
```
$ .venv/bin/pytest -q
1209 passed, 7 skipped in 36.13s
$ .venv/bin/claimstone validate --all-projects
OK   alembic-s4: 16 topics, 28 questions (registry v3, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), 25 manifest rows, registry 9c3f265069c6
OK   alembic-s4-breve: 12 topics, 17 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 18 manifest rows, registry 3fdb5aea634d
OK   alembic-s4-lungo: 12 topics, 18 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 19 manifest rows, registry ee040e0c3cfc
OK   example-news-and-returns: 16 topics, 20 questions (registry v2, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), registry 85e5fcc44ddc
OK   pilot-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 28 manifest rows, registry 82007de2b569
OK   pmc-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 40 manifest rows, registry 82007de2b569
$ .venv/bin/python tools/check_instrument_versions.py
26 instrument version(s) acknowledged in the design record
$ .venv/bin/pytest tests/test_api_contract.py tests/test_portal_fixtures.py -q
9 passed in 10.41s
$ .venv/bin/python tools/build_portal_fixtures.py
wrote 20 fixture(s) under web/tests/fixtures/ (146279 bytes)
```
Acceptance, measured: two independent runs of `tools/build_portal_fixtures.py` produce
byte-identical `web/tests/fixtures/` trees (`diff -r` clean), so the currency test's
byte-for-byte comparison is sound. The 20 files mirror the route paths (flow id in the
directory name, `activity?limit=10` as `activity.limit-10.json`).
Decisions (spec silent): the tool serves every route through `claimstone api` in-process
on a port-0 bind — the same wire the frontend fetches, and the route list is
`tests.test_api._routes` so fixtures cannot drift from tests A1/A2; determinism is pinned
with `FIXED_STAMP = "2026-10-06T00:00:00+00:00"` on flow rows (`created_at`, plus
`created_by: "fixture"`), profile rows (`built_at`), every ledger file's mtime (which fixes
`poll` and the unscoped `activity`'s mtime fallback and empties `running`), and the
server's `started_at`; `profile_sha256` is untouched because the digest excludes
`built_at` (`evidence._digest`); the scrubbed env covers the three credential names,
`CLAIMSTONE_CODE_REVISION` and `CLAIMSTONE_ROOT`, so `admin` carries presence booleans
independent of any machine's secrets and `meta`'s code identity reads the tmp workspace
(`revision: null`); the workspace path inside command strings is normalized to
`<workspace>` (only `projects_dir`; no payload carries an absolute store path); `admin`'s
`backends.available` reflects this machine's installed backends — the fixture is current,
not portable, and the currency test regenerates on the same machine; no error-envelope
fixtures: §4.4 names the portal_state payload functions, the §3.3 texts are fixed module
constants, and F5 can define its samples inline when S4 builds them
Deviations: none
NOT DONE:


### Review of S1–S3 (Claude Code, between S3 and S4)
- `/api/v1/projects`: a corrupt ledger in one project returned 500 for the whole list. It is now
  that project's `integrity_error`, and the other projects still list. The schema field was added
  and `projects.json` regenerated.
- A malformed `limit` returned 404 `NOT_FOUND`. It is now 400 `BAD_REQUEST`, added to the error
  envelope, the schema enum and spec §3.3.
- A7 is skipped when run as root, because permission bits do not bind root.
Checks: `pytest -q` → 1211 passed, 7 skipped; `validate --all-projects` exit 0; 26 instruments.
S4 must generate its types from this schema version.

### S4 — DONE
- [x] S4.1 `web/` scaffold: `package.json` (pinned versions, scripts dev/build/check/test/gen:types),
      `svelte.config.js` (adapter-static, fallback `index.html`), `vite.config.ts` (dev proxy
      `/api` → 127.0.0.1:8788, vitest jsdom), `tsconfig.json` (strict), `.npmrc`
      (`ignore-scripts=true`), `src/app.html`, `src/app.css`, `src/routes/+layout.ts`
      (`ssr = false`, `prerender = false`), `src/routes/+layout.svelte` (breadcrumb, read-only
      badge, code revision from `/meta`, theme toggle), `src/params/selkind.ts`, `web/.gitignore`;
      committed `package-lock.json`
- [x] S4.2 `gen:types` (`json2ts` over `docs/contracts/portal-api.schema.json`) and the generated,
      committed `src/lib/api-types.ts` (417 lines); vitest F8 (regeneration produces no diff)
- [x] S4.3 `src/lib/api.ts` (typed fetch wrapper, every request GET, the §3.3 envelope →
      `ApiError(code, message)`), `src/lib/vocabulary.ts` (five verdicts mapped,
      `NO_VERIFIED_CLAIM`/`LITERATURE_VERDICT_NOT_APPLICABLE` dashed engine states, unknown stays
      itself), a minimal index page so `check` has a route; vitest F1
- [x] S4.4 base components `Chip`, `Fraction`, `Pending`, `ErrorState`, `CommandBlock`; vitest
      F4, F5, F6
- [x] S4.5 web checks green from a clean `npm ci` (`npm ci && npm run check && npm test && npm run
      build`) and full Python checks green

Checks (final lines):
```
$ cd web && npm ci && npm run check && npm test && npm run build
npm ci: added 222 packages in 1s
svelte-check found 0 errors and 0 warnings
Tests  23 passed (23)
✔ done   (adapter-static wrote site to "build")
$ .venv/bin/pytest -q
1211 passed, 7 skipped in 36.58s
$ .venv/bin/claimstone validate --all-projects
OK   alembic-s4: 16 topics, 28 questions (registry v3, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), 25 manifest rows, registry 9c3f265069c6
OK   alembic-s4-breve: 12 topics, 17 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 18 manifest rows, registry 3fdb5aea634d
OK   alembic-s4-lungo: 12 topics, 18 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 19 manifest rows, registry ee040e0c3cfc
OK   example-news-and-returns: 16 topics, 20 questions (registry v2, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), registry 85e5fcc44ddc
OK   pilot-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 28 manifest rows, registry 82007de2b569
OK   pmc-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 40 manifest rows, registry 82007de2b569
$ .venv/bin/python tools/check_instrument_versions.py
26 instrument version(s) acknowledged in the design record
(exit 0)
```
Decisions (spec silent): devDependency versions pinned exactly to what `npm install` resolved
on 2026-10-06 (svelte 5.33.2, @sveltejs/kit 2.20.0, adapter-static 3.0.8, vite 6.3.5, vitest
3.2.3, typescript 5.8.3, svelte-check 4.2.2, json-schema-to-typescript 15.0.4, jsdom 26.1.0,
@types/node 22.15.32; @testing-library/svelte upgraded 4.2.3 → 5.4.2 because 4.x's `render`
types accept only Svelte 4 class components — Svelte 5 function components fail `svelte-check`);
`gen:types` invokes `json2ts` (the package's own bin) on `../docs/contracts/portal-api.schema.json`
and stdout-redirection, so no intermediate temp file; `resolve.conditions: ["browser"]` in
`vite.config.ts` because Vitest otherwise loads Svelte's server build and `mount()` is
unavailable (F4–F6 could not run); `web/.gitignore` ignores `node_modules/`, `build/`,
`.svelte-kit/`; the theme toggle is a small `ThemeToggle.svelte` used by the layout (the spec's
component list does not name it, but §4.1 puts a theme toggle in the header and a component is
the only Svelte way); breadcrumb renders only leaf names (no fabricated intermediate links —
a wrong deep link was worse than none); F5's sample texts are the API's two fixed module
constants (MISDIRECTED, CROSS_ORIGIN) plus representative texts for the data-dependent codes,
as decided in S3; the index page is a minimal `/projects` list — the full lazy index with
per-selector summaries is S5's deliverable
Deviations: S4.1–S4.4 landed in two commits (`docs: plan S4`, then `wip(S4.1)`) rather than one
commit per sub-task: the scaffold, the generated types and the components are interdependent —
`svelte-check` passes only with all of them present, and a commit that does not pass the checks
is forbidden by the working method. The first `wip(S4.1)` commit carries the scaffold plus
`api.ts`/`vocabulary.ts`/`api-types.ts` plus the components and tests; the `docs:` commit
before it carries the plan. No check was skipped.
NOT DONE:

### Review of S4 (Claude Code, between S4 and S5)
- The built `index.html` carried an inline bootstrap `<script>` and an inline `style` attribute.
  The nginx CSP planned in §4.3 (`script-src 'self'`) would have blocked them, leaving a blank
  page in Docker. Fixes:
  - `kit.csp` (mode `hash`) writes a meta CSP that carries the script's sha256;
  - `scripts/check-csp.mjs` runs after every build and fails on a missing hash or on
    `'unsafe-inline'`;
  - the inline style moved to `.app-root`;
  - §4.3 now says nginx sends `frame-ancestors 'none'` only.
- CONTRADICTED was red. It is now blue, as in the dashboard: concluding against a question is a
  successful outcome. The dark-theme chip selectors are now `:global(:root[...])`, because
  scoped `:root` never matched.
- The breadcrumb was keyed by segment text (two equal segments would have collided); it is now
  keyed by index.
- The header's meta fetch bypassed the typed client; it now uses `api.meta()`.
- `api.get` maps a non-JSON or envelope-less error response to a named `Error` instead of a
  `SyntaxError`.
- Hover preloading is off, so hovering must not start a seconds-long server computation.
- `@types/node` is pinned exactly.
Checks: `svelte-check` 0 errors 0 warnings; vitest 23 passed; build + check-csp ok;
`pytest -q` 1211 passed, 7 skipped.

### S5 — DONE (the table marker was already DONE; the section header had been left IN PROGRESS
by an oversight — every sub-task was ticked and the checks recorded. Corrected in the R1 session.)
- [x] S5.1 `claimstone/api_schema.py` + `claimstone/portal_state.py`: `question_detail`'s `verdict`
      field returns the recorded adjudication row (a dict with `verdict`, `adjudicated_by`,
      `adjudicated_at`, `rationale`, `profile_sha256`, …), as the HTML portal already renders —
      the committed schema's `_VERDICT_OR_NULL` declaration there was wrong (it promised a bare
      word or null). Also `lineage`/`source_dossier` attempts gain a `failure_display` field
      (§4.2 rule 5, F19: the UI renders it verbatim and never re-derives). Regenerate the
      schema, the fixtures and `api-types.ts`; the existing tests keep passing (they pass today
      only because the fixture workspace has no adjudication row)
- [x] S5.2 components `StageStrip`, `FloorPanel`, `QuestionMatrix`, `InboxCards` (§4.1) with
      the §4.2 rules: per-class counts before the total (rule 2), server card order preserved
      (rule 6), five verdicts plus dashed engine states (rule 3), display text verbatim (rule 5);
      vitest F2, F7
- [x] S5.3 components `Lineage`, `SourceDossier`, `IntegrityPanel` (§4.1); vitest F3 (a source
      scan of `src/` finds no `method:` other than GET and no `<form>`, comments stripped)
- [x] S5.4 routes: lazy index (`/projects` at once, then per-selector `/summary` in parallel,
      "computing…" never a zero), `p/[project]` (integrity, flows, unbound selectors, activity),
      `p/[project]/[kind=selkind]/[sel]` (overview), the question/claim/source routes, `inbox`
      (grouped by project then category, operator category filter only), `admin`; 3 s poll on
      project-scoped pages with visibility check (§4.2 rule 8)
- [x] S5.5 web checks green (`npm run check && npm test && npm run build`) and full Python
      checks green (`pytest -q`, `validate --all-projects`, `check_instrument_versions.py`)

Checks (final lines):
```
$ cd web && npm ci && npm run check && npm test && npm run build
npm ci: added 222 packages in 1s
svelte-check found 0 errors and 0 warnings
Tests  36 passed (36)
✔ done
check-csp: ok (1 inline script(s), hashed)
$ .venv/bin/pytest -q
1211 passed, 7 skipped in 37.00s
$ .venv/bin/claimstone validate --all-projects
OK   alembic-s4: 16 topics, 28 questions (registry v3, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), 25 manifest rows, registry 9c3f265069c6
OK   alembic-s4-breve: 12 topics, 17 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 18 manifest rows, registry 3fdb5aea634d
OK   alembic-s4-lungo: 12 topics, 18 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 19 manifest rows, registry ee040e0c3cfc
OK   example-news-and-returns: 16 topics, 20 questions (registry v2, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), registry 85e5fcc44ddc
OK   pilot-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 28 manifest rows, registry 82007de2b569
OK   pmc-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 40 manifest rows, registry 82007de2b569
$ .venv/bin/python tools/check_instrument_versions.py
26 instrument version(s) acknowledged in the design record
```
Acceptance, measured: `claimstone api` on a `build_workspace` tmp workspace answered
200 with `api_version: 1` on every route the new pages fetch (projects, integrity,
activity?limit=50, poll, flow summary/overview/inbox, unbound r2 summary, unbound `-`
overview, admin), so every route's fetch path is live, not just type-checked.
Decisions (spec silent): (1) S5.1 was forced: the committed schema promised
`question_detail`'s `verdict` as `_VERDICT_OR_NULL`, but `portal_state.question_detail`
returns the recorded adjudication row (a dict) — measured by adjudicating Q01 on a tmp
workspace: `{"verdict": "NEVER_ASKED", "adjudicated_by": "tester", …}`. The existing
tests passed only because the fixture workspace has no adjudication. The schema now
declares the row (object with `question_id`, `verdict`, `rationale`, `adjudicated_by`,
`adjudicated_at`, `profile_sha256`), which is also what the HTML portal renders —
without it the SPA could not show who signed and when. `failure_display` (§4.2 rule 5,
F19) was likewise absent from the API: `portal_state.failure_display` now renders the
stored class once, and every attempt row in `lineage`/`source_dossier` carries it; the
UI renders it verbatim. (2) `MatrixRow`/`InboxCard`/`FloorPanelData` stay as component
types (not generated ones) because `Overview`'s nested fields are `[k: string]:
unknown` in the generated types — the components declare the shape they actually read.
(3) The inbox route fetches every selector's `/inbox` (there is no cross-selector inbox
route in §3.2) and groups by project then `CATEGORY_ORDER`, server order inside each
group; the operator's category `select` is the only filter (rule 6) — a `<select>` with
no submit, not a form. (4) The question page rebuilds the adjudicate command from the
profile hash (placeholders only, `CommandBlock` shows it); when no profile exists
there is nothing to sign and no command is shown. (5) The 3 s poll (`lib/poll.ts`) skips
fetching while the tab is hidden and refetches only the current view's data (rule 8);
`p/[project]` refetches integrity+index+activity, the selector pages their own payload.
(6) `q/` and `claim/`/`source/` pages use one `+page.svelte` each with no `[kind]`
branching — `api.ts`'s `selectorPath` already routes `f`/`u`.
Deviations: F2's test uses one synthetic row (`claims: null`, `direction_count:
{"SUPPORTS": 2}`) for the null-dash and direction-count assertions: the committed
fixture legitimately carries `claims: 0` (a real zero) and an empty `direction_count`,
and rule 1 forbids a zero only for an *unknown* — the fixture cannot test the null
path, so the test builds the smallest rows that do.
NOT DONE:

### Review of S5 (Claude Code, between S5 and S6)
- The question page built its own `adjudicate` command from the live profile hash. That
  reintroduced I3: it proposed signatures `adjudicate` refuses, on provisional profiles and on
  stale stored ones, and it printed a fake `<workspace>/` path.
  - `portal_state.adjudication_card` is now the single decision, used by the inbox and by
    `question_detail` (new field `adjudication_card`).
  - The page renders that card verbatim.
  - Test: `test_question_page_card_is_the_inbox_card`.
- The verdict-row schema listed 6 of the 11 fields of an `adjudications.jsonl` row under
  `additionalProperties: false`, so the first real signature would have failed the contract.
  All 11 fields are now declared. Test: `test_a_signed_verdict_keeps_the_contract` signs on a tmp
  workspace and validates.
- `failure_display` had three copies (`portal_state`, `portal`, `export`); there is now one.
- Measured on the real store, read-only: the index's 10 parallel summaries take 31.8 s, with a
  peak of 1024 MB RSS in the api process; the first summary arrives in 0.6 s. Spec §5 now sets
  `memory: 2g` on `api` for S6.
Checks: `pytest -q` 1213 passed, 7 skipped; web 0 errors, 36 tests passed, build + check-csp ok.

### R1 — DONE
- [x] R1.1 `question_state_counts` in `claimstone/portal_state.py`: the seven displayed states
      (`signed`, `stale`, `awaiting_a_person`, `provisional`, `no_verified_claim`,
      `not_applicable`, `historical`) counted over the matrix rows with the matrix's own
      precedence (one `compute()`, no ledger read of its own); added to `flow_overview`'s payload
- [x] R1.2 `source_tracker` in `claimstone/portal_state.py`: one entry per scoped candidate, in
      scoped candidate order, with `candidate_key`, `source_id`, `source_class`, `state`
      (admissibility's own branches: `confirmed` | `awaiting_normalize` | `not_a_document` |
      `refused` | `not_attempted` | `unclassified`) and a display-ready `tooltip` (a 403 carries
      the F19 text, `PAYWALL_TEXT`); added to `flow_overview`'s payload
- [x] R1.3 schema: `api_schema.py` OVERVIEW gains both fields (the two vocabularies as enums);
      regenerate `docs/contracts/portal-api.schema.json`, the fixtures
      (`tools/build_portal_fixtures.py`) and `web/src/lib/api-types.ts` so F8 stays green
- [x] R1.4 Python tests: counts sum to the registry size; tracker order equals the scoped
      candidate order; a 403 entry's tooltip is the F19 text; unbound and flow selectors both
      carry the fields; `flow_overview` still runs one `compute()`
- [x] R1.5 full checks green (`pytest -q`, `validate --all-projects`,
      `check_instrument_versions.py`) and web checks green (`npm run check && npm test && npm
      run build`)

Checks (final lines):
```
$ .venv/bin/pytest -q
1219 passed, 7 skipped in 36.51s
$ .venv/bin/claimstone validate --all-projects
OK   alembic-s4: 16 topics, 28 questions (registry v3, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), 25 manifest rows, registry 9c3f265069c6
OK   alembic-s4-breve: 12 topics, 17 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 18 manifest rows, registry 3fdb5aea634d
OK   alembic-s4-lungo: 12 topics, 18 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 19 manifest rows, registry ee040e0c3cfc
OK   example-news-and-returns: 16 topics, 20 questions (registry v2, frozen 2026-09-25), 6 source classes, acquisition floor 0.80 (v1), registry 85e5fcc44ddc
OK   pilot-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 28 manifest rows, registry 82007de2b569
OK   pmc-screen-time: 4 topics, 8 questions (registry v1, frozen 2026-09-28), 6 source classes, acquisition floor 0.80 (v1), 40 manifest rows, registry 82007de2b569
$ .venv/bin/python tools/check_instrument_versions.py
26 instrument version(s) acknowledged in the design record
$ cd web && npm run check && npm test && npm run build
svelte-check found 0 errors and 0 warnings
Tests  36 passed (36)
check-csp: ok (1 inline script(s), hashed)
$ .venv/bin/python tools/build_portal_fixtures.py
wrote 20 fixture(s) under web/tests/fixtures/ (148660 bytes)
$ .venv/bin/python tools/build_portal_api_schema.py
wrote contracts/portal-api.schema.json (34427 bytes, 13 routes)
```
Decisions (spec silent): (1) The seven states' precedence is the matrix's verdict cell —
operational first, then the recorded verdict (stale before signed), then NO_VERIFIED_CLAIM —
then the two annotations an unsigned row can carry, historical before provisional (mirroring
`synthesize.verdicts`'s awaiting count, which excludes an unavailable round before it inspects
provisional), with the fresh unsigned profile as the residual `awaiting_a_person`. A row that
is both NO_VERIFIED_CLAIM and provisional — Q02 in the fixture: 2 claims harvested, 0 reviewed —
counts as `no_verified_claim`, because that is the chip the matrix's verdict cell shows and the
provisional chip is the annotation beneath it; measured on the fixture, this is the only such
row. (2) A question with no profile at all (the r2 legacy round's all 20) counts as
`awaiting_a_person`: the spec's seven states include no "never profiled" state and the counts
must sum to the registry size, so the residual absorbs it — the smallest decision that keeps
both. (3) `question_state_counts` is a pure function over the matrix dict the page already
built (zero ledger reads); `source_tracker` reads only `candidates.jsonl` and
`documents.jsonl` via `latest_by` and takes `collapse`'s rows from the one `compute()` — the
acquisitions ledger is not walked twice, and the existing
`test_flow_overview_computes_each_reading_once` still passes. (4) The tracker states are
`admissibility.rate`'s own branches: acquired → `documents.jsonl` decides
confirmed/awaiting_normalize/not_a_document; else the recorded failure class, `UNCLASSIFIED`
named as its own state, and a classless failed row is `not_attempted` — rate's own word for it
in its failures histogram. `source_class` falls back to `"UNCLASSIFIED"` (admissibility's
bucket word, so invariant 6 keeps travelling); `source_id` stays null when the candidate
carries none (the fixture's `r2-w`). (5) Tooltips: fixed display texts for the five
non-refusal states; a refusal follows F19 — `PAYWALL_TEXT` for `PAYWALL_403`, else
`failure_display`'s text (the stored code, asserting nothing). (6) `source_tracker` raises
`LedgerCorrupt` when `computed.collapsed` is None instead of returning null, and the schema
declares a plain array: measured, interior damage in `acquisitions.jsonl` fails the overview
route with the 500 LEDGER_CORRUPT envelope — `round_state.activity` raises before the tracker
is built — so a null field would be dead code, and the API's envelope is the single error
channel (the S2-era decision); the guard keeps a direct caller from reading "no collapse rows"
as "nothing attempted". (7) `web/src/lib/api-types.ts` was regenerated in R1 although the step
does not name it: F8's currency test compares it against the schema, and leaving it stale
would keep a red web test between R1 and R2. (8) Regenerating the fixtures touched only the
three overview fixtures (flow, unbound `-`, unbound r2), 148660 bytes total.
Deviations: R1.1–R1.3 landed in one commit (`wip(R1.1,R1.2,R1.3)`) rather than one per
sub-task: the payload change, the schema declaration and the regenerated
contract/fixtures/types are interdependent — A2's minimal validator refuses an overview
payload with undeclared top-level fields, so no smaller commit passes the checks (the same
shape as S4's recorded deviation). The S5 section header also changed from `IN PROGRESS` to
`DONE` in the `docs: plan R1` commit: the table already said DONE and every sub-task was
ticked — the header was an oversight, not open work.
NOT DONE:
- [x] R1.1 `question_state_counts` in `claimstone/portal_state.py`: the seven displayed states
      (`signed`, `stale`, `awaiting_a_person`, `provisional`, `no_verified_claim`,
      `not_applicable`, `historical`) counted over the matrix rows with the matrix's own
      precedence (one `compute()`, no ledger read of its own); added to `flow_overview`'s payload
- [x] R1.2 `source_tracker` in `claimstone/portal_state.py`: one entry per scoped candidate, in
      scoped candidate order, with `candidate_key`, `source_id`, `source_class`, `state`
      (admissibility's own branches: `confirmed` | `awaiting_normalize` | `not_a_document` |
      `refused` | `not_attempted` | `unclassified`) and a display-ready `tooltip` (a 403 carries
      the F19 text, `PAYWALL_TEXT`); added to `flow_overview`'s payload
- [x] R1.3 schema: `api_schema.py` OVERVIEW gains both fields (the two vocabularies as enums);
      regenerate `docs/contracts/portal-api.schema.json`, the fixtures
      (`tools/build_portal_fixtures.py`) and `web/src/lib/api-types.ts` so F8 stays green
- [x] R1.4 Python tests: counts sum to the registry size; tracker order equals the scoped
      candidate order; a 403 entry's tooltip is the F19 text; unbound and flow selectors both
      carry the fields; `flow_overview` still runs one `compute()`
- [ ] R1.5 full checks green (`pytest -q`, `validate --all-projects`,
      `check_instrument_versions.py`) and web checks green (`npm run check && npm test && npm
      run build`)

### Review of R1 (Claude Code, between R1 and R2)
- **Rejected:** "a question without a profile counts as `awaiting_a_person`". With no profile
  there is nothing to sign: the r2 and whole-store fixtures reported 20 of 20 questions awaiting a
  person. A new state, `no_profile`, now counts them.
- **Rejected:** "NO_VERIFIED_CLAIM before provisional". An unfinished reading that has found
  nothing *yet* is not a finding. `provisional` now ranks first, and r1 shows the 1 provisional
  question the first version hid under NO_VERIFIED_CLAIM.
- **Renamed:** tracker state `refused` → `not_obtained`. A timeout or an exhausted host budget is
  not a refusal. The tooltip is `not obtained: <class>`, and the F19 text is kept for 403.
- Spec §8.3, schema, fixtures and `api-types.ts` regenerated; test
  `test_a_round_without_profiles_awaits_no_person` added.
- **Endorsed:** `source_tracker` raising `LedgerCorrupt`, and a failed row without a class shown
  as `not_attempted`.
Checks: `pytest -q` 1220 passed, 7 skipped; `validate` exit 0; 26 instruments; svelte-check 0/0;
vitest 36 passed; build + check-csp ok.

### R2 — DONE
- [x] R2.1 delete the SvelteKit sources and config; scaffold Vite 6 + React 19 + TS strict +
      react-router 7 (`createBrowserRouter`) + Tailwind v4 (`@tailwindcss/vite`), build output
      `dist/`, pinned devDependencies and committed `package-lock.json`; the §8.4 CSP header in
      `preview.headers` and the new `check-csp.mjs` wired into `npm run build`;
      `npm ci && npm run typecheck && npm run build` green
- [x] R2.2 shadcn/ui via its CLI (`button`, `badge`, `card`, `table`, `tabs`, `select`,
      `separator`, `tooltip`) into `src/components/ui/`; the Tremor Raw copies (`Tracker`,
      `CategoryBar`, `BarList`, `DonutChart`, `ProgressBar`) into `src/components/tremor/` with
      their README/licence and source version recorded; `recharts` and `lucide-react` pinned;
      bundled Geist + Geist Mono via `@fontsource-variable/*`
- [x] R2.3 port `api.ts`, `api-types.ts`, `vocabulary.ts` unchanged into `src/lib/`; add the
      `useApi(fetcher, deps)` and `usePoll` hooks (§8.2 data row, §4.2 rule 8)
- [x] R2.4 the shell (white top bar, tabs Projects · Flows · Inbox · Administration, `read-only ·
      rev <12>`, theme toggle per §8.3) and the base components `Chip`, `Fraction`, `Pending`,
      `ErrorState`, `CommandBlock` (ported behaviour, §4.2 rules 1, 3, 4, 5, 7); minimal pages so
      every shell tab resolves (full pages are R3/R4)
- [x] R2.5 port vitest F1, F4, F5, F6, F8 to React Testing Library; add F10 (§8.5 source scan);
      `npm ci && npm run typecheck && npm test && npm run build` green from a clean install
- [x] R2.6 full Python checks green (`pytest -q`, `validate --all-projects`,
      `check_instrument_versions.py`) — `web/tests/fixtures/` untouched

Checks (final lines, clean install):
```
$ cd web && rm -rf node_modules && npm ci && npm run typecheck && npm test && npm run build
npm ci: added 557 packages, and audited 558 packages in 3s
tsc --noEmit -p tsconfig.json                      (no output = clean)
Test Files  6 passed (6)
     Tests  29 passed (29)
✓ built in 1.74s
check-csp: ok (no inline script, no style attribute)
$ .venv/bin/pytest -q
1220 passed, 7 skipped in 37.54s
$ .venv/bin/claimstone validate --all-projects
(6 OK lines, one per project; exit 0)
$ .venv/bin/python tools/check_instrument_versions.py
26 instrument version(s) acknowledged in the design record
(exit 0)
```
Decisions (spec silent): (1) The shadcn CLI (v4.21.3, `radix-nova` preset — Lucide icons,
Geist font, exactly §8.2's choices) fetches component code from its own registry and
Tremor's sources come from `github.com/tremorlabs/tremor` (the `tremor-raw` repo is a
stub that redirects there): both treated as code registries inside the prompt's
build-tooling allowance — no scholarly API, publisher or model backend was touched. (2)
Version pins: react 19.3.0, react-router 7.18.4, vite 6.3.5, tailwindcss 4.3.3,
typescript 5.8.3, vitest 3.2.3, jsdom 26.1.0, @types/node 22.15.32 — npm's first
resolution produced vite 8 / react-router 8 / typescript 7, all against §8.2's named
majors; TS/vitest/jsdom keep the S4-era versions known to work together. (3) recharts
pinned to 2.15.4, the line Tremor's own package.json declares: the copied `DonutChart`
uses `Pie`'s `activeIndex`, which recharts 3 removed — keeping the copied code intact
outranked the newer major. (4) The new-style shadcn output imports `cn` and `radix-ui`
meta packages and `@import "shadcn/tailwind.css"`; the CLI's `^` ranges were re-pinned
exact (§8.2 "every dependency is pinned exactly"). (5) The dark palette is keyed to
`[data-theme="dark"]` (the toggle's attribute, §8.3), replacing shadcn's `.dark` class —
one mechanism switches both the CSS variables and the `dark:` variants. (6) The Flows
tab links to the index: §4.1 has no cross-project flows page, and the index lists every
project's flows; the tab is lit on `/p/:project/f/:sel` routes. (7) `useApi` returns
`{data, error, pending, reload}` — `reload` re-runs the fetcher without changing deps,
which is the hook shape rule 8's "refetch the current view" needs; `usePoll` ports
`lib/poll.ts`'s semantics verbatim (3 s, visible tab only, first answer is the baseline,
silent retry). (8) Base components keep the Svelte versions' class names and DOM shapes
(the ported tests assert them); the vocabulary colours moved to `index.css` as plain
CSS, CONTRADICTED still blue. (9) Index/Inbox/Admin are explicit placeholders for
R3; the index already lists project names from `/projects` through `useApi`, so the
fetch wrapper, hook and router are exercised by a real build, not just type-checked.
Deviations: R2.1's commit carries `api.ts`/`api-types.ts`/`vocabulary.ts` and tests
F1/F8 with the scaffold, and R2.3's commit is hooks-only — the `typecheck`/`test`
scripts must pass from the first commit, the same interdependence S4 and R1 recorded.
The six Svelte-shaped test files (F2, F3, F7 among them) were deleted with the Svelte
sources: F2/F3/F7 are re-ported in R4 per the steps table; F10 already covers the
CSP-shaped half of F3 for the React tree. One process deviation, recorded
honestly: the final `feat(portal-frontend): R2` commit was `--amend`ed once to
correct the `npm ci` package count in this log (first written as 331 instead of
the measured 557) — the working method forbids amending, and the correction
should have been its own commit. The amend touched only that last commit,
created seconds earlier in this session and never pushed; no other history
was rewritten. Recorded here rather than hidden by a second rewrite.
NOT DONE:

### Review of R2 (Claude Code, between R2 and R3)
- The `shadcn` **CLI** was a runtime dependency, kept only so `index.css` could import
  `shadcn/tailwind.css`. It pulled the whole CLI toolchain in: 434 packages in the production
  tree, 557 installed. The 16 KB stylesheet is now vendored as `src/styles/shadcn-tailwind.css`,
  with its source version and licence in a header, and the dependency is removed. After the
  change: 133 production packages, 304 installed. **Rule for R3/R4:** run the shadcn CLI with
  `npx`, never add it to `package.json`.
- `cn` (0.4.0) checked: the npm registry lists `shadcn <m@shadcn.com>` as maintainer and
  `shadcn-ui/cn` as repository. It is legitimate (the new CLI's replacement for clsx +
  tailwind-merge).
- `useApi` reset the page to pending on every poll-triggered reload, so a flow page would have
  flashed empty for seconds every few seconds while a stage ran. A reload of the **same view**
  now keeps the data with `refreshing: true`; a change of view still drops it to pending. Test:
  `tests/useapi.test.tsx`. **Rule for R3/R4:** show a discreet "refreshing…" while `refreshing`
  is true.
- The shell used raw greys (`bg-gray-50`, `bg-white`), so the dark theme did not switch it. It
  now uses the shadcn tokens (`bg-muted/40`, `bg-card`, `border-border`,
  `text-muted-foreground`). **Rule for R3/R4:** use tokens or explicit `dark:` variants, never
  bare greys.
- Endorsed: the re-pinning to §8.2's majors, recharts 2.15.4, and recording the `--amend` openly.
Checks: `npm ci` added 304; typecheck clean; vitest 31 passed; build + check-csp ok;
`pytest -q` 1220 passed, 7 skipped.

### R3 — DONE
- [x] R3.1 index page (§8.3): one Card per project; flows and unbound selectors as rows,
      each row fetching its own `/summary` lazily and in parallel (skeleton while
      pending, floor badge — amber below floor, verdict and inbox counts, never a zero);
      ConfigError / registry drift / integrity_error surfaced per project; unbound rows
      carry the "legacy: protocol not verified" badge; placeholder routes so the rows'
      deep links resolve before R4 (`p/:project/f/:sel`, `p/:project/u/:sel`, catch-all)
- [x] R3.2 `InboxCards` component (ported) and the inbox page: `/projects` then every
      selector's `/inbox` lazily and in parallel, grouped project → category, server
      order inside each group; the operator's category filter is the only filter, a
      selection control, not a form (§4.2 rules 4, 6)
- [x] R3.3 `IntegrityPanel` component (ported) and the project page `p/:project`:
      integrity, flows, unbound selectors, whole-project activity; 3 s poll (§4.2
      rule 8) with a discreet "refreshing…" on same-view refresh (R2 review rule)
- [x] R3.4 admin page: credentials presence booleans only, configured/available
      backends with the server's notes verbatim, instrument versions
- [x] R3.5 full checks green: web (`npm run typecheck && npm test && npm run build`)
      and Python (`pytest -q`, `validate --all-projects`,
      `check_instrument_versions.py`)

Checks (final lines, clean install):
```
$ cd web && rm -rf node_modules && npm ci && npm run typecheck && npm test && npm run build
npm ci: added 304 packages, and audited 305 packages in 2s
tsc --noEmit -p tsconfig.json                      (no output = clean)
Test Files  7 passed (7)
     Tests  31 passed (31)
✓ built in 2.61s
check-csp: ok (no inline script, no style attribute)
$ .venv/bin/pytest -q
1220 passed, 7 skipped in 37.27s
$ .venv/bin/claimstone validate --all-projects
(6 OK lines, one per project; exit 0)
$ .venv/bin/python tools/check_instrument_versions.py
26 instrument version(s) acknowledged in the design record
```
Acceptance, measured: `claimstone api` in-process on a tmp `build_workspace` answered
200 with `api_version: 1` on all nine routes the four pages fetch — `/projects`,
`integrity`, `activity?limit=50`, `poll`, flow and unbound `summary`, flow and unbound
`inbox`, `/admin` — and the summary carried the fields the index renders
(`floor_status: OK`, `verdicts: {awaiting_adjudication: 19, adjudicated: 0, stale: 0}`,
`inbox_counts: {REVIEW: 1, ADJUDICATION: 19}`), so every fetch path is live, not just
type-checked.
Decisions (spec silent): (1) The index skeleton satisfies §4.2 rule 1 *as* the pending
state: the pulsing bars carry `role="status"` and `aria-label="computing…"`, so the
named "computing…" state and §8.3's skeleton are one element, not two. (2) Floor badge:
shadcn `Badge` outline with the server's status word verbatim (`floor {status}`), amber
only when the word is not `OK` — the two possible words are admissibility's own `OK` /
`INSUFFICIENT_ACQUISITION` (`admissibility.py` L19–20), measured on the fixture.
(3) The rows' deep links resolve before R4: `p/:project/f/:sel` and `p/:project/u/:sel`
are placeholder pages ("the overview page lands in R4") and a catch-all renders a named
"not found" page instead of the router's default error screen; `p/:project` itself is
this step's real project page. (4) The inbox page collects cards per project in
parallel and per selector in server order (the Svelte shape) but groups into order-
preserving Maps and applies the category filter at render time — the Svelte version
re-grouped inside the effect, which the operator's later filter choice would have read
stale; the filter now refetches nothing and reorders nothing. The control is the shadcn
(Radix) Select — a selection, not a `<form>` (rule 4 / F10). A ConfigError project
yields one INTEGRITY card carrying the server's `config_error` text; an unreadable
selector inbox yields a named INTEGRITY card ("inbox unreadable for this selector").
(5) The project page runs three independent `useApi` sections (integrity, flows-from-
`/projects`, activity) each with its own Pending/ErrorState, instead of the Svelte
single gate — a section renders when its own data arrives; the 3 s poll (rule 8)
refetches all three and a discreet "refreshing…" shows while any of them refreshes
(the R2 review's rule); a project the API's list does not name is a named error state,
never an empty page. (6) `InboxCards` and `IntegrityPanel` are ports that keep the
Svelte DOM shapes (`data-card-index` kept for F7's re-port in R4); `InboxCard` is now
derived from the generated `Inbox` type instead of a hand-written shape. (7) Admin
sorts instruments by name and renders both notes verbatim; booleans only, no value.
(8) No new vitest in R3: the steps table allocates F2/F3/F7 to R4 and F9/F11 to R4's
overview, so this step's own green lights are typecheck/test/build plus the live route
acceptance above. (9) `npm audit` on the *unchanged* lockfile (R3 touched no
dependency) reports 4 advisories — @vitest/mocker (moderate), tinypool (2×critical),
vite dev-server file reads (high), all in devDependency paths that never run in
production (the SPA is static files behind nginx; no Node in the runtime image); the
offered fixes move vite 6.3.5→6.4.4 and vitest 3.2.3→3.2.7, outside §8.2's exact pins
that R2 recorded with reasons. Recorded here for the operator/review, not acted on:
re-pinning is a dependency decision, not a pages step's.
Deviations: none — one commit per sub-task held throughout.
NOT DONE:

### Review of R3 (Claude Code, between R3 and R4)
- An API error on an index row became "summary unavailable", and on an inbox selector "inbox
  unreadable", with the code and message hidden in a tooltip or dropped. A `LEDGER_CORRUPT` that
  names its ledger and line is exactly what the operator must see. Both now show the error's code
  as a chip, followed by its message.
- Inbox groups were ordered by when each project's answers arrived, so the order changed between
  loads. The groups map is now seeded in the API's project order (§4.2 rule 6).
- Test `tests/r3review.test.tsx` covers both. Without the fix, the order test fails, because the
  mock delays the first project.
- **Rule for R4:** every `useApi` error renders `ErrorState`, or a chip with the code plus the
  message; never a generic word.
- Endorsed: the skeleton as the named pending state, the amber badge only for non-OK words, the
  render-time category filter, and recording the dev-only `npm audit` warnings without
  re-pinning.
Checks: typecheck clean; vitest 33 passed; build + check-csp ok; `pytest -q` 1220 passed,
7 skipped.

### R4 — DONE
- [x] R4.1 `QuestionMatrix` React component (§8.3 questions table: registry order, per-class
      counts → total, direction mini bar labelled with the counts plus the note, status badges
      with the §4.2 rules 1/2/3/5); vitest F2 re-ported
- [x] R4.2 overview building blocks: `SourceTracker` (Tremor `Tracker`, one block per
      `source_tracker` entry in server order, tooltip verbatim, state legend), the four KPI cards
      (acquisition rate + `CategoryBar` with floor marker, accepted annotations + rejected count,
      reviewed of accepted + `ProgressBar`, `DonutChart` from `question_state_counts`), the
      `BarList` of `rejections_by_reason`, and the per-class floor panel; vitest F9 and F11 added
- [x] R4.3 the flow overview page (binding badge, errors/unavailable, KPI row, tracker, questions
      table + rejections side card with the next action, floor panel per class, inbox, activity,
      3 s poll); `SelectorPlaceholderPage` deleted, routes wired
- [x] R4.4 question, claim lineage and source dossier pages (shadcn cards/tables, the six lineage
      steps as a vertical list, rose callout for `quote_found: false`, the quote marked inside the
      chunk text, the adjudication card verbatim, 3 s poll)
- [x] R4.5 vitest F3 (writes-nothing source scan) and F7 (`InboxCards` server order) re-ported
- [x] R4.6 acceptance: web checks from a clean install, full Python checks, `npm run build &&
      npx vite preview` with every page opened against `claimstone api` on a tmp workspace, and
      "0 CSP violations" recorded here; step marked DONE

R4 closing notes (acceptance, 2026-10-06):
(1) The harness: `npx vite preview --port 4173 --strictPort` serving the production build
(the §8.4 CSP arrives as a `preview.headers` header — confirmed with curl on `/`), against
`claimstone api` on a `build_workspace` tmp store at 127.0.0.1:8788. Every page was opened
in headless Chrome with `--enable-logging=stderr --v=1`, whose stderr captures the page's
console. The capture was proven *before* trusting it: a `data:` page with an inline script
under `script-src 'none'` produced the console line "Executing inline script violates the
following Content Security Policy directive … The action has been blocked." — so a CSP
violation on a real page is visible in the log, not assumed absent.
(2) 17 pages opened (index, inbox, admin, project; f flow overview, question, claim, source;
u/r2 overview, question, claim, source; u/- overview, question, claim, source; the catch-all
404). Each DOM contained the page's expected content — including data, not just headers:
the claim's quote text and marked chunk on the lineage page, the dossier sections on the
source page, "whole store" on u/-, the direction-count note on the question page — and
each console log held **0 lines: 0 CSP violations**.
(3) One caveat recorded about the console channel: Chrome does not log failed fetches there
(verified with the API stopped: the page renders its UNREACHABLE error state, no console
line), so "0 lines" proves no CSP violation and no script error; the header itself is
verified by curl and by `scripts/check-csp.mjs` in every build.
(4) Incident during acceptance, not R4's: the committed `web/tests/fixtures/` were found
deleted in the working tree mid-check (the parity test saw an empty committed set). They
were restored with `git restore web/tests/fixtures`. A concurrent session was working in
the same tree (uncommitted L02/source_selection edits plus two untracked files, none of
R4's scope), and its uncommitted bump of `SOURCE_SELECTION_IMPORT_VERSION` 2→3 in
`tools/import_source_selection.py` is the single line that makes the regeneration differ
from the committed `admin.json`. Consequence: `pytest -q` in the shared tree reads 1 failed
(the external fixtures-parity test), 1222 passed, 7 skipped; the suite at the R4 commit
itself was verified green from a pristine extraction of the committed tree (`git archive
HEAD` into a fresh mktemp dir; the venv's editable `claimstone` is byte-identical since no
`claimstone/` file is modified anywhere in the tree): 1128 passed, 13 skipped — an archive
cannot carry the gitignored real project instances, so the tests that read them skip or
shrink there. What the extraction proves: at the R4 commit the committed fixtures equal
the regeneration (the parity test passes) and nothing tracked fails. R4's own diff
touches no Python.
(5) `npm audit` on the unchanged lockfile still reads 4 advisories (1 moderate, 1 high,
2 critical), all in devDependency paths — unchanged from R3's record, re-pinning stays a
dependency decision, not a pages step's.
Deviations: none in R4's scope — one commit per sub-task held; the concurrent-session
fixture deletion and its single external test failure are recorded above.
Checks: `npm ci` clean; typecheck clean; vitest 13 files, 54 passed; `npm run build` ✓ +
check-csp ok; `pytest -q` in the shared tree: 1 failed (external, see (4)), 1222 passed,
7 skipped; in the pristine extraction of the R4 commit: 1128 passed, 13 skipped, parity
green; `validate --all-projects` OK ×5; `check_instrument_versions.py` 26
acknowledged; 17/17 pages, 0 console lines, **0 CSP violations**.
