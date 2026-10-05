"""API credentials must never travel to a redirect destination or the request ledger."""
import json

import pytest

from claimstone import net
from claimstone.request_log import RecordingFetcher
from claimstone.store import Store


class Response:
    def __init__(self, url, status=200, location=None):
        self.url = url
        self.status_code = status
        self.headers = {'Content-Type': 'application/json'}
        if location:
            self.headers['Location'] = location
        self.content = b'{"results": []}'
        self.text = self.content.decode()


def test_key_is_sent_per_hop_but_not_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENALEX_API_KEY', 'test-secret')
    start = 'https://api.openalex.org/works?search=news'
    target = 'https://publisher.example/paper'
    calls = []
    fetcher = net.Fetcher(obey_robots=False, pause_s=0)
    fetcher._session.close()
    def get(url, **kwargs):
        calls.append((url, kwargs['headers']))
        return Response(url, 302, target) if url == start else Response(url)
    fetcher._session = type('Session', (), {'get': staticmethod(get)})()
    store = Store('synthetic', base=tmp_path)
    _, outcome = RecordingFetcher(fetcher, store).get_json(start)
    assert outcome.ok
    assert calls[0][1]['Authorization'] == 'Bearer test-secret'
    assert 'Authorization' not in calls[1][1]
    assert 'test-secret' not in json.dumps(list(store.read('requests.jsonl')))
    assert 'test-secret' not in json.dumps(calls[0][0])


@pytest.mark.parametrize('url', ['http://api.openalex.org/works',
    'https://api.openalex.org.evil.example/works', 'https://api.crossref.org/works'])
def test_key_is_not_sent_to_other_origins(monkeypatch, url):
    monkeypatch.setenv('OPENALEX_API_KEY', 'test-secret')
    fetcher = net.Fetcher(obey_robots=False, pause_s=0)
    fetcher._session.close()
    calls = []
    def get(destination, **kwargs):
        calls.append(kwargs['headers'])
        return Response(destination)
    fetcher._session = type('Session', (), {'get': staticmethod(get)})()
    assert fetcher.get(url).ok
    assert all(not h or 'Authorization' not in h for h in calls)


def test_keyless_requests_remain_anonymous(monkeypatch):
    monkeypatch.delenv('OPENALEX_API_KEY', raising=False)
    fetcher = net.Fetcher(obey_robots=False, pause_s=0)
    fetcher._session.close()
    def get(url, **kwargs):
        assert kwargs['headers'] == {'Accept': 'application/json'}
        return Response(url)
    fetcher._session = type('Session', (), {'get': staticmethod(get)})()
    assert fetcher.get_json('https://api.openalex.org/works')[1].ok
