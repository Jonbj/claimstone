"""Machine-shared start spacing for scholarly API requests.

The project writer lock protects one project's ledgers. Provider limits also
apply when different projects run in different processes, so reservations live
in a small append-only ledger shared by every project under the same store root.
"""

from __future__ import annotations

import time
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
}


@contextmanager
def provider_slot(project_store: Store, host: str) -> Iterator[None]:
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
        recent = next((row for row in reversed(list(shared.read('starts.jsonl')))
                       if row.get('host') == host), None)
        if recent is not None:
            wait = interval - (time.time() - float(recent['started_at_epoch']))
            if wait > 0:
                time.sleep(wait)
        shared.append('starts.jsonl', {'host': host, 'started_at_epoch': time.time()})
        yield
