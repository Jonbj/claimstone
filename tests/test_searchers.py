"""The three API searchers, against saved payloads. No request leaves the process."""

import pytest
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
    assert row["openalex_work_id"] == "https://openalex.org/W123"
    assert row["query_rank"] == 1


def test_openalex_page_url_is_explicit_and_bounded(monkeypatch):
    monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'research@example.org')
    fetcher = FakeFetcher(json_pages={OPENALEX: {'results': []}})
    list(searchers.search_openalex(fetcher, 'news sentiment', 'T02'))
    assert fetcher.calls[0] == searchers.openalex_query_url('news sentiment')
    url = searchers.openalex_query_url('news sentiment', per_page=100,
        mode='search.title_abstract_keywords', page=2)
    assert 'search.title_abstract_keywords=news+sentiment' in url
    assert 'per-page=100' in url and 'page=2' in url
    assert 'cursor=' not in url
    with pytest.raises(ValueError, match='combined'):
        searchers.openalex_query_url('news', page=2, cursor='opaque')
    with pytest.raises(ValueError, match='10000'):
        searchers.openalex_query_url('news', per_page=100, page=101)
    with pytest.raises(ValueError, match='1..100'):
        searchers.openalex_query_url('news', per_page=101)


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
    assert rows[0]["arxiv_base_id"] == "2401.01234"
    assert rows[0]["arxiv_version"] == 1


def test_an_empty_payload_yields_nothing():
    fetcher = FakeFetcher(json_pages={OPENALEX: {"results": []}})
    assert list(searchers.search_openalex(fetcher, "x", "T01")) == []


def test_a_failed_request_is_distinct_from_an_empty_search():
    for searcher in (searchers.search_openalex, searchers.search_crossref, searchers.search_arxiv):
        with pytest.raises(searchers.SearchError):
            list(searcher(FakeFetcher(), 'x', 'T01'))


def test_malformed_atom_yields_nothing():
    url = ARXIV + "search_query=all%3A%22x%22&max_results=25"
    fetcher = FakeFetcher(pages={url: ok(url, b"<feed><entry", "application/atom+xml")})
    with pytest.raises(searchers.SearchError, match="unclosed"):
        list(searchers.search_arxiv(fetcher, "x", max_results=25, topic_id="T01"))


def test_a_row_records_the_query_that_found_it():
    fetcher = FakeFetcher(json_pages={OPENALEX: OPENALEX_PAYLOAD})
    row = next(iter(searchers.search_openalex(fetcher, "news sentiment", "T02")))
    assert row["query"] == "news sentiment"
    assert row["query_hash"]

