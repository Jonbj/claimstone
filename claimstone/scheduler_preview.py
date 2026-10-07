"""Read-only scheduler preview for one protocol-bound research flow.

The portal already owns the meaning of an inbox card. This module turns those
cards into a cautious queue without treating a suggested CLI command as an
authorization or a job. No process, model or network call is made here.
"""

from __future__ import annotations

from typing import Any

from claimstone import flows, portal_state, scope
from claimstone.config import Project, RegistryDrift, check_registry_drift
from claimstone.store import LedgerCorrupt, Store

SCHEDULER_PREVIEW_VERSION = 2


def preview(project: Project, store: Store, flow_id: str) -> dict[str, Any]:
    """Describe the next work and blockers; never authorize or execute it."""
    held = flows.flows(store).get(flow_id)
    if held is None:
        raise ValueError(f"unknown or invalid flow id: {flow_id}")
    binding = flows.binding_state(project, store, held)
    selected = held["binding"]["selector"]
    selector = scope.Selector(selected.get("round"), bool(selected.get("manifest_only")))
    result: dict[str, Any] = {
        "scheduler_preview_version": SCHEDULER_PREVIEW_VERSION,
        "project": project.name,
        "flow_id": flow_id,
        "selector": selector.as_dict(),
        "binding": binding,
        "execution": "PREVIEW_ONLY",
        "authorized": False,
        "proposals": [],
        "blockers": [],
    }
    if binding["state"] != "CURRENT":
        result["blockers"].append({"code": "PROTOCOL_DRIFT", "detail": binding})
    try:
        check_registry_drift(project, store, record=False)
    except RegistryDrift as exc:
        result["blockers"].append({"code": "REGISTRY_DRIFT", "detail": str(exc)})

    try:
        computed = portal_state.compute(project, store, selector)
        cards = portal_state.inbox_cards(project, store, selector, held, computed)
        count = len(scope.candidates(store, selector))
    except LedgerCorrupt as exc:
        result["blockers"].append({"code": "LEDGER_CORRUPT", "detail": str(exc)})
        result["state"] = "BLOCKED"
        return result

    result["candidate_count"] = count
    result["candidate_scope_state"] = (
        "EMPTY_NOT_A_CLOSED_COHORT" if count == 0 else "CANDIDATES_PRESENT")
    # The admission engine's zero-candidate object may say final=True while its
    # rate is null. That flag is about its arithmetic, not selection closure.
    result["floor"] = None if count == 0 else computed.rs.floor
    if count == 0:
        result["floor_note"] = "not evaluated: no candidates in this scope"
    result["stages"] = [{"name": stage.name, "inputs": stage.inputs,
                         "outputs": stage.outputs, "progress": (
                             None if stage.progress is None else
                             {"done": stage.progress.done, "total": stage.progress.total,
                              "label": stage.progress.label})}
                        for stage in computed.rs.stages]
    for error in computed.rs.errors:
        result["blockers"].append({"code": "INTEGRITY", "detail": error})
    for name in store.torn_tail:
        result["blockers"].append({"code": "TORN_LEDGER_TAIL", "detail": name})
    if held.get("bound_after_data"):
        result["blockers"].append({
            "code": "LATE_FLOW_BINDING",
            "detail": "rows written before this flow was bound are not verified against its protocol",
        })

    for card in cards:
        # These categories already come from one server-side source of meaning.
        if card.category in {"INTEGRITY", "PROTOCOL"}:
            continue
        if card.category == "ADVISORY":
            kind = "ADVISORY_ONLY"
        elif card.category == "ADJUDICATION":
            kind = "HUMAN_READING_AND_SIGNATURE"
        elif card.category in {"ACQUISITION", "CLASSIFICATION"}:
            kind = "PLAN_OR_OPERATOR_DECISION"
        elif card.category in {"EXTRACT", "REVIEW"}:
            kind = "SCOPED_OFFLINE_STAGE_PLAN_AVAILABLE"
        else:
            kind = "OFFLINE_INSPECTION_OR_STAGE_WORK"
        result["proposals"].append({
            "category": card.category, "subject": card.subject, "reason": card.cause,
            "kind": kind, "note": card.note,
        })

    if count == 0:
        result["proposals"].insert(0, {
            "category": "DISCOVERY", "subject": selector.round or "whole store",
            "reason": "this flow has no candidates; literature completeness is unknown",
            "kind": "PLAN_OR_OPERATOR_DECISION",
            "note": "prepare a bounded search or controlled candidate intake; an empty round is not a closed cohort",
        })
    if result["blockers"]:
        result["state"] = "BLOCKED"
    elif result["proposals"]:
        result["state"] = "WORK_PROPOSED"
    else:
        result["state"] = "NO_WORK_PROPOSED"
    return result
