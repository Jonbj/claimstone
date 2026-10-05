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

import re
from typing import Any, Iterable

from claimstone import claim_records, classify, ids, net, searchers, population
from claimstone.config import Project
from claimstone.searchers import CHANNEL_CITATION, CHANNEL_KEYWORD, SEARCHERS, _limit_kw, _row
from claimstone.store import Store, sha256_text
from claimstone.request_log import RecordingFetcher

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
    policy = getattr(project, "population", {})
    population.check_round(store, policy, round_name)
    known = set(store.latest_by("candidates.jsonl", "candidate_key"))
    new = 0
    possible_duplicates = 0
    seen_this_run = 0
    unclassified: list[dict[str, Any]] = []
    queries = 0
    completed = 0
    failures = {}
    outside_population = 0

    for topic in project.topics:
        if wanted and topic.id not in wanted:
            continue
        for term in topic.terms:
            for api in apis:
                queries += 1
                searcher = SEARCHERS[api]
                context = {'purpose': 'discovery', 'round': round_name, 'source_api': api,
                           'query': term, 'topic_id': topic.id}
                logged = RecordingFetcher(fetcher, store, **context)
                returned = 0
                failure = None
                detail = ''
                rows = []
                try:
                    rows = list(searcher(logged, term, topic.id, **{_limit_kw(api): per_query}))
                except (searchers.SearchError, AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
                    from .store import LedgerCorrupt
                    if isinstance(exc, LedgerCorrupt):
                        raise
                    failure = getattr(exc, 'failure', 'INVALID_SEARCH_RESPONSE')
                    detail = str(exc)[:400]
                    failures[failure] = failures.get(failure, 0) + 1
                else:
                    completed += 1
                returned = len(rows)
                for row in rows:
                    if not row["title"] and not row["url"]:
                        continue
                    seen_this_run += 1
                    row["round"] = round_name
                    if not population.observe(store, policy, row):
                        outside_population += 1
                        continue
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
                store.append('queries.jsonl', context | {
                    'query_id': sha256_text(f'{round_name}|{api}|{topic.id}|{term}'),
                    'discovery_version': searchers.DISCOVERY_VERSION, 'per_query': per_query,
                    'ok': failure is None, 'failure_class': failure, 'detail': detail,
                    'returned': returned, 'completed_at': searchers._now()})

    return {
        "returned": seen_this_run,
        "new": new,
        "total": len(known),
        "queries": queries, "completed_queries": completed,
        "final": completed == queries, "failures": failures,
        "unclassified": len(unclassified),
        # Which attribute values went unmatched, so the remedy is a declared rule.
        "uncovered": classify.uncovered(unclassified, project.classes),
        "possible_duplicates": possible_duplicates,
        "round": round_name,
        "outside_population": outside_population,
    }


RESOLVED = frozenset({"BY_DOI", "BY_TITLE"})


def run_citations(
    project: Project,
    store: Store,
    *,
    round_name: str = ROUTINE,
    fetcher: net.FetcherLike | None = None,
) -> dict[str, Any]:
    """Admit references extracted in stage 3 as candidates, by the project's declared rule.

    Without a `fetcher` this opens no socket: it reads a ledger, so it is re-runnable at no cost when
    the threshold changes — the same arrangement as `gate-audit` and `normalize --confirm-audit`. That
    promise is why resolution is opt-in rather than automatic.

    **With one, each admitted reference is resolved into a work.** A reference carries a title,
    sometimes a DOI, and nothing else — no venue, no venue type, no address — so measured on the real
    corpus every one of the 37 candidates this wrote was unclassified and 25 had no URL at all. Stage
    3 resolves nothing by design and no spec said who does; this does, through the same API the
    keyword channel queries, and records which way each one went.

    The rule filters on `citations_in_corpus`, which is a property of this channel and not of the
    keyword channel's terms, so the two channels stay independent — the condition D10 needs. What
    it does introduce is a bias toward canonical works, recorded in the spec as a limit of any
    completeness estimate rather than hidden.
    """
    policy = getattr(project, "population", {})
    population.check_round(store, policy, round_name)
    outside_population = 0
    if fetcher is not None:
        fetcher = RecordingFetcher(fetcher, store, purpose='citation-resolution', round=round_name)
    references = store.latest_by("references.jsonl", "key")
    if not references:
        # Distinct from "zero admitted": nothing was there to read, and reporting 0 candidates
        # would read as the bibliography having found nothing.
        return {"references_available": False, "considered": 0, "admitted": 0, "new": 0,
                "unclassified": 0, "uncovered": {}, "possible_duplicates": 0,
                "resolved": 0, "unresolved": {}, "round": round_name}

    # config.load_citation_channel already merged the engine defaults, so this is complete.
    rule = dict(project.citation_channel)
    held = store.latest_by("candidates.jsonl", "candidate_key")
    known = set(held)
    by_doi = {str(row["doi"]): key for key, row in held.items() if row.get("doi")}
    admitted = new = possible_duplicates = resolved = 0
    unresolved: dict[str, int] = {}
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

        key = str(reference.get("key") or "")
        previous = held.get(key)
        if previous is not None and (
            previous.get("resolution") in RESOLVED or fetcher is None
        ):
            # Already resolved, or there is nothing new to say about it without a fetcher. A
            # previously unresolved row *is* retried when one is given, and supersedes itself.
            continue

        if previous is not None:
            population.check_round(store, policy, str(previous.get("round") or round_name), record=False)

        doi = reference.get("doi")
        found = (
            searchers.resolve_work(fetcher, title=title, doi=doi)
            if fetcher is not None
            else {**searchers.UNRESOLVED, "resolution": "NOT_ATTEMPTED"}
        )
        if found["resolution"] in RESOLVED:
            resolved += 1
        else:
            unresolved[found["resolution"]] = unresolved.get(found["resolution"], 0) + 1

        found_doi = found["doi"] or ids.normalize_doi(doi)
        row = _row(
            title=title,
            # The resolved location if there is one, else the DOI's own address, else nothing to
            # fetch — which stage 2 will refuse, correctly.
            url=found["url"] or (f"https://doi.org/{found_doi}" if found_doi else ""),
            doi=found_doi,
            year=found["year"] or (int(year) if year else None),
            venue=found["venue"],
            venue_type=found["venue_type"],
            # The API that told us about the work, which after resolution is the resolver's and not
            # "citation". `channel` is what records that the reference came from a bibliography, and
            # `query` names the ledger it came out of. Without this the resolved venue type is a word
            # in a vocabulary nobody owns, and no predicate can read it.
            source_api=found["api"] or "citation",
            query="references.jsonl",
            topic_id="",
            channel=CHANNEL_CITATION,
            is_oa=found["is_oa"],
            citations=int(reference.get("citations_in_corpus") or 0),
            candidate_key=key,
            extra={
                "cited_by": list(reference.get("cited_by") or []),
                "citations_in_corpus": int(reference.get("citations_in_corpus") or 0),
                "resolution": found["resolution"],
            },
        )
        row["source_class"] = classify.classify(row, project.classes)
        # The round that first found it, as in `import_manifest`: a retry that resolves a candidate
        # must not move it out of the round that admitted it.
        row["round"] = str((previous or {}).get("round") or round_name)
        if not population.observe(store, policy, row):
            outside_population += 1
            continue
        # A shared DOI under two keys is a *certain* duplicate rather than a near-match, and it only
        # becomes reachable once resolution can put a DOI on a title-keyed row. Still only noted: a
        # wrong merge loses a source, a duplicate costs one wasted fetch.
        note = (by_doi.get(str(found_doi)) if found_doi else None) or near_match(key, known)
        if note and note != key:
            row["possible_duplicate_of"] = note
            possible_duplicates += 1
        if row["source_class"] is None:
            unclassified.append(row)
        if key not in known:
            known.add(key)
            new += 1
        held[key] = row
        store.append("candidates.jsonl", row)

    return {
        "references_available": True,
        "considered": len(references),
        "admitted": admitted,
        "new": new,
        "unclassified": len(unclassified),
        "uncovered": classify.uncovered(unclassified, project.classes),
        "possible_duplicates": possible_duplicates,
        "resolved": resolved,
        "unresolved": dict(sorted(unresolved.items(), key=lambda kv: -kv[1])),
        "round": round_name,
        "outside_population": outside_population,
    }


def import_manifest(
    store: Store, entries: Iterable[Any], *, round_name: str = ROUTINE,
    population_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Seed candidates from a validated manifest. Parsing and validation live in config.

    This exists so acquisition can be measured against a real frozen corpus rather than a fresh
    search: the point of the first milestone is whether the acquisition rate moves on the
    manifest that produced 0.42, holding the source list constant.
    """
    population.check_round(store, population_policy or {}, round_name)
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
        # `round` is the round that **first** found this candidate, not the one that last mentioned
        # it. "How many are new this round" is a round-over-round figure, and a re-import under a new
        # name must not move a candidate out of the round that found it — latest-wins would do that
        # silently and empty the earlier round's population.
        previous = known.get(row["candidate_key"])
        row["round"] = str((previous or {}).get("round") or round_name)
        held = previous
        if held is not None:
            # Append-only: a candidate whose recorded facts changed gets a new row rather than an
            # edit, and `latest_by` prefers it. Skipping on the key alone would freeze a stale
            # source_class — an earlier import stored the manifest's own word for the class
            # instead of the id it resolves to, which would quietly split one class into two.
            # `round` is in the comparison so a row written before rounds existed can be stamped by
            # a re-import; without it those candidates can never be given one, and `report --round`
            # finds nothing where the whole corpus is.
            if all(held.get(f) == row.get(f)
                   for f in ("source_class", "source_id", "url", "title", "declared_format",
                             "round")):
                continue
            updated += 1
        else:
            added += 1
        known[row["candidate_key"]] = row
        store.append("candidates.jsonl", row)
    return {"rows": rows, "new": added, "updated": updated, "total": len(known)}


def reclassify(project: Project, store: Store) -> dict[str, Any]:
    """Re-apply the project's `assign_when` rules to every candidate held. Opens no socket.

    The third time this shape has been needed: `regate` re-reads stored bytes under a corrected
    content gate, `model-run --rejudge` re-reads a stored answer under a corrected classifier, and this
    re-reads a stored candidate under corrected class rules. The pattern is not a coincidence — every
    judgement the engine makes over rules a project declares needs a way back, or editing a line of
    YAML costs a round of requests.

    Measured on the real corpus: 35 references resolved to a venue while `alembic-s4` declared no
    `assign_when` at all, so all 35 were written with a null class. Adding the rules changed nothing
    until this existed, because a resolved candidate is skipped rather than re-requested.

    Append-only: a candidate whose class moves gets a new row and keeps the round that found it.
    """
    changed = 0
    declared = 0
    moves: dict[str, int] = {}
    unclassified: list[dict[str, Any]] = []

    for row in store.latest_by("candidates.jsonl", "candidate_key").values():
        if row.get("source_api") == "manifest":
            # A manifest states its class. Invariant 6 says the class travels with the item, and this
            # is the item arriving with it — an inferred class must not replace a given one.
            # Reproduced destructively on the real store before this guard existed: 9 IND and 4 MET
            # rows overwritten with null and 6 ACA demoted to WP, because a manifest row has no venue
            # type and the host rule matched some of the URLs.
            declared += 1
            continue
        assigned = classify.classify(row, project.classes)
        if assigned is None:
            unclassified.append(row)
        if assigned == row.get("source_class"):
            continue
        key = f"{row.get('source_class')} -> {assigned}"
        moves[key] = moves.get(key, 0) + 1
        store.append("candidates.jsonl", {**row, "source_class": assigned})
        changed += 1

    return {
        "changed": changed,
        "declared": declared,
        "moves": dict(sorted(moves.items(), key=lambda kv: -kv[1])),
        "unclassified": len(unclassified),
        "uncovered": classify.uncovered(unclassified, ()),
    }


# The citation as it appears in a rejected claim's text: a surname and a year, in the claim's subject
# position, which is what `claimgate.SECONDHAND` matched to reject it.
_NAMED_WORK = re.compile(
    r"\b([A-Z][A-Za-zÀ-ɏ'’-]+)"
    r"(?:\s*(?:,|and|&|et al\.?)\s*[A-Z][A-Za-zÀ-ɏ'’-]+)*"
    r"\s*\((\d{4})[a-z]?\)"
)


def promote_contested(project: Project, store: Store, *, round_name: str = ROUTINE) -> dict[str, Any]:
    """Admit a work a rejected claim named, whatever the citation channel's threshold says.

    D26's finding, with its instance. The gate rejected H02's only contradicting claim, correctly: it was
    `ACA002` reporting Roll (1988), a source nobody had read. Roll (1988) is in the bibliography as
    `R-squared`, cited once, nine folded characters — so it failed both `min_citations_in_corpus` and
    `require_title_chars` and was invisible. Every rule behaved as declared, and a question with a cited
    contradiction read as uncontested.

    So a rejected `SECONDHAND_CLAIM` is a discovery signal and not only a rejection: a work cited once
    for a contradiction is worth more to this project than a textbook cited three times. The threshold
    still governs the ordinary channel; this is the named exception, and it is recorded on the row as
    `promoted_by` so a corpus can be read back without it.

    Opens no socket: it reads `rejections.jsonl` against `references.jsonl`. A name with no matching
    reference is **reported and never invented** — nothing here knows a work's title or address, and the
    reference is what carries those.
    """
    policy = getattr(project, "population", {})
    population.check_round(store, policy, round_name)
    references = store.latest_by("references.jsonl", "key")
    by_author_year: dict[tuple[str, str], dict[str, Any]] = {}
    for reference in references.values():
        year = str(reference.get("year") or "")
        for author in reference.get("authors") or []:
            surname = str(author).strip().split()[-1] if str(author).strip() else ""
            if surname and year:
                by_author_year.setdefault((surname.lower(), year), reference)

    # Every reference by surname regardless of year, so a name that matched no (surname, year) pair can
    # be reported as ambiguous rather than as absent. Measured: the corpus holds ten Roll references, one
    # titled `R-squared` with no year — the 1988 paper the rejected claim named — and one titled
    # `Journal of Finance`, GROBID having taken the venue for the title.
    by_author: dict[str, int] = {}
    for reference in references.values():
        for author in reference.get("authors") or []:
            surname = str(author).strip().split()[-1].lower() if str(author).strip() else ""
            if surname:
                by_author[surname] = by_author.get(surname, 0) + 1

    held = store.latest_by("candidates.jsonl", "candidate_key")
    named = promoted = outside_population = 0
    unmatched: list[list[str]] = []
    ambiguous: list[list[Any]] = []
    seen: set[tuple[str, str]] = set()

    for row in claim_records.current(store)[1].values():
        if row.get("failure") != "SECONDHAND_CLAIM":
            continue
        claim = str((row.get("record") or {}).get("claim") or "")
        for surname, year in _NAMED_WORK.findall(claim):
            if (surname.lower(), year) in seen:
                continue
            seen.add((surname.lower(), year))
            named += 1
            reference = by_author_year.get((surname.lower(), year))
            if reference is None:
                count = by_author.get(surname.lower(), 0)
                if count:
                    # The surname is in the bibliography and the year is not. Matching on the surname
                    # alone would promote every one of them, and guessing which is the right year is the
                    # fabrication this module exists to refuse.
                    ambiguous.append([surname, year, count])
                else:
                    unmatched.append([surname, year])
                continue
            key = str(reference.get("key") or "")
            if key in held:
                continue

            doi = ids.normalize_doi(reference.get("doi"))
            candidate = _row(
                title=str(reference.get("title") or ""),
                url=f"https://doi.org/{doi}" if doi else "",
                doi=doi,
                year=int(reference["year"]) if reference.get("year") else None,
                venue="",
                venue_type="",
                source_api="citation",
                query="rejections.jsonl",
                topic_id="",
                channel=CHANNEL_CITATION,
                citations=int(reference.get("citations_in_corpus") or 0),
                candidate_key=key,
                extra={
                    "cited_by": list(reference.get("cited_by") or []),
                    "citations_in_corpus": int(reference.get("citations_in_corpus") or 0),
                    "resolution": "NOT_ATTEMPTED",
                    # Why this one is here despite the threshold, so the exception is visible and a
                    # corpus can be read back without it.
                    "promoted_by": "SECONDHAND_CLAIM",
                    "promoted_for": str((row.get("record") or {}).get("question_id") or ""),
                    "promoted_from": row.get("chunk_id"),
                },
            )
            candidate["source_class"] = classify.classify(candidate, project.classes)
            candidate["round"] = round_name
            if not population.observe(store, policy, candidate):
                outside_population += 1
                continue
            held[key] = candidate
            store.append("candidates.jsonl", candidate)
            promoted += 1

    return {
        "named": named,
        "promoted": promoted,
        "outside_population": outside_population,
        # Both reported so somebody can look, neither guessed into a candidate.
        "unmatched": unmatched,
        "ambiguous": ambiguous,
        "round": round_name,
    }
