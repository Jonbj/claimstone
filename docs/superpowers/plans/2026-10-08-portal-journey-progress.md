# Portal journey — progress log

Spec: `docs/superpowers/specs/2026-10-08-portal-journey-spec.md`. Branch `research-portal`.
Precedent for payload and schema work: `docs/superpowers/plans/2026-10-07-portal-backend-reads-progress.md` (BR).

## Step table

| step | content | done when | marker |
|---|---|---|---|
| **J1** | `journey` block in the flow overview, computed on the server; schema, fixtures, types, contract doc | J1's listed tests pass; all checks pass | IN PROGRESS |
| **J2** | the flow page rendered as the journey | J2's tests pass; all checks pass | TODO |

## Log entries

### J1 — IN PROGRESS

- [ ] J1.1 `claimstone/journey.py`: the eight step rules, fixed summary templates, topics and
      question counts, built only from `Computed` and the inbox cards (files: `claimstone/journey.py`)
- [ ] J1.2 `needs_you` and `running`, and the `journey` key wired into `portal_state.flow_overview`
      (no second ledger pass; no `control` import) (files: `claimstone/journey.py`,
      `claimstone/portal_state.py`)
- [ ] J1.3 schema in `api_schema.py`, `JOURNEY_VERSION` registered in
      `tools/check_instrument_versions.py` with a dated D entry, `docs/contracts/journey.md`
      (files: `claimstone/api_schema.py`, `tools/check_instrument_versions.py`,
      `docs/DESIGN_DECISIONS.md`, `docs/contracts/journey.md`, `docs/contracts/portal-api.schema.json`)
- [ ] J1.4 `tests/test_journey.py`: each status rule, nulls, legacy, running operation, route, F13
      (files: `tests/test_journey.py`)
- [ ] J1.5 fixtures and web types regenerated, every check green, J1 marked DONE
      (files: `web/tests/fixtures/**`, `web/src/lib/api-types.ts`, this log)
