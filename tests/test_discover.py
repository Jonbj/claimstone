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


def test_openalex_query_records_incomplete_first_page_even_when_one_candidate_is_kept(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    payload = {**OPENALEX_PAYLOAD, "meta": {"count": 42, "next_cursor": "opaque-next"}}
    fetcher = FakeFetcher(json_pages={OPENALEX: payload})
    discover.run(project, store, fetcher, apis=("openalex",), topics=("T02",),
                 per_query=1)
    queries = list(store.read("queries.jsonl"))
    assert queries and all(row["total_available"] == 42 for row in queries)
    assert all(row["depth_capped"] is True and row["next_cursor"] == "opaque-next"
               for row in queries)
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


# --- Resolution: the citation channel's candidates become fetchable ------------------------------

def _resolving_fetcher(work_title="Is all that talk just noise? A long enough title"):
    from tests.test_resolve_reference import OPENALEX, WORK

    return FakeFetcher(json_pages={OPENALEX: {"results": [{**WORK, "title": work_title}]}})


def test_resolution_gives_a_citation_candidate_a_class_and_an_address(tmp_path):
    """Before this, all 37 citation candidates on the real corpus were unclassified and 25 had no URL."""
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    title = "Is all that talk just noise? A long enough title"
    store.append("references.jsonl", reference("title:is all that talk just noise a long enough title",
                                              title=title, cited=3))
    result = discover.run_citations(project, store, fetcher=_resolving_fetcher(title))
    row = next(iter(store.read("candidates.jsonl")))
    assert row["source_class"] == "ACA"
    assert row["url"] == "https://x.example/talk"
    assert row["venue_type"] == "journal"
    assert row["resolution"] == "BY_TITLE"
    assert result["resolved"] == 1


def test_resolution_does_not_move_the_candidate_key(tmp_path):
    """The trap. `candidate_key` prefers a DOI, so a row that gains one on resolution would land under
    a second key — and the same work would be two candidates, one of them a ghost nothing supersedes.
    The citation channel keys on the reference, which is stable across resolution.
    """
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    title = "Is all that talk just noise? A long enough title"
    key = "title:is all that talk just noise a long enough title"
    store.append("references.jsonl", reference(key, title=title, cited=3))

    discover.run_citations(project, store)                                   # no network, unresolved
    discover.run_citations(project, store, fetcher=_resolving_fetcher(title))  # then resolved
    rows = list(store.read("candidates.jsonl"))
    assert {r["candidate_key"] for r in rows} == {key}
    latest = store.latest_by("candidates.jsonl", "candidate_key")[key]
    assert latest["doi"] == "10.1111/j.1540-6261.2004.00662.x"
    assert latest["source_class"] == "ACA"


def test_an_unresolved_candidate_records_why_and_is_retried_next_time(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    title = "A title that resolves to nothing at all here"
    store.append("references.jsonl", reference("title:a title that resolves to nothing at all here",
                                               title=title, cited=3))
    result = discover.run_citations(project, store, fetcher=FakeFetcher())
    assert result["resolved"] == 0
    assert result["unresolved"] == {"LOOKUP_FAILED": 1}
    row = next(iter(store.read("candidates.jsonl")))
    assert row["resolution"] == "LOOKUP_FAILED"
    assert row["source_class"] is None

    # A second pass with a working fetcher supersedes it rather than skipping it as already seen.
    again = discover.run_citations(project, store, fetcher=_resolving_fetcher(title))
    assert again["resolved"] == 1


def test_without_a_fetcher_nothing_is_resolved_and_nothing_is_requested(tmp_path):
    """`--channel citation` promises to read a ledger and open no socket. Resolution is opt-in."""
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("references.jsonl", reference("title:a perfectly good long title here",
                                               title="A perfectly good long title here", cited=3))
    result = discover.run_citations(project, store)
    assert result["resolved"] == 0
    assert result["unresolved"] == {"NOT_ATTEMPTED": 1}
    assert next(iter(store.read("candidates.jsonl")))["resolution"] == "NOT_ATTEMPTED"


def test_a_resolved_doi_matching_an_existing_candidate_is_noted_as_a_duplicate(tmp_path):
    """A certain duplicate, not a near-match: the same DOI under two keys. Still only noted, because
    a wrong merge loses a source and a duplicate costs one wasted fetch."""
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    title = "Is all that talk just noise? A long enough title"
    store.append("candidates.jsonl", {
        "candidate_key": "doi:10.1111/j.1540-6261.2004.00662.x",
        "doi": "10.1111/j.1540-6261.2004.00662.x", "channel": "keyword", "title": "Whatever"})
    store.append("references.jsonl", reference("title:is all that talk just noise a long enough title",
                                               title=title, cited=3))
    discover.run_citations(project, store, fetcher=_resolving_fetcher(title))
    row = [r for r in store.read("candidates.jsonl") if r.get("channel") == "citation"][0]
    assert row["possible_duplicate_of"] == "doi:10.1111/j.1540-6261.2004.00662.x"


def test_reclassify_reapplies_the_rules_without_a_request(tmp_path, monkeypatch):
    """The third time this pattern has been needed: `regate` for the content gate, `--rejudge` for a
    model answer, and now this. A judgement the engine makes over rules a project declares must be
    re-appliable when the rules change, and re-requesting what is already on disk would be a toll on
    editing a YAML file.
    """
    import socket

    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    # A candidate resolved under rules that did not yet cover it.
    store.append("candidates.jsonl", {
        "candidate_key": "title:a resolved work with a venue", "channel": "citation",
        "source_api": "openalex", "venue_type": "journal", "source_class": None,
        "resolution": "BY_TITLE", "round": "first", "title": "A resolved work with a venue",
        "url": "https://x.example/a"})

    def refuse(*args, **kwargs):
        raise AssertionError("reclassify re-reads a ledger; it must open no socket")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    result = discover.reclassify(project, store)
    assert result["changed"] == 1
    latest = store.latest_by("candidates.jsonl", "candidate_key")
    assert latest["title:a resolved work with a venue"]["source_class"] == "ACA"


def test_reclassify_writes_nothing_when_no_class_moves(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("candidates.jsonl", {
        "candidate_key": "doi:10.1/x", "channel": "keyword", "source_api": "openalex",
        "venue_type": "journal", "source_class": "ACA", "round": "first"})
    before = len(list(store.read("candidates.jsonl")))
    result = discover.reclassify(project, store)
    assert result["changed"] == 0
    assert len(list(store.read("candidates.jsonl"))) == before


def test_reclassify_keeps_the_round_that_found_a_candidate(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("candidates.jsonl", {
        "candidate_key": "title:a resolved work with a venue", "channel": "citation",
        "source_api": "openalex", "venue_type": "journal", "source_class": None,
        "round": "spring", "title": "A resolved work with a venue"})
    discover.reclassify(project, store)
    assert store.latest_by("candidates.jsonl", "candidate_key")[
        "title:a resolved work with a venue"]["round"] == "spring"


def test_reclassify_never_overrules_a_class_the_operator_declared(tmp_path):
    """Reproduced on the real store, destructively: reclassify overwrote 9 IND and 4 MET manifest rows
    with null and demoted 6 ACA to WP, because a manifest row has no venue type and the host rule
    matched some of them. A manifest states its class; invariant 6 says the class travels with the item
    and this is the item arriving with it. An inferred class must not replace a given one.
    """
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("candidates.jsonl", {
        "candidate_key": "doi:10.1/declared", "channel": "keyword", "source_api": "manifest",
        "venue_type": "", "url": "https://papers.ssrn.com/abstract=1", "source_class": "IND",
        "source_id": "IND001", "round": "manifest", "title": "A vendor paper"})

    result = discover.reclassify(project, store)
    assert result["changed"] == 0
    latest = store.latest_by("candidates.jsonl", "candidate_key")["doi:10.1/declared"]
    assert latest["source_class"] == "IND"
    # And it is not counted as an unclassified row needing a rule, because it needs none.
    assert result["unclassified"] == 0


# --- The feedback D26 asked for -------------------------------------------------------------------
#
# The gate rejected H02's only contradicting claim, correctly: ACA002 was reporting Roll (1988), a source
# nobody had read. Roll (1988) is in the bibliography as "R-squared", cited once — nine folded characters
# — so it fails both min_citations_in_corpus and require_title_chars and is invisible. Every rule behaved
# as declared, and the effect was that a question with a cited contradiction read as uncontested.

def rejection(claim, *, chunk="ACA002#c7", source="ACA002", failure="SECONDHAND_CLAIM"):
    return {"claim_id": f"r-{abs(hash(claim)) % 9999}", "failure": failure, "source_id": source,
            "chunk_id": chunk, "record": {"claim": claim, "question_id": "H02"}}


def test_a_work_named_in_a_secondhand_rejection_is_promoted_however_little_cited(tmp_path):
    """A work cited once for a contradiction is worth more here than a textbook cited three times."""
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("references.jsonl", {"key": "title:r squared", "title": "R-squared",
                                      "authors": ["Roll"], "year": 1988, "doi": None,
                                      "cited_by": ["ACA002"], "citations_in_corpus": 1})
    store.append("rejections.jsonl", rejection(
        "Roll (1988) found little discernible difference in return variation."))

    result = discover.promote_contested(project, store)
    assert result["named"] == 1
    assert result["promoted"] == 1
    row = next(iter(store.read("candidates.jsonl")))
    assert row["candidate_key"] == "title:r squared"
    assert row["promoted_by"] == "SECONDHAND_CLAIM"
    assert row["citations_in_corpus"] == 1


def test_only_a_secondhand_rejection_promotes_anything(tmp_path):
    """A quote that was not in the chunk names nothing and says nothing about another work."""
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("references.jsonl", {"key": "title:r squared", "title": "R-squared",
                                      "authors": ["Roll"], "citations_in_corpus": 1})
    store.append("rejections.jsonl", rejection("Roll (1988) found nothing.",
                                               failure="QUOTE_NOT_FOUND"))
    assert discover.promote_contested(project, store)["promoted"] == 0


def test_a_named_work_absent_from_the_bibliography_is_counted_and_not_invented(tmp_path):
    """Nothing here knows the work's title or address; the reference is what carries those. A name with
    no reference is reported so somebody can look, never guessed into a candidate."""
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("rejections.jsonl", rejection("Roll (1988) found little difference."))
    result = discover.promote_contested(project, store)
    assert result["named"] == 1
    assert result["promoted"] == 0
    assert result["unmatched"] == [["Roll", "1988"]]
    assert list(store.read("candidates.jsonl")) == []


def test_promoting_twice_adds_nothing(tmp_path):
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("references.jsonl", {"key": "title:r squared", "title": "R-squared",
                                      "authors": ["Roll"], "year": 1988,
                                      "citations_in_corpus": 1})
    store.append("rejections.jsonl", rejection("Roll (1988) found little difference."))
    discover.promote_contested(project, store)
    assert discover.promote_contested(project, store)["promoted"] == 0


def test_promotion_opens_no_socket(tmp_path, monkeypatch):
    import socket

    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("rejections.jsonl", rejection("Roll (1988) found little difference."))

    def refuse(*args, **kwargs):
        raise AssertionError("promotion reads two ledgers")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    discover.promote_contested(project, store)


def test_a_surname_in_the_bibliography_without_a_usable_year_is_reported_as_ambiguous(tmp_path):
    """Measured: the corpus holds ten Roll references. One is titled `R-squared` with no year at all —
    which is the 1988 paper the rejected claim named — and one is titled `Journal of Finance`, GROBID
    having taken the venue for the title. Matching on the surname alone would promote all ten, and
    guessing which is the 1988 one is the fabrication this whole module refuses. It says so instead.
    """
    project = load_project(PROJECT)
    store = Store("t", base=tmp_path)
    store.append("references.jsonl", {"key": "title:r squared", "title": "R-squared",
                                      "authors": ["Roll"], "year": None,
                                      "citations_in_corpus": 1})
    store.append("references.jsonl", {"key": "title:orange juice and weather",
                                      "title": "Orange Juice and Weather", "authors": ["Roll"],
                                      "year": None, "citations_in_corpus": 1})
    store.append("rejections.jsonl", rejection("Roll (1988) found little difference."))

    result = discover.promote_contested(project, store)
    assert result["promoted"] == 0
    assert result["ambiguous"] == [["Roll", "1988", 2]]
    assert list(store.read("candidates.jsonl")) == []
