"""Append-only storage, and what "resumable after a crash" actually guarantees."""

import pytest

from claimstone.store import LedgerCorrupt, Store


def test_a_complete_ledger_reads_back(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("x.jsonl", {"k": 1})
    store.append("x.jsonl", {"k": 2})
    assert [row["k"] for row in store.read("x.jsonl")] == [1, 2]


def test_a_torn_last_line_is_skipped_and_recorded(tmp_path):
    # A process killed mid-append leaves a line with no newline. That is the recoverable case,
    # and it is recognised by incompleteness rather than by failing to parse — a half-written
    # row can be valid JSON right up to the truncation point.
    store = Store("t", base=tmp_path)
    store.append("x.jsonl", {"k": 1})
    with store.path("x.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"k": 2, "partial"')
    rows = list(store.read("x.jsonl"))
    assert [row["k"] for row in rows] == [1]
    assert store.torn_tail == ["x.jsonl"]


def test_a_torn_line_that_is_valid_json_is_still_skipped(tmp_path):
    # {"k": 2} is valid JSON and still incomplete: the writer had more to write. Judging by
    # parseability would silently accept a truncated row as a whole one.
    store = Store("t", base=tmp_path)
    store.append("x.jsonl", {"k": 1})
    with store.path("x.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"k": 2}')
    assert [row["k"] for row in store.read("x.jsonl")] == [1]


def test_corruption_that_is_not_at_the_end_raises(tmp_path):
    # Mid-file damage is not a crash artefact. Skipping it would drop a row from a denominator
    # without telling anyone, which is the class of failure this project exists to refuse.
    store = Store("t", base=tmp_path)
    store.path("x.jsonl").parent.mkdir(parents=True, exist_ok=True)
    store.path("x.jsonl").write_text('{"k": 1}\nnot json at all\n{"k": 3}\n', encoding="utf-8")
    with pytest.raises(LedgerCorrupt, match="line 2"):
        list(store.read("x.jsonl"))


def test_repair_truncates_a_torn_tail_so_the_next_append_is_clean(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("x.jsonl", {"k": 1})
    with store.path("x.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"k": 2, "part')
    assert store.repair("x.jsonl") is True
    store.append("x.jsonl", {"k": 3})
    assert [row["k"] for row in store.read("x.jsonl")] == [1, 3]
    assert store.torn_tail == []


def test_repair_leaves_an_intact_ledger_alone(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("x.jsonl", {"k": 1})
    assert store.repair("x.jsonl") is False
    assert [row["k"] for row in store.read("x.jsonl")] == [1]


def test_an_absent_ledger_is_empty_not_an_error(tmp_path):
    assert list(Store("t", base=tmp_path).read("nothing.jsonl")) == []


# --- appending after a crash must not make the damage permanent ----------------

def test_appending_after_a_torn_tail_repairs_it_first(tmp_path):
    # The first fix made a torn tail detectable and left append free to make it permanent:
    # complete row, crash mid-write, process restarts and appends, and the next read raises.
    # The torn line was never accepted by any reader, so truncating it loses nothing.
    store = Store("t", base=tmp_path)
    store.append("x.jsonl", {"k": 1})
    with store.path("x.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"k": 2, "partial"')
    store.append("x.jsonl", {"k": 3})
    assert [row["k"] for row in store.read("x.jsonl")] == [1, 3]


def test_a_repair_leaves_an_audit_row(tmp_path):
    # Something was lost. The rows that survive are consistent, and the operator has to know
    # that work between the last complete row and the restart needs redoing.
    store = Store("t", base=tmp_path)
    store.append("x.jsonl", {"k": 1})
    with store.path("x.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"k": 2, "part')
    store.append("x.jsonl", {"k": 3})
    audit = list(store.read("ledger_repairs.jsonl"))
    assert audit[0]["ledger"] == "x.jsonl"
    assert audit[0]["discarded_bytes"] == len('{"k": 2, "part')


def test_the_audit_ledger_repairs_itself_without_recursing(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("ledger_repairs.jsonl", {"ledger": "x.jsonl"})
    with store.path("ledger_repairs.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"ledger": "tr')
    store.append("ledger_repairs.jsonl", {"ledger": "y.jsonl"})
    rows = list(store.read("ledger_repairs.jsonl"))
    assert [r["ledger"] for r in rows] == ["x.jsonl", "y.jsonl"]


def test_an_intact_ledger_gets_no_audit_row(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("x.jsonl", {"k": 1})
    store.append("x.jsonl", {"k": 2})
    assert list(store.read("ledger_repairs.jsonl")) == []


def test_a_ledger_under_a_subpath_can_be_appended_to(tmp_path):
    """`calls/<lane>/<batch>/requests.jsonl` is one. Creating only the project root left append
    raising FileNotFoundError on a name that is otherwise perfectly valid."""
    store = Store("t", base=tmp_path)
    store.append("calls/extract/b1/requests.jsonl", {"call_id": "x"})
    assert [row["call_id"] for row in store.read("calls/extract/b1/requests.jsonl")] == ["x"]
