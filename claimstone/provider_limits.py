"""Machine-shared start spacing for scholarly API requests.

The project writer lock protects one project's ledgers. Provider limits also
apply when different projects run in different processes, so reservations live
in a small append-only ledger shared by every project under the same store root.
"""

from __future__ import annotations

import os
import re
import time
import datetime as dt
import urllib.parse
from contextlib import contextmanager
from typing import Iterator

from .store import Store


# Conservative intervals, including robots requests. Crossref's public list
# pool allows one request/s; arXiv's legacy API requires one every three seconds
# and a single connection across machines under our control. OpenAlex is not in
# this table: its documented limit depends on the key and the query class, and
# `openalex_interval` reads both (issue #10, D148).
INTERVALS = {
    'export.arxiv.org': 3.0,
    'api.crossref.org': 1.0,
    # Europe PMC publishes no numeric limit that was verified (D141): half a second keeps well under any.
    'www.ebi.ac.uk': 0.5,
    # CORE's free key is published as 5 single requests per 10 s (D144): one every 2 s.
    'api.core.ac.uk': 2.0,
    # Brave's plan limit was not stated where it was read (D145); one request per 1.2 s is the conservative figure.
    'api.search.brave.com': 1.2,
}

# Read from https://help.openalex.org/api/authentication/ on 2026-10-18. A key
# does not say which plan it belongs to, so the keyed figure is the free/prepaid
# 30/s, never the annual plan's 50/s. "Complex" is the provider's own definition:
# a search with more than five OR/AND/NOT operators. Semantic search is 1/s.
OPENALEX_REQUESTS_PER_SECOND = {
    'standard': {'keyless': 10, 'keyed': 30},
    'complex': {'keyless': 1, 'keyed': 5},
    'semantic': {'keyless': 1, 'keyed': 1},
}
_OPENALEX_BOOLEAN = re.compile(r'\b(?:OR|AND|NOT)\b', re.I)


def openalex_query_class(url: str) -> str:
    """Which documented OpenAlex class this request belongs to."""
    params = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    if any(key == 'search.semantic' or key.startswith('search.semantic.')
           for key in params):
        return 'semantic'
    terms = [value for key, values in params.items()
             if key == 'search' or key.startswith('search.')
             for value in values]
    operators = sum(len(_OPENALEX_BOOLEAN.findall(term)) for term in terms)
    return 'complex' if operators > 5 else 'standard'


def openalex_requests_per_second(url: str, *, keyed: bool | None = None) -> int:
    """The documented rate, with `keyed=None` reading `OPENALEX_API_KEY`."""
    if keyed is None:
        keyed = bool(os.environ.get('OPENALEX_API_KEY', '').strip())
    return OPENALEX_REQUESTS_PER_SECOND[openalex_query_class(url)][
        'keyed' if keyed else 'keyless']


def openalex_interval(url: str, *, keyed: bool | None = None) -> float:
    """Spacing between starts, at (not below) the documented limit."""
    return 1.0 / openalex_requests_per_second(url, keyed=keyed)


def _interval(host: str, url: str) -> float | None:
    if host == 'api.openalex.org':
        return openalex_interval(url)
    return INTERVALS.get(host)

# OpenAlex's October 2026 free-key allowance is 10,000 credits/day. This
# machine-local guard counts Claimstone's own estimated calls; another client
# using the key can still exhaust the provider account first.
OPENALEX_DAILY_CREDIT_CEILING = 10_000


class ProviderCreditLimit(ValueError):
    """A request was refused before transport because its local budget is spent."""


class ProviderRouteUnpriced(ValueError):
    """An API route has no reviewed credit estimate and must not be guessed."""


def _openalex_credits(url: str) -> int:
    parsed = urllib.parse.urlsplit(url)
    if parsed.path in {'/robots.txt', '/rate-limit'}:
        return 0
    params = urllib.parse.parse_qs(parsed.query)
    if parsed.path.startswith('/works/') and params.get('rerank') != ['true']:
        return 0  # one Work by ID or DOI
    if parsed.path == '/works':
        searched = any(key == 'search' or key.startswith('search.') for key in params)
        if params.get('rerank') == ['true']:
            return 20 if searched else 11
        return 10 if searched else 1
    raise ProviderRouteUnpriced('OpenAlex route has no frozen credit estimate')


@contextmanager
def provider_slot(project_store: Store, host: str, url: str) -> Iterator[None]:
    """Reserve a physical start and serialize that provider's connections.

    The lock is retained through the transfer. This is deliberately stricter
    than Crossref and OpenAlex require and satisfies arXiv's one-connection rule.
    An interrupted transfer leaves its start reservation in the ledger.
    """
    interval = _interval(host, url)
    if interval is None:
        yield
        return
    shared = Store('.provider_limits', base=project_store.root.parent)
    with shared.writer_lock():
        starts = list(shared.read('starts.jsonl'))
        credits = _openalex_credits(url) if host == 'api.openalex.org' else 0
        recent = next((row for row in reversed(starts)
                       if row.get('host') == host), None)
        if recent is not None:
            wait = interval - (time.time() - float(recent['started_at_epoch']))
            if wait > 0:
                time.sleep(wait)
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        if credits and sum(int(row.get('estimated_credits') or 0) for row in starts
                           if row.get('utc_date') == today and
                           row.get('host') == 'api.openalex.org') + credits > OPENALEX_DAILY_CREDIT_CEILING:
            raise ProviderCreditLimit('local OpenAlex daily credit ceiling reached')
        shared.append('starts.jsonl', {'host': host, 'started_at_epoch': time.time(),
                                      'utc_date': today, 'estimated_credits': credits})
        yield
