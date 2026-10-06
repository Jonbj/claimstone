# Portal frontend progress log

Working document for `docs/superpowers/specs/2026-10-06-portal-frontend-glm-prompt.md`
(spec: `docs/superpowers/specs/2026-10-06-portal-frontend-docker-design.md`).
One step per session; markers below are the authority for "what is next".

| step | marker |
|---|---|
| S1 shared transport base class out of `claimstone/portal.py` | DONE |
| S2 `claimstone/api.py` + tests A1–A7 | TODO |
| S3 schema, validator, fixtures | TODO |
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
Deviations: none. Note, measured: the session's first baseline run printed `1191 passed, 7 skipped`; every later full run prints `1192 passed, 7 skipped`, and `pytest --collect-only` node ids are byte-identical (1199) with the pre-S1 files restored and at HEAD, so the change adds no test — the first run's count is an environment anomaly of that single execution, recorded rather than smoothed over
NOT DONE:
