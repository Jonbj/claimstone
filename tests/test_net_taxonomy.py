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


def test_failure_budget_survives_fetcher_restart(tmp_path):
    from claimstone.request_log import RecordingFetcher
    from claimstone.store import Store
    import requests

    store = Store('one', base=tmp_path)
    first = net.Fetcher(max_403_per_host=1, obey_robots=False, pause_s=0)
    def timeout(*args, **kwargs):
        raise requests.Timeout('slow')
    first._session = type('Session', (), {'get': staticmethod(timeout)})()
    assert RecordingFetcher(first, store).get('https://slow.example/a').failure_class == net.TIMEOUT

    second = net.Fetcher(max_403_per_host=1, obey_robots=False, pause_s=0)
    calls = []
    def get(*args, **kwargs):
        calls.append(args)
        raise AssertionError('the budget should stop this request')
    second._session = type('Session', (), {'get': staticmethod(get)})()
    outcome = RecordingFetcher(second, store).get('https://slow.example/b')
    assert outcome.failure_class == net.BUDGET
    assert calls == []
    assert len([row for row in store.read('requests.jsonl')
                if row.get('event') == 'transport' and row.get('failure_class') == net.TIMEOUT]) == 1


def test_bounded_fetcher_rejects_private_addresses_and_caps_physical_requests():
    private = net.Fetcher(obey_robots=False, pause_s=0,
                          allowed_hosts=frozenset({'127.0.0.1'}),
                          enforce_global_addresses=True)
    private._session = type('Session', (), {'get': staticmethod(
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('socket opened')))})()
    assert private.get('http://127.0.0.1/a').failure_class == net.ADDRESS_REFUSED

    capped = net.Fetcher(obey_robots=False, pause_s=0,
                         allowed_hosts=frozenset({'example.org'}), max_physical_requests=0)
    capped._session = private._session
    assert capped.get('https://example.org/a').failure_class == net.REQUEST_LIMIT
    assert capped.get('https://other.example/a').failure_class == net.EXCLUDED


def test_bounded_adapter_pins_public_dns_answer_and_tls_name(monkeypatch):
    import socket
    import requests

    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.215.14', 0))])
    fetcher = net.Fetcher(obey_robots=False, pause_s=0,
                          allowed_hosts=frozenset({'example.org'}),
                          enforce_global_addresses=True)
    assert fetcher._session.trust_env is False
    assert fetcher._address_allowed('example.org')
    adapter = fetcher._pinned_adapter
    assert adapter is not None
    passed = {}
    class Pools:
        def connection_from_host(self, host, **kwargs):
            passed.update(host=host, **kwargs)
            return object()
    adapter.poolmanager = Pools()
    prepared = requests.Request('GET', 'https://example.org/a').prepare()
    adapter.get_connection_with_tls_context(prepared, True)
    assert passed == {'host': '93.184.215.14', 'port': None, 'scheme': 'https',
                      'pool_kwargs': {'assert_hostname': 'example.org',
                                      'server_hostname': 'example.org'}}


def test_physical_request_ceiling_survives_restart(tmp_path):
    from claimstone.request_log import RecordingFetcher
    from claimstone.store import Store

    class Response:
        status_code = 200
        headers = {'Content-Type': 'text/plain'}
        content = b'body'
        url = 'https://example.org/a'

    store = Store('one', base=tmp_path)
    first = net.Fetcher(obey_robots=False, pause_s=0,
                        max_physical_requests=1,
                        allowed_hosts=frozenset({'example.org'}))
    first._session = type('Session', (), {'get': staticmethod(lambda *a, **k: Response())})()
    assert RecordingFetcher(first, store, campaign='one').get('https://example.org/a').ok
    assert sum(row.get('event') == 'request_started' for row in store.read('requests.jsonl')) == 1

    second = net.Fetcher(obey_robots=False, pause_s=0,
                         max_physical_requests=1,
                         allowed_hosts=frozenset({'example.org'}))
    second._session = type('Session', (), {'get': staticmethod(
        lambda *a, **k: (_ for _ in ()).throw(AssertionError('request repeated')))})()
    assert RecordingFetcher(second, store, campaign='one').get(
        'https://example.org/b').failure_class == net.REQUEST_LIMIT


