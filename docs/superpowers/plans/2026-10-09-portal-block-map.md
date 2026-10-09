# Portal block map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The flow page shows six blocks (Protocol, Pipeline, Source selection, Manual intake, Execution, Human reading) as a strip of tiles with the selected block's detail under it, and the Source selection block gets real, advisory figures.

**Architecture:** The server decides everything. `claimstone/selection_view.py` reads a declared selection scope and calls the existing `source_selection.preview()`; `journey.py` adds `blocks` (six tiles) and `selection` to the `journey` block of the overview (`journey_version 2`); the browser renders them. No new route. The React side adds a `BlockMap` (tablist + panels, selection in `?block=`) and a `SelectionPanel`, and reuses the existing journey components inside the panels.

**Tech Stack:** Python 3.11 stdlib + the existing package (pytest); React 19, react-router 7, Tailwind, vitest + testing-library; `json2ts` for generated types.

**Spec:** `docs/superpowers/specs/2026-10-09-portal-block-map-design.md`. `CLAUDE.md` overrides this plan. Honesty rules that hold in every task: unknown is `null` and "—", never 0; a summary is a fixed template chosen by status; nothing reads a claim's stance; the selection block is advisory and never says `done`, `closed` or `admitted`.

**Commits:** the commit steps below are for whoever executes the plan *after the operator has authorized committing*; do not commit before that. End each commit message with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

**Baseline (2026-10-09):** `.venv/bin/pytest -q tests/test_journey.py tests/test_api_contract.py tests/test_portal_fixtures.py` → 27 passed; `cd web && npx vitest run` → 205 passed in 33 files.

## File structure

| File | Responsibility |
|---|---|
| `claimstone/selection_view.py` (new) | Read `scopes.json`, check inventories, call `preview()`, return the advisory `selection` dict. Read-only. |
| `claimstone/journey.py` (modify) | `blocks` (six tiles) and `selection` in `build()`; `JOURNEY_VERSION = 2`. |
| `claimstone/api_schema.py` (modify) | Schema for `journey.blocks` and `journey.selection`. |
| `docs/contracts/portal-api.schema.json`, `web/src/lib/api-types.ts`, `web/tests/fixtures/**` | Generated; regenerated, never hand-edited. |
| `web/src/components/JourneySteps.tsx` (modify) | `keys`, `heading`, `bar` props so a panel can show a subset of steps. |
| `web/src/components/SelectionPanel.tsx` (new) | The Source selection detail. |
| `web/src/components/BlockMap.tsx` (new) | Tiles, `?block=` selection, default rule, panels. |
| `web/src/pages/FlowOverviewPage.tsx` (modify) | Replace the journey + aside layout with `BlockMap`. |
| `tests/test_selection_view.py` (new), `tests/test_journey.py` (modify) | Backend tests. |
| `web/tests/blockmap.test.tsx`, `web/tests/selectionpanel.test.tsx` (new), `web/tests/flowpage.test.tsx` (modify) | Frontend tests. |
| `docs/contracts/journey.md`, `docs/contracts/source_selection.md`, `docs/DESIGN_DECISIONS.md` (modify) | Contract and decision record (D116). |

---

### Task 1: `selection_view` — the advisory read

**Files:**
- Create: `claimstone/selection_view.py`
- Test: `tests/test_selection_view.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_selection_view.py`:

```python
"""selection_view: the source-selection block of the journey. Advisory, read-only, and it names
its failures instead of showing zeros."""

from __future__ import annotations

import hashlib
import json

from claimstone import scope, selection_view
from claimstone import source_selection as selection
from claimstone.store import Store

H = "a" * 64
ROUND = "r1"


def _assessment(key, decision="UNCERTAIN", role="UNRESOLVED", supersedes=None):
    return selection.identified({
        "selection_version": selection.SOURCE_SELECTION_VERSION,
        "scope_id": "s1", "question_id": "Q1", "registry_sha256": H,
        "candidate_key": key, "source_class": "UNCLASSIFIED",
        "assessment_status": "AI_PROVISIONAL", "decision": decision, "role": role,
        "screening_level": "ABSTRACT", "criterion_ids": ["C1"], "reason": "fixture",
        "assessed_by": "test agent", "input_sha256": H,
        "evidence": [{"quote": "text", "locator": "fixture:1", "text_sha256": H}],
        "supersedes": supersedes,
    }, "assessment_id")


def _declare(store, keys, *, round_name=ROUND, path="inv/inventory.json", sha=None):
    base = store.path(selection_view.BASE_DIR)
    (base / "inv").mkdir(parents=True, exist_ok=True)
    data = json.dumps([{"candidate_key": key} for key in keys]).encode()
    (base / "inv" / "inventory.json").write_bytes(data)
    (base / "scopes.json").write_text(json.dumps({"scopes": [{
        "scope_id": "s1", "question_id": "Q1", "round": round_name,
        "inventory_path": path, "inventory_sha256": sha or hashlib.sha256(data).hexdigest()}]}))


def _screen(store, rows, inventory):
    selection.append_observations(store, rows, [], scope_id="s1", question_id="Q1",
                                  inventory_keys=set(inventory))


def _read(store):
    return selection_view.read(store, scope.Selector(ROUND))


def _tree(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


def _assert_advisory(result):
    assert result["advisory"] is True
    assert result["assessment_status"] == "AI_PROVISIONAL"
    assert result["cohort_closed"] is False
    assert result["admitted_candidates"] == 0
    assert result["selection_version"] == selection_view.SELECTION_VIEW_VERSION


def test_no_declaration_is_named_not_zero(tmp_path):
    result = _read(Store("fixture", base=tmp_path))
    assert result["state"] == "NO_SCOPE_DECLARED" and result["scopes"] == []
    _assert_advisory(result)


def test_a_scope_for_another_round_is_not_this_rounds(tmp_path):
    store = Store("fixture", base=tmp_path)
    _declare(store, ["a"], round_name="other")
    assert _read(store)["state"] == "NO_SCOPE_DECLARED"


def test_an_unreadable_declaration_is_named(tmp_path):
    store = Store("fixture", base=tmp_path)
    path = store.path(selection_view.SCOPES_FILE)
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    result = _read(store)
    assert result["state"] == "SCOPES_FILE_INVALID" and result["scopes"] == []
    _assert_advisory(result)


def test_counts_use_the_latest_row_per_key(tmp_path):
    store = Store("fixture", base=tmp_path)
    keys = ["a", "b", "c", "d"]
    first = _assessment("a")
    rows = [first,
            _assessment("a", "EXCLUDE", "CONTEXT", supersedes=first["assessment_id"]),
            _assessment("b", "INCLUDE", "DIRECT_CANDIDATE"),
            _assessment("c", "EXCLUDE", "NOT_DIRECT")]
    _declare(store, keys)
    _screen(store, rows, keys)
    result = _read(store)
    assert result["state"] == "DECLARED"
    (only,) = result["scopes"]
    assert only["state"] == "OK"
    assert only["scope_id"] == "s1" and only["question_id"] == "Q1"
    assert only["figures"] == {
        "inventory_count": 4, "screened_count": 3, "unobserved_count": 1,
        "direct": 1, "context": 1, "not_direct": 1, "uncertain": 0,
        "identity_observations": 0}
    _assert_advisory(result)


def test_a_drifted_inventory_shows_no_figures(tmp_path):
    store = Store("fixture", base=tmp_path)
    _declare(store, ["a", "b"], sha="0" * 64)
    (only,) = _read(store)["scopes"]
    assert only["state"] == "INVENTORY_DRIFTED" and only["figures"] is None


def test_a_missing_inventory_shows_no_figures(tmp_path):
    store = Store("fixture", base=tmp_path)
    _declare(store, ["a"], path="inv/nowhere.json")
    (only,) = _read(store)["scopes"]
    assert only["state"] == "INVENTORY_UNREADABLE" and only["figures"] is None


def test_an_inventory_path_that_leaves_the_directory_is_refused(tmp_path):
    store = Store("fixture", base=tmp_path)
    outside = tmp_path / "fixture" / "outside.json"
    data = json.dumps([{"candidate_key": "a"}]).encode()
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(data)
    _declare(store, ["a"], path="../../outside.json", sha=hashlib.sha256(data).hexdigest())
    (only,) = _read(store)["scopes"]
    assert only["state"] == "INVENTORY_UNREADABLE" and only["figures"] is None


def test_screening_outside_the_inventory_is_named(tmp_path):
    store = Store("fixture", base=tmp_path)
    _screen(store, [_assessment("a"), _assessment("b")], ["a", "b"])
    _declare(store, ["a"])
    (only,) = _read(store)["scopes"]
    assert only["state"] == "SCREENING_OUTSIDE_INVENTORY" and only["figures"] is None


def test_an_invalid_screening_ledger_is_named(tmp_path):
    store = Store("fixture", base=tmp_path)
    store.append(selection.SCREENING_LEDGER, {"x": 1})
    _declare(store, ["a"])
    (only,) = _read(store)["scopes"]
    assert only["state"] == "SELECTION_LEDGER_INVALID" and only["figures"] is None


def test_the_read_writes_nothing(tmp_path):
    store = Store("fixture", base=tmp_path)
    keys = ["a", "b"]
    _declare(store, keys)
    _screen(store, [_assessment("a")], keys)
    before = _tree(store.root)
    _read(store)
    _read(store)
    assert _tree(store.root) == before
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest -q tests/test_selection_view.py`
Expected: FAIL at collection with `ImportError: cannot import name 'selection_view' from 'claimstone'`.

