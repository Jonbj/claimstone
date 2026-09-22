"""Stage 2 — acquire: turn candidates into frozen texts, legally, and account for failures.

This is the binding constraint on the science, not extraction quality: the corpus that
motivated this project sits at an acquisition rate of 0.42 because publishers return 403.
The strategy is therefore open-access first. When a publisher refuses and a DOI is known,
Unpaywall and OpenAlex are asked where a legal free copy lives, and the cascade continues
there instead of retrying the wall.

Every attempt is recorded, successful or not. The acquisition rate computed from this log
is what gates whether a round may produce verdicts at all.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any, Iterable, Iterator

from claimstone import ids, net
from claimstone.store import Store

PDF_TYPES = ("application/pdf", "application/octet-stream")
HTML_TYPES = ("text/html", "application/xhtml+xml", "application/xml", "text/xml", "text/plain")

# Hosts we know serve landing pages rather than full text; a hit here is not a success.
KNOWN_WALLS = (
    "sciencedirect.com", "onlinelibrary.wiley.com", "link.springer.com",
    "tandfonline.com", "jstor.org", "academic.oup.com", "papers.ssrn.com",
    "journals.sagepub.com", "doi.org",
)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Location:
    """One place a copy might live, and why we believe it."""

    url: str
    provenance: str           # unpaywall | openalex | arxiv | candidate | crossref
    version: str = ""         # publishedVersion | acceptedVersion | submittedVersion
    licence: str | None = None
    oa_status: str | None = None
    host_type: str | None = None


def unpaywall_locations(fetcher: net.Fetcher, doi: str) -> tuple[list[Location], str | None]:
    """Ask Unpaywall for legal free copies. Returns locations and the record's oa_status."""
    email = net.contact_email()
    payload, _ = fetcher.get_json(f"https://api.unpaywall.org/v2/{doi}?email={email}")
    if not payload:
        return [], None
    oa_status = payload.get("oa_status")
    locations: list[Location] = []
    raw = payload.get("oa_locations") or []
    best = payload.get("best_oa_location")
    if best and best not in raw:
        raw = [best, *raw]
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        for key in ("url_for_pdf", "url"):
            url = entry.get(key)
            if not url:
                continue
            locations.append(
                Location(
                    url=str(url),
                    provenance="unpaywall",
                    version=str(entry.get("version") or ""),
                    licence=entry.get("license"),
                    oa_status=oa_status,
                    host_type=entry.get("host_type"),
                )
            )
    return locations, oa_status


def openalex_locations(fetcher: net.Fetcher, doi: str) -> list[Location]:
    """OpenAlex carries its own view of where a copy lives; used as the 403 fallback."""
    payload, _ = fetcher.get_json(f"https://api.openalex.org/works/doi:{doi}")
    if not payload:
        return []
    locations: list[Location] = []
    seen: set[str] = set()
    entries = [payload.get("best_oa_location"), *(payload.get("locations") or [])]
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("is_oa"):
            continue
        for key in ("pdf_url", "landing_page_url"):
            url = entry.get(key)
            if not url or url in seen:
                continue
            seen.add(str(url))
            locations.append(
                Location(
                    url=str(url),
                    provenance="openalex",
                    version=str(entry.get("version") or ""),
                    licence=entry.get("license"),
                    oa_status=(payload.get("open_access") or {}).get("oa_status"),
                )
            )
    return locations


def resolve_doi_by_title(fetcher: net.Fetcher, title: str) -> str | None:
    """Find a DOI from a title via OpenAlex, when the URL does not carry one.

    Publisher URLs often use an internal identifier — a ScienceDirect PII, an SSRN
    abstract id — so DOI extraction from the URL fails and no open-access lookup is even
    attempted. Without this step those sources are recorded as paywalled when a legal free
    copy may exist. The match is accepted only on an exact normalised-title equality, so a
    near-miss becomes no DOI rather than the wrong paper.
    """
    folded = ids.normalize_title(title)
    if len(folded) < 15:
        return None
    import urllib.parse

    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(
        {"search": title, "per-page": 5, "mailto": net.contact_email(), "select": "doi,title"}
    )
    payload, _ = fetcher.get_json(url)
    for work in (payload or {}).get("results") or []:
        if ids.normalize_title(work.get("title")) == folded:
            return ids.normalize_doi(work.get("doi"))
    return None


def _version_rank(version: str) -> int:
    """Prefer the version of record, but never refuse a legal preprint over a paywall."""
    return {"publishedversion": 0, "acceptedversion": 1, "submittedversion": 2}.get(
        version.lower().replace(" ", ""), 3
    )


