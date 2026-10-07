"""Record scholarly request outcomes, including empty searches and metadata/robots failures."""
from __future__ import annotations

import datetime as dt
from typing import Any
from . import net
from .store import Store


class RecordingFetcher:
    def __init__(self, fetcher: net.FetcherLike, store: Store, **context: Any):
        self.fetcher = fetcher.fetcher if isinstance(fetcher, RecordingFetcher) else fetcher
        self.store = store
        self.context = context
        if isinstance(net.Fetcher, type) and isinstance(self.fetcher, net.Fetcher):
            self.fetcher.failure_store = store
            if self.fetcher.max_physical_requests is not None:
                campaign = context.get('campaign')
                if not campaign:
                    raise ValueError('bounded fetcher requires a recorded campaign')
                used = sum(row.get('event') == 'request_started' and
                           row.get('campaign') == campaign
                           for row in store.read('requests.jsonl'))
                self.fetcher._physical_requests = max(self.fetcher._physical_requests, used)

    def _record(self, outcome: net.Outcome, event='response'):
        row = outcome.as_row() | self.context | {
            'event': event, 'recorded_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        if outcome.body:
            digest, path = self.store.store_bytes_at('requests/raw', outcome.body, '.bin')
            row.update(raw_sha256=digest, raw_path=str(path))
        self.store.append('requests.jsonl', row)

    def _call(self, method, *args, **kwargs):
        # Real transport emits every redirect and robots outcome before the next request starts.
        previous = getattr(self.fetcher, 'on_outcome', None)
        previous_request = getattr(self.fetcher, 'on_request', None)
        if isinstance(net.Fetcher, type) and isinstance(self.fetcher, net.Fetcher):
            self.fetcher.on_outcome = self._record
            if self.fetcher.max_physical_requests is not None:
                self.fetcher.on_request = lambda url: self.store.append(
                    'requests.jsonl', {'event': 'request_started', 'url': url,
                                       'request_url': url, 'fetch_version': net.FETCH_VERSION,
                                       'ok': None, 'http_status': None,
                                       'recorded_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                                       **self.context})
        try:
            result = getattr(self.fetcher, method)(*args, **kwargs)
            self._record(result[1] if method == 'get_json' else result,
                         'validated_response' if method == 'get_json' else 'response')
            return result
        finally:
            if isinstance(net.Fetcher, type) and isinstance(self.fetcher, net.Fetcher):
                self.fetcher.on_outcome = previous
                self.fetcher.on_request = previous_request

    def get(self, url, *, expect=(), as_json=False):
        return self._call('get', url, expect=expect, as_json=as_json)

    def get_json(self, url):
        return self._call('get_json', url)
