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

NEAR_MATCH_MIN_CHARS = 25


def near_match(key: str, known: Iterable[str]) -> str | None:
    """A key whose title looks like an existing one. Recorded, never acted on.

    "Approximate" is defined rather than left to judgement: one folded title contains the other
    and the shorter of the two is at least 25 characters. That is the check that found both the 15
    banner cases in the measured corpus and its one false positive — "And the Cross-Section of
    Expected Returns" inside "Media coverage and the cross-section of expected returns", which are
    different papers.

    The rule survives that false positive because of an asymmetry. A duplicate costs one wasted
    acquisition attempt, and not even a second download, since bytes are content-addressed. A
    wrong merge loses a source permanently and attributes its claims to another work. So the
    outcome here is a note on a row and nothing else.
    """
    if not key.startswith("title:"):
        return None
    mine = key[len("title:"):]
    if len(mine) < NEAR_MATCH_MIN_CHARS:
        return None
    for other in known:
        if other == key or not other.startswith("title:"):
            continue
        theirs = other[len("title:"):]
        shorter = mine if len(mine) <= len(theirs) else theirs
        if len(shorter) < NEAR_MATCH_MIN_CHARS:
            continue
        if mine in theirs or theirs in mine:
            return other
    return None


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
    possible_duplicates = 0
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
                    note = near_match(row["candidate_key"], known)
                    if note:
                        row["possible_duplicate_of"] = note
                        possible_duplicates += 1
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
        "possible_duplicates": possible_duplicates,
        "round": round_name,
    }


def run_citations(
    project: Project, store: Store, *, round_name: str = ROUTINE
) -> dict[str, Any]:
    """Admit references extracted in stage 3 as candidates, by the project's declared rule.

    Opens no socket: this reads a ledger. So it is re-runnable at no cost when the threshold
    changes — the same arrangement as `gate-audit` and `normalize --confirm-audit`.

    The rule filters on `citations_in_corpus`, which is a property of this channel and not of the
    keyword channel's terms, so the two channels stay independent — the condition D10 needs. What
    it does introduce is a bias toward canonical works, recorded in the spec as a limit of any
    completeness estimate rather than hidden.
    """
    references = store.latest_by("references.jsonl", "key")
    if not references:
        # Distinct from "zero admitted": nothing was there to read, and reporting 0 candidates
        # would read as the bibliography having found nothing.
        return {"references_available": False, "considered": 0, "admitted": 0, "new": 0,
                "unclassified": 0, "uncovered": {}, "possible_duplicates": 0,
                "round": round_name}

    # config.load_citation_channel already merged the engine defaults, so this is complete.
    rule = dict(project.citation_channel)
    known = set(store.latest_by("candidates.jsonl", "candidate_key"))
    admitted = new = possible_duplicates = 0
    unclassified: list[dict[str, Any]] = []

    for reference in references.values():
        title = str(reference.get("title") or "")
        year = reference.get("year")
        if int(reference.get("citations_in_corpus") or 0) < rule["min_citations_in_corpus"]:
            continue
        if len(title) < rule["require_title_chars"]:
            continue
        if year is not None and int(year) < rule["min_year"]:
            continue
        admitted += 1

        doi = reference.get("doi")
        row = _row(
            title=title,
            url=f"https://doi.org/{doi}" if doi else "",
            doi=doi,
            year=int(year) if year else None,
            venue="",
            venue_type="",
            source_api="citation",
            query="references.jsonl",
            topic_id="",
            channel=CHANNEL_CITATION,
            citations=int(reference.get("citations_in_corpus") or 0),
            extra={
                "cited_by": list(reference.get("cited_by") or []),
                "citations_in_corpus": int(reference.get("citations_in_corpus") or 0),
            },
        )
        if row["candidate_key"] in known:
            continue
        row["source_class"] = classify.classify(row, project.classes)
        row["round"] = round_name
        note = near_match(row["candidate_key"], known)
        if note:
            row["possible_duplicate_of"] = note
            possible_duplicates += 1
        if row["source_class"] is None:
            unclassified.append(row)
        known.add(row["candidate_key"])
        store.append("candidates.jsonl", row)
        new += 1

    return {
        "references_available": True,
        "considered": len(references),
        "admitted": admitted,
        "new": new,
        "unclassified": len(unclassified),
        "uncovered": classify.uncovered(unclassified, project.classes),
        "possible_duplicates": possible_duplicates,
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
