"""OpenAlex pacing follows the key and the query class; production paging is bounded (issue #10).

The documented figures, read on 2026-10-18 at
https://help.openalex.org/api/authentication/: 10 requests/s with no key, 30 with a free key or
prepaid usage, 50 on an annual plan; a search with more than five OR/AND/NOT operators is limited
to 1, 5 or 25/s respectively, and semantic search to 1/s. We assume the conservative keyed class
(30/s), because a key does not say which plan it belongs to.
"""

import urllib.parse

import pytest

from claimstone import discover, net, provider_limits, searchers
from claimstone.config import load_project
from claimstone.store import Store

PROJECT = "projects/example-news-and-returns"


def openalex_url(term: str, mode: str = "search") -> str:
    if mode == "search.semantic":
        return ("https://api.openalex.org/works?"
                + urllib.parse.urlencode({"search.semantic": term,
                                          "mailto": "tests@example.org"}))
    return searchers.openalex_query_url(term, mode=mode)


def test_the_guard_uses_the_documented_keyless_and_keyed_standard_rates():
    url = openalex_url("news sentiment")
    assert provider_limits.openalex_query_class(url) == "standard"
    assert provider_limits.openalex_requests_per_second(url, keyed=False) == 10
    assert provider_limits.openalex_requests_per_second(url, keyed=True) == 30
    assert provider_limits.openalex_interval(url, keyed=False) == pytest.approx(0.1)
    assert provider_limits.openalex_interval(url, keyed=True) == pytest.approx(1 / 30)


def test_more_than_five_boolean_operators_are_classified_complex():
    url = openalex_url("a OR b OR c OR d OR e OR f OR g")
    assert provider_limits.openalex_query_class(url) == "complex"
    assert provider_limits.openalex_requests_per_second(url, keyed=False) == 1
    assert provider_limits.openalex_requests_per_second(url, keyed=True) == 5


def test_five_operators_are_not_complex():
    url = openalex_url("a OR b OR c OR d OR e OR f")
    assert provider_limits.openalex_query_class(url) == "standard"


def test_semantic_search_is_one_request_per_second_even_with_a_key():
    url = openalex_url("news sentiment", mode="search.semantic")
    assert provider_limits.openalex_query_class(url) == "semantic"
    assert provider_limits.openalex_requests_per_second(url, keyed=False) == 1
    assert provider_limits.openalex_requests_per_second(url, keyed=True) == 1


def test_key_presence_is_read_from_the_environment(monkeypatch):
    url = openalex_url("news sentiment")
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    assert provider_limits.openalex_requests_per_second(url) == 10
    monkeypatch.setenv("OPENALEX_API_KEY", "a-key")
    assert provider_limits.openalex_requests_per_second(url) == 30


def test_provider_slot_spaces_an_openalex_start_by_the_keyed_interval(tmp_path, monkeypatch):
    def slot(base):
        store = Store("t", base=base)
        shared = Store(".provider_limits", base=store.root.parent)
        shared.append("starts.jsonl", {"host": "api.openalex.org",
                                       "started_at_epoch": 1_000.0,
                                       "utc_date": "2026-10-18",
                                       "estimated_credits": 0})
        return provider_limits.provider_slot(store, "api.openalex.org",
                                             openalex_url("news"))

    monkeypatch.setattr(provider_limits.time, "time", lambda: 1_000.05)
    slept = []
    monkeypatch.setattr(provider_limits.time, "sleep", slept.append)

    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    with slot(tmp_path / "keyless"):
        pass
    assert slept and slept[0] == pytest.approx(0.05)

    slept.clear()
    monkeypatch.setenv("OPENALEX_API_KEY", "a-key")
    with slot(tmp_path / "keyed"):
        pass
    assert slept == []


# --- bounded production paging ------------------------------------------------

def work(n: int) -> dict:
    return {
        "id": f"https://openalex.org/W{n}",
        "doi": f"https://doi.org/10.1234/w{n}",
        "title": f"Paper number {n}",
        "publication_year": 2020,
        "primary_location": {"pdf_url": f"https://repo.example/{n}.pdf",
                             "landing_page_url": f"https://x.example/{n}",
                             "source": {"display_name": "Journal", "type": "journal"}},
        "open_access": {"is_oa": True},
        "cited_by_count": 1,
    }


