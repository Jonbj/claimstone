"""`claimstone notify` derives events from the ledgers (issue #5).

Two kinds of event. A state — an operation waiting for authorization, a question waiting for
a signature, an open integrity problem, a round below its floor — is derived on every drain
and deduplicated by its identity, so it is sent once while it stays true. An occurrence — a
copy obtained after a retry, a candidate given up, a batch completed, an operation failed, a
breaker opened — is historical, so it is only derived from the moment the outbox was started
(`--since` overrides that for a deliberate replay).
"""

from __future__ import annotations

import pytest

from claimstone import (acquire, admissibility, intake, net, notifications, notify, operations,
                        portal_state, retry_policy)
from claimstone.store import Store

NOW = "2026-10-18T12:00:00+00:00"
START = "2026-10-18T10:00:00+00:00"
BEFORE = "2026-10-18T09:00:00+00:00"


def _store(tmp_path) -> Store:
    return Store("example", tmp_path)


def _add_operation(store: Store, events=(), plan: dict | None = None,
                   candidate_key: str = "c1") -> str:
    """A valid operations.jsonl history, because `operations._events` validates transitions."""
    plan = plan or {"flow_id": "flow-1", "project": "example", "stage": "acquire",
                    "candidate_key": candidate_key}
    operation_id = operations._digest(plan)
    base = {"operation_version": operations.OPERATIONS_VERSION,
            "operation_id": operation_id, "plan_id": operation_id,
            "flow_id": plan["flow_id"], "actor": "test", "code_sha256": "sha"}
    rows = [base | {"event": "planned", "plan": plan}]
    rows += [base | dict(event=event, **extra) for event, extra in events]
    for body in rows:
        store.append(operations.LEDGER,
                     body | {"event_id": operations._digest(body), "at": NOW})
    return operation_id


def _add_batch(store: Store, operation_ids: list[str]) -> str:
    body = {"stage": "acquire", "flow_id": "flow-1", "operation_ids": operation_ids,
            "units": [{"operation_id": op} for op in operation_ids],
            "max_total_requests": 10, "selected": len(operation_ids),
            "remaining_unplanned": 0, "skipped": 0}
    batch_id = operations._digest(body)
    store.append(operations.BATCH_LEDGER,
                 body | {"batch_id": batch_id, "created_at": NOW})
    return batch_id


def _add_acquisition(store: Store, **row) -> None:
    body = {"candidate_key": "c1", "source_id": "doi:10.1/one", "attempt_no": 1,
            "campaign": acquire.ROUTINE, "acquired": False, "failure_class": None,
            "fetched_at": NOW}
    body.update(row)
    store.append("acquisitions.jsonl", body)


def _add_policy(store: Store, policy: dict, *, reserve: bool = False) -> str:
    policy = {"flow_id": "flow-1", "max_retries": 1, "max_attempts_each": 2,
              "max_requests_each": 1, "max_total_requests": 1,
              "allowed_hosts": ["a.example"], "use_apis": False, "retry_classes": [],
              "not_before": "2026-10-16T00:00:00+00:00",
              "expires_at": "2026-10-17T00:00:00+00:00", **policy}
    policy_id = operations._digest(policy)
    for body in ({"version": retry_policy.VERSION, "event": "planned",
                  "policy_id": policy_id, "policy": policy},
                 {"version": retry_policy.VERSION, "event": "authorized",
                  "policy_id": policy_id, "identity": {"actor": "test"}}):
        store.append(retry_policy.LEDGER,
                     body | {"event_id": operations._digest(body), "at": NOW})
    if reserve:
        _add_operation(
            store,
            [("authorized", {"identity": {"retry_policy_id": policy_id}})],
            plan={"flow_id": "flow-1", "project": "example", "stage": "acquire",
                  "max_network_requests": 1, "allowed_hosts": ["a.example"],
                  "use_apis": False, "retry_classes": [], "candidate_key": "c1"})
    return policy_id


def _by_reason(events, reason):
    return [event for event in events if event["reason"] == reason]


def test_a_planned_operation_waits_for_a_person(tmp_path):
    store = _store(tmp_path)
    operation_id = _add_operation(store)
    events = notify.derive(None, store, project_name="example", now=NOW)
    (event,) = _by_reason(events, "plan_awaiting_authorization")
    assert event["ids"] == [operation_id]
    assert event["subject"] == f"operation:{operation_id}"
    assert event["occurred_at"] == NOW


