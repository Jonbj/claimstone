"""Where a legal copy of this source might live, in the order worth trying.

Open access first, always. A publisher that returns 403 is not argued with: Unpaywall and
OpenAlex are asked where a free copy lives and the cascade continues there. A shadow library is
never a location — `excluded_hosts` is enforced in net.Fetcher before any request, and this
module never proposes one.
"""

from __future__ import annotations

import html as _html
import re

import urllib.parse
from dataclasses import dataclass, replace
from typing import Any

from claimstone import ids, net

KNOWN_WALLS = (
    "sciencedirect.com", "onlinelibrary.wiley.com", "link.springer.com",
    "tandfonline.com", "jstor.org", "academic.oup.com", "papers.ssrn.com",
    "journals.sagepub.com", "doi.org",
)

WAYBACK_API = "https://archive.org/wayback/available?url="

# PubMed Central: only the designated service, never the article host.
#
# `pmc.ncbi.nlm.nih.gov/robots.txt` allows `/articles/`, and D35 read that as a sanction to fetch the
# article HTML. It is not: PMC's text-mining terms (read 2026-10-18) name only the PMC Cloud Service,
# OAI-PMH, E-Utilities and BioC API for automated retrieval, and prohibit systematic retrieval through
# any other automated process. Robots permission is not an authorisation. Europe PMC's RESTful service
# is the designated route we can parse, so a PMC article identity is rewritten to its JATS endpoint and
# the article page is never requested (D151). A service failure is a failure, not a fallback.
_PMC_ANY_ARTICLE = re.compile(
    r"^https?://(?:(?:www\.)?ncbi\.nlm\.nih\.gov/pmc|pmc\.ncbi\.nlm\.nih\.gov)/articles/(PMC)?(\d+)/?$", re.I
)
EUROPE_PMC_FULLTEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest"


def europe_pmc_route(url: str) -> str | None:
    """The OA-subset JATS endpoint for an explicit PMC article identity."""
    found = _PMC_ANY_ARTICLE.match(str(url or '').strip())
    return f'{EUROPE_PMC_FULLTEXT}/PMC{found.group(2)}/fullTextXML' if found else None


@dataclass(frozen=True)
class Location:
    """One place a copy might live, and why we believe it."""

    url: str
    provenance: str           # unpaywall | openalex | arxiv | candidate | wayback
    version: str = ""         # publishedVersion | acceptedVersion | submittedVersion
    licence: str | None = None
    oa_status: str | None = None
    host_type: str | None = None


# A file a repository record page links to. Pure and DSpace serve the deposited PDF one link away from
# the page Unpaywall names as the free location, and measured on the pilot the cascade fetched that page,
# refused it correctly as a summary, and stopped — 7 of 25 open-access misses had the file link sitting in
# bytes already on disk. Following it is what "prefer the open-access copy by construction" requires.
_DEPOSITED_FILE = re.compile(
    r"""href=["']([^"']{4,300}?(?:\.pdf|/pdf(?:/|["'])|/download|/bitstreams?/[^"']*|"""
    r"""/ws/files/[^"']*|/files/\d+/[^"']*)[^"']*)["']""",
    re.I | re.X)

# At most this many per page, and no following a followed link. The job is the deposited file, not a
# crawl of the repository — and an unbounded version of this would walk a site map.
MAX_FOLLOWED = 3


def deposited_files(markup: str, page_url: str) -> list[Location]:
    """Files a record page links to, absolute, in the order the page lists them.

    `provenance` says `landing` so the ledger records that this location was not named by any metadata
    API: it was read off a page, which is a weaker warrant and has to be visible as one.
    """
    seen: list[str] = []
    for found in _DEPOSITED_FILE.finditer(markup):
        target = _html.unescape(found.group(1)).strip()
        if target.startswith(("mailto:", "javascript:", "#")):
            continue
        absolute = urllib.parse.urljoin(page_url, target)
        if not absolute.lower().startswith(("http://", "https://")):
            continue
        if absolute == page_url or absolute in seen:
            continue
        seen.append(absolute)
        if len(seen) >= MAX_FOLLOWED:
            break
    return [Location(url=u, provenance="landing") for u in seen]


def unpaywall_locations(fetcher: net.FetcherLike, doi: str) -> tuple[list[Location], str | None]:
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

def openalex_locations(fetcher: net.FetcherLike, doi: str) -> list[Location]:
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

def core_locations(fetcher: net.FetcherLike, doi: str) -> list[Location]:
    """Repository copies CORE holds for this exact DOI (D144). A hit whose DOI differs is not used:
    never the wrong work. Needs `CORE_API_KEY`; without one nothing is asked."""
    import os
    import urllib.parse as _u

    if not os.environ.get("CORE_API_KEY", "").strip():
        return []
    query = _u.urlencode({"q": f'doi:"{doi}"', "limit": 3})
    payload, _ = fetcher.get_json(f"https://api.core.ac.uk/v3/search/works?{query}")
    results = (payload or {}).get("results") if isinstance(payload, dict) else None
    out: list[Location] = []
    wanted = ids.normalize_doi(doi)
    for work in results or []:
        # An unparseable DOI on either side never matches: two `None`s are not the same work.
        if not wanted or not isinstance(work, dict) or ids.normalize_doi(work.get("doi")) != wanted:
            continue
        url = work.get("downloadUrl")
        if not (isinstance(url, str) and url.startswith(("http://", "https://"))):
            continue
        out.append(Location(url=url, provenance="core", host_type="repository"))
    return out


