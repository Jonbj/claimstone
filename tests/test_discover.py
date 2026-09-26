"""Both channels, the round, and what happens to a candidate no rule covers."""

from claimstone import discover
from claimstone.config import load_project
from claimstone.store import Store
from tests.fakes import FakeFetcher
from tests.test_searchers import CROSSREF, CROSSREF_PAYLOAD, OPENALEX, OPENALEX_PAYLOAD

PROJECT = "projects/example-news-and-returns"


def _fetcher():
    return FakeFetcher(json_pages={OPENALEX: OPENALEX_PAYLOAD, CROSSREF: CROSSREF_PAYLOAD})


def test_a_discovered_candidate_carries_a_source_class(tmp_path):
    # The whole point: without this, acquire raises MissingSourceClass on every row.
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    discover.run(project, store, _fetcher(), apis=("openalex",), topics=("T02",))
    rows = list(store.read("candidates.jsonl"))
    assert rows
    assert all(row["source_class"] == "ACA" for row in rows)


def test_the_round_is_written_on_every_candidate(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    discover.run(project, store, _fetcher(), apis=("openalex",), topics=("T02",),
                 round_name="autumn-sweep")
    assert all(row["round"] == "autumn-sweep" for row in store.read("candidates.jsonl"))


def test_the_round_defaults_to_routine(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    discover.run(project, store, _fetcher(), apis=("openalex",), topics=("T02",))
    assert all(row["round"] == "routine" for row in store.read("candidates.jsonl"))


def test_an_unclassified_candidate_is_written_and_counted(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    payload = {"results": [{**OPENALEX_PAYLOAD["results"][0],
                            "primary_location": {"landing_page_url": "https://x.example/a",
                                                 "source": {"display_name": "A conf",
                                                            "type": "conference"}}}]}
    fetcher = FakeFetcher(json_pages={OPENALEX: payload})
    result = discover.run(project, store, fetcher, apis=("openalex",), topics=("T02",))
    assert result["unclassified"] == 1
    rows = list(store.read("candidates.jsonl"))
    assert rows[0]["source_class"] is None
    # Not discarded: it is visible, and the remedy is to declare a rule.
    assert result["uncovered"] == {"openalex_source_type": {"conference": 1}}


def test_the_same_candidate_is_not_written_twice(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    discover.run(project, store, _fetcher(), apis=("openalex",), topics=("T02",))
    second = discover.run(project, store, _fetcher(), apis=("openalex",), topics=("T02",))
    assert second["new"] == 0
    assert len(list(store.read("candidates.jsonl"))) == 1


def test_only_the_requested_topics_are_searched(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    fetcher = _fetcher()
    discover.run(project, store, fetcher, apis=("openalex",), topics=("T02",))
    topic = next(t for t in project.topics if t.id == "T02")
    assert len(fetcher.calls) == len(topic.terms)


import pytest


def reference(key, *, title, cited=2, year=2010, doi=None):
    return {"key": key, "title": title, "year": year, "authors": ["Someone"], "doi": doi,
            "cited_by": [f"S{n:02d}" for n in range(cited)], "citations_in_corpus": cited}


def test_a_reference_cited_twice_becomes_a_candidate(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("references.jsonl", reference(
        "title:is all that talk just noise", title="Is all that talk just noise?", cited=3))
    result = discover.run_citations(project, store)
    assert result["new"] == 1
    row = next(iter(store.read("candidates.jsonl")))
    assert row["channel"] == "citation"
    assert row["source_api"] == "citation"
    assert row["citations_in_corpus"] == 3
    assert row["cited_by"] == ["S00", "S01", "S02"]


def test_a_reference_cited_once_is_not_admitted(tmp_path):
    # 657 of the 711 measured references are cited once. Admitting them all would mean 711
    # acquisition attempts, mostly against textbooks with no open copy.
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("references.jsonl", reference("title:a", title="A lone citation", cited=1))
    assert discover.run_citations(project, store)["new"] == 0


def test_a_reference_too_old_is_not_admitted(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("references.jsonl", reference("title:b", title="Risk, return, and equilibrium",
                                              cited=3, year=1973))
    assert discover.run_citations(project, store)["new"] == 0


def test_a_title_fragment_is_not_admitted(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("references.jsonl", reference("title:see example", title="See Example", cited=3))
    assert discover.run_citations(project, store)["new"] == 0


def test_the_citation_channel_opens_no_socket(tmp_path, monkeypatch):
    import socket

    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("references.jsonl", reference("title:x", title="A long enough title here",
                                               cited=2))

    def refuse(*args, **kwargs):
        raise AssertionError("the citation channel reads a ledger, not the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    discover.run_citations(project, store)


def test_no_references_file_is_reported_as_nothing_to_read(tmp_path):
    # Not "zero citation candidates", which would read as the bibliography having found nothing.
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    result = discover.run_citations(project, store)
    assert result["references_available"] is False
    assert result["new"] == 0


def test_a_citation_candidate_gets_a_class_from_its_host_or_none(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("references.jsonl", reference(
        "title:a working paper title", title="A working paper title long enough", cited=2,
        doi="10.1234/xyz"))
    discover.run_citations(project, store)
    row = next(iter(store.read("candidates.jsonl")))
    # No venue type and a doi.org URL: no rule covers it, so it is null and counted.
    assert row["source_class"] is None


def test_the_threshold_is_configurable(tmp_path):
    from claimstone.config import load_citation_channel

    (tmp_path / "sources.yaml").write_text(
        "acquisition_floor: 0.8\nclasses:\n  - id: ACA\n    name: a\n    weight_hint: highest\n"
        "citation_channel:\n  min_citations_in_corpus: 1\n  min_year: 2000\n"
        "  require_title_chars: 10\n", encoding="utf-8")
    assert load_citation_channel(tmp_path) == {
        "min_citations_in_corpus": 1, "min_year": 2000, "require_title_chars": 10}


def test_an_unknown_citation_setting_is_an_error(tmp_path):
    from claimstone.config import ConfigError, load_citation_channel

    (tmp_path / "sources.yaml").write_text(
        "acquisition_floor: 0.8\nclasses: []\ncitation_channel:\n  min_fame: 3\n",
        encoding="utf-8")
    with pytest.raises(ConfigError, match="min_fame"):
        load_citation_channel(tmp_path)


def test_a_banner_title_is_noted_as_a_possible_duplicate(tmp_path):
    # Measured: GROBID took an NBER cover banner as a title, so one work has two keys. 15 such
    # cases in the first corpus.
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("candidates.jsonl", {
        "candidate_key": "title:which news moves stock prices a textual analysis",
        "title": "Which News Moves Stock Prices? A Textual Analysis", "source_class": "ACA"})
    store.append("references.jsonl", reference(
        "title:nber working paper series which news moves stock prices a textual analysis",
        title="NBER WORKING PAPER SERIES WHICH NEWS MOVES STOCK PRICES A TEXTUAL ANALYSIS",
        cited=2))
    discover.run_citations(project, store)
    added = [r for r in store.read("candidates.jsonl") if r.get("channel") == "citation"]
    assert added[0]["possible_duplicate_of"] == \
        "title:which news moves stock prices a textual analysis"


def test_a_noted_duplicate_is_still_written_as_its_own_candidate(tmp_path):
    # A duplicate costs one wasted fetch, and not even a second download since bytes are
    # content-addressed. A wrong merge loses a source and misattributes its claims.
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("candidates.jsonl", {
        "candidate_key": "title:which news moves stock prices a textual analysis",
        "title": "Which News Moves Stock Prices? A Textual Analysis"})
    store.append("references.jsonl", reference(
        "title:nber working paper series which news moves stock prices a textual analysis",
        title="NBER WORKING PAPER SERIES WHICH NEWS MOVES STOCK PRICES A TEXTUAL ANALYSIS",
        cited=2))
    result = discover.run_citations(project, store)
    assert result["new"] == 1
    assert result["possible_duplicates"] == 1


def test_a_short_shared_prefix_is_not_a_near_match(tmp_path):
    # The check needs 25 characters of the shorter title, or every paper about returns would
    # look like every other one.
    assert discover.near_match("title:on returns", {"title:on returns and news and more"}) is None


def test_containment_is_the_declared_rule_and_its_false_positive_is_known():
    # Measured: "And the Cross-Section of Expected Returns" (Harvey, Liu, Zhu) is contained in
    # "Media coverage and the cross-section of expected returns" (Fang, Peress) and they are
    # different papers. The rule keeps it because the outcome is a note, never a merge.
    held = {"title:media coverage and the cross section of expected returns"}
    assert discover.near_match("title:and the cross section of expected returns", held) == \
        "title:media coverage and the cross section of expected returns"
