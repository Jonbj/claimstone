"""D144: CORE as an opt-in keyword channel and a repository-copy source; exact-DOI only, key never in a URL."""
import pytest

from claimstone import net, resolve, searchers

PAYLOAD = {"results": [
    {"id": 99, "doi": "10.1000/ABC", "title": "Exercise in mood", "yearPublished": 2018, "publisher": "Univ Press",
     "documentType": ["research"], "downloadUrl": "https://repo.example.edu/files/abc.pdf", "journals": [{"title": "J Mood"}]},
    {"id": 100, "doi": "10.9999/zzz", "title": "Different work", "downloadUrl": "https://repo.example.edu/zzz.pdf"},
    {"id": 101, "doi": None, "title": "No file", "links": []},
]}


class Fetcher:
    def __init__(self, payload=PAYLOAD, outcome=None, allowed=None):
        self.payload, self.outcome, self.urls = payload, outcome or net.Outcome("u", True, 200), []
        self.allowed_hosts = allowed

    def get_json(self, url):
        self.urls.append(url)
        return self.payload, self.outcome


def test_search_rows_carry_the_download_address_and_flag_oa_only_when_a_file_is_named():
    rows = list(searchers.search_core(Fetcher(), "exercise depression", "T"))
    first, _other, nofile = rows
    assert first["url"] == "https://repo.example.edu/files/abc.pdf" and first["is_oa"] is True
    assert first["candidate_key"] == "doi:10.1000/abc" and first["venue"] == "J Mood" and first["venue_type"] == "research"
    assert first["source_api"] == "core" and first["core_id"] == "99"
    assert nofile["is_oa"] is None and nofile["url"] == "https://core.ac.uk/works/101"


def test_a_failed_search_is_a_named_failure():
    with pytest.raises(searchers.SearchError):
        list(searchers.search_core(Fetcher(None, net.Outcome("u", False, 429, net.RATE_LIMITED)), "q", "T"))


def test_it_is_registered_not_a_default_and_paced():
    from claimstone import provider_limits
    assert "core" in searchers.SEARCHERS and "core" not in searchers.DEFAULT_APIS
    assert searchers._limit_kw("core") == "limit" and provider_limits.INTERVALS["api.core.ac.uk"] >= 2.0


def test_the_copy_lookup_takes_only_the_exact_doi_and_nothing_without_a_key(monkeypatch):
    monkeypatch.delenv("CORE_API_KEY", raising=False)
    quiet = Fetcher()
    assert resolve.core_locations(quiet, "10.1000/abc") == [] and quiet.urls == [], "no key, no request"
    monkeypatch.setenv("CORE_API_KEY", "x-test-key")
    fetcher = Fetcher()
    got = resolve.core_locations(fetcher, "10.1000/abc")
    assert [l.url for l in got] == ["https://repo.example.edu/files/abc.pdf"] and got[0].provenance == "core"
    assert "x-test-key" not in fetcher.urls[0], "the key travels in a header, never in a URL"


def test_the_cascade_asks_core_only_when_the_plan_named_its_host(monkeypatch):
    monkeypatch.setenv("CORE_API_KEY", "x-test-key")
    candidate = {"doi": "10.1000/abc", "url": "https://doi.org/10.1000/abc", "title": "t"}
    for allowed, expect in ((None, False), (frozenset({"api.unpaywall.org"}), False),
                            (frozenset({"api.core.ac.uk"}), True)):
        fetcher = Fetcher({"results": []}, allowed=allowed)
        monkeypatch.setenv("CLAIMSTONE_CONTACT_EMAIL", "a@b.example")
        resolve.plan(fetcher, candidate, use_apis=True)
        assert any("api.core.ac.uk" in u for u in fetcher.urls) is expect, allowed


def test_the_fetcher_adds_the_bearer_header_for_core_only(monkeypatch):
    monkeypatch.setenv("CORE_API_KEY", "x-test-key")
    seen = []

    class Response:
        status_code, url, content, headers = 200, "", b"{}", {"Content-Type": "application/json"}

    def get(url, **kwargs):
        seen.append((url, (kwargs.get("headers") or {}).get("Authorization")))
        response = Response()
        response.url = url
        return response

    fetcher = net.Fetcher(obey_robots=False, pause_s=0)
    fetcher._session = type("S", (), {"get": staticmethod(get)})()
    fetcher.get("https://api.core.ac.uk/v3/search/works?q=x")
    fetcher.get("https://api.crossref.org/works?q=x")
    assert seen[0][1] == "Bearer x-test-key" and seen[1][1] is None
