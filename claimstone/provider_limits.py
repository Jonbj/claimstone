"""Machine-shared start spacing for scholarly API requests.

The project writer lock protects one project's ledgers. Provider limits also
apply when different projects run in different processes, so reservations live
in a small append-only ledger shared by every project under the same store root.
"""

from __future__ import annotations

import time
import datetime as dt
import urllib.parse
from contextlib import contextmanager
from typing import Iterator

from .store import Store


# Conservative intervals, including robots requests. Crossref's public list
# pool allows one request/s; arXiv's legacy API requires one every three seconds
# and a single connection across machines under our control. OpenAlex allows
# 100 requests/s; 20 ms keeps our own workers well below that ceiling.
INTERVALS = {
    'export.arxiv.org': 3.0,
    'api.crossref.org': 1.0,
    'api.openalex.org': 0.02,
    # Europe PMC publishes no numeric limit that was verified (D141): half a second keeps well under any.
    'www.ebi.ac.uk': 0.5,
    # CORE's free key is published as 5 single requests per 10 s (D144): one every 2 s.
    'api.core.ac.uk': 2.0,
    # E-utilities allows 3 requests/s without a key (10 with one, which this engine does not use;
    # see D155): 0.34 s is one every 2.94 requests/s, under the unkeyed ceiling.
    'eutils.ncbi.nlm.nih.gov': 0.34,
    # Brave's plan limit was not stated where it was read (D145); one request per 1.2 s is the conservative figure.
    'api.search.brave.com': 1.2,
}

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
    interval = INTERVALS.get(host)
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