def page_payload(numbers, *, count=None, cursor=None):
    payload = {"results": [work(n) for n in numbers]}
    meta = {}
    if count is not None:
        meta["count"] = count
    if cursor is not None:
        meta["next_cursor"] = cursor
    if meta:
        payload["meta"] = meta
    return payload


class PagedFetcher:
    """Answers by the `page` parameter, so a paging rule can be exercised without a socket."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get_json(self, url):
        self.calls.append(url)
        page = int(urllib.parse.parse_qs(
            urllib.parse.urlsplit(url).query).get("page", ["1"])[0])
        answer = self.pages.get(page)
        if isinstance(answer, net.Outcome):
            return None, answer
        if answer is None:
            return None, net.Outcome(url, False, 404, net.NOT_FOUND, "no page")
        return answer, net.Outcome(url, True, 200)


def _run(store, fetcher, *, max_pages, per_query=2):
    project = load_project(PROJECT)
    term = next(t.terms for t in project.topics if t.id == "T02")[0]
    return discover.run(project, store, fetcher, apis=("openalex",), topics=("T02",),
                        terms=(term,), per_query=per_query, max_pages=max_pages)


def test_a_page_budget_of_one_keeps_the_frozen_single_request(tmp_path):
    fetcher = PagedFetcher({1: page_payload([1, 2], count=5)})
    result = _run(Store("t", base=tmp_path), fetcher, max_pages=1)
    assert len(fetcher.calls) == 1
    query = next(iter(Store("t", base=tmp_path).read("queries.jsonl")))
    assert query["page_budget"] == 1 and query["pages_requested"] == 1
    assert query["stop_reason"] == "PAGE_BUDGET"
    assert result["final"] is True


def test_a_full_first_page_is_followed_within_an_explicit_budget(tmp_path):
    store = Store("t", base=tmp_path)
    fetcher = PagedFetcher({
        1: page_payload([1, 2], count=5, cursor="opaque"),
        2: page_payload([3, 4], count=5, cursor="later"),
    })
    result = _run(store, fetcher, max_pages=2)
    assert len(fetcher.calls) == 2
    assert result["new"] == 4
    query = next(iter(store.read("queries.jsonl")))
    assert query["page_budget"] == 2 and query["pages_requested"] == 2
    assert query["stop_reason"] == "PAGE_BUDGET"
    assert query["returned"] == 4
    assert query["total_available"] == 5 and query["depth_capped"] is True
    # Ranks continue across pages, so a hit id remains unique and means provider rank.
    hits = list(store.read("query_hits.jsonl"))
    assert sorted(hit["rank"] for hit in hits) == [1, 2, 3, 4]


def test_a_short_page_stops_paging_before_the_budget(tmp_path):
    store = Store("t", base=tmp_path)
    fetcher = PagedFetcher({
        1: page_payload([1, 2], count=10),
        2: page_payload([3], count=10),
        3: page_payload([4], count=10),
    })
    _run(store, fetcher, max_pages=5)
    assert len(fetcher.calls) == 2
    query = next(iter(store.read("queries.jsonl")))
    assert query["pages_requested"] == 2 and query["stop_reason"] == "SHORT_PAGE"


def test_reaching_the_provider_count_stops_paging(tmp_path):
    store = Store("t", base=tmp_path)
    fetcher = PagedFetcher({1: page_payload([1, 2], count=2)})
    _run(store, fetcher, max_pages=5)
    assert len(fetcher.calls) == 1
    query = next(iter(store.read("queries.jsonl")))
    assert query["stop_reason"] == "COUNT_REACHED"
    assert query["depth_capped"] is False


def test_a_later_page_failure_keeps_earlier_rows_and_is_recorded(tmp_path):
    store = Store("t", base=tmp_path)
    fetcher = PagedFetcher({
        1: page_payload([1, 2], count=10),
        2: net.Outcome("https://api.openalex.org/works?page=2", False, 500,
                       net.SERVER_ERROR, "status 500", "text/html"),
    })
    result = _run(store, fetcher, max_pages=3)
    # The page that returned is not thrown away because a later page failed.
    assert result["new"] == 2
    assert result["final"] is False
    query = next(iter(store.read("queries.jsonl")))
    assert query["ok"] is False
    assert query["failure_class"] == net.SERVER_ERROR
    assert query["stop_reason"] == "PAGE_FAILED"
    assert query["pages_requested"] == 2
    assert query["page_failures"] == [{"page": 2, "failure_class": net.SERVER_ERROR,
                                       "detail": "status 500"}]
