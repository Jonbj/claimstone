"""The cascade: where a legal copy might live, cheapest and most likely first."""

from claimstone import resolve
from tests.fakes import FakeFetcher

UNPAYWALL = "https://api.unpaywall.org/v2/"
OPENALEX_WORK = "https://api.openalex.org/works/doi:"
OPENALEX_SEARCH = "https://api.openalex.org/works?"
WAYBACK = "https://archive.org/wayback/available"


def test_arxiv_comes_first_because_it_is_certainly_legal():
    candidate = {"url": "https://arxiv.org/abs/2401.01234", "title": "A paper"}
    locations, _ = resolve.plan(FakeFetcher(), candidate, use_apis=False)
    assert locations[0].url == "https://arxiv.org/pdf/2401.01234"
    assert locations[0].provenance == "arxiv"


def test_a_known_wall_is_tried_last():
    fetcher = FakeFetcher(json_pages={
        UNPAYWALL: {"oa_status": "green", "oa_locations": [
            {"url_for_pdf": "https://repo.example/paper.pdf", "version": "acceptedVersion",
             "license": "cc-by", "host_type": "repository"}]},
    })
    candidate = {"url": "https://www.sciencedirect.com/science/article/pii/S0304405X",
                 "doi": "10.1016/j.jfineco.2019.05.001", "title": "A paper"}
    locations, oa_status = resolve.plan(fetcher, candidate)
    assert locations[-1].provenance == "candidate"
    assert "sciencedirect.com" in locations[-1].url
    assert oa_status == "green"


def test_openalex_is_consulted_only_when_unpaywall_returns_nothing():
    fetcher = FakeFetcher(json_pages={
        UNPAYWALL: {"oa_status": "closed", "oa_locations": []},
        OPENALEX_WORK: {"open_access": {"oa_status": "bronze"}, "locations": [
            {"is_oa": True, "pdf_url": "https://oa.example/x.pdf", "version": "publishedVersion"}]},
    })
    candidate = {"url": "https://x.example/a", "doi": "10.1234/abc", "title": "A paper"}
    locations, _ = resolve.plan(fetcher, candidate)
    assert any(loc.provenance == "openalex" for loc in locations)


def test_published_version_outranks_a_preprint():
    fetcher = FakeFetcher(json_pages={
        UNPAYWALL: {"oa_status": "hybrid", "oa_locations": [
            {"url": "https://a.example/preprint.pdf", "version": "submittedVersion"},
            {"url": "https://b.example/vor.pdf", "version": "publishedVersion"}]},
    })
    candidate = {"url": "https://x.example/a", "doi": "10.1234/abc", "title": "A paper"}
    locations, _ = resolve.plan(fetcher, candidate)
    versions = [loc.version for loc in locations if loc.provenance == "unpaywall"]
    assert versions[0] == "publishedVersion"


def test_the_same_url_is_never_planned_twice():
    fetcher = FakeFetcher(json_pages={
        UNPAYWALL: {"oa_status": "green", "oa_locations": [
            {"url": "https://a.example/x.pdf?utm_source=alert"},
            {"url": "https://a.example/x.pdf"}]},
    })
    candidate = {"url": "https://x.example/a", "doi": "10.1234/abc", "title": "A paper"}
    locations, _ = resolve.plan(fetcher, candidate)
    assert len(locations) == len({loc.url for loc in locations})


def test_a_title_resolves_a_doi_only_on_an_exact_match():
    fetcher = FakeFetcher(json_pages={
        OPENALEX_SEARCH: {"results": [
            {"doi": "https://doi.org/10.1234/close",
             "title": "News sentiment and returns, revisited"}]},
    })
    assert resolve.resolve_doi_by_title(fetcher, "News sentiment and returns") is None
    assert resolve.resolve_doi_by_title(
        fetcher, "News sentiment and returns, revisited") == "10.1234/close"


def test_a_source_without_a_doi_falls_back_to_the_wayback_machine():
    fetcher = FakeFetcher(json_pages={
        OPENALEX_SEARCH: {"results": []},
        WAYBACK: {"archived_snapshots": {"closest": {
            "available": True,
            "url": "https://web.archive.org/web/2023/https://news.example/a"}}},
    })
    candidate = {"url": "https://news.example/a", "title": "A news item", "source_class": "NEW"}
    locations, _ = resolve.plan(fetcher, candidate)
    assert [loc.provenance for loc in locations][-1] == "wayback"
    assert locations[-1].licence == "unknown"
