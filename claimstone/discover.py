"""Stage 1 — discover: topics become candidates, through two independent channels.

Deterministic HTTP against scholarly metadata APIs; no model is involved, because a model adds
nothing to a keyword query and would make the round irreproducible.

Every candidate carries a **source class**, assigned by rules the project declared (see
`classify`). Without one, stage 2 refuses it — that is invariant 6 working, and it is why this
stage existed for a while producing rows nothing downstream could use.

Completeness is later estimated by comparing two *independent* channels: keyword search here, and
citations extracted from acquired texts in stage 3. This module reads that bibliography and writes
candidates; it never writes another stage's ledger.
"""

from __future__ import annotations

from typing import Any, Iterable

from claimstone import classify, ids, net
from claimstone.config import Project
from claimstone.searchers import CHANNEL_CITATION, CHANNEL_KEYWORD, SEARCHERS, _limit_kw, _row
from claimstone.store import Store

ROUTINE = "routine"


def run(
    project: Project,
    store: Store,
    fetcher: net.FetcherLike,
    *,
    apis: Iterable[str] = ("openalex", "crossref", "arxiv"),
    topics: Iterable[str] | None = None,
    per_query: int = 25,
    round_name: str = ROUTINE,
) -> dict[str, Any]:
    """Search every term of every selected topic; append only candidates not already seen."""
    wanted = set(topics) if topics else None
    known = set(store.latest_by("candidates.jsonl", "candidate_key"))
    new = 0
    seen_this_run = 0
    unclassified: list[dict[str, Any]] = []
    queries = 0

    for topic in project.topics:
        if wanted and topic.id not in wanted:
            continue
        for term in topic.terms:
            for api in apis:
                queries += 1
                searcher = SEARCHERS[api]
                for row in searcher(fetcher, term, topic.id, **{_limit_kw(api): per_query}):
                    if not row["title"] and not row["url"]:
                        continue
                    seen_this_run += 1
                    if row["candidate_key"] in known:
                        continue
                    row["source_class"] = classify.classify(row, project.classes)
                    row["round"] = round_name
                    if row["source_class"] is None:
                        unclassified.append(row)
                    known.add(row["candidate_key"])
                    store.append("candidates.jsonl", row)
                    new += 1

    return {
        "returned": seen_this_run,
        "new": new,
        "total": len(known),
        "queries": queries,
        "unclassified": len(unclassified),
        # Which attribute values went unmatched, so the remedy is a declared rule.
        "uncovered": classify.uncovered(unclassified, project.classes),
        "round": round_name,
    }


def import_manifest(
    store: Store, entries: Iterable[Any], *, round_name: str = ROUTINE
) -> dict[str, Any]:
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
        # Every candidate in the ledger carries a round, manifest imports included: "how many are
        # new this round" is a round-over-round figure, and reconstructing it from timestamps is what
        # append-only storage exists to make unnecessary.
        row["round"] = round_name
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