- [ ] **Step 3: Write the implementation**

Create `claimstone/selection_view.py`:

```python
"""The source-selection block of the journey: advisory counts, never an admission.

`source_selection.py` owns the append-only screening and identity ledgers. Its observations are
`AI_PROVISIONAL`: they can order work, but they never change a round's denominator, close a cohort
or admit a source. This module reads them for the portal and keeps that true in the shape it
returns — `advisory`, `assessment_status`, `cohort_closed` and `admitted_candidates` are always
present, and a failure is a named state with `figures: null`, never a count of 0.

A scope is declared in `store/<project>/audits/source-selection/scopes.json`, outside `projects/`
on purpose: the observations are advisory, so declaring one must not change the protocol digest
and turn every bound flow `DRIFTED`. The declaration names the inventory file and its sha256; the
inventory is what makes "not yet observed" a number, and a changed inventory is `INVENTORY_DRIFTED`.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from claimstone import source_selection
from claimstone.store import LedgerCorrupt, Store

SELECTION_VIEW_VERSION = 1

BASE_DIR = "audits/source-selection"
SCOPES_FILE = f"{BASE_DIR}/scopes.json"

DECLARED = "DECLARED"
NO_SCOPE_DECLARED = "NO_SCOPE_DECLARED"
SCOPES_FILE_INVALID = "SCOPES_FILE_INVALID"

OK = "OK"
INVENTORY_UNREADABLE = "INVENTORY_UNREADABLE"
INVENTORY_DRIFTED = "INVENTORY_DRIFTED"
SCREENING_OUTSIDE_INVENTORY = "SCREENING_OUTSIDE_INVENTORY"
SELECTION_LEDGER_INVALID = "SELECTION_LEDGER_INVALID"

_ENTRY_FIELDS = ("scope_id", "question_id", "round", "inventory_path", "inventory_sha256")


class _Refused(Exception):
    def __init__(self, state: str) -> None:
        super().__init__(state)
        self.state = state


def _result(state: str, scopes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"selection_version": SELECTION_VIEW_VERSION, "state": state,
            "advisory": True, "assessment_status": "AI_PROVISIONAL",
            "cohort_closed": False, "admitted_candidates": 0, "scopes": scopes or []}


def _declared(store: Store) -> list[dict[str, Any]] | None:
    """The declared entries, `[]` when there is no file, `None` when it cannot be trusted."""
    path = store.path(SCOPES_FILE)
    if not path.exists():
        return []
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))["scopes"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(entries, list) or not all(
            isinstance(entry, dict)
            and all(isinstance(entry.get(field), str) and entry[field] for field in _ENTRY_FIELDS)
            for entry in entries):
        return None
    return entries


def _inventory_keys(store: Store, entry: dict[str, Any]) -> set[str]:
    base = store.path(BASE_DIR).resolve()
    path = (base / entry["inventory_path"]).resolve()
    if base not in path.parents:
        raise _Refused(INVENTORY_UNREADABLE)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise _Refused(INVENTORY_UNREADABLE) from exc
    if hashlib.sha256(data).hexdigest() != entry["inventory_sha256"]:
        raise _Refused(INVENTORY_DRIFTED)
    try:
        return {str(row["candidate_key"]) for row in json.loads(data)}
    except (ValueError, KeyError, TypeError) as exc:
        raise _Refused(INVENTORY_UNREADABLE) from exc


def _scope(store: Store, entry: dict[str, Any]) -> dict[str, Any]:
    head = {"scope_id": entry["scope_id"], "question_id": entry["question_id"]}
    try:
        keys = _inventory_keys(store, entry)
        view = source_selection.preview(store, entry["scope_id"], entry["question_id"], keys)
    except _Refused as refused:
        return {**head, "state": refused.state, "figures": None}
    except LedgerCorrupt:
        return {**head, "state": SELECTION_LEDGER_INVALID, "figures": None}
    except ValueError as exc:
        state = (SCREENING_OUTSIDE_INVENTORY if "outside the frozen inventory" in str(exc)
                 else SELECTION_LEDGER_INVALID)
        return {**head, "state": state, "figures": None}
    return {**head, "state": OK, "figures": {
        "inventory_count": view["inventory_count"], "screened_count": view["screened_count"],
        "unobserved_count": view["unobserved_count"],
        "direct": view["provisional_direct_candidates"],
        "context": view["provisional_context"],
        "not_direct": view["provisional_not_direct"],
        "uncertain": view["provisional_uncertain"],
        "identity_observations": view["identity_observations"]}}


def read(store: Store, selector: Any) -> dict[str, Any]:
    """The advisory selection block for one round selector. Never writes."""
    declared = _declared(store)
    if declared is None:
        return _result(SCOPES_FILE_INVALID)
    mine = [entry for entry in declared if entry["round"] == selector.round]
    if not mine:
        return _result(NO_SCOPE_DECLARED)
    return _result(DECLARED, [_scope(store, entry) for entry in mine])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest -q tests/test_selection_view.py`
Expected: `10 passed`.

- [ ] **Step 5: Commit**

```bash
git add claimstone/selection_view.py tests/test_selection_view.py
git commit -m "feat(portal): selection_view, the advisory read of declared selection scopes"
```

---

### Task 2: `journey` — the six blocks and the selection

**Files:**
- Modify: `claimstone/journey.py` (imports, `JOURNEY_VERSION`, `_running_stages`, new block functions, `build`)
- Modify: `tests/test_journey.py` (imports, the version assertion, new tests)

- [ ] **Step 1: Write the failing tests**

In `tests/test_journey.py`, change the imports at the top:

```python
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from claimstone import flows, journey, operations, portal_state, round_state, scope
```
(keep the lines that follow unchanged), and change line 77 from `== journey.JOURNEY_VERSION == 1` to `== journey.JOURNEY_VERSION == 2`.

Append to the end of `tests/test_journey.py`:

