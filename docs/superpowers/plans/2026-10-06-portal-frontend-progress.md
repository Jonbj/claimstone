# Portal frontend progress log

Working document for `docs/superpowers/specs/2026-10-06-portal-frontend-glm-prompt.md`
(spec: `docs/superpowers/specs/2026-10-06-portal-frontend-docker-design.md`).
One step per session; markers below are the authority for "what is next".

| step | marker |
|---|---|
| S1 shared transport base class out of `claimstone/portal.py` | TODO |
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
