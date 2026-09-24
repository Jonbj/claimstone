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
