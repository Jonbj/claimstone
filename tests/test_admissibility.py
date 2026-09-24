"""The figure that gates verdicts, and the collapse that keeps it honest."""

from claimstone import admissibility
from claimstone.config import load_project
from claimstone.store import Store


def _ledger(store, rows):
    for row in rows:
        store.append("acquisitions.jsonl", row)


def row(key, *, acquired, klass="ACA", failure=None, url="https://x.example/a"):
    return {"candidate_key": key, "source_class": klass, "acquired": acquired,
            "failure_class": failure, "url": url, "fetched_at": "2026-09-22T10:00:00+00:00"}


def test_a_failed_retry_does_not_erase_a_recorded_success(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [row("a", acquired=True), row("a", acquired=False, failure="PAYWALL_403")])
    assert admissibility.rate(store)["acquired"] == 1


def test_the_rate_is_acquired_over_attempted(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [row("a", acquired=True), row("b", acquired=True),
                    row("c", acquired=False, failure="PAYWALL_403")])
    result = admissibility.rate(store)
    assert (result["attempted"], result["acquired"]) == (3, 2)
    assert round(result["rate"], 2) == 0.67


def test_classes_are_reported_separately(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [row("a", acquired=True, klass="ACA"),
                    row("b", acquired=False, klass="DOC", failure="NOT_FOUND_404"),
                    row("c", acquired=False, klass="DOC", failure="PAYWALL_403")])
    by_class = admissibility.rate(store)["by_class"]
    assert by_class["ACA"] == {"attempted": 1, "acquired": 1, "rate": 1.0}
    assert by_class["DOC"]["rate"] == 0.0


def test_an_empty_ledger_has_no_rate_rather_than_a_rate_of_zero(tmp_path):
    store = Store("t", base=tmp_path)
    result = admissibility.rate(store)
    assert result["attempted"] == 0
    assert result["rate"] is None


def test_below_the_floor_the_round_produces_no_verdicts(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [row("a", acquired=True), row("b", acquired=False, failure="PAYWALL_403")])
    project = load_project("projects/example-news-and-returns")
    verdict = admissibility.admit(project, store)
    assert verdict["status"] == "INSUFFICIENT_ACQUISITION"
    assert verdict["floor"] == 0.80


def test_at_or_above_the_floor_the_round_is_admissible(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [row(k, acquired=True) for k in "abcd"]
                   + [row("e", acquired=False, failure="PAYWALL_403")])
    project = load_project("projects/example-news-and-returns")
    assert admissibility.admit(project, store)["status"] == "OK"


def test_there_is_no_override(tmp_path):
    import inspect

    source = inspect.getsource(admissibility.admit)
    assert "force" not in source and "override" not in source


def test_a_regate_supersedes_a_success_but_a_retry_does_not(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [
        row("a", acquired=True),                                    # accepted without a gate
        {**row("a", acquired=False, failure="ABSTRACT_ONLY"),
         "regated_from": "2026-09-22T10:00:00+00:00"},               # corrected judgement
    ])
    assert admissibility.rate(store)["acquired"] == 0

    store2 = Store("u", base=tmp_path)
    _ledger(store2, [row("a", acquired=True),
                     row("a", acquired=False, failure="PAYWALL_403")])  # a retry, not a re-gate
    assert admissibility.rate(store2)["acquired"] == 1


def test_a_real_acquisition_after_a_regate_wins_again(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [
        row("a", acquired=True),
        {**row("a", acquired=False, failure="ABSTRACT_ONLY"),
         "regated_from": "2026-09-22T10:00:00+00:00"},
        row("a", acquired=True),   # the cascade found the real document later
    ])
    assert admissibility.rate(store)["acquired"] == 1


def test_a_row_without_a_class_is_filed_under_the_candidates_class(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("candidates.jsonl", {"candidate_key": "a", "source_class": "ACA"})
    store.append("acquisitions.jsonl", {"candidate_key": "a", "acquired": False,
                                        "failure_class": "PAYWALL_403",
                                        "url": "https://wall.example/a"})
    by_class = admissibility.rate(store)["by_class"]
    assert "UNCLASSIFIED" not in by_class
    assert by_class["ACA"]["attempted"] == 1
