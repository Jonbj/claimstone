"""Every failure class must be classified exactly once.

An unclassified class silently means "never retried", which is the difference between a
source that is gone and a source nobody tried again.
"""

from claimstone import net


def _declared_classes() -> set[str]:
    return {
        value
        for name, value in vars(net).items()
        if name.isupper() and isinstance(value, str) and name not in {"USER_AGENT"}
    }


def test_every_failure_class_is_terminal_or_transient():
    unclassified = _declared_classes() - net.TERMINAL - net.TRANSIENT
    assert unclassified == set(), f"unclassified failure classes: {sorted(unclassified)}"


def test_no_class_is_both():
    assert net.TERMINAL & net.TRANSIENT == frozenset()


def test_is_terminal_agrees_with_the_sets():
    assert net.is_terminal(net.PAYWALL) is True
    assert net.is_terminal(net.TIMEOUT) is False
    assert net.is_terminal("SOMETHING_NOBODY_DECLARED") is True


def test_fake_fetcher_satisfies_the_protocol():
    from tests.fakes import FakeFetcher

    fetcher: net.FetcherLike = FakeFetcher()
    assert fetcher.get("https://example.org").ok is False


def test_a_failure_is_charged_to_the_host_that_refused_us_not_the_one_we_asked():
    """Measured on the real corpus, and it cost 17 candidates.

    Every citation candidate's only address is a `doi.org` URL. With `allow_redirects=True`, a doi.org
    request that lands on Wiley and gets a 403 recorded the failure against *doi.org* — so one budget was
    shared by every publisher the resolver points at, and 17 candidates were refused on the strength of
    403s from journals they had nothing to do with. The budget exists so a host that refused us is not
    hammered; charging it to a redirector defeats exactly that.
    """
    class Redirected:
        status_code = 403
        url = "https://onlinelibrary.wiley.com/doi/10.1111/x"
        headers = {"Content-Type": "text/html"}
        content = b"<html>paywall</html>"
        text = "paywall"

    fetcher = net.Fetcher(max_403_per_host=2)
    fetcher._session = type("S", (), {
        "headers": {}, "get": staticmethod(lambda *a, **k: Redirected())})()
    fetcher._robots_allows = lambda url: True

    fetcher.get("https://doi.org/10.1111/x")
    assert fetcher._recent_failures("onlinelibrary.wiley.com") == 1
    assert fetcher._recent_failures("doi.org") == 0
    # So the resolver never exhausts, and the publisher's own budget does its job.
    fetcher.get("https://doi.org/10.1111/y")
    assert fetcher.budget_exhausted("onlinelibrary.wiley.com") is True
    assert fetcher.budget_exhausted("doi.org") is False


def test_a_failure_with_no_response_is_charged_to_the_host_we_asked():
    """A timeout or a refused connection reaches no final URL, and the requested host is all we know."""
    import requests

    fetcher = net.Fetcher(max_403_per_host=2)
    def boom(*args, **kwargs):
        raise requests.Timeout("too slow")
    fetcher._session = type("S", (), {"headers": {}, "get": staticmethod(boom)})()
    fetcher._robots_allows = lambda url: True

    fetcher.get("https://slow.example/a")
    assert fetcher._recent_failures("slow.example") == 1
