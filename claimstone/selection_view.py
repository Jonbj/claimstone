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
    try:
        base = store.path(BASE_DIR).resolve()
        path = (base / entry["inventory_path"]).resolve()
        if base not in path.parents:
            raise _Refused(INVENTORY_UNREADABLE)
        data = path.read_bytes()
    except (OSError, ValueError) as exc:
        raise _Refused(INVENTORY_UNREADABLE) from exc
    if hashlib.sha256(data).hexdigest() != entry["inventory_sha256"]:
        raise _Refused(INVENTORY_DRIFTED)
    try:
        rows = json.loads(data)
        if not isinstance(rows, list) or not rows or not all(
                isinstance(row, dict) and "candidate_key" in row for row in rows):
            raise _Refused(INVENTORY_UNREADABLE)
        return {str(row["candidate_key"]) for row in rows}
    except (ValueError, KeyError, TypeError) as exc:
        raise _Refused(INVENTORY_UNREADABLE) from exc


def _scope(store: Store, entry: dict[str, Any]) -> dict[str, Any]:
    head = {"scope_id": entry["scope_id"], "question_id": entry["question_id"]}
    try:
        keys = _inventory_keys(store, entry)
        view = source_selection.preview(store, entry["scope_id"], entry["question_id"], keys)
    except _Refused as refused:
        return {**head, "state": refused.state, "figures": None}
    except (LedgerCorrupt, OSError, AttributeError, KeyError, TypeError):
        return {**head, "state": SELECTION_LEDGER_INVALID, "figures": None}
    except ValueError as exc:
        # Depends on the wording of source_selection.preview's error for a screened key missing
        # from the inventory ("screened identity is outside ..."); the identity-ledger message
        # also says "frozen inventory", so it is deliberately not matched and stays a ledger fault.
        state = (SCREENING_OUTSIDE_INVENTORY if "screened identity is outside" in str(exc)
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
