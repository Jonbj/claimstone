"""Tests pinning the two defects found while measuring the reference manifest.

Both were silent and both moved the headline number, which is why they are pinned here:
a wrong acquisition rate decides whether a round may produce verdicts at all.
"""

from __future__ import annotations

import pytest

from claimstone import acquire, ids, net


class _FakeResponse:
    def __init__(self, status: int, body: str, content_type: str) -> None:
        self.status_code = status
        self.text = body
        self.content = body.encode()
        self.headers = {"Content-Type": content_type}


class _FakeSession:
    """Serves whatever the test declares for /robots.txt; records what was asked for."""

    def __init__(self, robots: _FakeResponse) -> None:
        self._robots = robots
        self.asked: list[str] = []
        self.headers: dict[str, str] = {}

    def get(self, url: str, **_: object) -> _FakeResponse:
        self.asked.append(url)
        if url.endswith("/robots.txt"):
            return self._robots
        raise AssertionError("only robots.txt should be fetched in these tests")


def _fetcher_with_robots(monkeypatch, response: _FakeResponse) -> net.Fetcher:
    monkeypatch.setenv("CLAIMSTONE_CONTACT_EMAIL", "test@example.org")
    fetcher = net.Fetcher(pause_s=0.0)
    fetcher._session = _FakeSession(response)  # type: ignore[assignment]
    return fetcher


@pytest.mark.parametrize(
    "response,why",
    [
        (_FakeResponse(403, "<html><h1>Forbidden</h1></html>", "text/html"),
         "a 403 on robots.txt is not a prohibition on the site"),
        (_FakeResponse(200, "<!doctype html><html>rate limit</html>", "text/html"),
         "an HTML error page is not a robots file"),
        (_FakeResponse(404, "", "text/plain"),
         "no robots.txt means no rules"),
        (_FakeResponse(200, "nonsense without any directives", "text/plain"),
         "a body with no User-agent line states nothing"),
    ],
)
def test_absent_or_bogus_robots_does_not_forbid(monkeypatch, response, why):
    """urllib's parser invents prohibitions here, which silently deflates the rate."""
    fetcher = _fetcher_with_robots(monkeypatch, response)
    assert fetcher._robots_allows("https://example.org/paper.pdf"), why


def test_real_robots_is_honoured(monkeypatch):
    fetcher = _fetcher_with_robots(
        monkeypatch, _FakeResponse(200, "User-agent: *\nDisallow: /private/\n", "text/plain")
    )
    assert fetcher._robots_allows("https://example.org/open/paper.pdf")
    assert not fetcher._robots_allows("https://example.org/private/paper.pdf")


def test_pdf_is_preferred_over_a_published_landing_page(monkeypatch):
    """Format outranks version label: a landing page may not carry the full text."""
    monkeypatch.setenv("CLAIMSTONE_CONTACT_EMAIL", "test@example.org")
    fetcher = net.Fetcher(pause_s=0.0)
    candidate = {"url": "https://example.org/paper.pdf", "title": "A paper", "doi": None}

    def fake_unpaywall(_f, _doi):
        return [acquire.Location("https://example.org/landing", "unpaywall", "publishedVersion")], "green"

    monkeypatch.setattr(acquire, "unpaywall_locations", fake_unpaywall)
    locations, _ = acquire.plan_locations(fetcher, candidate, use_apis=False)
    assert locations[0].url.endswith(".pdf")


def test_known_wall_is_tried_last(monkeypatch):
    """A publisher landing page is attempted only after every legal open copy."""
    monkeypatch.setenv("CLAIMSTONE_CONTACT_EMAIL", "test@example.org")
    fetcher = net.Fetcher(pause_s=0.0)
    candidate = {
        "url": "https://www.sciencedirect.com/science/article/pii/S0304405X21001306",
        "title": "Pervasive Underreaction",
        "doi": None,
    }
    locations, _ = acquire.plan_locations(fetcher, candidate, use_apis=False)
    assert locations, "the original URL must still be attempted"
    assert "sciencedirect.com" in locations[-1].url


def test_pii_url_yields_no_doi():
    """The reason title resolution exists: a ScienceDirect PII is not a DOI."""
    assert ids.normalize_doi(
        "https://www.sciencedirect.com/science/article/pii/S0304405X21001306"
    ) is None
    assert ids.normalize_doi("https://doi.org/10.1016/j.jfineco.2021.04.003") == (
        "10.1016/j.jfineco.2021.04.003"
    )


def test_rate_is_computed_from_the_latest_attempt_per_candidate(tmp_path):
    from claimstone.store import Store

    store = Store("p", tmp_path)
    store.append("acquisitions.jsonl", {"candidate_key": "a", "acquired": False,
                                        "failure_class": "PAYWALL_403", "url": "https://x.org/a"})
    store.append("acquisitions.jsonl", {"candidate_key": "a", "acquired": True, "url": "https://x.org/a"})
    store.append("acquisitions.jsonl", {"candidate_key": "b", "acquired": False,
                                        "failure_class": "PAYWALL_403", "url": "https://y.org/b"})
    stats = acquire.rate(store)
    assert stats == {
        "attempted": 2,
        "acquired": 1,
        "rate": 0.5,
        "failures_by_class": {"PAYWALL_403": 1},
        "failures_by_host": {"y.org": 1},
    }


def test_contact_email_is_required(monkeypatch):
    monkeypatch.delenv("CLAIMSTONE_CONTACT_EMAIL", raising=False)
    with pytest.raises(net.ContactNotConfigured):
        net.contact_email()
