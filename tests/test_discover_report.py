"""Three quantities, reported separately, and a fourth that must not exist."""

from claimstone import discover_report
from claimstone.store import Store


def candidate(key, *, channel, klass="ACA", round_name="routine", topic="T01"):
    return {"candidate_key": key, "channel": channel, "source_class": klass,
            "round": round_name, "topic_id": topic, "source_api": "openalex",
            "query_hash": "abcd1234", "title": key}


def _store(tmp_path, rows, references=0):
    store = Store("t", base=tmp_path)
    for row in rows:
        store.append("candidates.jsonl", row)
    for n in range(references):
        store.append("references.jsonl", {"key": f"title:ref {n}", "citations_in_corpus": 1})
    return store


def test_the_two_channels_are_counted_separately(tmp_path):
    store = _store(tmp_path, [candidate("a", channel="keyword"),
                              candidate("b", channel="keyword"),
                              candidate("c", channel="citation")], references=711)
    summary = discover_report.summarise(store)
    assert summary["keyword"]["candidates"] == 2
    assert summary["citation"]["candidates"] == 1
    assert summary["citation"]["references_seen"] == 711


def test_the_overlap_is_the_third_quantity(tmp_path):
    store = _store(tmp_path, [candidate("title:shared work here and now", channel="keyword"),
                              candidate("title:only from search at all", channel="keyword")])
    store.append("references.jsonl", {"key": "title:shared work here and now",
                                      "citations_in_corpus": 3})
    summary = discover_report.summarise(store)
    assert summary["overlap"] == 1


def test_unclassified_candidates_are_reported_with_their_attributes(tmp_path):
    rows = [{**candidate("a", channel="keyword", klass=None), "venue_type": "conference"},
            {**candidate("b", channel="keyword", klass=None), "venue_type": "conference"},
            {**candidate("c", channel="keyword", klass=None), "venue_type": "book-series"}]
    summary = discover_report.summarise(_store(tmp_path, rows))
    assert summary["unclassified"] == 3
    # "3 unclassified" is not actionable; naming the values is what points at the missing rule.
    assert summary["uncovered"] == {"conference": 2, "book-series": 1}


def test_a_round_can_be_isolated(tmp_path):
    store = _store(tmp_path, [candidate("a", channel="keyword", round_name="spring"),
                              candidate("b", channel="keyword", round_name="autumn")])
    assert discover_report.summarise(store, round_name="autumn")["keyword"]["candidates"] == 1


def test_there_is_no_population_estimate_anywhere_in_the_module():
    # Lincoln-Petersen is computable from these three numbers and all three of its assumptions
    # are violated here — one of them by our own citation threshold. This test exists so that
    # adding it means arguing with spec section 6 rather than quietly shipping it.
    import inspect

    source = inspect.getsource(discover_report)
    for forbidden in ("lincoln", "petersen", "population", "completeness", "coverage_pct"):
        assert forbidden not in source.lower(), f"{forbidden!r} appears in discover_report"


def test_the_summary_says_what_it_refuses_to_say(tmp_path):
    store = _store(tmp_path, [candidate("a", channel="keyword")], references=711)
    summary = discover_report.summarise(store)
    assert "estimate" in summary["caveat"].lower()
