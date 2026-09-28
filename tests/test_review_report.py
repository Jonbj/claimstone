"""A precision-side comparison that says so, and names the number it cannot produce."""

from claimstone import review_report
from claimstone.store import Store
from claimstone.review import REVIEW_VERSION


def claim(n, *, backend="ollama-cloud", model="deepseek-v4.1-flash"):
    return {"claim_id": f"c{n}", "question_id": "H02", "backend": backend, "model": model}


def rev(n, verdict, *, backend="claude-cli", model="claude-opus-5",
        extracted=("ollama-cloud", "deepseek-v4.1-flash")):
    return {"claim_id": f"c{n}", "question_id": "H02", "verdict": verdict, "review_version": REVIEW_VERSION,
            "reviewed_by": {"backend": backend, "model": model, "harness_version": "x"},
            "extracted_by": {"backend": extracted[0], "model": extracted[1]}}


def _store(tmp_path, claims=(), reviews=(), rejections=()):
    store = Store("t", base=tmp_path)
    for row in claims:
        store.append("claims.jsonl", row)
    for row in reviews:
        store.append("reviews.jsonl", row)
    for row in rejections:
        store.append("rejections.jsonl", row)
    return store


def test_verdicts_are_grouped_by_the_reader_that_extracted(tmp_path):
    store = _store(tmp_path,
                   claims=[claim(1), claim(2), claim(3, backend="claude-cli", model="claude-opus-5")],
                   reviews=[rev(1, "SUPPORTED"), rev(2, "OVERSTATED")])
    summary = review_report.summarise(store)
    deepseek = summary["by_extractor"]["ollama-cloud/deepseek-v4.1-flash"]
    assert deepseek["claims"] == 2
    assert deepseek["verdicts"] == {"SUPPORTED": 1, "OVERSTATED": 1}
    assert deepseek["supported_share"] == 0.5
    assert summary["by_extractor"]["claude-cli/claude-opus-5"]["awaiting_review"] == 1


def test_an_unreviewed_claim_is_awaiting_and_not_counted_either_way(tmp_path):
    store = _store(tmp_path, claims=[claim(1), claim(2)], reviews=[rev(1, "SUPPORTED")])
    bucket = review_report.summarise(store)["by_extractor"]["ollama-cloud/deepseek-v4.1-flash"]
    assert (bucket["reviewed"], bucket["awaiting_review"]) == (1, 1)
    assert bucket["supported_share"] == 1.0, "the share is of what was reviewed, not of what exists"


def test_nothing_reviewed_has_no_share_rather_than_a_perfect_one(tmp_path):
    store = _store(tmp_path, claims=[claim(1)])
    assert review_report.summarise(store)["by_extractor"][
        "ollama-cloud/deepseek-v4.1-flash"]["supported_share"] is None


def test_the_gate_rejections_are_the_third_number_and_are_per_reader(tmp_path):
    store = _store(tmp_path, claims=[claim(1)], reviews=[rev(1, "SUPPORTED")],
                   rejections=[{"claim_id": "r1", "failure": "QUOTE_NOT_FOUND",
                                "backend": "ollama-cloud", "model": "deepseek-v4.1-flash"}])
    bucket = review_report.summarise(store)["by_extractor"]["ollama-cloud/deepseek-v4.1-flash"]
    assert bucket["gate_rejections"] == 1
    assert bucket["gate_rejections_by_reason"] == {"QUOTE_NOT_FOUND": 1}


def test_misses_are_named_as_unmeasured_rather_than_omitted(tmp_path):
    """A backend proposing one safe claim per chunk wins this table while missing ten results. Leaving the
    recall side out would let a reader assume it was covered."""
    summary = review_report.summarise(_store(tmp_path, claims=[claim(1)]))
    assert summary["misses"] is None
    assert "cannot be without" in summary["caveat"]


def test_the_reviewers_are_stated_because_one_fixed_reviewer_keeps_its_bias(tmp_path):
    store = _store(tmp_path, claims=[claim(1)], reviews=[rev(1, "SUPPORTED")])
    assert review_report.summarise(store)["reviewed_by"] == {"claude-cli/claude-opus-5": 1}
