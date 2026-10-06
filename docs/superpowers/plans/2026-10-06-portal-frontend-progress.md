# Portal frontend progress log

Working document for `docs/superpowers/specs/2026-10-06-portal-frontend-glm-prompt.md`
(spec: `docs/superpowers/specs/2026-10-06-portal-frontend-docker-design.md`).
One step per session; markers below are the authority for "what is next".

| step | marker |
|---|---|
| S1 shared transport base class out of `claimstone/portal.py` | DONE |
| S2 `claimstone/api.py` + tests A1–A7 | DONE |
| S3 schema, validator, fixtures | IN PROGRESS |
| S4 scaffold `web/` | TODO |
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

### S3 — IN PROGRESS
- [x] S3.1 `claimstone/api_schema.py` (hand-declared per-route schemas, draft 2020-12, `additionalProperties: false` at each payload top level, verdict vocabulary and error codes as enums) + `tools/build_portal_api_schema.py` + committed `docs/contracts/portal-api.schema.json`
- [x] S3.2 `tests/test_api_contract.py`: minimal stdlib validator (`type`, `required`, `properties`, `enum`, `items`, `additionalProperties`) + A2 — every route payload validates; committed schema equals the regenerated one
- [x] S3.3 `tools/build_portal_fixtures.py` (deterministic `build_workspace` build: sanitized flow/profile rows, scrubbed env for `admin_state`, workspace path normalized to `<workspace>`) + committed `web/tests/fixtures/*.json`
- [ ] S3.4 `tests/test_portal_fixtures.py`: committed fixtures equal the regenerated ones
- [ ] S3.5 full checks green (`pytest -q`, `validate --all-projects`, `check_instrument_versions.py`)
NOT DONE:

