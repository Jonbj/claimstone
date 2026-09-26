"""What the two channels found, as three separate numbers.

The three are: how many candidates the keyword channel produced, how many the citation channel
produced, and how many works both found. They are **not** combined into one figure here, and that
is a requirement of the spec rather than an omission.

A capture-recapture estimate is computable from exactly these three numbers — on the first
measured corpus it gives about 2,962 works and a corpus covering 0.8% — and all three of its
assumptions are violated. The overlap is understated by an unknown amount, because title matching
misses a work whose title GROBID took from a cover banner. The keyword channel here was a
hand-curated manifest, not a random sample. And catchability is unequal by construction, since a
canonical paper is cited by everyone and an obscure one by nobody — which the citation channel's
own threshold relies on, so our filter violates the assumption the estimate needs.

What may be concluded from the three numbers is `synthesize`'s problem. What is solid, and belongs
in any reading of them, is the raw comparison: on the first corpus 705 of 711 references were not
in the manifest, so the second channel finds hundreds of things the first missed, and no estimate
is needed to know that.
"""

from __future__ import annotations

from typing import Any

from claimstone.store import Store

CAVEAT = (
    "Three quantities, deliberately not combined: an estimate from them would rest on "
    "assumptions this corpus violates. See the stage 1 spec, section 6."
)


def summarise(store: Store, *, round_name: str | None = None) -> dict[str, Any]:
    """Per channel: candidates, topics, queries, classes. Plus the overlap between them."""
    candidates = [
        row
        for row in store.latest_by("candidates.jsonl", "candidate_key").values()
        if round_name is None or row.get("round") == round_name
    ]
    references = store.latest_by("references.jsonl", "key")

    channels: dict[str, dict[str, Any]] = {}
    unclassified = 0
    uncovered: dict[str, int] = {}
    for row in candidates:
        name = str(row.get("channel") or "unknown")
        bucket = channels.setdefault(name, {
            "candidates": 0, "topics": set(), "queries": set(), "by_class": {},
        })
        bucket["candidates"] += 1
        if row.get("topic_id"):
            bucket["topics"].add(row["topic_id"])
        if row.get("query_hash"):
            bucket["queries"].add(row["query_hash"])
        klass = row.get("source_class")
        if klass is None:
            unclassified += 1
            value = str(row.get("venue_type") or "")
            if value:
                uncovered[value] = uncovered.get(value, 0) + 1
        else:
            bucket["by_class"][klass] = bucket["by_class"].get(klass, 0) + 1

    for name in ("keyword", "citation"):
        channels.setdefault(name, {"candidates": 0, "topics": set(), "queries": set(),
                                   "by_class": {}})
    for bucket in channels.values():
        bucket["topics"] = len(bucket["topics"])
        bucket["queries"] = len(bucket["queries"])
        bucket["by_class"] = dict(sorted(bucket["by_class"].items()))
    channels["citation"]["references_seen"] = len(references)

    keyword_keys = {
        str(row["candidate_key"]) for row in candidates if row.get("channel") == "keyword"
    }
    overlap = len(keyword_keys & set(references))

    return {
        "round": round_name,
        "candidates": len(candidates),
        "keyword": channels["keyword"],
        "citation": channels["citation"],
        "overlap": overlap,
        "unclassified": unclassified,
        "uncovered": dict(sorted(uncovered.items(), key=lambda kv: -kv[1])),
        "caveat": CAVEAT,
    }