def test_an_authorized_operation_is_not_waiting(tmp_path):
    store = _store(tmp_path)
    _add_operation(store, [("authorized", {"identity": {"actor": "test"}})])
    assert _by_reason(notify.derive(None, store, project_name="example", now=NOW),
                      "plan_awaiting_authorization") == []


def test_a_failed_operation_is_reported_with_its_failure_class(tmp_path):
    store = _store(tmp_path)
    operation_id = _add_operation(store, [
        ("authorized", {"identity": {"actor": "test"}}),
        ("failed", {"failure_class": "OperationError", "detail": "frozen inputs changed"})])
    (event,) = _by_reason(notify.derive(None, store, project_name="example", now=NOW), "operation_failed")
    assert event["code"] == "OperationError"
    assert event["ids"] == [operation_id]
    assert event["occurred_at"] == NOW


def test_a_batch_is_completed_only_when_every_operation_is(tmp_path):
    store = _store(tmp_path)
    done = [("authorized", {"identity": {"actor": "t"}}),
            ("started", {}), ("unit_completed", {"result": {}}),
            ("completed", {"result": {}})]
    _add_batch(store, [_add_operation(store, done, candidate_key="c1"),
                       _add_operation(store, done[:-1], candidate_key="c2")])
    assert _by_reason(notify.derive(None, store, project_name="example", now=NOW), "batch_completed") == []
    store = _store(tmp_path / "other")
    _add_batch(store, [_add_operation(store, done, candidate_key="c1"),
                       _add_operation(store, done, candidate_key="c2")])
    (event,) = _by_reason(notify.derive(None, store, project_name="example", now=NOW), "batch_completed")
    assert event["count"] == 2


def test_a_copy_obtained_after_a_retry_is_one_event(tmp_path):
    store = _store(tmp_path)
    notifications.start(store, now=START)
    _add_acquisition(store, acquired=True, attempt_no=2, campaign="operation-abc",
                     fetched_at="2026-10-18T11:00:00+00:00")
    (event,) = _by_reason(notify.derive(None, store, project_name="example", now=NOW), "copy_obtained_after_retry")
    assert event["ids"] == ["c1"]


def test_store_reuse_and_an_intake_are_not_fetch_retries(tmp_path):
    """Both make an acquisition row without a second request. A routine second attempt is a
    retry: the first attempt failed, this one succeeded, and that is the event."""
    store = _store(tmp_path)
    notifications.start(store, now=START)
    _add_acquisition(store, acquired=True, attempt_no=2, campaign="cached",
                     provenance="store-reuse")
    _add_acquisition(store, acquired=True, attempt_no=1, campaign=intake.CAMPAIGN,
                     candidate_key="c3")
    assert _by_reason(notify.derive(None, store, project_name="example", now=NOW),
                      "copy_obtained_after_retry") == []
    _add_acquisition(store, acquired=True, attempt_no=2, campaign=acquire.ROUTINE,
                     candidate_key="c2")
    (event,) = _by_reason(notify.derive(None, store, project_name="example", now=NOW),
                          "copy_obtained_after_retry")
    assert event["ids"] == ["c2"]


def test_a_terminal_failure_is_a_candidate_given_up(tmp_path):
    store = _store(tmp_path)
    notifications.start(store, now=START)
    _add_acquisition(store, acquired=False, failure_class=net.PAYWALL, attempt_no=2,
                     fetched_at="2026-10-18T11:00:00+00:00")
    (event,) = _by_reason(notify.derive(None, store, project_name="example", now=NOW), "candidate_given_up")
    assert event["code"] == net.PAYWALL


def test_a_transient_failure_is_not_given_up(tmp_path):
    store = _store(tmp_path)
    notifications.start(store, now=START)
    _add_acquisition(store, acquired=False, failure_class=net.TIMEOUT,
                     fetched_at="2026-10-18T11:00:00+00:00")
    assert _by_reason(notify.derive(None, store, project_name="example", now=NOW), "candidate_given_up") == []