```python
# --- the six blocks ---------------------------------------------------------------------------

PIPELINE_KEYS = ["search", "copies", "documents", "annotate", "review", "profiles"]
BLOCK_KEYS = ["protocol", "pipeline", "selection", "intake", "execution", "reading"]


def _pipeline_steps(statuses):
    return [{"key": key, "status": status} for key, status in zip(PIPELINE_KEYS, statuses)]


def test_the_overview_carries_six_blocks_in_order(tmp_path):
    _pd, _sd, project, store = build_workspace(tmp_path)
    block = _overview(project, store)["journey"]
    assert [b["key"] for b in block["blocks"]] == BLOCK_KEYS
    for tile in block["blocks"]:
        assert tile["status"] in journey.BLOCK_STATUSES
        assert isinstance(tile["title"], str) and isinstance(tile["figure"], str)
    assert block["selection"]["state"] == "NO_SCOPE_DECLARED"


@pytest.mark.parametrize("statuses,expected", [
    (["done"] * 6, "done"),
    (["done", "done", "blocked", "done", "done", "done"], "blocked"),
    (["done", "partial", "running", "not_started", "not_started", "not_started"], "running"),
    (["not_started"] * 6, "not_started"),
    (["done"] + ["not_started"] * 5, "partial"),
    (["partial"] + ["not_started"] * 5, "partial"),
])
def test_pipeline_tile_status_rule(statuses, expected):
    assert journey._pipeline_block(_pipeline_steps(statuses))["status"] == expected


def test_pipeline_tile_figure_counts_steps_not_percent():
    tile = journey._pipeline_block(_pipeline_steps(["done"] * 2 + ["partial"] + ["not_started"] * 3))
    assert tile["figure"] == "2 of 6 steps done"


def test_selection_tile_is_never_done_and_names_every_state():
    def sel(state, scopes=()):
        return {"state": state, "scopes": list(scopes)}

    def ok(screened=48, unobserved=782):
        return {"scope_id": "s", "question_id": "Q", "state": "OK",
                "figures": {"screened_count": screened, "unobserved_count": unobserved}}

    bad = {"scope_id": "s", "question_id": "Q", "state": "INVENTORY_DRIFTED", "figures": None}
    assert journey._selection_block(sel("NO_SCOPE_DECLARED"))["status"] == "not_declared"
    assert journey._selection_block(sel("SCOPES_FILE_INVALID"))["status"] == "unavailable"
    assert journey._selection_block(sel("DECLARED", [bad]))["status"] == "unavailable"
    tile = journey._selection_block(sel("DECLARED", [ok()]))
    assert tile["status"] == "advisory" and tile["figure"] == "48 seen · 782 unseen"
    # Even with nothing left unobserved the block stays advisory: this surface closes no cohort.
    assert journey._selection_block(sel("DECLARED", [ok(830, 0)]))["status"] == "advisory"
    assert journey._selection_block(sel("DECLARED", [ok(), ok()]))["figure"] == "2 scopes"


def test_intake_tile_rules():
    waiting = journey._intake_block({"x": 1}, {"required": 2, "optional": 1})
    assert waiting["status"] == "waits_for_you" and waiting["figure"] == "2 required · 1 optional"
    assert journey._intake_block({"x": 1}, {"required": 0, "optional": 3})["status"] == "idle"
    unreadable = journey._intake_block({"x": 1}, {"required": None, "optional": None})
    assert unreadable["status"] == "unavailable" and unreadable["figure"] == "— required · — optional"
    assert journey._intake_block(None, {"required": None, "optional": None})["status"] == "not_applicable"


def test_execution_tile_rules():
    assert journey._execution_block(None)["status"] == "unavailable"
    idle = journey._execution_block([])
    assert idle["status"] == "idle" and idle["figure"] == "0 running · 0 listed"
    authorized = [{"stage": "extract-drain", "state": "AUTHORIZED"}]
    assert journey._execution_block(authorized)["status"] == "idle"
    live = [{"stage": "extract-drain", "state": "RUNNING_OR_LOCK_HELD"}, authorized[0]]
    tile = journey._execution_block(live)
    assert tile["status"] == "running" and tile["figure"] == "1 running · 2 listed"


def test_a_legacy_selector_has_a_protocol_tile_that_says_it_is_not_verified(tmp_path):
    _pd, _sd, project, store = build_workspace(tmp_path)
    tiles = {b["key"]: b for b in _overview(project, store, "r2")["journey"]["blocks"]}
    assert tiles["protocol"]["status"] == "not_applicable"
    assert tiles["protocol"]["figure"] == "protocol not verified"
    assert tiles["intake"]["status"] == "not_applicable"


def test_selection_is_carried_in_the_overview_and_the_read_writes_nothing(tmp_path):
    _pd, _sd, project, store = build_workspace(tmp_path)
    base = store.path("audits/source-selection")
    (base / "inv").mkdir(parents=True)
    data = json.dumps([{"candidate_key": key} for key in ("x", "y", "z")]).encode()
    (base / "inv" / "inventory.json").write_bytes(data)
    (base / "scopes.json").write_text(json.dumps({"scopes": [{
        "scope_id": "s1", "question_id": "Q1", "round": "r1",
        "inventory_path": "inv/inventory.json",
        "inventory_sha256": hashlib.sha256(data).hexdigest()}]}))
    audits = store.path("audits")
    before = {p: p.read_bytes() for p in audits.rglob("*") if p.is_file()}
    block = _overview(project, store)["journey"]
    assert block["selection"]["state"] == "DECLARED"
    assert block["selection"]["scopes"][0]["figures"]["unobserved_count"] == 3
    tile = {b["key"]: b for b in block["blocks"]}["selection"]
    assert tile["status"] == "advisory" and tile["figure"] == "0 seen · 3 unseen"
    assert {p: p.read_bytes() for p in audits.rglob("*") if p.is_file()} == before
    assert not store.path("source_screening.jsonl").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest -q tests/test_journey.py`
Expected: FAIL — `AttributeError: module 'claimstone.journey' has no attribute 'BLOCK_STATUSES'` (and the version assertion).

- [ ] **Step 3: Write the implementation**

In `claimstone/journey.py`:

(a) Imports and constants. Replace
`from claimstone import admissibility, decisions, operations_view` with
`from claimstone import admissibility, decisions, operations_view, selection_view`,
replace `JOURNEY_VERSION = 1` with `JOURNEY_VERSION = 2`, and add after the `STATUSES = (...)` tuple:

```python
# The six blocks of the flow page. A block's status is a step's status where one block is one step,
# and one of four more words where it is not: `idle` (the ledger reads and nothing is waiting),
# `advisory` (source selection: figures exist, nothing is admitted), `not_declared` and
# `unavailable` (a named failure; never a zero).
BLOCK_STATUSES = STATUSES + ("idle", "advisory", "not_declared", "unavailable")
PIPELINE_STEP_KEYS = ("search", "copies", "documents", "annotate", "review", "profiles")
```

(b) Replace `_running_stages` with a version that shares one definition of "in flight":

```python
def _in_flight(running: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Operations with work actually in flight. An authorized operation no worker has started, and
    an interrupted one, stay listed in `running` with their state, but they do not make a step say
    Claimstone is working: that would be a claim no recorded event supports (D107, review of J1)."""
    return [item for item in running or []
            if item.get("stage") in OPERATION_STAGE
            and item.get("state") == "RUNNING_OR_LOCK_HELD"]


def _running_stages(running: list[dict[str, Any]] | None) -> set[str]:
    return {OPERATION_STAGE[item["stage"]] for item in _in_flight(running)}
```

(c) Insert before the `# --- the two small reads` comment:

```python
# --- the six blocks ---------------------------------------------------------------------------


def _block(key: str, title: str, status: str, template: str,
           figures: Mapping[str, Any]) -> dict[str, Any]:
    assert status in BLOCK_STATUSES, status
    return {"key": key, "title": title, "status": status,
            "figure": sentence(template, figures)}


def _protocol_block(steps: list[dict[str, Any]]) -> dict[str, Any]:
    protocol = steps[0]
    if protocol["status"] == "not_applicable":
        return _block("protocol", "Protocol", "not_applicable", "protocol not verified", {})
    copies = next(step for step in steps if step["key"] == "copies")
    figures = {"questions_total": protocol["figures"]["questions_total"],
               "floor": copies["figures"]["floor"]}
    return _block("protocol", "Protocol", protocol["status"],
                  "{questions_total} questions · floor {floor}", figures)


def _pipeline_block(steps: list[dict[str, Any]]) -> dict[str, Any]:
    """From steps 2-7. A count of steps, never a percentage: the steps have different bases."""
    middle = [step for step in steps if step["key"] in PIPELINE_STEP_KEYS]
    seen = {step["status"] for step in middle}
    if seen == {"done"}:
        status = "done"
    elif "blocked" in seen:
        status = "blocked"
    elif "running" in seen:
        status = "running"
    elif seen == {"not_started"}:
        status = "not_started"
    else:
        status = "partial"  # some work exists and some is missing
    figures = {"done": sum(1 for step in middle if step["status"] == "done"),
               "total": len(middle)}
    return _block("pipeline", "Pipeline", status, "{done} of {total} steps done", figures)


def _selection_block(selection: Mapping[str, Any]) -> dict[str, Any]:
    """Never `done`: this surface does not close a cohort."""
    state, scopes = selection["state"], selection["scopes"]
    if state == selection_view.NO_SCOPE_DECLARED:
        return _block("selection", "Source selection", "not_declared",
                      "no scope for this flow", {})
    if state == selection_view.SCOPES_FILE_INVALID:
        return _block("selection", "Source selection", "unavailable",
                      "declaration unreadable", {})
    if any(scope["state"] != selection_view.OK for scope in scopes):
        return _block("selection", "Source selection", "unavailable",
                      "{n} scope(s) unreadable",
                      {"n": sum(1 for scope in scopes if scope["state"] != selection_view.OK)})
    if len(scopes) == 1:
        return _block("selection", "Source selection", "advisory",
                      "{screened_count} seen · {unobserved_count} unseen", scopes[0]["figures"])
    return _block("selection", "Source selection", "advisory", "{n} scopes", {"n": len(scopes)})


def _intake_block(flow_row: dict[str, Any] | None, needs: Mapping[str, Any]) -> dict[str, Any]:
    if flow_row is None:
        return _block("intake", "Manual intake", "not_applicable",
                      "decisions belong to a bound flow", {})
    template = "{required} required · {optional} optional"
    if needs["required"] is None:
        status = "unavailable"
    elif needs["required"] > 0:
        status = "waits_for_you"
    else:
        status = "idle"
    return _block("intake", "Manual intake", status, template, needs)


def _execution_block(running: list[dict[str, Any]] | None) -> dict[str, Any]:
    if running is None:
        return _block("execution", "Execution", "unavailable", "operations unreadable", {})
    live = len(_in_flight(running))
    return _block("execution", "Execution", "running" if live else "idle",
                  "{live} running · {listed} listed", {"live": live, "listed": len(running)})


def _reading_block(steps: list[dict[str, Any]]) -> dict[str, Any]:
    sign = steps[-1]
    if sign["status"] == "not_applicable":
        return _block("reading", "Human reading", "not_applicable",
                      "no literature question", {})
    return _block("reading", "Human reading", sign["status"],
                  "{ready_to_sign} to sign · {signed} of {literature_total} signed",
                  sign["figures"])
```

(d) Replace the body of `build()` from `return {` to the end with:

