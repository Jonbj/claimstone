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


# The second ratio needs a denominator, and the registry is where it lives.

class FakeProject:
    from claimstone.config import Question as _Q
    questions = (
        _Q(id="H02", text="a", kind="effect"),
        _Q(id="H23", text="b", kind="effect"),
        _Q(id="H06", text="c", kind="heterogeneity"),
        _Q(id="H11", text="d", kind="operational"),
    )


def test_coverage_is_against_the_questions_that_can_receive_a_verdict(tmp_path):
    """Three of the four, because an `operational` question receives no verdict (invariant 2) and
    counting it in the denominator would make full coverage unreachable by construction."""
    store = _store(tmp_path, [claim(1, question="H02")])
    summary = extract_report.summarise(store, project=FakeProject())
    assert summary["questions_asked"] == 3
    assert summary["questions_with_a_claim"] == 1
    assert round(summary["coverage"], 2) == 0.33


def test_a_question_nobody_asked_about_is_named_so_the_gap_is_visible(tmp_path):
    """`UNANSWERED_IN_LITERATURE` and `NEVER_ASKED` are different states, and this is the difference:
    a question with no claim after a complete round is the first, and one whose calls never ran is the
    second. Naming them is what lets somebody tell which."""
    store = _store(tmp_path, [claim(1, question="H02")])
    summary = extract_report.summarise(store, project=FakeProject())
    assert summary["questions_without_a_claim"] == ["H06", "H23"]


def test_without_a_project_the_coverage_is_unknown_rather_than_zero(tmp_path):
    """A ratio needs its denominator. Printing one without the registry would invent it."""
    summary = extract_report.summarise(_store(tmp_path, [claim(1)]))
    assert summary["questions_asked"] is None
    assert summary["coverage"] is None
    assert summary["questions_with_a_claim"] == 1
