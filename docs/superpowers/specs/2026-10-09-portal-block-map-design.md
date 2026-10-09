# Portal block map — the flow page mirrors the logical schema

**Date:** 2026-10-09. **Branch:** `research-portal`. **Status:** design, awaiting operator review.

**Why.** The flow page shows the journey as a list of eight steps (`docs/contracts/journey.md`). The
operator's mental map of the project has six blocks, two of which the journey does not show: the
source-selection work that runs beside the pipeline, and the manual intake and decisions. The page
should mirror that map. One block, source selection, has no data in the portal today, so this design
adds a read for it, carried in the overview.

`CLAUDE.md` overrides everything here. The honesty rules of the journey spec hold for every new
element: unknown is `null` and "—", never 0; a summary is a fixed template chosen by status, never by
what a result says; no element reads a claim's stance or a profile's direction count.

## The six blocks

| Block | Plain name | Source of its status |
|---|---|---|
| Protocol | Protocollo | journey step 1 |
| Pipeline | Pipeline | journey steps 2–7 |
| Source selection | Selezione fonti | `journey.selection` (below) |
| Manual intake | Ingresso manuale | `journey.needs_you` |
| Execution | Esecuzione | `journey.running` |
| Human reading | Lettura umana | journey step 8 |

The UI uses names, never letters.

## Layout (chosen by the operator: strip above, detail below)

A strip of six tiles under the flow header, each with a status mark, one word and one figure. Selecting
a tile shows that block's detail under the strip.

- The selection lives in the URL (`?block=protocol|pipeline|selection|intake|execution|reading`).
- On open with no `block` parameter: the first block, in the order above, whose status is
  `waits_for_you` or `blocked`; otherwise Pipeline.
- Phone width: the strip becomes two tiles per row; no horizontal page scroll.
- Detail reuses existing components: Pipeline → `JourneySteps` (steps 2–7); Protocol → binding notice,
  `TheQuestions`, `TheTopic`; Manual intake → `NeedsYou` and the links to Add material and Decisions;
  Execution → `OperationsPanel`; Human reading → the signature `InboxCards`. Source selection is the
  one new component.

### Tile status

Computed on the server in `journey.py` (a `blocks` entry beside `steps`), so the browser renders what it
receives. `journey_version` becomes 2.

- **Protocol**: the status of step 1.
- **Pipeline**: from steps 2–7. `done` when all six are `done`; else `blocked` if any is `blocked`; else
  `running` if any is `running`; else `not_started` when all six are `not_started`; else `partial`
  (some work exists and some is missing). The figure is a count of steps ("2 of 6 steps done"), never a
  percentage: the steps have different bases.
- **Source selection**: never `done` (the cohort is not closed by this surface). `advisory` when every
  declared scope was read; `not_declared` when no scope is declared for the round; `unavailable` when any
  scope or the declaration file is in a named error state.
- **Manual intake**: `waits_for_you` when `needs_you.required` > 0; `idle` when the ledger reads and
  nothing required is open; `unavailable` when `required` is null; `not_applicable` for a legacy selector.
- **Execution**: `running` when an operation is "running for" a stage in the journey contract's sense;
  `idle` when none is; `unavailable` when `journey.running` is null.

- **Human reading**: the status of step 8.

Block statuses are the journey's statuses plus `idle`, `advisory`, `not_declared` and `unavailable`.

## Source selection: declaration and read

### Declaration

`store/<project>/audits/source-selection/scopes.json`, outside `projects/` so it is neither part of the
protocol digest (it would turn every flow `DRIFTED`) nor published. Entries:

```json
{"scopes": [{"scope_id": "...", "question_id": "L02", "round": "...",
             "inventory_path": "l02-v1/inventory.json", "inventory_sha256": "..."}]}
```

`inventory_path` is relative to `audits/source-selection/`. A path that leaves that directory is
refused.

### Where it is served (revised during planning)