```python
    steps = [
        _protocol(project, flow_row, binding),
        _search(rs, admitted, active),
        _copies(rs, admitted, active),
        _documents(rs, admitted, active),
        _annotate(rs, active),
        _review(rs, active),
        _profiles(rs, active, refused),
        _sign(rs, ready),
    ]
    needs = needs_you(store, selector, flow_row, ready)
    selection = selection_view.read(store, selector)
    return {
        "journey_version": JOURNEY_VERSION,
        "topics": topics_block(project),
        "questions": questions_block(project),
        "steps": steps,
        "blocks": [
            _protocol_block(steps),
            _pipeline_block(steps),
            _selection_block(selection),
            _intake_block(flow_row, needs),
            _execution_block(running),
            _reading_block(steps),
        ],
        "selection": selection,
        "needs_you": needs,
        "running": running,
        "running_note": running_note,
    }
```

- [ ] **Step 4: Run the journey tests to verify they pass**

Run: `.venv/bin/pytest -q tests/test_journey.py tests/test_selection_view.py`
Expected: all pass (the three earlier `test_journey.py` tests that compare exact payloads keep passing because they read `steps`, not the whole block). If `tests/test_journey.py::test_route_serves_the_block_and_stays_get_only` fails with a schema error, that is Task 3's job (the API schema), continue to Task 3 before running the whole suite.

- [ ] **Step 5: Commit**

```bash
git add claimstone/journey.py tests/test_journey.py
git commit -m "feat(portal): journey blocks and selection (journey_version 2)"
```

---

### Task 3: Schema, generated types and fixtures

**Files:**
- Modify: `claimstone/api_schema.py` (`_JOURNEY`)
- Regenerate: `docs/contracts/portal-api.schema.json`, `web/src/lib/api-types.ts`, `web/tests/fixtures/**`

- [ ] **Step 1: Add the failing contract test**

Append to `tests/test_api_contract.py`:

```python
def test_journey_block_statuses_match_the_schema():
    from claimstone import api_schema, journey
    assert tuple(api_schema.JOURNEY_BLOCK_STATUSES) == journey.BLOCK_STATUSES
```

Run: `.venv/bin/pytest -q tests/test_api_contract.py -k journey_block`
Expected: FAIL with `AttributeError: module 'claimstone.api_schema' has no attribute 'JOURNEY_BLOCK_STATUSES'`.

- [ ] **Step 2: Declare the schema**

In `claimstone/api_schema.py`, right after the `_JOURNEY_STEP = {...}` definition add:

```python
# journey.BLOCK_STATUSES: the six blocks' statuses (a step's, plus four words of their own).
JOURNEY_BLOCK_STATUSES = JOURNEY_STATUSES + ("idle", "advisory", "not_declared", "unavailable")

_JOURNEY_BLOCK = {
    "type": "object",
    "required": ["key", "title", "status", "figure"],
    "properties": {
        "key": _STR, "title": _STR,
        "status": {"type": "string", "enum": list(JOURNEY_BLOCK_STATUSES)},
        "figure": _STR,
    },
    "additionalProperties": False,
}

_SELECTION_FIGURES = {
    "type": ["object", "null"],
    "required": ["inventory_count", "screened_count", "unobserved_count", "direct", "context",
                 "not_direct", "uncertain", "identity_observations"],
    "properties": {name: _INT for name in (
        "inventory_count", "screened_count", "unobserved_count", "direct", "context",
        "not_direct", "uncertain", "identity_observations")},
    "additionalProperties": False,
}

# Advisory by construction: `advisory` is always true, nothing is ever admitted or closed here.
_SELECTION = {
    "type": "object",
    "required": ["selection_version", "state", "advisory", "assessment_status", "cohort_closed",
                 "admitted_candidates", "scopes"],
    "properties": {
        "selection_version": _INT,
        "state": {"type": "string",
                  "enum": ["DECLARED", "NO_SCOPE_DECLARED", "SCOPES_FILE_INVALID"]},
        "advisory": {"const": True},
        "assessment_status": {"const": "AI_PROVISIONAL"},
        "cohort_closed": {"const": False},
        "admitted_candidates": {"const": 0},
        "scopes": {"type": "array", "items": {
            "type": "object",
            "required": ["scope_id", "question_id", "state", "figures"],
            "properties": {
                "scope_id": _STR, "question_id": _STR,
                "state": {"type": "string", "enum": [
                    "OK", "INVENTORY_UNREADABLE", "INVENTORY_DRIFTED",
                    "SCREENING_OUTSIDE_INVENTORY", "SELECTION_LEDGER_INVALID"]},
                "figures": _SELECTION_FIGURES,
            },
            "additionalProperties": False}},
    },
    "additionalProperties": False,
}
```

In `_JOURNEY`, change `"required": ["journey_version", "topics", "questions", "steps", "needs_you", "running", "running_note"]` to include the two new keys, i.e.

```python
    "required": ["journey_version", "topics", "questions", "steps", "blocks", "selection",
                 "needs_you", "running", "running_note"],
```
and add under `"steps": {"type": "array", "items": _JOURNEY_STEP},`:

```python
        "blocks": {"type": "array", "items": _JOURNEY_BLOCK},
        "selection": _SELECTION,
```

- [ ] **Step 3: Regenerate the schema file, the types and the fixtures**

Run, in this order:

```bash
.venv/bin/python tools/build_portal_api_schema.py
(cd web && npm run gen:types)
.venv/bin/python tools/build_portal_fixtures.py
```
Expected: the first prints `wrote contracts/portal-api.schema.json (... bytes, ... routes)`; `git diff --stat` shows changes in `docs/contracts/portal-api.schema.json`, `web/src/lib/api-types.ts`, `web/tests/fixtures/meta.json` (journey_version 2) and every `overview.json` fixture.

- [ ] **Step 4: Run both sides**

Run: `.venv/bin/pytest -q tests/test_api_contract.py tests/test_portal_fixtures.py tests/test_journey.py tests/test_selection_view.py`
Expected: all pass.
Run: `(cd web && npx vitest run tests/api-types.test.ts && npm run typecheck)`
Expected: `api-types.test.ts` passes; typecheck is clean (no frontend code uses the new fields yet).

- [ ] **Step 5: Commit**

```bash
git add claimstone/api_schema.py tests/test_api_contract.py docs/contracts/portal-api.schema.json web/src/lib/api-types.ts web/tests/fixtures
git commit -m "feat(portal): schema, types and fixtures for journey blocks and selection"
```

---

### Task 4: `JourneySteps` can show a subset of steps

