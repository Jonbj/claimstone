# Portal journey — the guided research page, computed on the server

**Date:** 2026-10-08. **Branch:** `research-portal`. **Steps:** J1 (backend) and J2 (frontend), each done
by a delegated agent and reviewed before the next.

**Why.** The operator approved the guided journey (`docs/design/portal/v2/V2Journey.html`), but the flow
page shipped as a technical page. The data exists, but no endpoint turned it into a journey. Meaning is
decided on the server, so the server must produce the steps, and the browser renders them as received.

`CLAUDE.md` overrides everything here. Measured inputs: `round_state.state()` already gives, per stage,
`inputs`, `outputs`, `rejected`, `progress` and `detail`. `admissibility.admit()` gives the floor.
`operations_view` gives the scheduler's operations.

## J1 — backend: a `journey` block in the flow overview

Add `journey` to `portal_state.flow_overview()`, the read API's `…/flows/{id}/overview` and
`…/unbound/{slug}/overview`. Compute it from the `Computed` object and the reads that already exist. No
second pass over the ledgers.

Shape:

```json
{
  "journey_version": 1,
  "topics": [{"id", "label", "terms": [...]}],
  "questions": {"total", "literature", "operational"},
  "steps": [ {"n", "key", "title", "actor", "status", "summary", "figures": {...}} ],
  "needs_you": {"required": int|null, "optional": int|null, "ready_to_sign": int, "note": str|null},
  "running": [ {"operation_id", "stage", "state", "state_note"} ]
}
```

- `actor`: `"you"` or `"claimstone"`.
- `status`: one of `done`, `partial`, `running`, `waits_for_you`, `blocked`, `not_started`,
  `not_applicable`.
- `figures`: the numbers the summary quotes, with `null` where unknown. **Never 0 for unknown.**
- `summary`: one plain English sentence built only from `figures`. Templates are fixed strings with
  numbers filled in; no wording varies by result.

The eight steps and their rules. "Stage S" means the `StageState` named S in `rs.stages`; "running for
S" means an operation of this flow in `operations_view.continuing()` whose plan stage maps to S
(`discover`→discover, `acquire`→acquire, `normalize`→normalize, `extract-build` and
`extract-drain`→extract, `review-drain`→review, `synthesize`→synthesize).

