"""Two ratios, never fused, and studies counted by source rather than by record."""

from claimstone import extract_report
from claimstone.store import Store


def claim(n, *, question="H02", source="S01", stance="SUPPORTS", klass="ACA"):
    return {"claim_id": f"c{n}", "question_id": question, "source_id": source, "stance": stance,
            "source_class": klass, "call_id": "k1", "chunk_id": f"{source}#c{n}"}


def _store(tmp_path, claims=(), rejections=()):
    store = Store("t", base=tmp_path)
    for row in claims:
        store.append("claims.jsonl", row)
    for row in rejections:
        store.append("rejections.jsonl", row)
    return store


def test_ten_claims_from_one_paper_are_one_study():
    """Counting them as ten is the vote counting invariant 7 forbids."""
    import pathlib
    import tempfile

    store = _store(pathlib.Path(tempfile.mkdtemp()), [claim(n) for n in range(10)])
    summary = extract_report.summarise(store)
    assert summary["by_question"]["H02"]["claims"] == 10
    assert summary["by_question"]["H02"]["studies"] == 1


def test_the_gate_ratio_and_the_coverage_are_separate_numbers(tmp_path):
    store = _store(tmp_path, [claim(1), claim(2, question="H23")],
                   [{"claim_id": "r1", "failure": "QUOTE_NOT_FOUND", "call_id": "k1"}])
    summary = extract_report.summarise(store)
    assert (summary["accepted"], summary["rejected"], summary["proposed"]) == (2, 1, 3)
    assert round(summary["gate_rate"], 2) == 0.67
    assert summary["questions_with_a_claim"] == 2


def test_nothing_offered_has_no_pass_rate_rather_than_a_perfect_one(tmp_path):
    """A gate that judged nothing has no pass rate, and 1.00 would describe a measurement never taken."""
    assert extract_report.summarise(_store(tmp_path))["gate_rate"] is None


def test_stances_and_classes_are_reported_per_question(tmp_path):
    store = _store(tmp_path, [claim(1), claim(2, stance="CONTRADICTS", source="S02", klass="WP")])
    bucket = extract_report.summarise(store)["by_question"]["H02"]
    assert bucket["stances"] == {"SUPPORTS": 1, "CONTRADICTS": 1}
    assert bucket["by_class"] == {"ACA": 1, "WP": 1}
    assert bucket["studies"] == 2


def test_failures_are_broken_down(tmp_path):
    store = _store(tmp_path, [claim(1)], [
        {"claim_id": "r1", "failure": "SECONDHAND_CLAIM", "call_id": "k1"},
        {"claim_id": "r2", "failure": "SECONDHAND_CLAIM", "call_id": "k1"},
        {"claim_id": "r3", "failure": "QUOTE_NOT_FOUND", "call_id": "k1"}])
    assert extract_report.summarise(store)["failures"] == {
        "SECONDHAND_CLAIM": 2, "QUOTE_NOT_FOUND": 1}
