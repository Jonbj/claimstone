"""Stage 1 — discover: topics become candidates.

Deterministic HTTP against scholarly metadata APIs. No model is involved: a model adds
nothing to a keyword query and would make the round irreproducible. Every candidate records
the hash of the query that found it and the channel it came through, because completeness
is later estimated by comparing two *independent* channels — keyword search here, and
citations extracted from acquired texts in stage 3.
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator

from claimstone import ids, net
from claimstone.config import Project
from claimstone.searchers import CHANNEL_KEYWORD, SEARCHERS, _limit_kw, _row
from claimstone.store import Store


def run(
    project: Project,
    store: Store,
    fetcher: net.Fetcher,
    *,
    apis: Iterable[str] = ("openalex", "crossref", "arxiv"),
    topics: Iterable[str] | None = None,
    per_query: int = 25,
) -> dict[str, Any]:
    """Search every term of every selected topic; append only candidates not already seen."""
    wanted = set(topics) if topics else None
    known = set(store.latest_by("candidates.jsonl", "candidate_key"))
    new = 0
    seen_this_run = 0

    for topic in project.topics:
        if wanted and topic.id not in wanted:
            continue
        for term in topic.terms:
            for api in apis:
                searcher = SEARCHERS[api]
                for row in searcher(fetcher, term, topic.id, **{_limit_kw(api): per_query}):
                    if not row["title"] and not row["url"]:
                        continue
                    seen_this_run += 1
                    if row["candidate_key"] in known:
                        continue
                    known.add(row["candidate_key"])
                    store.append("candidates.jsonl", row)
                    new += 1

    return {"returned": seen_this_run, "new": new, "total": len(known)}


def import_manifest(store: Store, entries: Iterable[Any]) -> dict[str, Any]:
    """Seed candidates from a validated manifest. Parsing and validation live in config.

    This exists so acquisition can be measured against a real frozen corpus rather than a fresh
    search: the point of the first milestone is whether the acquisition rate moves on the
    manifest that produced 0.42, holding the source list constant.
    """
    known = store.latest_by("candidates.jsonl", "candidate_key")
    added = 0
    updated = 0
    rows = 0
    for entry in entries:
        rows += 1
        row = _row(
            title=entry.title,
            url=entry.url,
            doi=ids.normalize_doi(entry.url),
            year=None,
            venue="",
            # No API reported a venue type for this row, so there is none to record. A manifest
            # entry needs no classification anyway: it declares its own class, which is where
            # `source_class` below comes from.
            venue_type="",
            source_api="manifest",
            query="manifest.tsv",
            topic_id="",
            channel=CHANNEL_KEYWORD,
            extra={
                "source_id": entry.source_id,
                "source_class": entry.source_class,
                "declared_format": entry.declared_format,
            },
        )
        held = known.get(row["candidate_key"])
        if held is not None:
            # Append-only: a candidate whose recorded facts changed gets a new row rather than an
            # edit, and `latest_by` prefers it. Skipping on the key alone would freeze a stale
            # source_class — an earlier import stored the manifest's own word for the class
            # instead of the id it resolves to, which would quietly split one class into two.
            if all(held.get(f) == row.get(f)
                   for f in ("source_class", "source_id", "url", "title", "declared_format")):
                continue
            updated += 1
        else:
            added += 1
        known[row["candidate_key"]] = row
        store.append("candidates.jsonl", row)
    return {"rows": rows, "new": added, "updated": updated, "total": len(known)}