| n | key | title | actor | status rule | figures |
|---|---|---|---|---|---|
| 1 | protocol | Protocol frozen | you | flow present: `done` if `binding_state.state == "CURRENT"`, else `blocked` (summary names the drifted parts); legacy selector: `not_applicable` ("protocol not verified") | registry_version, questions total/literature/operational, bound_at (the flow row's own timestamp field, read it; do not invent one) |
| 2 | search | Search the declared scope | claimstone | running for discover → `running`; outputs is None or 0 → `not_started`; `awaiting_discovery` in the floor's `blocking` → `partial`; else `done` | candidates (stage outputs), per class (`admitted.by_class[*].found`), stage detail verbatim as `note` |
| 3 | copies | Obtain legal copies | claimstone | running → `running`; found 0 or None → `not_started`; `admitted.status == "OK"` and `admitted.final` → `done`; `admitted.final` and status INSUFFICIENT → `blocked` (below floor); else `partial` | confirmed, found, rate, floor, status, not obtained = found − obtained, not_a_document count |
| 4 | documents | Prepare the documents | claimstone | running → `running`; normalize outputs None/0 and acquire outputs 0 → `not_started`; `awaiting_normalize` in blocking → `partial`; outputs > 0 → `done` | documents (outputs), rejected |
| 5 | annotate | Annotate every passage | claimstone | running → `running`; extract progress None → `not_started`; done == total → `done`; else `partial` | readings answered, readings expected, annotations kept (outputs), rejected |
| 6 | review | Independent review | claimstone | running → `running`; progress None → `not_started`; done == total → `done`; done > 0 → `partial`; else `not_started` | reviewed, accepted (total) |
| 7 | profiles | Evidence profiles | claimstone | `rs.unavailable` non-empty → `blocked` (summary is that text verbatim); synthesize outputs None/0 → `not_started`; any literature question provisional → `partial`; else `done` | profiles, provisional count, final count |
| 8 | sign | Read and sign | you | literature questions 0 → `not_applicable`; ready_to_sign > 0 → `waits_for_you`; all literature questions signed (non-stale verdict) → `done`; some signed → `partial`; else `not_started` | ready_to_sign (inbox `ADJUDICATION` cards), signed (verdicts not stale), literature total, operational |

`needs_you`:
- `ready_to_sign` is the number of `ADJUDICATION` inbox cards.
- `required` and `optional` come from `decisions.open_items(store, selector, flow_id)`, split on its
  `required` flag. For a legacy selector they are `null`, with
  `note: "decisions belong to a bound flow"`.
- The read API must not import the control server; `decisions` and `intake` are plain modules and may
  be read.

`running` is `operations_view.continuing()` filtered to this flow, with `[]` for a legacy selector. A
damaged operations ledger (`OperationError`) gives `running: null` and a named note, never a crash.

Schema and fixtures: add the shape to `claimstone/api_schema.py`; regenerate
`docs/contracts/portal-api.schema.json`, `web/tests/fixtures/*.json` and `web/src/lib/api-types.ts`. Bump
nothing else. Register `JOURNEY_VERSION` in `tools/check_instrument_versions.py` with a dated D entry: the
step rules are an operator-visible interpretation.

Tests (`tests/test_journey.py`):
- each status rule on a built workspace (`tests.test_portal_state.build_workspace` and small appended
  rows);
- unknown values stay `null`;
- a legacy selector gives step 1 `not_applicable` and `needs_you` null with its note;
- a running operation sets its step to `running` (plan one with `operations.plan` as
  `tests/test_operations.py` does, then authorize it);
- the read API serves the block (route test);
- no step reads claims' stances (F13-style: flipping stances changes no step status except 7 and 8).

Docs: a "Journey" section in `docs/contracts/` (new file `journey.md`) with the table above as built.

## J2 — frontend: the flow page as the journey

Rebuild `web/src/pages/FlowOverviewPage.tsx` as the design board `V2Journey.html` (layout and copy only):
- **Header:** project name and flow title in serif; a selector of research flows (bound flows, then
  legacy rounds as "History", labelled "protocol not verified"); the buttons Add material, Decisions,
  Export and Activity.
- **Left, "the journey":** the 8 steps from `journey.steps` in order:
  - a coloured segment bar with one segment per step, using the status colours: done emerald, running
    teal, waits_for_you violet, blocked rose, partial half-filled, not_started grey, not_applicable
    slate;
  - each step shows its number or a check, title, actor chip (Claimstone teal, you violet), summary
    verbatim and key figures.
  - Step 3 shows the floor ("floor met · 0.93 ≥ 0.80" or "below floor").
  - Step 8 shows "Read and sign Qnn" buttons for each ready question (from the existing question
    matrix: questions whose state is ready to sign), linking to the reading desk.
- **Right column:**
  - "Right now": the existing `OperationsPanel` (F3), kept;
  - "The topic": `journey.topics`, labels with their search terms;
  - "The questions": the existing question matrix rows, compact, each with its state chip;
  - "Needs you": counts from `journey.needs_you`, linking to Decisions.
- **Below, collapsed by default (`<details>`):** "Evidence path and technical details". It holds the
  existing KPIs, floor panel, source tracker and activity, unchanged.
- **Project page** (`/p/:project`): when the project has exactly one bound flow, or one with
  `binding_state.state == "CURRENT"` among several, redirect to that flow's journey. Otherwise list the
  flows as cards, as now. The integrity block and the ledger list move into a `<details>` "Technical
  details" section, collapsed.

Rules: §1 of `docs/superpowers/specs/2026-10-07-portal-frontend-v21-spec.md` applies. Render only what the
API returned; unknown is "—"; no computation of status in the browser. Tests:
- the steps render in server order with their status and summary verbatim;
- an unknown figure renders "—";
- the technical details are collapsed;
- the project page redirects to the single current flow.

## Checks (both steps)

```bash
.venv/bin/pytest -q
.venv/bin/claimstone validate --all-projects
.venv/bin/python tools/check_instrument_versions.py
cd web && npm run gen:types && npm run typecheck && npm test && npm run build
```

Commits:
- one per sub-task (`wip(J<n>.<k>): …`), then `feat(portal): J<n> …`;
- stage by explicit path, on `research-portal` only, never push, rebase, amend or reset;
- trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

Log: `docs/superpowers/plans/2026-10-08-portal-journey-progress.md` (plan first, then ticks, exact check
lines, decisions, deviations, NOT DONE).

Never write `store/` or `projects/`. Never run stage commands. No network.