def test_bounded_transport_rejects_downgrade_credentials_and_other_port():
    fetcher = net.Fetcher(obey_robots=False, pause_s=0,
                          allowed_hosts=frozenset({'example.org'}),
                          allowed_schemes=frozenset({'https'}),
                          enforce_global_addresses=True)
    fetcher._session = type('Session', (), {'get': staticmethod(
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('socket opened')))})()
    assert fetcher.get('http://example.org/a').failure_class == net.REDIRECT
    assert fetcher.get('https://user:secret@example.org/a').failure_class == net.ADDRESS_REFUSED
    assert fetcher.get('https://example.org:8080/a').failure_class == net.ADDRESS_REFUSED


def test_provider_start_spacing_and_single_connection_are_shared_across_projects(
        tmp_path, monkeypatch):
    """Two project workers must not turn arXiv's one-client limit into two clients."""
    import threading
    import time

    from claimstone import provider_limits
    from claimstone.request_log import RecordingFetcher
    from claimstone.store import Store

    monkeypatch.setitem(provider_limits.INTERVALS, 'export.arxiv.org', 0.05)
    active = 0
    starts = []
    guard = threading.Lock()

    class Response:
        status_code = 200
        headers = {'Content-Type': 'application/atom+xml'}
        content = b'<feed />'
        url = 'https://export.arxiv.org/api/query'

    def request(*args, **kwargs):
        nonlocal active
        with guard:
            assert active == 0
            active += 1
            starts.append(time.time())
        time.sleep(0.06)
        with guard:
            active -= 1
        return Response()

    barrier = threading.Barrier(2)
    outcomes = []

    def worker(name):
        fetcher = net.Fetcher(obey_robots=False, pause_s=0)
        fetcher._session = type('Session', (), {'get': staticmethod(request)})()
        barrier.wait()
        outcomes.append(RecordingFetcher(fetcher, Store(name, base=tmp_path)).get(
            'https://export.arxiv.org/api/query'))

    threads = [threading.Thread(target=worker, args=(name,)) for name in ('a', 'b')]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive()
    assert len(outcomes) == 2 and all(outcome.ok for outcome in outcomes)
    assert starts[1] - starts[0] >= 0.05
    rows = list(Store('.provider_limits', base=tmp_path).read('starts.jsonl'))
    assert len(rows) == 2 and all(row['host'] == 'export.arxiv.org' for row in rows)


def test_openalex_usage_is_recorded_and_zero_remaining_is_not_an_empty_search(tmp_path):
    from claimstone.request_log import RecordingFetcher
    from claimstone.store import Store

    class Response:
        status_code = 429
        headers = {'Content-Type': 'application/json', 'X-RateLimit-Remaining': '0',
                   'X-RateLimit-Credits-Used': '0'}
        content = b'{"error":"quota"}'
        url = 'https://api.openalex.org/works?search=x'

    fetcher = net.Fetcher(obey_robots=False, pause_s=0)
    fetcher._session = type('Session', (), {'get': staticmethod(
        lambda *args, **kwargs: Response())})()
    store = Store('one', base=tmp_path)
    payload, outcome = RecordingFetcher(fetcher, store).get_json(Response.url)
    assert payload is None
    assert outcome.failure_class == net.RATE_LIMITED
    assert outcome.detail == 'daily credits exhausted'
    assert outcome.provider_usage == {'daily_remaining': '0', 'credits_used': '0'}
    transport = next(row for row in store.read('requests.jsonl')
                     if row['event'] == 'transport')
    assert transport['provider_usage'] == outcome.provider_usage


def test_openalex_meta_cost_is_kept_with_validated_response(tmp_path):
    from claimstone.request_log import RecordingFetcher
    from claimstone.store import Store

    class Response:
        status_code = 200
        headers = {'Content-Type': 'application/json', 'X-RateLimit-Credits-Used': '10'}
        content = b'{"meta":{"cost_usd":0.001,"count":42},"results":[]}'
        url = 'https://api.openalex.org/works?search=x'

    fetcher = net.Fetcher(obey_robots=False, pause_s=0)
    fetcher._session = type('Session', (), {'get': staticmethod(
        lambda *args, **kwargs: Response())})()
    store = Store('one', base=tmp_path)
    payload, outcome = RecordingFetcher(fetcher, store).get_json(Response.url)
    assert payload['meta']['count'] == 42
    assert outcome.provider_usage == {'credits_used': '10', 'meta_cost_usd': 0.001}
    validated = next(row for row in store.read('requests.jsonl')
                     if row['event'] == 'validated_response')
    assert validated['provider_usage'] == outcome.provider_usage