**Files:**
- Modify: `web/src/components/JourneySteps.tsx` (the default export's signature and the first lines of its body)
- Test: `web/tests/journey.test.tsx`

- [ ] **Step 1: Write the failing test**

Append inside the `describe("J2: JourneySteps", ...)` block of `web/tests/journey.test.tsx`, before its closing `});`:

```tsx
  it("shows only the steps named in `keys`, with a chosen heading and no bar", () => {
    render(
      <MemoryRouter>
        <JourneySteps journey={journey} rows={rows} base="/p/demo/f/sel1" writable
                      keys={["copies", "documents"]} heading="Pipeline" bar={false} />
      </MemoryRouter>,
    );
    const shown = Array.from(document.querySelectorAll("[data-step]")).map((n) => n.getAttribute("data-step"));
    expect(shown).toEqual(["copies", "documents"]);
    expect(screen.getByRole("heading", { name: "Pipeline" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "The journey" })).toBeNull();
    expect(screen.queryByLabelText("Journey progress")).toBeNull();
  });

  it("a null heading renders no heading at all", () => {
    render(
      <MemoryRouter>
        <JourneySteps journey={journey} rows={rows} base="/p/demo/f/sel1" writable
                      keys={["protocol"]} heading={null} bar={false} />
      </MemoryRouter>,
    );
    expect(document.querySelector("section h2")).toBeNull();
    expect(document.querySelectorAll("[data-step]")).toHaveLength(1);
  });
```

Run: `(cd web && npx vitest run tests/journey.test.tsx)`
Expected: the two new tests FAIL (the extra props are ignored, so all steps render).

- [ ] **Step 2: Implement**

In `web/src/components/JourneySteps.tsx`, replace

```tsx
export default function JourneySteps({
  journey, rows, base, writable,
}: {
  journey: Journey;
  rows: MatrixRow[];
  base: string;
  writable: boolean;
}) {
  const ready = readyToSign(rows);
  return (
    <section aria-label="The journey" className="flex flex-col gap-4">
      <h2 className="text-base font-semibold">The journey</h2>
      <SegmentBar steps={journey.steps} />
      <ol className="flex flex-col gap-3">
        {journey.steps.map((step) => {
```

with

```tsx
// `keys`, `heading` and `bar` let a block panel show part of the journey: the flow page puts step 1
// under Protocol, steps 2-7 under Pipeline and step 8 under Human reading. Defaults keep the whole
// journey, as before. Nothing here decides a status; the steps are the server's.
export default function JourneySteps({
  journey, rows, base, writable, keys, heading = "The journey", bar = true,
}: {
  journey: Journey;
  rows: MatrixRow[];
  base: string;
  writable: boolean;
  keys?: readonly string[];
  heading?: string | null;
  bar?: boolean;
}) {
  const ready = readyToSign(rows);
  const steps = keys ? journey.steps.filter((step) => keys.includes(step.key)) : journey.steps;
  return (
    <section aria-label={heading ?? "Journey steps"} className="flex flex-col gap-4">
      {heading === null ? null : <h2 className="text-base font-semibold">{heading}</h2>}
      {bar ? <SegmentBar steps={steps} /> : null}
      <ol className="flex flex-col gap-3">
        {steps.map((step) => {
```

- [ ] **Step 3: Run the tests**

Run: `(cd web && npx vitest run tests/journey.test.tsx)`
Expected: all pass, including the original J2 tests.

- [ ] **Step 4: Commit**

```bash
git add web/src/components/JourneySteps.tsx web/tests/journey.test.tsx
git commit -m "feat(portal): JourneySteps can show a subset of steps"
```

---

### Task 5: `SelectionPanel`

**Files:**
- Create: `web/src/components/SelectionPanel.tsx`
- Test: `web/tests/selectionpanel.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `web/tests/selectionpanel.test.tsx`:

```tsx
// The Source selection detail: advisory by construction, named failures, no figure on error.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import SelectionPanel from "@/components/SelectionPanel";
import type { Journey } from "@/components/JourneySteps";

type Selection = Journey["selection"];

const figures = {
  inventory_count: 830, screened_count: 48, unobserved_count: 782, direct: 3, context: 21,
  not_direct: 18, uncertain: 6, identity_observations: 3,
};

function declared(over: Partial<Selection["scopes"][number]> = {}): Selection {
  return {
    selection_version: 1, state: "DECLARED", advisory: true, assessment_status: "AI_PROVISIONAL",
    cohort_closed: false, admitted_candidates: 0,
    scopes: [{ scope_id: "l02-v2", question_id: "L02", state: "OK", figures, ...over }],
  };
}

describe("SelectionPanel", () => {
  afterEach(cleanup);

  it("says in words that it is advisory, and that nothing is admitted", () => {
    render(<SelectionPanel selection={declared()} />);
    expect(screen.getByText(/Advisory · AI_PROVISIONAL judgements/)).toBeTruthy();
    expect(screen.getByText(/cohort open · admitted 0/)).toBeTruthy();
  });

  it("shows the counts as received", () => {
    render(<SelectionPanel selection={declared()} />);
    const get = (name: string) => document.querySelector(`[data-figure="${name}"] dd`)?.textContent;
    expect(get("direct")).toBe("3");
    expect(get("context")).toBe("21");
    expect(get("not_direct")).toBe("18");
    expect(get("uncertain")).toBe("6");
    expect(get("unobserved_count")).toBe("782");
    expect(screen.getByText("L02")).toBeTruthy();
    expect(screen.getByText("l02-v2")).toBeTruthy();
  });

  it("no scope declared is a sentence, not a zero", () => {
    render(<SelectionPanel selection={{
      selection_version: 1, state: "NO_SCOPE_DECLARED", advisory: true,
      assessment_status: "AI_PROVISIONAL", cohort_closed: false, admitted_candidates: 0, scopes: [],
    }} />);
    expect(screen.getByText("No selection scope is declared for this flow.")).toBeTruthy();
    expect(screen.getByText("This does not mean there is nothing to select.")).toBeTruthy();
    expect(document.querySelector("[data-figure]")).toBeNull();
  });

  it("an unreadable declaration shows a sentence and no figures", () => {
    render(<SelectionPanel selection={{
      selection_version: 1, state: "SCOPES_FILE_INVALID", advisory: true,
      assessment_status: "AI_PROVISIONAL", cohort_closed: false, admitted_candidates: 0, scopes: [],
    }} />);
    expect(screen.getByText(/declaration cannot be read/)).toBeTruthy();
    expect(document.querySelector("[data-figure]")).toBeNull();
  });

  it.each([
    ["INVENTORY_UNREADABLE", /inventory file cannot be read/],
    ["INVENTORY_DRIFTED", /no longer matches the hash declared/],
    ["SCREENING_OUTSIDE_INVENTORY", /not in the declared inventory/],
    ["SELECTION_LEDGER_INVALID", /screening ledger is not valid/],
  ] as const)("a scope in %s names it and shows no figures", (state, text) => {
    render(<SelectionPanel selection={declared({ state, figures: null })} />);
    expect(screen.getByText(text)).toBeTruthy();
    expect(screen.getByText(state)).toBeTruthy();
    expect(document.querySelector("[data-figure]")).toBeNull();
  });
});
```

Run: `(cd web && npx vitest run tests/selectionpanel.test.tsx)`
Expected: FAIL — `Failed to resolve import "@/components/SelectionPanel"`.

- [ ] **Step 2: Implement**

Create `web/src/components/SelectionPanel.tsx`:

```tsx
import type { Journey } from "@/components/JourneySteps";

// The Source selection block (spec 2026-10-09). These are the screening ledger's advisory
// observations: AI_PROVISIONAL judgements that order work but admit nothing and close no cohort.
// The server sends them already counted; a failure arrives as a named state with no figures, and
// this component prints a fixed sentence for it, never a zero.
type Selection = Journey["selection"];
type Scope = Selection["scopes"][number];

const STATE_TEXT: Record<string, string> = {
  INVENTORY_UNREADABLE: "The inventory file cannot be read. No figures are shown.",
  INVENTORY_DRIFTED:
    "The inventory file no longer matches the hash declared for this scope. No figures are shown.",
  SCREENING_OUTSIDE_INVENTORY:
    "Some screened works are not in the declared inventory. No figures are shown.",
  SELECTION_LEDGER_INVALID: "The screening ledger is not valid. No figures are shown.",
};

const LABELS: [keyof NonNullable<Scope["figures"]>, string][] = [
  ["direct", "direct candidates"],
  ["context", "context"],
  ["not_direct", "not direct"],
  ["uncertain", "uncertain"],
  ["unobserved_count", "not yet observed"],
];

function ScopeBlock({ scope }: { scope: Scope }) {
  return (
    <div className="mt-3 border-t pt-3" data-scope={scope.scope_id}>
      <p className="text-sm">
        <b>{scope.question_id}</b>{" "}
        <span className="font-mono text-xs text-muted-foreground">{scope.scope_id}</span>
      </p>
      {scope.figures === null ? (
        <p className="mt-1 text-sm">
          {STATE_TEXT[scope.state] ?? "This scope cannot be read. No figures are shown."}{" "}
          <code className="text-xs">{scope.state}</code>
        </p>
      ) : (
        <>
          <dl className="mt-2 grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-2.5">
            {LABELS.map(([key, label]) => (
              <div key={key} data-figure={key} className="rounded-lg bg-muted p-2.5">
                <dt className="text-xs text-muted-foreground">
                  {key === "unobserved_count" ? `${label}, of ${scope.figures!.inventory_count}` : label}
                </dt>
                <dd className="text-xl font-semibold">{scope.figures![key]}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-xs text-muted-foreground">
            {scope.figures.identity_observations} identity observations (possible versions of the
            same work).
          </p>
        </>
      )}
    </div>
  );
}

export default function SelectionPanel({ selection }: { selection: Selection }) {
  return (
    <section aria-label="Source selection" className="flex flex-col gap-1">
      <h2 className="text-base font-semibold">Source selection</h2>
      <p className="text-sm text-muted-foreground">
        Which works belong in the population. It runs beside the pipeline and admits nothing.
      </p>
      {selection.state === "NO_SCOPE_DECLARED" ? (
        <>
          <p className="mt-2 text-sm">No selection scope is declared for this flow.</p>
          <p className="text-xs text-muted-foreground">This does not mean there is nothing to select.</p>
        </>
      ) : selection.state === "SCOPES_FILE_INVALID" ? (
        <p className="mt-2 text-sm">
          The selection declaration cannot be read. No figures are shown.{" "}
          <code className="text-xs">SCOPES_FILE_INVALID</code>
        </p>
      ) : (
        <>
          <p className="mt-2 rounded-lg px-3 py-2 text-sm ring-1 ring-provisional">
            Advisory · {selection.assessment_status} judgements, not a person's · no admission ·{" "}
            {selection.cohort_closed ? "cohort closed" : "cohort open"} · admitted{" "}
            {selection.admitted_candidates}
          </p>
          {selection.scopes.map((scope) => <ScopeBlock key={scope.scope_id} scope={scope} />)}
        </>
      )}
    </section>
  );
}
```

Note: the banner prints the exact text "Advisory · AI_PROVISIONAL judgements, not a person's · no admission · cohort open · admitted 0" assembled from the server's fields; the two assertions in the test match substrings of it (`Advisory · AI_PROVISIONAL judgements` and `cohort open · admitted 0`). If the JSX line breaks split a text node, the regex `/cohort open · admitted 0/` still matches because React concatenates adjacent text in one element.

- [ ] **Step 3: Run the tests**

Run: `(cd web && npx vitest run tests/selectionpanel.test.tsx && npm run typecheck)`
Expected: 9 passed (the `it.each` counts four); typecheck clean.

- [ ] **Step 4: Commit**

```bash
git add web/src/components/SelectionPanel.tsx web/tests/selectionpanel.test.tsx
git commit -m "feat(portal): SelectionPanel, the advisory source-selection detail"
```

---

### Task 6: `BlockMap` — the strip, the URL and the default

**Files:**
- Create: `web/src/components/BlockMap.tsx`
- Test: `web/tests/blockmap.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `web/tests/blockmap.test.tsx`:

```tsx
// The strip of six tiles: server order and words as received, the selection in the URL, and the
// default rule (the first block that waits for you or is blocked, otherwise Pipeline).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import BlockMap, { BLOCK_KEYS, defaultBlock } from "@/components/BlockMap";
import type { BlockKey, JourneyBlock } from "@/components/BlockMap";

function tile(key: BlockKey, status: JourneyBlock["status"], figure = "fig " + key): JourneyBlock {
  const titles: Record<BlockKey, string> = {
    protocol: "Protocol", pipeline: "Pipeline", selection: "Source selection",
    intake: "Manual intake", execution: "Execution", reading: "Human reading",
  };
  return { key, title: titles[key], status, figure };
}

const calm: JourneyBlock[] = [
  tile("protocol", "done"), tile("pipeline", "partial"), tile("selection", "advisory"),
  tile("intake", "idle"), tile("execution", "idle"), tile("reading", "not_started"),
];

const panels = Object.fromEntries(
  BLOCK_KEYS.map((key) => [key, <p key={key}>panel {key}</p>]),
) as Record<BlockKey, ReactNode>;

function Probe() {
  const location = useLocation();
  return <output data-testid="loc">{location.search}</output>;
}

function mount(blocks: JourneyBlock[], at = "/p/demo/f/x") {
  render(
    <MemoryRouter initialEntries={[at]}>
      <BlockMap blocks={blocks} panels={panels} />
      <Probe />
    </MemoryRouter>,
  );
}

describe("defaultBlock", () => {
  it("is Pipeline when nothing waits for you or is blocked", () => {
    expect(defaultBlock(calm)).toBe("pipeline");
  });

  it("is the first block, in strip order, that waits for you or is blocked", () => {
    const blocks = calm.map((b) => b.key === "reading" ? { ...b, status: "waits_for_you" as const }
      : b.key === "selection" ? { ...b, status: "blocked" as const } : b);
    expect(defaultBlock(blocks)).toBe("selection");
  });
});

describe("BlockMap", () => {
  afterEach(cleanup);

  it("renders the six tiles in server order with the server's status word and figure", () => {
    mount(calm);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.getAttribute("data-block"))).toEqual([...BLOCK_KEYS]);
    expect(tabs[0].textContent).toContain("Protocol");
    expect(tabs[0].textContent).toContain("done");
    expect(tabs[0].textContent).toContain("fig protocol");
    expect(tabs[2].textContent).toContain("advisory");
    expect(tabs[1].getAttribute("data-status")).toBe("partial");
  });

  it("opens on Pipeline by default and shows exactly one panel", () => {
    mount(calm);
    expect(screen.getByRole("tab", { name: /^Pipeline/ }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
    expect(screen.getByRole("tabpanel").textContent).toBe("panel pipeline");
  });

  it("opens on the block that waits for you", () => {
    mount(calm.map((b) => b.key === "reading" ? { ...b, status: "waits_for_you" as const } : b));
    expect(screen.getByRole("tabpanel").textContent).toBe("panel reading");
    expect(screen.getByRole("tab", { name: /^Human reading/ }).textContent).toContain("waits for you");
  });

  it("reads the block from the URL", () => {
    mount(calm, "/p/demo/f/x?block=selection");
    expect(screen.getByRole("tabpanel").textContent).toBe("panel selection");
  });

  it("falls back to the default for an unknown block", () => {
    mount(calm, "/p/demo/f/x?block=nonsense");
    expect(screen.getByRole("tabpanel").textContent).toBe("panel pipeline");
  });

  it("clicking a tile switches the panel and writes the URL, keeping other parameters", () => {
    mount(calm, "/p/demo/f/x?details=1");
    fireEvent.click(screen.getByRole("tab", { name: /^Manual intake/ }));
    expect(screen.getByRole("tabpanel").textContent).toBe("panel intake");
    expect(screen.getByTestId("loc").textContent).toBe("?details=1&block=intake");
  });

  it("keeps every panel in the document, hidden, so the page's content is not lost", () => {
    mount(calm);
    expect(document.querySelectorAll("[data-panel]")).toHaveLength(6);
  });
});
```

Run: `(cd web && npx vitest run tests/blockmap.test.tsx)`
Expected: FAIL — `Failed to resolve import "@/components/BlockMap"`.

- [ ] **Step 2: Implement**

Create `web/src/components/BlockMap.tsx`:

```tsx
import type { ReactNode } from "react";
import { useSearchParams } from "react-router";
import type { Journey } from "@/components/JourneySteps";
import { cn } from "@/lib/utils";

// The six blocks of the research flow as a strip of tiles with the selected block's detail under
// it (spec 2026-10-09). The server decides each tile's status and figure (`journey.blocks`); this
// file maps a status to a mark and prints the status word beside it (colour never alone), keeps the
// selection in the URL (`?block=`), and renders the panels it is given. It computes no status.
export type JourneyBlock = Journey["blocks"][number];

export const BLOCK_KEYS = ["protocol", "pipeline", "selection", "intake", "execution", "reading"] as const;
export type BlockKey = (typeof BLOCK_KEYS)[number];

function isBlockKey(value: string | null): value is BlockKey {
  return value !== null && (BLOCK_KEYS as readonly string[]).includes(value);
}

const HALF = "bg-gradient-to-r from-done from-50% to-gray-300 to-50%";
const DASHED = "border-2 border-dashed border-slate-400";

const STATUS: Record<JourneyBlock["status"], { word: string; mark: string }> = {
  done: { word: "done", mark: "bg-done" },
  partial: { word: "partial", mark: HALF },
  running: { word: "running", mark: "bg-acting" },
  waits_for_you: { word: "waits for you", mark: "bg-waits" },
  blocked: { word: "blocked", mark: "bg-not-obtained" },
  not_started: { word: "not started", mark: "bg-gray-300" },
  not_applicable: { word: "not applicable", mark: DASHED },
  idle: { word: "nothing waiting", mark: "bg-gray-300" },
  advisory: { word: "advisory", mark: HALF },
  not_declared: { word: "not declared", mark: DASHED },
  unavailable: { word: "unavailable", mark: "border-2 border-dashed border-not-obtained" },
};

// On open: the first block, in strip order, that waits for you or is blocked; otherwise Pipeline.
export function defaultBlock(blocks: JourneyBlock[]): BlockKey {
  const first = blocks.find((b) => b.status === "waits_for_you" || b.status === "blocked");
  return first !== undefined && isBlockKey(first.key) ? first.key : "pipeline";
}

export default function BlockMap({ blocks, panels }: {
  blocks: JourneyBlock[];
  panels: Record<BlockKey, ReactNode>;
}) {
  const [params, setParams] = useSearchParams();
  const asked = params.get("block");
  const selected: BlockKey = isBlockKey(asked) ? asked : defaultBlock(blocks);

  function choose(key: BlockKey) {
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      next.set("block", key);
      return next;
    }, { replace: true });
  }

  return (
    <section aria-label="Blocks of the research flow" className="flex flex-col gap-3.5">
      <div role="tablist" aria-label="Blocks" className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
        {blocks.map((block) => {
          const s = STATUS[block.status];
          const on = block.key === selected;
          return (
            <button key={block.key} type="button" role="tab" id={`tab-${block.key}`}
                    aria-selected={on} aria-controls={`panel-${block.key}`}
                    data-block={block.key} data-status={block.status}
                    onClick={() => isBlockKey(block.key) && choose(block.key)}
                    className={cn(
                      "flex min-h-[104px] flex-col gap-1 rounded-xl bg-card p-3 text-left ring-1 ring-gray-200 hover:bg-gray-50",
                      "dark:ring-gray-800 dark:hover:bg-gray-900 aria-selected:ring-2 aria-selected:ring-foreground",
                    )}>
              <span className="text-xs tracking-wide text-muted-foreground uppercase">{block.title}</span>
              <span className="flex items-center gap-2 font-semibold">
                <span aria-hidden="true" className={cn("size-4 shrink-0 rounded-full", s.mark)} />
                <span data-status-word>{s.word}</span>
              </span>
              <span className="text-xs text-muted-foreground" data-block-figure>{block.figure}</span>
            </button>
          );
        })}
      </div>
      {BLOCK_KEYS.map((key) => (
        <div key={key} role="tabpanel" id={`panel-${key}`} aria-labelledby={`tab-${key}`}
             hidden={key !== selected} data-panel={key}
             className="flex flex-col gap-5 rounded-xl bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
          {panels[key]}
        </div>
      ))}
    </section>
  );
}
```

- [ ] **Step 3: Run the tests**

Run: `(cd web && npx vitest run tests/blockmap.test.tsx && npm run typecheck)`
Expected: 9 passed; typecheck clean. If `getByRole("tabpanel")` finds six instead of one, jsdom is not applying `[hidden]`; in that case add `className={... key !== selected && "hidden"}` next to the `hidden` attribute and re-run (the attribute stays for assistive technology).

- [ ] **Step 4: Commit**

```bash
git add web/src/components/BlockMap.tsx web/tests/blockmap.test.tsx
git commit -m "feat(portal): BlockMap, six tiles with the selection in the URL"
```

---

### Task 7: Put the BlockMap on the flow page

**Files:**
- Modify: `web/src/pages/FlowOverviewPage.tsx`
- Modify: `web/tests/flowpage.test.tsx`

- [ ] **Step 1: Update the flow page tests first (they now describe the new page)**

In `web/tests/flowpage.test.tsx`:

1. Replace every `await screen.findByRole("heading", { name: "The journey" });` (four occurrences: the "renders the server's steps" test, the two J3.6 tests, and the legacy test) with
   `await screen.findByRole("tablist", { name: "Blocks" });`
2. Append inside the `describe("F3: flow journey page", ...)` block, before its closing `});`:

```tsx
  it("shows the six blocks, opens on Pipeline, and keeps all eight steps in the document in order", async () => {
    mount("/p/demo/f/sel1", true);
    const tabs = await screen.findAllByRole("tab");
    expect(tabs.map((t) => t.getAttribute("data-block"))).toEqual(
      ["protocol", "pipeline", "selection", "intake", "execution", "reading"]);
    expect(tabs.map((t) => t.getAttribute("data-block"))).toEqual(
      flowOverview.journey.blocks.map((b) => b.key));
    const open = tabs.find((t) => t.getAttribute("aria-selected") === "true");
    expect(open?.getAttribute("data-block")).toBe("pipeline");
    const steps = Array.from(document.querySelectorAll("[data-step]")).map((n) => n.getAttribute("data-step"));
    expect(steps).toEqual(flowOverview.journey.steps.map((st) => st.key));
  });

  it("the Source selection tile says the scope is not declared when the server says so", async () => {
    mount("/p/demo/f/sel1?block=selection", true);
    await screen.findByRole("tablist", { name: "Blocks" });
    expect(screen.getByText("No selection scope is declared for this flow.")).toBeTruthy();
    expect(document.querySelector('[data-block="selection"]')?.textContent).toContain("not declared");
  });
```

Run: `(cd web && npx vitest run tests/flowpage.test.tsx)`
Expected: FAIL (no tablist yet).

- [ ] **Step 2: Implement**

In `web/src/pages/FlowOverviewPage.tsx`:

(a) Add imports next to the existing component imports:

```tsx
import BlockMap from "@/components/BlockMap";
import SelectionPanel from "@/components/SelectionPanel";
```

(b) Above the component, after the other top-level declarations, add:

```tsx
// Steps 2-7 are the pipeline; step 1 sits under Protocol and step 8 under Human reading.
const PIPELINE_STEPS = ["search", "copies", "documents", "annotate", "review", "profiles"] as const;
```

(c) Replace the whole block

```tsx
      <div className="flex flex-wrap items-start gap-5">
        <div className="min-w-0 flex-[3_1_520px]">
          <JourneySteps journey={data.journey} rows={data.questions.rows} base={base} writable={kind === "f"} />
        </div>
        <aside aria-label="Beside the journey" className="flex min-w-0 flex-[2_1_320px] flex-col gap-5">
          {kind === "f" && flowId ? <OperationsPanel project={project} flowId={flowId} /> : null}
          <RunningNote journey={data.journey} />
          <TheTopic topics={data.journey.topics} />
          <TheQuestions rows={data.questions.rows} base={base} />
          <NeedsYou needs={data.journey.needs_you} base={base} writable={kind === "f"} />
        </aside>
      </div>
```

with

```tsx
      <BlockMap
        blocks={data.journey.blocks}
        panels={{
          protocol: (
            <>
              <JourneySteps journey={data.journey} rows={data.questions.rows} base={base}
                            writable={kind === "f"} keys={["protocol"]} heading="Protocol" bar={false} />
              <TheTopic topics={data.journey.topics} />
              <TheQuestions rows={data.questions.rows} base={base} />
            </>
          ),
          pipeline: (
            <JourneySteps journey={data.journey} rows={data.questions.rows} base={base}
                          writable={kind === "f"} keys={PIPELINE_STEPS} heading="Pipeline" />
          ),
          selection: <SelectionPanel selection={data.journey.selection} />,
          intake: <NeedsYou needs={data.journey.needs_you} base={base} writable={kind === "f"} />,
          execution: (
            <>
              {kind === "f" && flowId ? <OperationsPanel project={project} flowId={flowId} /> : null}
              <RunningNote journey={data.journey} />
            </>
          ),
          reading: (
            <JourneySteps journey={data.journey} rows={data.questions.rows} base={base}
                          writable={kind === "f"} keys={["sign"]} heading="Human reading" bar={false} />
          ),
        }}
      />
```

- [ ] **Step 3: Run the whole frontend suite, typecheck and build**

Run: `(cd web && npx vitest run && npm run typecheck && npm run build)`
Expected: all test files pass (the earlier 205 tests plus the new ones: 2 in `journey`, 9 in `selectionpanel`, 9 in `blockmap`, 2 in `flowpage`); typecheck clean; build succeeds and `check-csp.mjs` passes.

If a pre-existing test other than `flowpage` fails because it looked for the old "The journey" heading or the aside, change only its wait to `findByRole("tablist", { name: "Blocks" })`; do not weaken an assertion about content.

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/FlowOverviewPage.tsx web/tests/flowpage.test.tsx
git commit -m "feat(portal): the flow page shows the six-block map"
```

---

### Task 8: Declare the real scope for `alembic-s4-lungo` and check the figures

**Files:**
- Create (data, not tracked — `store/` is gitignored): `store/alembic-s4-lungo/audits/source-selection/scopes.json`

- [ ] **Step 1: Write the declaration**

Run:

```bash
.venv/bin/python - <<'PY'
import hashlib, json
from pathlib import Path

base = Path("store/alembic-s4-lungo/audits/source-selection")
inventory = base / "l02-v1" / "inventory.json"
scopes = {"scopes": [{
    "scope_id": "l02-v2-ai-selection-2026-10-05",
    "question_id": "L02",
    "round": "s4-l02-repository-copies-2026-10-06-v2",
    "inventory_path": "l02-v1/inventory.json",
    "inventory_sha256": hashlib.sha256(inventory.read_bytes()).hexdigest(),
}]}
(base / "scopes.json").write_text(json.dumps(scopes, indent=1) + "\n")
print(scopes["scopes"][0]["inventory_sha256"])
PY
```
Expected output: `fa160b117a84a071e975acb0422f3a6a47a47263b7f0445e4ed455e39c05ab67` (the hash measured on 2026-10-09). If it differs, the inventory changed: stop and tell the operator.

- [ ] **Step 2: Check the live figures**

Run:

```bash
.venv/bin/python - <<'PY'
from claimstone import scope, selection_view
from claimstone.store import Store

result = selection_view.read(
    Store("alembic-s4-lungo"), scope.Selector("s4-l02-repository-copies-2026-10-06-v2"))
(only,) = result["scopes"]
print(result["state"], only["state"], only["figures"])
assert result["state"] == "DECLARED" and only["state"] == "OK"
assert only["figures"] == {
    "inventory_count": 830, "screened_count": 48, "unobserved_count": 782, "direct": 3,
    "context": 21, "not_direct": 18, "uncertain": 6, "identity_observations": 3}
assert result["admitted_candidates"] == 0 and result["cohort_closed"] is False
print("OK")
PY
```
Expected: the printed line `DECLARED OK {...}` followed by `OK`. These are the values `source_selection.preview()` gave on 2026-10-09; if the screening ledger has grown since, the assertion fails: update the expected numbers to the new `preview()` output and record the new date in Task 9's decision entry.

- [ ] **Step 3: Look at it in the portal (manual, optional but recommended)**

The portal serves the built frontend from a container. Rebuild and open it as the project's runbook says (`./portal.sh`, then http://127.0.0.1:8788/p/alembic-s4-lungo and the flow bound to round `s4-l02-repository-copies-2026-10-06-v2`). Expected: six tiles; Pipeline reads "not started" ("0 of 6 steps done") because that round has no candidates yet; Source selection reads "advisory", "48 seen · 782 unseen"; its panel shows the advisory banner and 3 / 21 / 18 / 6 / 782. Nothing is committed in this task.

---

### Task 9: Contract and decision record

**Files:**
- Modify: `docs/contracts/journey.md`
- Modify: `docs/contracts/source_selection.md`
- Modify: `docs/DESIGN_DECISIONS.md` (append D116 at the end)

- [ ] **Step 1: `docs/contracts/journey.md`**

(a) Replace the first sentence's version: change ``` `journey_version 1` (`claimstone/journey.py`, D111). ``` to ``` `journey_version 2` (`claimstone/journey.py`, D111, D116). ```

(b) In the shape block, change the line that lists `steps[...]` so it also lists the two new keys: after `steps[{n,key,title,actor,status,summary,figures}],` insert ` blocks[{key,title,status,figure}], selection{…},`.

(c) Append this section at the end of the file:

```markdown
## The six blocks (D116)

`blocks` is the flow page's strip, in this order: `protocol`, `pipeline`, `selection`, `intake`,
`execution`, `reading`. Each tile has a `status`, a short `figure` (a fixed template over numbers;
unknown is "—") and the block's `title`. Statuses are the journey's, plus `idle` (the ledger reads and
nothing is waiting), `advisory`, `not_declared` and `unavailable`.

| block | status rule | figure |
|---|---|---|
| protocol | step 1's status; `not_applicable` for a legacy selector | `{questions_total} questions · floor {floor}`, or `protocol not verified` |
| pipeline | from steps 2–7: `done` if all `done`; else `blocked` if any; else `running` if any; else `not_started` if all; else `partial` | `{done} of {total} steps done` (a count of steps, never a percentage) |
| selection | `not_declared`; `unavailable` (declaration or any scope in a named error); otherwise `advisory`. **Never `done`.** | `{screened_count} seen · {unobserved_count} unseen`, or `{n} scopes` |
| intake | `waits_for_you` if `needs_you.required` > 0; `idle` if 0; `unavailable` if null; `not_applicable` for a legacy selector | `{required} required · {optional} optional` |
| execution | `running` if an operation is in flight in the sense above; `idle`; `unavailable` if `running` is null | `{live} running · {listed} listed` |
| reading | step 8's status | `{ready_to_sign} to sign · {signed} of {literature_total} signed` |

The page opens on the first block, in this order, whose status is `waits_for_you` or `blocked`;
otherwise on `pipeline`. The selection lives in the URL as `?block=`.

`selection` carries the advisory source-selection read of `claimstone/selection_view.py`; see
`source_selection.md`. It is present for every selector; `state` is `NO_SCOPE_DECLARED` when nothing is
declared for the round.
```

- [ ] **Step 2: `docs/contracts/source_selection.md`**

Append at the end of the file:

```markdown
## Scope declaration for the portal (D116)

`store/<project>/audits/source-selection/scopes.json` declares which screening scopes the portal shows
for which round. It lives under `store/`, not `projects/`: the observations are advisory, so declaring
one must not change the protocol digest and turn every bound flow `DRIFTED`.

```json
{"scopes": [{"scope_id": "…", "question_id": "L02", "round": "…",
             "inventory_path": "l02-v1/inventory.json", "inventory_sha256": "…"}]}
```

`inventory_path` is relative to `audits/source-selection/`; a path that leaves that directory is
`INVENTORY_UNREADABLE`. `round` only routes the scope to a flow's page; it feeds no computation and does
not claim the inventory was drawn from that round.

`claimstone/selection_view.py` reads it with `source_selection.preview()` and returns, in the overview's
`journey.selection`, per scope: `inventory_count`, `screened_count`, `unobserved_count`, `direct`,
`context`, `not_direct`, `uncertain`, `identity_observations` — counted from the latest row per key, so
superseded rows are not counted twice. Always present: `advisory: true`,
`assessment_status: "AI_PROVISIONAL"`, `cohort_closed: false`, `admitted_candidates: 0`.

A failure is a named state with `figures: null`, never a zero: `NO_SCOPE_DECLARED`,
`SCOPES_FILE_INVALID` (whole declaration), and per scope `INVENTORY_UNREADABLE`, `INVENTORY_DRIFTED`
(the inventory's sha256 differs from the declared one), `SCREENING_OUTSIDE_INVENTORY`,
`SELECTION_LEDGER_INVALID`. The read writes nothing.
```

- [ ] **Step 3: `docs/DESIGN_DECISIONS.md`**

Append at the end of the file (D115 is the last entry on 2026-10-09; confirm with `grep -n '^## D11' docs/DESIGN_DECISIONS.md | tail -2` and use the next number if another decision landed meanwhile):

```markdown

## D116 — The flow page mirrors six blocks, and source selection becomes visible (2026-10-09)

The flow page showed the journey as eight steps in one list. The operator's map of the project has six
blocks, and two of them were invisible in the portal: the source-selection work that runs beside the
pipeline, and the manual intake. `journey_version 2` adds `journey.blocks` (six tiles, each with a
status and a figure decided on the server) and `journey.selection`; the page renders them as a strip of
tiles with the selected block's detail under it, the selection in the URL as `?block=`.

Source selection is advisory by construction. `claimstone/selection_view.py` reads a declared scope
(`audits/source-selection/scopes.json`, outside `projects/` so declaring one cannot change the protocol
digest) through `source_selection.preview()`, and always returns `advisory: true`,
`assessment_status: AI_PROVISIONAL`, `cohort_closed: false`, `admitted_candidates: 0`. Its tile is never
`done`. A failure is a named state with no figures. There is no separate route: the tile needs the
figures on every poll of the overview, so a route would compute them twice.

Measured, 2026-10-09, `source_selection.preview()` on `alembic-s4-lungo` (scope
`l02-v2-ai-selection-2026-10-05`, question L02, inventory `l02-v1/inventory.json`, 830 keys, sha256
`fa160b117a84a071e975acb0422f3a6a47a47263b7f0445e4ed455e39c05ab67`): 48 screened, 782 unobserved,
3 direct candidates, 21 context, 18 not direct, 6 uncertain, 3 identity observations. The ledger holds
49 rows for 48 keys: the count is of the latest row per key. These are the values the live check in the
plan asserts. The Pipeline tile's status is a rule over steps 2–7 and its figure a count of steps; a
percentage was refused because the steps have different bases.
```

- [ ] **Step 3b: Regenerate the fixtures after D116**

The integrity check refuses to stay silent when an instrument version changes without being recorded: after Task 3 the fixture `web/tests/fixtures/projects/example-news-and-returns/integrity.json` carries the warning "docs/DESIGN_DECISIONS.md never mentions journey_version 2". D116 (written in step 3, and containing the words "journey_version 2") records it, so regenerate and confirm the warning is gone:

```bash
.venv/bin/python tools/build_portal_fixtures.py
git diff -- web/tests/fixtures/projects/example-news-and-returns/integrity.json
.venv/bin/pytest -q tests/test_portal_fixtures.py
```
Expected: the `instruments` list in `integrity.json` is back to `[]` (the diff against HEAD for that file is empty), and the fixtures test passes.

- [ ] **Step 4: Full verification**

Run:

```bash
.venv/bin/pytest -q
(cd web && npx vitest run && npm run typecheck && npm run build)
.venv/bin/claimstone validate --all-projects
```
Expected: pytest all green (the count printed is the new total, higher than the 1191 passed + 7 skipped recorded earlier — report the number actually printed); vitest all green; typecheck and build clean; `validate` reports every project valid. Report any failure with its output; do not claim success without these three results.

- [ ] **Step 5: Commit**

```bash
git add docs/contracts/journey.md docs/contracts/source_selection.md docs/DESIGN_DECISIONS.md docs/superpowers/specs/2026-10-09-portal-block-map-design.md docs/superpowers/plans/2026-10-09-portal-block-map.md
git commit -m "docs: block map contract, scope declaration and D116"
```

---

## Self-review (done against the spec)

- **Spec coverage:** six blocks and tile status rules → Task 2 (and the rules documented in Task 9); layout, `?block=`, default selection, hidden panels, responsive grid (`grid-cols-2 sm:grid-cols-3 lg:grid-cols-6`) → Task 6; detail reusing existing components → Task 7; `scopes.json`, read, named states, advisory fields, latest-row counting, path escape, read-only → Task 1; `journey_version 2`, schema, generated types, fixtures → Task 3; live check on `-lungo` and the round decision (v2 round) → Task 8; contracts and D116 → Task 9; "Source selection never `done`", "unknown is —" → asserted in Task 2/5 tests. Out of scope respected: no queue, no per-source detail, no writes, no scopes for the other two projects.
- **Spec revised during planning (already applied to the spec):** no separate route (carried in the overview); `INVENTORY_UNREADABLE` replaces `INVENTORY_MISSING`; the Pipeline rule distinguishes "some work exists" (`partial`) from "nothing started"; a new `idle` status; `journey_version` 2.
- **Type consistency:** `BLOCK_STATUSES` (journey.py) = `JOURNEY_BLOCK_STATUSES` (api_schema.py), asserted by a test; `BLOCK_KEYS`/`BlockKey` (BlockMap.tsx) match the server's six keys, asserted in `flowpage.test.tsx`; `selection_view` state constants are the schema enums; the figures keys in `SelectionPanel` (`direct`, `context`, `not_direct`, `uncertain`, `unobserved_count`, `inventory_count`, `identity_observations`) match `_SELECTION_FIGURES`.
- **Known risks to watch while executing:** (1) jsdom and `[hidden]` (Task 6 note); (2) `json2ts` output for `const`/union types may name the generated interfaces differently — if `tsc` reports that `Journey["selection"]` or `["blocks"]` is missing, read `web/src/lib/api-types.ts` and adjust the indexed-access types, not the schema; (3) other tests in the repo may assert the instrument-version listing (`meta.json` shows `journey_version`), which the fixture regeneration in Task 3 updates.