def resolve_doi_by_title(fetcher: net.FetcherLike, title: str) -> str | None:
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


def wayback_location(fetcher: net.FetcherLike, url: str) -> Location | None:
    """The last resort for a source with no DOI: a legal archived snapshot.

    A news page eighteen months old is often dead or behind a wall. `licence` is recorded as
    "unknown" rather than left absent: "nobody wrote it down" and "we did not look" are
    different facts and the ledger must keep them apart.
    """
    if not url:
        return None
    payload, _ = fetcher.get_json(WAYBACK_API + urllib.parse.quote(url, safe=""))
    snapshot = ((payload or {}).get("archived_snapshots") or {}).get("closest") or {}
    if snapshot.get("available") and snapshot.get("url"):
        return Location(str(snapshot["url"]), "wayback", licence="unknown")
    return None


def _preference(loc: Location) -> tuple[int, int]:
    """Format outranks version label.

    A PDF gives the parser a real document, whereas a "publishedVersion" landing page may not
    carry the full text at all. ACA001 in the reference manifest regressed exactly this way:
    Unpaywall's HTML beat a direct PDF.
    """
    format_rank = (0 if loc.url.lower().endswith('.pdf') else
                   1 if loc.url.endswith('/fullTextXML') else 2)
    return (format_rank, _version_rank(loc.version))


def plan(
    fetcher: net.FetcherLike, candidate: dict[str, Any], *, use_apis: bool = True
) -> tuple[list[Location], str | None]:
    """Build the cascade for one candidate, cheapest and most likely first."""
    doi = ids.normalize_doi(candidate.get("doi")) or ids.normalize_doi(candidate.get("url"))
    original = str(candidate.get("url") or "")
    on_a_wall = bool(original) and any(w in net.host_of(original) for w in KNOWN_WALLS)
    oa_status: str | None = None
    locations: list[Location] = []

    # An arXiv identifier is a guaranteed legal full text; try it before anything else.
    arxiv = ids.arxiv_id(original) or ids.arxiv_id(candidate.get("title"))
    if arxiv:
        locations.append(
            Location(f"https://arxiv.org/pdf/{arxiv}", "arxiv", "submittedVersion",
                     oa_status="green")
        )

    if original and not on_a_wall:
        locations.append(Location(original, "candidate"))

    if not doi and use_apis and candidate.get("title"):
        doi = resolve_doi_by_title(fetcher, str(candidate["title"]))

    if doi and use_apis:
        # Both, always, deduped below. `openalex_locations` used to be reachable only `if not upw`, and
        # measured on the pilot that cost nine of eighteen failures: Unpaywall answered with exactly one
        # location whose URL was `doi.org` — the resolver, not a file — and one useless answer suppressed the
        # source that might have had a real address. Five of those nine were `green`, so a repository copy
        # existed. Two polite metadata APIs with a contact address is the right price for not missing it.
        upw, oa_status = unpaywall_locations(fetcher, doi)
        locations.extend(upw)
        locations.extend(openalex_locations(fetcher, doi))
        # CORE only when the plan named its host: an authorised plan that predates it never reaches it,
        # and a blocked call would only add a refusal to the record (D144).
        allowed = getattr(fetcher, "allowed_hosts", None)
        if allowed is not None and "api.core.ac.uk" in allowed:
            locations.extend(core_locations(fetcher, doi))

    # Rewritten before ordering. A PMC article identity becomes the designated Europe PMC JATS
    # endpoint and nothing else: the article host is reachable by robots but is not an authorised
    # route for systematic retrieval, and a forbidden address is dropped rather than demoted
    # (D151). The same rewrite covers a candidate whose own URL is a PMC article page.
    rewritten: list[Location] = []
    for location in locations:
        xml = europe_pmc_route(location.url)
        if xml:
            rewritten.append(replace(location, url=xml, provenance='europe-pmc'))
            continue
        rewritten.append(location)

    # Deduped, and an address that is only the DOI resolver is dropped: it adds nothing over the candidate
    # URL, which is already the DOI, and counting it as an attempt is how nine pilot failures looked as
    # though something had been tried.
    seen: set[str] = set()
    locations = []
    for location in rewritten:
        key = ids.normalize_url(location.url)
        if not key or key in seen:
            continue
        if net.host_of(location.url) == "doi.org" and key != ids.normalize_url(original):
            # A second doi.org address that is not the candidate's own is still just the resolver.
            if not original:
                locations.append(location)
                seen.add(key)
            continue
        seen.add(key)
        locations.append(location)

    ordered = sorted(locations, key=_preference)

    # A known wall is tried last: better a landing page than nothing, but only after every
    # legal open copy has been attempted. It is appended *after* the sort, so no ranking can
    # promote it back up the list — a wall URL ending in .pdf otherwise sorted to the front.
    if on_a_wall:
        ordered.append(Location(original, "candidate"))

    # No DOI and no arXiv id means no open-access infrastructure exists for this source. The
    # archive is the only remaining legal option, and it goes after the live URL.
    if not doi and not arxiv and use_apis:
        snapshot = wayback_location(fetcher, original)
        if snapshot:
            ordered.append(snapshot)

    deduped: list[Location] = []
    seen: set[str] = set()
    for loc in ordered:
        key = ids.normalize_url(loc.url)
        if key and key not in seen:
            seen.add(key)
            deduped.append(loc)
    return deduped, oa_status