def plan_locations(
    fetcher: net.Fetcher, candidate: dict[str, Any], *, use_apis: bool = True
) -> tuple[list[Location], str | None]:
    """Build the cascade for one candidate, cheapest and most likely first."""
    doi = ids.normalize_doi(candidate.get("doi")) or ids.normalize_doi(candidate.get("url"))
    original = str(candidate.get("url") or "")
    oa_status: str | None = None
    locations: list[Location] = []

    # An arXiv identifier is a guaranteed legal full text; try it before anything else.
    arxiv = ids.arxiv_id(original) or ids.arxiv_id(candidate.get("title"))
    if arxiv:
        locations.append(
            Location(f"https://arxiv.org/pdf/{arxiv}", "arxiv", "submittedVersion", oa_status="green")
        )

    # The URL we were given, unless it is a host we know serves only a landing page.
    if original and not any(w in net.host_of(original) for w in KNOWN_WALLS):
        locations.append(Location(original, "candidate"))

    if not doi and use_apis and candidate.get("title"):
        doi = resolve_doi_by_title(fetcher, str(candidate["title"]))

    if doi and use_apis:
        upw, oa_status = unpaywall_locations(fetcher, doi)
        locations.extend(upw)
        if not upw:
            locations.extend(openalex_locations(fetcher, doi))

    # A known wall is tried last: better a landing page than nothing, but only after
    # every legal open copy has been attempted.
    if original and any(w in net.host_of(original) for w in KNOWN_WALLS):
        locations.append(Location(original, "candidate"))

    # Format outranks version label: a PDF gives the parser a real document, whereas a
    # "publishedVersion" landing page may not carry the full text at all. ACA001 in the
    # reference manifest regressed exactly this way — Unpaywall's HTML beat a direct PDF.
    ordered = sorted(
        locations,
        key=lambda loc: (0 if loc.url.lower().endswith(".pdf") else 1, _version_rank(loc.version)),
    )
    deduped: list[Location] = []
    seen: set[str] = set()
    for loc in ordered:
        key = ids.normalize_url(loc.url)
        if key and key not in seen:
            seen.add(key)
            deduped.append(loc)
    return deduped, oa_status


def _suffix_for(content_type: str, url: str) -> str:
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        return ".pdf"
    if "xml" in content_type:
        return ".xml"
    return ".html"


def acquire_one(
    fetcher: net.Fetcher, store: Store, candidate: dict[str, Any], *, use_apis: bool = True
) -> dict[str, Any]:
    """Try the cascade for one candidate. Returns the ledger row; never raises on failure."""
    locations, oa_status = plan_locations(fetcher, candidate, use_apis=use_apis)
    robots = {h: n for h, n in fetcher.robots_notes.items() if n != "honoured"}
    attempts: list[dict[str, Any]] = []

    for loc in locations:
        expect = PDF_TYPES if loc.url.lower().endswith(".pdf") else PDF_TYPES + HTML_TYPES
        outcome = fetcher.get(loc.url, expect=expect)
        row = outcome.as_row() | {"provenance": loc.provenance, "version": loc.version}
        attempts.append(row)
        if outcome.ok and outcome.body:
            digest, path = store.store_bytes(outcome.body, _suffix_for(outcome.content_type, loc.url))
            return {
                "candidate_key": candidate["candidate_key"],
                "source_id": candidate.get("source_id"),
                "acquired": True,
                "sha256": digest,
                "stored_at": str(path),
                "url": loc.url,
                "provenance": loc.provenance,
                "version": loc.version,
                "licence": loc.licence,
                "oa_status": loc.oa_status or oa_status,
                "content_type": outcome.content_type,
                "bytes": len(outcome.body),
                "attempts": attempts,
                "failure_class": None,
                "robots_notes": robots,
                "fetched_at": _now(),
            }

    return {
        "candidate_key": candidate["candidate_key"],
        "source_id": candidate.get("source_id"),
        "acquired": False,
        "sha256": None,
        "url": str(candidate.get("url") or ""),
        "oa_status": oa_status,
        "attempts": attempts,
        # The class of the last attempt is the honest headline: it says what stopped us.
        "failure_class": (attempts[-1]["failure_class"] if attempts else net.NOT_FOUND),
        "robots_notes": robots,
        "fetched_at": _now(),
    }


def run(
    candidates: Iterable[dict[str, Any]],
    store: Store,
    fetcher: net.Fetcher,
    *,
    skip_acquired: bool = True,
    use_apis: bool = True,
) -> Iterator[dict[str, Any]]:
    """Acquire every candidate not already held. Idempotent by candidate key."""
    already = {
        key for key, row in store.latest_by("acquisitions.jsonl", "candidate_key").items()
        if row.get("acquired")
    }
    for candidate in candidates:
        if skip_acquired and candidate["candidate_key"] in already:
            continue
        row = acquire_one(fetcher, store, candidate, use_apis=use_apis)
        store.append("acquisitions.jsonl", row)
        yield row


def rate(store: Store) -> dict[str, Any]:
    """Acquisition accounting. This is the figure that gates verdicts."""
    latest = store.latest_by("acquisitions.jsonl", "candidate_key")
    attempted = len(latest)
    acquired = sum(1 for row in latest.values() if row.get("acquired"))
    failures: dict[str, int] = {}
    hosts: dict[str, int] = {}
    for row in latest.values():
        if row.get("acquired"):
            continue
        failures[str(row.get("failure_class"))] = failures.get(str(row.get("failure_class")), 0) + 1
        host = net.host_of(str(row.get("url") or ""))
        if host:
            hosts[host] = hosts.get(host, 0) + 1
    return {
        "attempted": attempted,
        "acquired": acquired,
        "rate": (acquired / attempted) if attempted else 0.0,
        "failures_by_class": dict(sorted(failures.items(), key=lambda kv: -kv[1])),
        "failures_by_host": dict(sorted(hosts.items(), key=lambda kv: -kv[1])),
    }
