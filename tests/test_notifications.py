"""The notification outbox (issue #5): an append-only record of events that need a
person, and of every attempt to tell them.

The outbox is derived from the ledgers, not written by the stages. An event is identified
by a deterministic key, so a stage re-run, a second `notify`, or a crashed process cannot
produce a second message for the same occurrence. Attempts are rows too: a send that
failed is a fact with a cause, never a silence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claimstone import notifications
from claimstone.store import Store


def _store(tmp_path: Path) -> Store:
    return Store("example", tmp_path)


def _event(**changes):
    row = {
        "event": "needs_person",
        "reason": "signature_required",
        "project": "example",
        "subject": "flow:abc/Q02",
        "ids": ["Q02"],
        "count": 1,
        "occurrence": "profile-1",
        "occurred_at": "2026-10-18T10:00:00+00:00",
    }
    row.update(changes)
    return row


def _rows(store: Store) -> list[dict]:
    return list(store.read(notifications.LEDGER))


def test_the_same_occurrence_is_recorded_once_however_often_it_is_derived(tmp_path):
    store = _store(tmp_path)
    first = notifications.record(store, _event())
    second = notifications.record(store, _event())
    assert first["event_key"] == second["event_key"]
    assert len(_rows(store)) == 1


def test_the_key_is_stable_across_processes_and_independent_of_key_order(tmp_path):
    """The key is what makes a restart safe: it must not depend on dict ordering or on
    anything a second process would compute differently."""
    store = _store(tmp_path)
    one = notifications.record(store, _event())
    two = notifications.record(store, dict(reversed(list(_event().items()))))
    assert one["event_key"] == two["event_key"]
    assert one["event_key"].startswith("n1-")


def test_a_different_occurrence_is_a_different_event(tmp_path):
    store = _store(tmp_path)
    one = notifications.record(store, _event(occurrence="profile-1"))
    two = notifications.record(store, _event(occurrence="profile-2"))
    assert one["event_key"] != two["event_key"]
    assert len(_rows(store)) == 2


def test_an_event_carries_only_ids_and_counts(tmp_path):
    """The structural guarantee behind "no claim text leaves the machine": an event has a
    fixed set of fields, and a free-text field is not one of them. A title, a quote or an
    abstract cannot be smuggled into the outbox because there is nowhere to put it."""
    with pytest.raises(ValueError, match="not an event field"):
        notifications.record(_store(tmp_path), _event(title="A study of things"))
    assert _rows(_store(tmp_path)) == []


def test_an_unknown_reason_is_refused(tmp_path):
    with pytest.raises(ValueError, match="reason"):
        notifications.record(_store(tmp_path), _event(reason="something_new"))
    assert _rows(_store(tmp_path)) == []


def test_a_code_is_an_identifier_not_prose(tmp_path):
    """A cause reaches the message as a code (`OperationError`, `DOMAIN_BUDGET_EXHAUSTED`).
    It is validated as an identifier, so a sentence cannot be sent through this field."""
    store = _store(tmp_path)
    row = notifications.record(store, _event(code="OperationError"))
    assert row["code"] == "OperationError"
    with pytest.raises(ValueError, match="code"):
        notifications.record(store, _event(code="the paper says the effect is large",
                                           occurrence="other"))
    assert len(_rows(store)) == 1


def test_a_hostile_id_cannot_forge_a_second_ledger_line(tmp_path):
    store = _store(tmp_path)
    notifications.record(store, _event(ids=["Q02\n{\"record\": \"attempt\"}\t"], subject="s\r"))
    (row,) = _rows(store)
    assert "\n" not in row["ids"][0] and "\t" not in row["ids"][0]
    assert "\r" not in row["subject"]


def test_an_attempt_records_its_outcome_and_its_cause(tmp_path):
    store = _store(tmp_path)
    event = notifications.record(store, _event())
    notifications.attempt(store, event["event_key"], "telegram", "FAILED",
                          http_status=500, failure_class="SERVER_ERROR",
                          detail="telegram answered 500", now="2026-10-18T10:01:00+00:00")
    rows = _rows(store)
    assert [row["record"] for row in rows] == ["event", "attempt"]
    attempt_row = rows[1]
    assert attempt_row["outcome"] == "FAILED"
    assert attempt_row["http_status"] == 500
    assert attempt_row["failure_class"] == "SERVER_ERROR"
    assert attempt_row["event_key"] == event["event_key"]
    assert attempt_row["attempt"] == 1


def test_an_unknown_outcome_is_refused(tmp_path):
    store = _store(tmp_path)
    event = notifications.record(store, _event())
    with pytest.raises(ValueError, match="outcome"):
        notifications.attempt(store, event["event_key"], "telegram", "PROBABLY_FINE")
    assert len(_rows(store)) == 1


def test_an_attempt_for_an_event_that_was_never_recorded_is_refused(tmp_path):
    with pytest.raises(ValueError, match="unknown event"):
        notifications.attempt(_store(tmp_path), "n1-nope", "telegram", "SENT")
    assert _rows(_store(tmp_path)) == []


def test_a_delivered_event_is_not_pending_again(tmp_path):
    store = _store(tmp_path)
    event = notifications.record(store, _event())
    assert [row["event_key"] for row in notifications.pending(store, "telegram")] == [
        event["event_key"]]
    notifications.attempt(store, event["event_key"], "telegram", "SENT", http_status=200)
    assert notifications.pending(store, "telegram") == []


def test_another_channel_does_not_consume_the_event(tmp_path):
    """#6 adds email on the same outbox: a Telegram send says nothing about email."""
    store = _store(tmp_path)
    event = notifications.record(store, _event())
    notifications.attempt(store, event["event_key"], "telegram", "SENT")
    assert notifications.pending(store, "email") == [
        row for row in _rows(store) if row["record"] == "event"]
    assert notifications.pending(store, "email")[0]["event_key"] == event["event_key"]


