"""Re-judging bytes already held, when the gate changes but the corpus does not."""

import pytest

from claimstone import gate_audit
from claimstone.store import Store
from tests.test_fulltext import page, pdf


def _round(tmp_path):
    """A round recorded by a gateless acquire: 'acquired' set on HTTP 200 alone."""
    store = Store("t", base=tmp_path)
    for key, body, ctype, acquired in (
        ("a", pdf(), "application/pdf", True),
        ("b", page(60), "text/html", True),        # a summary page, wrongly accepted
        ("c", None, "text/html", False),           # a genuine 403, no bytes
    ):
        row = {"candidate_key": key, "source_id": key.upper(), "acquired": acquired,
               "url": f"https://x.example/{key}", "content_type": ctype,
               "fetched_at": "2026-09-22T10:00:00+00:00", "attempts": []}
        if body is not None:
            digest, path = store.store_bytes(body, ".pdf" if "pdf" in ctype else ".html")
            row |= {"sha256": digest, "stored_at": str(path)}
        else:
            row |= {"failure_class": "PAYWALL_403"}
        store.append("acquisitions.jsonl", row)
        store.append("candidates.jsonl", {"candidate_key": key, "source_class": "ACA",
                                          "source_id": key.upper()})
    return store


def test_regate_corrects_a_row_accepted_without_a_gate(tmp_path):
    store = _round(tmp_path)
    rows = list(gate_audit.regate(store, campaign="regate-v2"))
    by_key = {r["candidate_key"]: r for r in rows}
    assert by_key["a"]["acquired"] is True
    assert by_key["b"]["acquired"] is False
    assert by_key["b"]["failure_class"] == "ABSTRACT_ONLY"


def test_regate_leaves_a_source_with_no_bytes_alone(tmp_path):
    store = _round(tmp_path)
    keys = {r["candidate_key"] for r in gate_audit.regate(store, campaign="regate-v2")}
    # Nothing to re-judge: no bytes ever arrived, and the 403 stands as recorded.
    assert "c" not in keys


def test_regate_backfills_the_source_class_from_the_candidate(tmp_path):
    store = _round(tmp_path)
    rows = list(gate_audit.regate(store, campaign="regate-v2"))
    assert all(row["source_class"] == "ACA" for row in rows)


def test_regate_refuses_a_candidate_with_no_class_anywhere(tmp_path):
    store = Store("t", base=tmp_path)
    digest, path = store.store_bytes(pdf(), ".pdf")
    store.append("acquisitions.jsonl", {
        "candidate_key": "a", "acquired": True, "url": "https://x.example/a",
        "content_type": "application/pdf", "sha256": digest, "stored_at": str(path),
        "attempts": []})
    from claimstone.acquire import MissingSourceClass

    with pytest.raises(MissingSourceClass):
        list(gate_audit.regate(store, campaign="regate-v2"))


def test_regate_records_that_no_network_was_involved(tmp_path):
    store = _round(tmp_path)
    rows = list(gate_audit.regate(store, campaign="regate-v2"))
    assert all(row["regated_from"] == "2026-09-22T10:00:00+00:00" for row in rows)
    # One synthetic attempt per row, with no HTTP status: nothing was requested.
    assert all(len(row["attempts"]) == 1 for row in rows)
    assert all(row["attempts"][0]["http_status"] is None for row in rows)


def test_a_rejected_regate_still_points_at_the_bytes(tmp_path):
    # Otherwise the next gate_version cannot re-judge what is still on disk.
    store = _round(tmp_path)
    rows = list(gate_audit.regate(store, campaign="first"))
    rejected = next(r for r in rows if not r["acquired"])
    assert rejected["stored_path"] is None          # nothing was accepted at row level
    assert rejected["attempts"][0]["stored_path"]   # but the artifact is still findable
    # And a second pass can therefore re-judge every artifact the first pass saw.
    again = list(gate_audit.regate(store, campaign="second"))
    assert len(again) == len(rows)


def test_regate_is_appended_and_wins_the_collapse(tmp_path):
    from claimstone import admissibility

    store = _round(tmp_path)
    list(gate_audit.regate(store, campaign="regate-v2"))
    result = admissibility.rate(store)
    # One PDF survives; the summary page does not; the 403 never did.
    assert (result["acquired"], result["attempted"]) == (1, 3)


def test_regate_opens_no_socket(tmp_path, monkeypatch):
    import socket

    store = _round(tmp_path)

    def refuse(*args, **kwargs):
        raise AssertionError("regate must not touch the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    list(gate_audit.regate(store, campaign="regate-v2"))


def test_regate_prefers_the_candidates_class_over_a_stale_ledger_row(tmp_path):
    # An earlier round recorded the manifest's own word for the class. The candidate has since
    # been re-imported with the id it resolves to, and that is what must land on the new row.
    store = Store("t", base=tmp_path)
    digest, path = store.store_bytes(pdf(), ".pdf")
    store.append("candidates.jsonl", {"candidate_key": "a", "source_class": "ACA"})
    store.append("acquisitions.jsonl", {
        "candidate_key": "a", "source_class": "academic", "acquired": True,
        "url": "https://x.example/a", "content_type": "application/pdf",
        "sha256": digest, "stored_at": str(path), "attempts": []})
    row = next(iter(gate_audit.regate(store, campaign="regate-v2")))
    assert row["source_class"] == "ACA"
