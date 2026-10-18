"""Citation edges around candidates we already hold, and the works they point to that we do not (D143).

Snowballing proposes leads; it never decides eligibility. A work cited by, or citing, several of our candidates is a
*suggestion* a person may propose through the intake, where it is routed like anything else a person proposes. The
number shown beside it is **a count of seeds that link to it, not a measure of relevance** — the same discipline as the
direction count in a profile (invariant 7).

Depth is one. Each seed is asked twice (who cites it, what it cites), each answer is capped, and a capped answer is
recorded as such so a long list is never mistaken for a complete one. Nothing here writes `candidates.jsonl`.
"""

from __future__ import annotations

import datetime as _dt
import urllib.parse
from collections import defaultdict
from typing import Any

from claimstone import ids

SNOWBALL_VERSION = 1
EDGES = "citation_edges.jsonl"
TITLES = "citation_titles.jsonl"
MAX_EDGES_PER_DIRECTION = 200
CITED_BY = "cited_by"   # other work cites the seed
CITES = "cites"         # the seed cites the other work


def edges_url(doi: str, direction: str) -> str:
    path = "citations" if direction == CITED_BY else "references"
    return f"https://api.opencitations.net/index/v2/{path}/doi:{urllib.parse.quote(doi, safe='/')}"


def _doi_of(identifiers: Any) -> str | None:
    """OpenCitations writes `omid:… doi:10.x pmid:…` in one string; take the DOI token."""
    for token in str(identifiers or "").replace(",", " ").split():
        if token.lower().startswith("doi:"):
            return ids.normalize_doi(token[4:])
    return None


def parse_edges(payload: Any, seed_doi: str, direction: str) -> tuple[list[dict[str, Any]], bool]:
    """(edges, truncated). The other end is `citing` for CITED_BY and `cited` for CITES."""
    if not isinstance(payload, list):
        return [], False
    field = "citing" if direction == CITED_BY else "cited"
    seen: set[str] = set()
    edges: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        other = _doi_of(item.get(field))
        if not other or other == seed_doi or other in seen:
            continue
        seen.add(other)
        edges.append({"other_doi": other, "creation": item.get("creation"), "oci": item.get("oci")})
    truncated = len(edges) > MAX_EDGES_PER_DIRECTION
    return edges[:MAX_EDGES_PER_DIRECTION], truncated


def edge_row(seed_key: str, seed_doi: str, direction: str, edges: list[dict[str, Any]], *, ok: bool,
             truncated: bool, campaign: str | None = None, observed_at: str | None = None) -> dict[str, Any]:
    return {"snowball_version": SNOWBALL_VERSION, "seed_candidate_key": seed_key, "seed_doi": seed_doi,
            "direction": direction, "ok": ok, "truncated": truncated, "edges": edges, "campaign": campaign,
            "observed_at": observed_at or _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")}


def suggestions(store, *, min_links: int = 2, limit: int = 30,
                seeds_in: set[str] | None = None) -> list[dict[str, Any]]:
    """Works linked to by at least `min_links` distinct seeds that are not candidates yet, most-linked first.

    `links` counts seeds. It is labelled a count wherever it is shown. Ties are broken by DOI so the order is stable.
    """
    try:
        rows = latest_edges(store)
    except FileNotFoundError:
        return []
    held = {str(r.get("candidate_key")) for r in store.read("candidates.jsonl")}
    linked: dict[str, set[str]] = defaultdict(set)
    how: dict[str, set[str]] = defaultdict(set)
    for (seed, direction), row in rows.items():
        if not row.get("ok") or (seeds_in is not None and seed not in seeds_in):
            continue
        for edge in row.get("edges") or []:
            other = edge.get("other_doi")
            if other and f"doi:{other}" not in held:
                linked[other].add(seed)
                how[other].add(direction)
    titles = latest_titles(store)
    out = []
    for doi, seeds in linked.items():
        if len(seeds) < min_links:
            continue
        info = titles.get(doi) or {}
        out.append({"doi": doi, "links": len(seeds), "seeds": sorted(seeds), "directions": sorted(how[doi]),
                    "title": info.get("title"), "year": info.get("year"), "venue": info.get("venue")})
    out.sort(key=lambda item: (-item["links"], item["doi"]))
    return out[:limit]


def latest_edges(store) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in store.read(EDGES):
        out[(str(row.get("seed_candidate_key")), str(row.get("direction")))] = row
    return out


def latest_titles(store) -> dict[str, dict[str, Any]]:
    try:
        return store.latest_by(TITLES, "doi")
    except FileNotFoundError:
        return {}