def test_a_failed_attempt_is_retried_only_after_the_interval(tmp_path):
    store = _store(tmp_path)
    event = notifications.record(store, _event())
    notifications.attempt(store, event["event_key"], "telegram", "TIMEOUT",
                          now="2026-10-18T10:01:00+00:00")
    assert notifications.pending(store, "telegram", now="2026-10-18T10:05:00+00:00") == []
    later = notifications.pending(store, "telegram", now="2026-10-18T10:30:00+00:00")
    assert [row["event_key"] for row in later] == [event["event_key"]]


def test_retries_are_capped_per_event_and_channel(tmp_path):
    store = _store(tmp_path)
    event = notifications.record(store, _event())
    for number in range(notifications.MAX_ATTEMPTS):
        notifications.attempt(store, event["event_key"], "telegram", "CONNECTION",
                              now=f"2026-10-18T10:0{number}:00+00:00")
    assert notifications.pending(store, "telegram", now="2026-10-19T00:00:00+00:00") == []


def test_deliver_sends_at_most_the_rate_limit_and_leaves_the_rest_pending(tmp_path):
    store = _store(tmp_path)
    for number in range(3):
        notifications.record(store, _event(occurrence=f"profile-{number}",
                                           subject=f"flow:abc/Q0{number}",
                                           ids=[f"Q0{number}"]))
    sent = []

    class Channel:
        name = "telegram"

        def send(self, event):
            sent.append(event["event_key"])
            return notifications.SendResult("SENT", http_status=200)

    summary = notifications.deliver(store, Channel(), limit=2)
    assert summary["sent"] == 2
    assert len(sent) == 2
    assert len(notifications.pending(store, "telegram")) == 1


def test_deliver_writes_one_attempt_row_per_send(tmp_path):
    store = _store(tmp_path)
    notifications.record(store, _event())

    class Channel:
        name = "telegram"

        def send(self, event):
            return notifications.SendResult("SENT", http_status=200)

    notifications.deliver(store, Channel(), limit=10)
    attempts = [row for row in _rows(store) if row["record"] == "attempt"]
    assert len(attempts) == 1
    assert attempts[0]["outcome"] == "SENT"


def test_deliver_records_a_channel_exception_as_a_failure_not_a_silence(tmp_path):
    """A swallowed send is the defect this ledger exists to make impossible: an exception
    from the channel is an attempt with a cause, and the drain goes on."""
    store = _store(tmp_path)
    notifications.record(store, _event())

    class Channel:
        name = "telegram"

        def send(self, event):
            raise TimeoutError("the connection timed out")

    summary = notifications.deliver(store, Channel(), limit=10)
    assert summary["timed_out"] == 1
    (attempt,) = [row for row in _rows(store) if row["record"] == "attempt"]
    assert attempt["outcome"] == "TIMEOUT"
    assert attempt["failure_class"] == "TIMEOUT"
    assert "timed out" in attempt["detail"]


def test_a_detail_cannot_forge_a_ledger_line(tmp_path):
    store = _store(tmp_path)
    event = notifications.record(store, _event())
    notifications.attempt(store, event["event_key"], "telegram", "FAILED",
                          detail="boom\n{\"record\": \"event\"}\t")
    (attempt,) = [row for row in _rows(store) if row["record"] == "attempt"]
    assert "\n" not in attempt["detail"] and "\t" not in attempt["detail"]


def test_the_first_drain_marks_its_start_so_history_is_not_replayed(tmp_path):
    """An operator who enables notifications should be told what needs them now, not every
    retry success the project has ever had. The start row is the watermark one-shot events
    are compared against; it is written once."""
    store = _store(tmp_path)
    assert notifications.watermark(store) is None
    first = notifications.start(store, now="2026-10-18T09:00:00+00:00")
    second = notifications.start(store, now="2026-10-19T09:00:00+00:00")
    assert first == second
    assert notifications.watermark(store) == "2026-10-18T09:00:00+00:00"


def test_the_ledger_is_plain_jsonl_sorted_and_reloadable(tmp_path):
    store = _store(tmp_path)
    notifications.record(store, _event())
    text = store.path(notifications.LEDGER).read_text()
    assert text.endswith("\n")
    assert json.loads(text)["record"] == "event"