def test_a_blocked_host_is_one_event_per_episode(tmp_path):
    store = _store(tmp_path)
    notifications.start(store, now=START)
    for minute in (10, 20, 30):
        store.append("requests.jsonl", {
            "event": "blocked", "failure_class": net.BUDGET,
            "url": "https://a.example/x", "request_url": "https://a.example/x",
            "recorded_at": f"2026-10-18T11:{minute}:00+00:00"})
    (event,) = _by_reason(notify.derive(None, store, project_name="example", now=NOW), "host_breaker_open")
    assert event["ids"] == ["a.example"]
    assert event["count"] == 3


def test_events_before_the_outbox_started_are_not_replayed(tmp_path):
    store = _store(tmp_path)
    notifications.start(store, now=START)
    _add_acquisition(store, acquired=True, attempt_no=2, campaign="operation-abc",
                     fetched_at=BEFORE)
    assert _by_reason(notify.derive(None, store, project_name="example", now=NOW),
                      "copy_obtained_after_retry") == []
    assert _by_reason(notify.derive(None, store, project_name="example", now=NOW, since=BEFORE),
                      "copy_obtained_after_retry")


def test_an_expired_retry_window_is_an_event(tmp_path):
    store = _store(tmp_path)
    _add_policy(store, {"expires_at": "2026-10-17T00:00:00+00:00"})
    (event,) = _by_reason(notify.derive(None, store, project_name="example", now=NOW,
                                        since="2026-10-16T00:00:00+00:00"),
                          "retry_window_expired")
    assert event["code"] == "RETRY_WINDOW"
    assert event["ids"]


def test_a_retry_ceiling_used_up_is_an_event(tmp_path):
    store = _store(tmp_path)
    _add_policy(store, {"max_retries": 1}, reserve=True)
    (event,) = _by_reason(notify.derive(None, store, project_name="example", now=NOW), "retry_ceiling_used")
    assert event["code"] == "RETRY_CEILING"


def test_deriving_twice_produces_the_same_keys_whatever_the_order(tmp_path):
    store = _store(tmp_path)
    _add_operation(store, [("authorized", {"identity": {"actor": "t"}}),
                           ("failed", {"failure_class": "OperationError"})],
                   candidate_key="c1")
    _add_operation(store, candidate_key="c2")
    first = notify.derive(None, store, project_name="example", now=NOW)
    second = notify.derive(None, store, project_name="example", now=NOW)
    assert sorted(notifications.key(event) for event in first) == \
        sorted(notifications.key(event) for event in second)
    assert len({notifications.key(event) for event in first}) == len(first)


def test_a_card_maps_to_a_person_event_or_to_nothing():
    card = portal_state.Card("ADJUDICATION", "flow abc", "Q02", "no verdict recorded",
                             "claimstone adjudicate ...", "note")
    event = notify.card_event("example", card)
    assert event["reason"] == "signature_required"
    assert event["ids"] == ["Q02"]
    assert notify.card_event("example", portal_state.Card(
        "ACQUISITION", "", "doi:1", "acquisition failed", "cmd", "note")) is None
    protocol = notify.card_event("example", portal_state.Card(
        "PROTOCOL", "", "flow", "binding DRIFTED", None, "note"))
    assert protocol["reason"] == "integrity_error" and protocol["code"] == "PROTOCOL"


def test_a_round_below_the_floor_is_one_event_with_its_coverage():
    event = notify.floor_event("example", "round-1", False, {
        "status": admissibility.INSUFFICIENT, "found": 10, "rate": 0.4})
    assert event["reason"] == "round_below_floor"
    assert event["count"] == 10
    assert event["code"] == admissibility.INSUFFICIENT
    assert notify.floor_event("example", "round-1", False, {
        "status": admissibility.OK, "found": 10, "rate": 0.9}) is None
    assert notify.floor_event("example", "empty", False, {
        "status": admissibility.INSUFFICIENT, "found": 0, "rate": None}) is None


def test_the_portal_inbox_is_the_source_of_what_needs_a_person(tmp_path):
    """The wiring, not the mapping: every event derived from a real project names that
    project, and reading the inbox does not raise on a complete round."""
    from tests.test_portal_state import build_workspace

    _projects_dir, _store_dir, project, store = build_workspace(tmp_path)
    events = notify.derive(project, store, now=NOW)
    assert all(event["project"] == project.name for event in events)
