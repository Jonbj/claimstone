"""A read model of the scheduler's operations, for the control server (spec B12).

It reads `operations.jsonl` through the scheduler's own replay (`operations._events`), so a damaged
or conflicting ledger raises here exactly as it does for the worker. Nothing is appended. The state
words are the scheduler's: an operation whose last event is `started`, `call_started` or
`unit_completed` is running only while the writer lock is held, and otherwise interrupted. The
ledger records no heartbeat, so "worker last seen" is reported as unknown, never inferred from the
last event (an old event is not proof that work is running).
"""

from __future__ import annotations

from typing import Any

from claimstone import operations
from claimstone.store import Store

IN_FLIGHT = frozenset({"started", "call_started", "unit_completed"})

STATE_NOTES = {
    "PLANNED": "waiting for a person to authorize this exact plan",
    "AUTHORIZED": "authorized; waiting for the worker to start it",
    "RUNNING_OR_LOCK_HELD": "a writer holds the project lock; work is probably running",
    "INTERRUPTED": "started but no writer holds the lock: interrupted until a worker resumes it",
    "COMPLETED": "every planned unit has a recorded outcome",
    "FAILED": "stopped by a named failure",
}


def _state(store: Store, rows: list[dict[str, Any]]) -> str:
    last = rows[-1]["event"]
    if last in IN_FLIGHT:
        return "RUNNING_OR_LOCK_HELD" if store.writer_busy() else "INTERRUPTED"
    return str(last).upper()


def summary(store: Store, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """One operation as a person reads it: what it may do, what it did, and its state."""
    plan = rows[0]["plan"]
    state = _state(store, rows)
    spent = 0.0
    unknown_cost = 0
    completed = 0
    for row in rows:
        if row["event"] != "unit_completed":
            continue
        completed += 1
        result = row.get("result") or {}
        cost = result.get("cost_usd") if isinstance(result, dict) else None
        if cost is None and plan.get("max_spend_usd"):
            unknown_cost += 1   # a paid unit whose cost was not reported: reserved, never zero
        elif cost is not None:
            spent += float(cost)
    authorized = next((row for row in rows if row["event"] == "authorized"), None)
    limit = plan.get("max_spend_usd")
    return {
        "operation_id": rows[0]["operation_id"],
        "stage": plan.get("stage"),
        "state": state,
        "state_note": STATE_NOTES.get(state, ""),
        "limits": {"network_requests": plan.get("max_network_requests"),
                   "model_calls": plan.get("max_model_calls"),
                   "spend_usd": limit},
        "spent_usd": round(spent, 6),
        "units_with_unknown_cost": unknown_cost,
        "remaining_usd": (round(float(limit) - spent, 6) if limit else None),
        "units_completed": completed,
        "planned_at": rows[0].get("at"),
        "last_event": rows[-1]["event"], "last_event_at": rows[-1].get("at"),
        "authorized_by": (authorized or {}).get("identity"),
        "worker_last_seen": None,
        "worker_note": "the scheduler records no heartbeat yet; the last event is not proof "
                       "that work is running",
    }


def for_flow(store: Store, flow_id: str) -> list[dict[str, Any]]:
    """Every operation of one flow, newest plan first."""
    grouped = operations._events(store)
    found = [summary(store, rows) for rows in grouped.values()
             if rows[0]["plan"].get("flow_id") == str(flow_id)]
    return sorted(found, key=lambda item: str(item["planned_at"]), reverse=True)


def batches_for_flow(store: Store, flow_id: str) -> list[dict[str, Any]]:
    """Reviewable frozen batches and their current operation states."""
    grouped = operations._events(store)
    found = []
    for row in store.read(operations.BATCH_LEDGER):
        if row.get('flow_id') != str(flow_id):
            continue
        body = {key: value for key, value in row.items()
                if key not in {'batch_id', 'created_at'}}
        if operations._digest(body) != row.get('batch_id'):
            raise operations.OperationError('altered operation batch')
        states = {}
        for operation_id in row['operation_ids']:
            rows = grouped.get(operation_id)
            if rows is None or rows[0]['plan'].get('flow_id') != str(flow_id):
                raise operations.OperationError('batch contains an unknown or mismatched operation')
            states[operation_id] = _state(store, rows)
        found.append({
            'batch_id': row['batch_id'], 'stage': row['stage'],
            'created_at': row['created_at'],
            'operation_ids': row['operation_ids'],
            'units': [unit | {'state': states[unit['operation_id']]}
                      for unit in row['units']],
            'max_total_requests': row['max_total_requests'],
            'selected': row['selected'],
            'remaining_unplanned': row['remaining_unplanned'],
            'skipped': row['skipped'],
            'awaiting_approval': sum(state == 'PLANNED' for state in states.values()),
        })
    return sorted(found, key=lambda item: str(item['created_at']), reverse=True)


def continuing(store: Store) -> list[dict[str, Any]]:
    """Operations that go on without a person: authorized, running or interrupted."""
    grouped = operations._events(store)
    return [summary(store, rows) for rows in grouped.values()
            if rows[-1]["event"] == "authorized" or rows[-1]["event"] in IN_FLIGHT]
