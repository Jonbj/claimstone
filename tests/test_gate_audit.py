"""Re-running the gate over stored bytes: free, offline, and the only calibration we have."""

from claimstone import fulltext, gate_audit
from claimstone.store import Store
from tests.test_fulltext import cited, page, pdf


def _corpus(tmp_path):
    """Three artifacts: a real PDF, a long cited article, a short page near the threshold."""
    store = Store("t", base=tmp_path)
    for key, body, ctype in (
        ("a", pdf(), "application/pdf"),
        ("b", cited(400), "text/html"),
        ("c", page(30), "text/html"),
    ):
        _, path = store.store_bytes(body, ".pdf" if "pdf" in ctype else ".html")
        store.append("acquisitions.jsonl", {
            "candidate_key": key, "source_class": "ACA", "source_id": key.upper(),
            "acquired": ctype == "application/pdf" or key == "b",
            "url": f"https://x.example/{key}",
            "attempts": [{"url": f"https://x.example/{key}", "http_status": 200,
                          "content_type": ctype, "stored_path": str(path),
                          "gate_kind": None, "gate_reason": None}],
        })
    for key, row in store.latest_by('acquisitions.jsonl', 'candidate_key').items():
        store.append('candidates.jsonl', {'candidate_key': key, 'source_class': row['source_class']})
    return store


def test_the_sweep_reports_a_rate_per_threshold_value(tmp_path):
    store = _corpus(tmp_path)
    result = gate_audit.sweep(store, "min_text_chars", [500, 3000, 20000])
    assert [point["value"] for point in result] == [500, 3000, 20000]
    assert all(0.0 <= point["rate"] <= 1.0 for point in result)


def test_raising_the_fulltext_bar_cannot_raise_the_rate(tmp_path):
    store = _corpus(tmp_path)
    rates = [p["rate"] for p in gate_audit.sweep(store, "fulltext_chars", [1000, 20000, 90000])]
    assert rates == sorted(rates, reverse=True)


def test_the_sweep_opens_no_socket(tmp_path, monkeypatch):
    import socket

    store = _corpus(tmp_path)

    def refuse(*args, **kwargs):
        raise AssertionError("gate-audit must not touch the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    gate_audit.sweep(store, "min_text_chars", [1000, 3000])


def test_an_unknown_threshold_name_is_refused(tmp_path):
    import pytest

    store = _corpus(tmp_path)
    with pytest.raises(ValueError, match="nonsense"):
        gate_audit.sweep(store, "nonsense", [1, 2])


def test_rejections_name_the_phrase_that_triggered_them(tmp_path):
    store = Store("t", base=tmp_path)
    body = page(40, "<p>Purchase PDF to read the full article.</p>")
    _, path = store.store_bytes(body, ".html")
    store.append("acquisitions.jsonl", {
        "candidate_key": "a", "source_id": "S01", "source_class": "ACA", "acquired": False,
        "failure_class": "LANDING_PAGE_ONLY", "url": "https://p.example/a",
        "attempts": [{"url": "https://p.example/a", "http_status": 200,
                      "content_type": "text/html", "stored_path": str(path),
                      "gate_kind": "LANDING_PAGE_ONLY", "gate_reason": "x"}],
    })
    listing = gate_audit.rejections(store)
    assert listing[0]["source_id"] == "S01"
    assert listing[0]["kind"] == fulltext.LANDING_PAGE_ONLY
    assert "purchase pdf" in listing[0]["reason"]
    assert listing[0]["chars"] is not None


def test_an_artifact_whose_bytes_are_gone_is_reported_not_skipped(tmp_path):
    # An audit that silently skips what it cannot read reports a cleaner corpus than exists.
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", {
        "candidate_key": "a", "source_id": "S01", "source_class": "ACA", "acquired": False,
        "failure_class": "ABSTRACT_ONLY", "url": "https://p.example/a",
        "attempts": [{"url": "https://p.example/a", "http_status": 200,
                      "stored_path": str(tmp_path / "gone.html"), "content_type": "text/html",
                      "gate_kind": "ABSTRACT_ONLY", "gate_reason": "x"}],
    })
    listing = gate_audit.rejections(store)
    assert listing[0]["kind"] == gate_audit.MISSING


def test_a_row_from_the_older_schema_is_still_audited(tmp_path):
    # The first measured round wrote the accepted artifact at the top level as `stored_at` and
    # carried no stored_path on its attempts. Reading only the attempts would make the audit
    # silently empty on that corpus, which is the one worth auditing.
    store = Store("t", base=tmp_path)
    _, path = store.store_bytes(page(60), ".html")
    store.append("acquisitions.jsonl", {
        "candidate_key": "a", "source_id": "S01", "source_class": "IND", "acquired": True,
        "url": "https://vendor.example/research/x", "content_type": "text/html",
        "sha256": path.stem, "stored_at": str(path),
        "attempts": [{"url": "https://vendor.example/research/x", "http_status": 200}],
    })
    listing = gate_audit.rejections(store)
    assert [item["kind"] for item in listing] == [fulltext.ABSTRACT_ONLY]
    store.append("candidates.jsonl", {"candidate_key": "a", "source_class": "IND"})
    assert gate_audit.sweep(store, "fulltext_chars", [1000])[0]["rate"] == 1.0


def test_the_sweep_denominator_is_every_candidate_not_only_those_with_bytes(tmp_path):
    # A 403 cannot pass the gate at any threshold. Leaving it out of the denominator would make
    # the sweep's "rate" a different number from the one `report` prints under the same name.
    store = _corpus(tmp_path)
    store.append("acquisitions.jsonl", {
        "candidate_key": "d", "source_id": "D", "source_class": "ACA", "acquired": False,
        "failure_class": "PAYWALL_403", "url": "https://wall.example/d", "attempts": [],
    })
    store.append("candidates.jsonl", {"candidate_key": "d", "source_class": "ACA"})
    point = gate_audit.sweep(store, "min_text_chars", [3000])[0]
    assert point["attempted"] == 4
    assert point["accepted"] == 2
    assert point["rate"] == 0.5


def test_an_artifact_named_by_an_earlier_row_is_still_found(tmp_path):
    # Append-only plus content-addressed means a pointer to bytes never goes stale. A later row
    # that happens not to mention an artifact — which a rejection does, since row-level
    # stored_path means "what we accepted" — must not hide it from the audit.
    store = Store("t", base=tmp_path)
    _, path = store.store_bytes(page(60), ".html")
    store.append("acquisitions.jsonl", {
        "candidate_key": "a", "source_id": "S01", "source_class": "IND", "acquired": True,
        "url": "https://vendor.example/x", "content_type": "text/html",
        "stored_at": str(path), "attempts": []})
    store.append("acquisitions.jsonl", {
        "candidate_key": "a", "source_id": "S01", "source_class": "IND", "acquired": False,
        "failure_class": "ABSTRACT_ONLY", "url": "https://vendor.example/x",
        "stored_path": None, "attempts": [], "regated_from": "x"})
    listing = gate_audit.rejections(store)
    assert [item["kind"] for item in listing] == [fulltext.ABSTRACT_ONLY]
