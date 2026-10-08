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

- [x] J1.1 `claimstone/journey.py` (eight step rules, fixed templates, topics, question counts,
      `needs_you`, `running`) wired into `portal_state.flow_overview` from the same `computed` and
      cards; schema in `api_schema.py`; contract schema, web fixtures and `api-types.ts`
      regenerated in the same commit because the contract and fixture tests compare them
      (files: `claimstone/journey.py`, `claimstone/portal_state.py`, `claimstone/api_schema.py`,
      `docs/contracts/portal-api.schema.json`, `web/tests/fixtures/**`, `web/src/lib/api-types.ts`)
- [x] J1.2 `JOURNEY_VERSION` registered in `tools/check_instrument_versions.py` with a dated D entry,
      `docs/contracts/journey.md` (files: `tools/check_instrument_versions.py`,
      `docs/DESIGN_DECISIONS.md`, `docs/contracts/journey.md`)
- [ ] J1.3 `tests/test_journey.py`: each status rule, nulls, legacy, running operation, route, F13
      (files: `tests/test_journey.py`)
- [ ] J1.4 real-project read-only sanity check, all checks, J1 marked DONE (files: this log)

The sub-task split changed from the plan: schema and regenerated artifacts moved into J1.1 because
the contract and fixture tests fail on any overview payload change until they are regenerated.
