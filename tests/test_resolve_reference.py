"""Turning a reference into something stage 2 can fetch and `classify` can read.

Measured before this existed: the citation channel wrote 37 candidates, 37 of them unclassified and 25
with no URL at all. A reference carries a title, sometimes a DOI, and nothing else — no venue, no venue
type, no address — so no declared predicate can read anything and there is nothing to request.
"""

from claimstone import searchers
from tests.fakes import FakeFetcher

OPENALEX = "https://api.openalex.org/works?"
BY_DOI = "https://api.openalex.org/works/doi:"

WORK = {
    "id": "https://openalex.org/W99",
    "doi": "https://doi.org/10.1111/j.1540-6261.2004.00662.x",
    "title": "Is all that talk just noise? The information content of internet stock message boards",
    "publication_year": 2004,
    "primary_location": {"landing_page_url": "https://x.example/talk",
                         "source": {"display_name": "The Journal of Finance", "type": "journal"}},
    "open_access": {"is_oa": False},
    "cited_by_count": 3000,
}

TITLE = WORK["title"]


def test_a_reference_with_a_doi_is_looked_up_directly():
    """One request, no matching to get wrong. A DOI is an identifier, not a guess."""
    fetcher = FakeFetcher(json_pages={BY_DOI: WORK})
    found = searchers.resolve_work(fetcher, title=TITLE, doi="10.1111/j.1540-6261.2004.00662.x")
    assert found["venue"] == "The Journal of Finance"
    assert found["venue_type"] == "journal"
    assert found["url"] == "https://x.example/talk"
    assert found["resolution"] == "BY_DOI"
    assert len(fetcher.calls) == 1


def test_a_reference_without_a_doi_is_matched_on_an_exact_folded_title():
    fetcher = FakeFetcher(json_pages={OPENALEX: {"results": [WORK]}})
    found = searchers.resolve_work(fetcher, title=TITLE)
    assert found["doi"] == "10.1111/j.1540-6261.2004.00662.x"
    assert found["venue_type"] == "journal"
    assert found["resolution"] == "BY_TITLE"


def test_a_near_miss_on_the_title_is_no_match_and_not_the_wrong_paper():
    """The whole risk of this step. Attaching the wrong work would attribute its claims to a paper
    that never made them, which is worse than a candidate stage 2 refuses."""
    other = {**WORK, "title": "Is all that talk just noise? A comment"}
    fetcher = FakeFetcher(json_pages={OPENALEX: {"results": [other]}})
    found = searchers.resolve_work(fetcher, title=TITLE)
    assert found["resolution"] == "NO_MATCH"
    assert found["doi"] is None
    assert found["url"] == ""


def test_punctuation_and_case_do_not_defeat_the_match():
    loose = {**WORK, "title": "IS ALL THAT TALK JUST NOISE?  The Information Content of "
                              "Internet Stock Message Boards."}
    fetcher = FakeFetcher(json_pages={OPENALEX: {"results": [loose]}})
    assert searchers.resolve_work(fetcher, title=TITLE)["resolution"] == "BY_TITLE"


def test_a_title_too_short_to_match_is_not_even_requested():
    """A four-word fragment matches many works. Requesting one and taking the first is how a
    bibliography parsing error becomes a confident citation of the wrong paper."""
    fetcher = FakeFetcher()
    found = searchers.resolve_work(fetcher, title="See Example")
    assert found["resolution"] == "TITLE_TOO_SHORT"
    assert fetcher.calls == []


def test_a_failed_request_is_reported_rather_than_silently_unresolved():
    # A swallowed failure here would look identical to "this reference does not exist", and the
    # remedy for the two is different.
    found = searchers.resolve_work(FakeFetcher(), title=TITLE)
    assert found["resolution"] == "LOOKUP_FAILED"


def test_a_doi_lookup_that_misses_falls_back_to_the_title():
    """A DOI GROBID mis-parsed should not end the attempt: the title is still there to try."""
    fetcher = FakeFetcher(json_pages={OPENALEX: {"results": [WORK]}})
    found = searchers.resolve_work(fetcher, title=TITLE, doi="10.9999/wrong")
    assert found["resolution"] == "BY_TITLE"
    assert found["doi"] == "10.1111/j.1540-6261.2004.00662.x"


def test_the_resolved_shape_is_the_one_the_keyword_channel_already_produces():
    """So `classify` reads a resolved citation candidate with the same predicates, and nothing
    downstream needs to know which channel a row came through."""
    fetcher = FakeFetcher(json_pages={BY_DOI: WORK})
    found = searchers.resolve_work(fetcher, title=TITLE, doi="10.1111/j.1540-6261.2004.00662.x")
    assert set(found) == {"api", "doi", "title", "url", "venue", "venue_type", "year", "is_oa",
                          "citations", "resolution"}
    # `api` names whose vocabulary `venue_type` is in, which is what a resolved row carries as its
    # source_api — without it the venue type is a word nobody owns and no predicate can read it.
    assert found["api"] == "openalex"


def test_a_mis_parsed_doi_that_resolves_to_a_different_paper_is_not_believed():
    """The failure this step must not have. GROBID mis-parses DOIs, and a confident lookup can return
    a real work that is not the one cited — attaching it would attribute its claims to a source that
    never made them."""
    wrong_paper = {**WORK, "doi": "https://doi.org/10.9999/wrong",
                   "title": "An entirely different paper about something else"}
    fetcher = FakeFetcher(json_pages={BY_DOI: wrong_paper, OPENALEX: {"results": [WORK]}})
    found = searchers.resolve_work(fetcher, title=TITLE, doi="10.9999/wrong")
    assert found["resolution"] == "BY_TITLE"
    assert found["doi"] == "10.1111/j.1540-6261.2004.00662.x"


def test_a_mis_parsed_doi_with_no_title_match_anywhere_resolves_to_nothing():
    wrong_paper = {**WORK, "title": "An entirely different paper about something else"}
    fetcher = FakeFetcher(json_pages={BY_DOI: wrong_paper, OPENALEX: {"results": []}})
    found = searchers.resolve_work(fetcher, title=TITLE, doi="10.9999/wrong")
    assert found["resolution"] == "NO_MATCH"
    assert found["doi"] is None