There is no separate route. The tile needs the selection figures on every poll of the overview, so the
read lives in `claimstone/selection_view.py` and its result is carried in the overview, as
`journey.selection`; a second route would compute the same thing twice. The read is the overview's: GET
only, no write.

`selection_view.read(store, selector)` selects the scopes whose `round` is the selector's round, loads
each inventory, checks its sha256, and calls `source_selection.preview()` with no new rows. Result:

```json
{"selection_version": 1, "state": "DECLARED",
 "advisory": true, "assessment_status": "AI_PROVISIONAL",
 "cohort_closed": false, "admitted_candidates": 0,
 "scopes": [{"scope_id", "question_id", "state": "OK",
             "figures": {"inventory_count", "screened_count", "unobserved_count",
                         "direct", "context", "not_direct", "uncertain",
                         "identity_observations"}}]}
```

Counts come from the latest row per key (`supersedes` chains), so the 49 rows in `source_screening.jsonl`
give 48 observed. `pending_keys`, quotes and per-source evidence are not returned.

Named states instead of numbers (`figures` is `null`): top level `NO_SCOPE_DECLARED` and
`SCOPES_FILE_INVALID`; per scope `INVENTORY_UNREADABLE` (missing, unreadable, malformed, or a path that
leaves `audits/source-selection/`), `INVENTORY_DRIFTED`, `SCREENING_OUTSIDE_INVENTORY` and
`SELECTION_LEDGER_INVALID`. The other five tiles do not depend on it.

### Component

Shows the counts under the line "Advisory · AI_PROVISIONAL judgements · no admission", then
"cohort open · admitted 0". With `NO_SCOPE_DECLARED` it says no selection scope is declared for this flow
and that this does not mean there is nothing to select. Error states show a fixed sentence and no figures.

## Measured inputs

`source_selection.preview()` on `alembic-s4-lungo`, scope `l02-v2-ai-selection-2026-10-05`, question
`L02`, inventory `l02-v1/inventory.json` (830 keys, sha256
`fa160b117a84a071e975acb0422f3a6a47a47263b7f0445e4ed455e39c05ab67`), run 2026-10-09:
48 screened, 782 unobserved, 3 direct candidates, 21 context, 18 not direct, 6 uncertain,
3 identity observations, `cohort_closed` false, `admitted_candidates` 0. These are the expected values
of the live check below.

## Tests

- Backend: counts on a fixture ledger with a superseded row; one test per named state; the advisory
  fields always present; a path-escape in `inventory_path` refused (`INVENTORY_UNREADABLE`); store bytes identical before and
  after the call.
- Backend (`journey.py`): `blocks` for every combination of step statuses; Pipeline is the worst of six;
  Source selection is never `done`; unknown is `null`.
- Frontend: initial selection rule; URL round trip; "—" for unknown; the Source selection tile never
  rendered as done; the existing rule that only `control.ts` makes non-GET requests still passes.
- Live check: `journey.selection` on `alembic-s4-lungo` equals the figures above.

## In and out

In: `scopes.json` for `alembic-s4-lungo`, `selection_view.py`, the `blocks` and `selection` entries, the strip, the new component,
`docs/contracts/` updates (`journey.md`, a `scopes.json` section in `source_selection.md`), and a `DESIGN_DECISIONS`
entry citing the measurement above.

Out: the work queue and per-source detail; any write from the portal for this block; scopes for
`alembic-s4` and `alembic-s4-breve` (they show `NO_SCOPE_DECLARED`); pause and resume controls.

## Decision: which round owns the scope

Which flow shows a scope is decided by the `round` field. `-lungo`'s only flow is bound to round
`s4-l02-repository-copies-2026-10-06-v2`; the screening scope was built on the earlier `l02-v1`
inventory, which is not a round in the candidates ledger. Decided (2026-10-09, operator delegated the
choice): the existing scope is declared under the v2 round, the one flow that exists. The `round` field
is display routing only; it feeds no computation, so declaring it does not claim the inventory was
drawn from that round.
