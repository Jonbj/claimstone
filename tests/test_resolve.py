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


# --- PubMed Central has a sanctioned route, and we were using the forbidden one -------------------

def test_a_pmc_article_location_is_rewritten_to_the_host_that_allows_it():
    """Measured on the pilot: three open copies were declined for robots.txt, all on
    `www.ncbi.nlm.nih.gov/pmc/articles/…`, which that host's robots disallows for `*` — correctly refused.

    `pmc.ncbi.nlm.nih.gov` is a different host whose robots says `Allow: /articles/` in as many words, and it
    serves 211 KB of article HTML there. So the copy was always reachable and we were asking the one host that
    says no. Honouring robots.txt is not negotiable; reading which host it belongs to is our job.
    """
    old = "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7196181"
    assert resolve.pmc_route(old) == "https://pmc.ncbi.nlm.nih.gov/articles/PMC7196181/"
    # With a trailing slash, a version suffix, and http.
    assert resolve.pmc_route("http://www.ncbi.nlm.nih.gov/pmc/articles/PMC123456/") == \
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC123456/"
    # A bare numeric id is how Unpaywall sometimes writes it.
    assert resolve.pmc_route("https://www.ncbi.nlm.nih.gov/pmc/articles/7196181") == \
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC7196181/"


def test_a_non_pmc_url_is_left_alone():
    for url in ("https://link.springer.com/content/pdf/10.1007/x.pdf",
                "https://pmc.ncbi.nlm.nih.gov/articles/PMC1/",
                "https://www.ncbi.nlm.nih.gov/pubmed/12345",
                ""):
        assert resolve.pmc_route(url) is None, url


def test_the_plan_offers_the_allowed_pmc_host_instead_of_the_forbidden_one():
    fetcher = FakeFetcher(json_pages={
        "https://api.unpaywall.org/v2/": {
            "oa_status": "green",
            "oa_locations": [{"url_for_pdf": None,
                              "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7196181",
                              "version": "publishedVersion", "license": "cc-by"}]}})
    locations, _ = resolve.plan(fetcher, {"doi": "10.1007/s00787-020-01541-4", "url": ""})
    urls = [loc.url for loc in locations]
    assert "https://pmc.ncbi.nlm.nih.gov/articles/PMC7196181/" in urls
    # The forbidden one is not merely reordered: asking it at all spends a request on a certain refusal.
    assert not any("www.ncbi.nlm.nih.gov/pmc/articles" in u for u in urls)


# --- One useless location was suppressing a second source -----------------------------------------

def test_openalex_is_consulted_even_when_unpaywall_answered():
    """Measured on the pilot: nine of eighteen failures tried exactly one address, and for every one of them
    Unpaywall's single offered location was `doi.org` — the resolver, not a file. Five were `green`, so a
    repository copy existed. `openalex_locations` was reachable only `if not upw`, so one useless answer
    suppressed the source that might have had a real address.
    """
    fetcher = FakeFetcher(json_pages={
        "https://api.unpaywall.org/v2/": {
            "oa_status": "green",
            "oa_locations": [{"url": "https://doi.org/10.1234/abc", "url_for_pdf": None,
                              "version": "submittedVersion", "license": "cc-by"}]},
        # `is_oa` is what openalex_locations reads, and a real best_oa_location always carries it.
        OPENALEX_WORK: {"best_oa_location": {"pdf_url": "https://osf.io/abcde/download",
                                             "is_oa": True,
                                             "version": "submittedVersion", "license": "cc-by"},
                        "locations": []},
    })
    locations, oa = resolve.plan(fetcher, {"doi": "10.1234/abc", "url": ""})
    assert "https://osf.io/abcde/download" in [loc.url for loc in locations]
    assert oa == "green"


def test_the_same_address_from_two_sources_is_one_attempt():
    """Otherwise a candidate looks like it was tried twice and the log says nothing it did not already."""
    both = {"url": "https://repo.example/a.pdf", "url_for_pdf": "https://repo.example/a.pdf",
            "version": "publishedVersion", "license": "cc-by"}
    fetcher = FakeFetcher(json_pages={
        "https://api.unpaywall.org/v2/": {"oa_status": "gold", "oa_locations": [both]},
        OPENALEX_WORK: {"best_oa_location": {"pdf_url": "https://repo.example/a.pdf", "is_oa": True},
                        "locations": []},
    })
    locations, _ = resolve.plan(fetcher, {"doi": "10.1234/abc", "url": ""})
    assert [loc.url for loc in locations].count("https://repo.example/a.pdf") == 1


def test_a_location_that_is_only_the_doi_resolver_is_not_an_address():
    """It adds nothing over the candidate URL, which is already the DOI, and counting it as an attempt is how
    nine failures looked like they had been tried."""
    fetcher = FakeFetcher(json_pages={
        "https://api.unpaywall.org/v2/": {
            "oa_status": "closed",
            "oa_locations": [{"url": "https://doi.org/10.1234/abc", "url_for_pdf": None}]},
        OPENALEX_WORK: {},
    })
    locations, _ = resolve.plan(fetcher, {"doi": "10.1234/abc", "url": "https://doi.org/10.1234/abc"})
    assert [loc.url for loc in locations] == ["https://doi.org/10.1234/abc"]
