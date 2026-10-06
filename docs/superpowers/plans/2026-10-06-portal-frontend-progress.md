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
| S5 routes and components | TODO |
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
