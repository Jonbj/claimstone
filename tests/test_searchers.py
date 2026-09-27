"""The three API searchers, against saved payloads. No request leaves the process."""

from claimstone import searchers
from tests.fakes import FakeFetcher, ok

OPENALEX = "https://api.openalex.org/works?"
CROSSREF = "https://api.crossref.org/works?"
ARXIV = "https://export.arxiv.org/api/query?"

OPENALEX_PAYLOAD = {"results": [{
    "id": "https://openalex.org/W123",
    "doi": "https://doi.org/10.1234/abc",
    "title": "News versus Sentiment",
    "publication_year": 2019,
    "primary_location": {"pdf_url": "https://repo.example/a.pdf",
                         "landing_page_url": "https://x.example/a",
                         "source": {"display_name": "Journal of Finance", "type": "journal"}},
    "open_access": {"is_oa": True},
    "cited_by_count": 42,
}]}

CROSSREF_PAYLOAD = {"message": {"items": [{
    "DOI": "10.1234/def",
    "title": ["A reality check for data snooping"],
    "issued": {"date-parts": [[1999]]},
    "container-title": ["Econometrica"],
    "URL": "https://doi.org/10.1234/def",
    "type": "journal-article",
    "is-referenced-by-count": 900,
}]}}

ARXIV_ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.01234v1</id>
    <title>Can ChatGPT Forecast Stock Price Movements?</title>
    <published>2024-01-02T00:00:00Z</published>
  </entry>
</feed>"""


def test_openalex_reports_the_venue_type_classify_needs():
    fetcher = FakeFetcher(json_pages={OPENALEX: OPENALEX_PAYLOAD})
    row = next(iter(searchers.search_openalex(fetcher, "news sentiment", "T02")))
    assert row["venue_type"] == "journal"
    assert row["source_api"] == "openalex"
    assert row["doi"] == "10.1234/abc"
    assert row["venue"] == "Journal of Finance"
    assert row["url"] == "https://repo.example/a.pdf"
    assert row["topic_id"] == "T02"
    assert row["channel"] == "keyword"


def test_crossref_asks_for_type_and_reports_it():
    # The live select clause omitted `type`, so crossref_type had nothing to match on.
    fetcher = FakeFetcher(json_pages={CROSSREF: CROSSREF_PAYLOAD})
    row = next(iter(searchers.search_crossref(fetcher, "data snooping", "T01")))
    assert row["venue_type"] == "journal-article"
    assert "type" in fetcher.calls[-1]
    assert row["year"] == 1999


def test_arxiv_parses_atom_and_is_always_a_preprint_venue():
    url = ARXIV + "search_query=all%3A%22chatgpt%22&max_results=25"
    fetcher = FakeFetcher(pages={url: ok(url, ARXIV_ATOM, "application/atom+xml")})
    rows = list(searchers.search_arxiv(fetcher, "chatgpt", "T02", max_results=25))
    assert rows[0]["url"] == "https://arxiv.org/pdf/2401.01234"
    assert rows[0]["venue"] == "arXiv"
    assert rows[0]["venue_type"] == "preprint"
    assert rows[0]["is_oa"] is True


def test_an_empty_payload_yields_nothing():
    fetcher = FakeFetcher(json_pages={OPENALEX: {}})
    assert list(searchers.search_openalex(fetcher, "x", "T01")) == []


def test_a_failed_request_yields_nothing_rather_than_raising():
    assert list(searchers.search_openalex(FakeFetcher(), "x", "T01")) == []
    assert list(searchers.search_crossref(FakeFetcher(), "x", "T01")) == []
    assert list(searchers.search_arxiv(FakeFetcher(), "x", "T01")) == []


def test_malformed_atom_yields_nothing():
    url = ARXIV + "search_query=all%3A%22x%22&max_results=25"
    fetcher = FakeFetcher(pages={url: ok(url, b"<feed><entry", "application/atom+xml")})
    assert list(searchers.search_arxiv(fetcher, "x", max_results=25, topic_id="T01")) == []


def test_a_row_records_the_query_that_found_it():
    fetcher = FakeFetcher(json_pages={OPENALEX: OPENALEX_PAYLOAD})
    row = next(iter(searchers.search_openalex(fetcher, "news sentiment", "T02")))
    assert row["query"] == "news sentiment"
    assert row["query_hash"]

