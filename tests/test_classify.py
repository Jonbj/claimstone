"""Assigning a source class from rules the project declares, never from what the engine guesses."""

import pytest

from claimstone import classify
from claimstone.config import ConfigError, SourceClass

CLASSES = (
    SourceClass(id="ACA", name="academic", weight_hint="highest",
                assign_when={"openalex_source_type": ("journal",),
                             "crossref_type": ("journal-article",)}),
    SourceClass(id="WP", name="working paper", weight_hint="high",
                assign_when={"source_api": ("arxiv",),
                             "openalex_source_type": ("repository",),
                             "host": ("papers.ssrn.com", "nber.org")}),
    SourceClass(id="NEW", name="journalism", weight_hint="low", assign_when={}),
)


def candidate(**overrides):
    base = {"source_api": "openalex", "venue_type": "journal",
            "url": "https://doi.org/10.1234/abc", "title": "A paper"}
    return {**base, **overrides}


def test_a_journal_in_openalex_is_academic():
    assert classify.classify(candidate(), CLASSES) == "ACA"


def test_a_journal_article_in_crossref_is_academic():
    assert classify.classify(
        candidate(source_api="crossref", venue_type="journal-article"), CLASSES) == "ACA"


def test_arxiv_is_a_working_paper_whatever_its_venue_says():
    assert classify.classify(
        candidate(source_api="arxiv", venue_type=""), CLASSES) == "WP"


def test_a_repository_in_openalex_is_a_working_paper():
    assert classify.classify(candidate(venue_type="repository"), CLASSES) == "WP"


def test_a_host_matches_on_its_suffix():
    assert classify.classify(
        candidate(venue_type="", url="https://papers.ssrn.com/abstract=123"), CLASSES) == "WP"
    assert classify.classify(
        candidate(venue_type="", url="https://www.nber.org/papers/w1234"), CLASSES) == "WP"


def test_a_similar_looking_host_does_not_match():
    # Suffix matching must not turn notnber.org into nber.org.
    assert classify.classify(
        candidate(venue_type="", url="https://notnber.org/x"), CLASSES) is None


def test_declaration_order_decides_when_two_classes_match():
    """sources.yaml declares classes most-authoritative-first, so the order is already the right one
    and no separate priority system is needed.

    The candidate has to match two classes for this to test anything. An arXiv row with
    `venue_type="journal"` does not: a venue type only counts alongside the API that reported it, and
    arXiv does not report OpenAlex vocabulary — so that candidate matches WP alone and demonstrates
    nothing about order. A real double match is a refereed paper whose open copy sits on SSRN:
    OpenAlex calls the work a journal article and the URL is a working-paper host.
    """
    both = candidate(venue_type="journal", url="https://papers.ssrn.com/abstract=99")
    assert classify.classify(both, CLASSES) == "ACA"
    # And it is the right answer: the work is refereed and we merely obtained the preprint copy,
    # which `oa_status` and `version` record. Reading the host first would demote every paper whose
    # only open copy is a preprint.


def test_a_class_with_no_rules_never_matches():
    # NEW declares no assign_when: it arrives from the manifest, not from a search.
    assert classify.classify(candidate(source_api="searxng", venue_type="", url=""),
                             CLASSES) is None


def test_an_uncovered_candidate_is_none_not_a_guess():
    assert classify.classify(
        candidate(venue_type="book-series"), CLASSES) is None


def test_the_uncovered_attributes_are_reported_so_a_rule_can_be_written():
    seen = classify.uncovered([candidate(venue_type="book-series"),
                               candidate(venue_type="conference"),
                               candidate(venue_type="conference")], CLASSES)
    assert seen == {"openalex_source_type": {"book-series": 1, "conference": 2}}


# --- config validation -------------------------------------------------------

def test_an_unknown_predicate_is_a_configuration_error(tmp_path):
    from claimstone.config import load_sources

    (tmp_path / "sources.yaml").write_text(
        "acquisition_floor: 0.8\nclasses:\n"
        "  - id: ACA\n    name: a\n    weight_hint: highest\n"
        "    assign_when:\n      publisher_mood: [cheerful]\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="publisher_mood"):
        load_sources(tmp_path)


def test_a_predicate_must_hold_a_list(tmp_path):
    from claimstone.config import load_sources

    (tmp_path / "sources.yaml").write_text(
        "acquisition_floor: 0.8\nclasses:\n"
        "  - id: ACA\n    name: a\n    weight_hint: highest\n"
        "    assign_when:\n      source_api: arxiv\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="source_api"):
        load_sources(tmp_path)
