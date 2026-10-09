"""The three scholarly-metadata APIs, and the candidate row they produce.

Split out of `discover` because this is the part that ages: an API renames a field or changes its
envelope and nothing else in the pipeline moves. A saved payload exercises all three without a store,
a ledger or a socket.

Every row records the query that found it and the channel it came through, because completeness is
later estimated by comparing two *independent* channels — keyword search here, and citations
extracted from acquired texts in stage 3.
"""

from __future__ import annotations

import datetime as _dt
import re
import urllib.parse
from typing import Any, Iterator

from claimstone import ids, net
from claimstone.store import sha256_text


DISCOVERY_VERSION = 4


class SearchError(ValueError):
    def __init__(self, failure, detail=''):
        super().__init__(detail or failure)
        self.failure = failure


def records(payload, outcome, path):
    if not outcome.ok:
        raise SearchError(outcome.failure_class or 'LOOKUP_FAILED', outcome.detail)
    current = payload
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise SearchError('INVALID_SEARCH_RESPONSE', f'missing {key}')
        current = current[key]
    if not isinstance(current, list) or any(not isinstance(row, dict) for row in current):
        raise SearchError('INVALID_SEARCH_RESPONSE', 'expected a list of records')
    return current


CHANNEL_KEYWORD = "keyword"
CHANNEL_CITATION = "citation"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _row(
    *,
    title: str,
    url: str,
    doi: str | None,
    year: int | None,
    venue: str,
    venue_type: str,
    source_api: str,
    query: str,
    topic_id: str,
    channel: str,
    is_oa: bool | None = None,
    citations: int | None = None,
    extra: dict[str, Any] | None = None,
    candidate_key: str | None = None,
) -> dict[str, Any]:
    doi = ids.normalize_doi(doi)
    return {
        # An override exists for one caller. The citation channel keys on the reference stage 3 gave
        # it, because `candidate_key` prefers a DOI and resolution *adds* one — so a derived key would
        # move, and the same work would become two candidates with nothing superseding either.
        "candidate_key": candidate_key or ids.candidate_key(doi=doi, title=title, url=url),
        "title": title,
        "url": url,
        "doi": doi,
        "year": year,
        "venue": venue,
        # What the API called this venue. Only meaningful alongside source_api: "journal" from
        # OpenAlex and "journal-article" from Crossref are different vocabularies.
        "venue_type": venue_type,
        "source_api": source_api,
        "query": query,
        "query_hash": sha256_text(f"{source_api}|{query}")[:16],
        "topic_id": topic_id,
        "channel": channel,
        "is_oa": is_oa,
        "citations": citations,
        "found_at": _now(),
        **(extra or {}),
    }


OPENALEX_SEARCH_MODES = frozenset({'search', 'search.title_abstract_keywords'})


def openalex_query_url(term: str, *, per_page: int = 25, mode: str = 'search',
                       page: int | None = None, cursor: str | None = None) -> str:
    """Build one bounded Work-search URL; default bytes match discovery version 4."""
    if mode not in OPENALEX_SEARCH_MODES or not isinstance(term, str) or not term.strip():
        raise ValueError('unsupported OpenAlex search mode or empty term')
    if type(per_page) is not int or not 1 <= per_page <= 100:
        raise ValueError('OpenAlex per_page must be 1..100')
    if page is not None and cursor is not None:
        raise ValueError('page and cursor cannot be combined')
    if page is not None and (type(page) is not int or page < 1 or page * per_page > 10_000):
        raise ValueError('OpenAlex basic paging cannot exceed 10000 results')
    if cursor is not None and (not isinstance(cursor, str) or not cursor):
        raise ValueError('OpenAlex cursor must be a nonempty string')
    params = {mode: term, 'per-page': per_page, 'mailto': net.contact_email(),
              'select': 'id,doi,title,publication_year,primary_location,open_access,cited_by_count'}
    if page is not None:
        params['page'] = page
    if cursor is not None:
        params['cursor'] = cursor
    return 'https://api.openalex.org/works?' + urllib.parse.urlencode(params)


def search_openalex(
    fetcher: net.FetcherLike, term: str, topic_id: str, *, per_page: int = 25
) -> Iterator[dict[str, Any]]:
    # Keep the frozen discovery-v4 request unchanged. The bounded URL builder
    # above is for separately approved page/strategy probes.
    url = (
        'https://api.openalex.org/works?'
        + urllib.parse.urlencode({
            'search': term,
            'per-page': per_page,
            'mailto': net.contact_email(),
            'select': 'id,doi,title,publication_year,primary_location,open_access,cited_by_count',
        })
    )
    payload, outcome = fetcher.get_json(url)
    for rank, work in enumerate(records(payload, outcome, ("results",)), start=1):
        location = work.get("primary_location") or {}
        source = (location.get("source") or {}) if isinstance(location, dict) else {}
        landing = location.get("pdf_url") or location.get("landing_page_url") or work.get("id")
        yield _row(
            title=str(work.get("title") or "").strip(),
            url=str(landing or ""),
            doi=work.get("doi"),
            year=work.get("publication_year"),
            venue=str(source.get("display_name") or ""),
            # primary_location was already selected whole; this field was simply never read.
            venue_type=str(source.get("type") or ""),
            source_api="openalex",
            query=term,
            topic_id=topic_id,
            channel=CHANNEL_KEYWORD,
            is_oa=(work.get("open_access") or {}).get("is_oa"),
            citations=work.get("cited_by_count"),
            extra={"openalex_work_id": work.get("id"), "query_rank": rank},
        )


def search_crossref(
    fetcher: net.FetcherLike, term: str, topic_id: str, *, rows: int = 25
) -> Iterator[dict[str, Any]]:
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(
        {"query.bibliographic": term, "rows": rows, "mailto": net.contact_email(),
         "select": "DOI,title,issued,container-title,URL,type,is-referenced-by-count"}
    )
    payload, outcome = fetcher.get_json(url)
    for item in records(payload, outcome, ("message", "items")):
        titles = item.get("title") or []
        issued = ((item.get("issued") or {}).get("date-parts") or [[None]])[0]
        containers = item.get("container-title") or []
        yield _row(
            title=str(titles[0] if titles else "").strip(),
            url=str(item.get("URL") or ""),
            doi=item.get("DOI"),
            year=issued[0] if issued else None,
            venue=str(containers[0] if containers else ""),
            venue_type=str(item.get("type") or ""),
            source_api="crossref",
            query=term,
            topic_id=topic_id,
            channel=CHANNEL_KEYWORD,
            citations=item.get("is-referenced-by-count"),
        )


def search_arxiv(
    fetcher: net.FetcherLike, term: str, topic_id: str, *, max_results: int = 25
) -> Iterator[dict[str, Any]]:
    """arXiv returns Atom, not JSON; parsed with the stdlib rather than adding a dependency."""
    import xml.etree.ElementTree as ET

    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": f'all:"{term}"', "max_results": max_results}
    )
    outcome = fetcher.get(url)
    if not outcome.ok or not outcome.body:
        raise SearchError(outcome.failure_class or net.EMPTY, outcome.detail)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(outcome.body)
    except ET.ParseError as exc:
        raise SearchError('INVALID_SEARCH_RESPONSE', str(exc)) from exc
    if root.tag != '{http://www.w3.org/2005/Atom}feed':
        raise SearchError('INVALID_SEARCH_RESPONSE', 'expected an Atom feed')
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        link = entry.findtext("a:id", default="", namespaces=ns) or ""
        published = entry.findtext("a:published", default="", namespaces=ns) or ""
        arxiv = ids.arxiv_id(link)
        path = urllib.parse.urlsplit(link).path
        version_match = (re.search(rf'/{re.escape(arxiv)}v([1-9][0-9]*)$', path)
                         if arxiv else None)
        yield _row(
            title=title,
            url=f"https://arxiv.org/pdf/{arxiv}" if arxiv else link,
            doi=None,
            year=int(published[:4]) if published[:4].isdigit() else None,
            venue="arXiv",
            # Everything on arXiv is a preprint. Saying so lets a project write one rule instead of
            # two, and it is the one venue type that needs no API to report it.
            venue_type="preprint",
            source_api="arxiv",
            query=term,
            topic_id=topic_id,
            channel=CHANNEL_KEYWORD,
            is_oa=True,
            extra={"arxiv_base_id": arxiv,
                   "arxiv_version": (int(version_match.group(1)) if version_match else None)},
        )


SEARCHERS = {"openalex": search_openalex, "crossref": search_crossref, "arxiv": search_arxiv}


def _limit_kw(api: str) -> str:
    return {"openalex": "per_page", "crossref": "rows", "arxiv": "max_results"}[api]


# --- Resolving a reference into something fetchable ----------------------------------------------
#
# Stage 3 extracts a bibliography and resolves nothing, deliberately: 817 references would be 817
# lookups. What no spec said is who resolves them, and the answer is here, because this is the module
# that already knows what an OpenAlex work looks like.
#
# Measured before this existed: the citation channel wrote 37 candidates, all 37 unclassified and 25
# with no URL at all. A reference is a title, sometimes a DOI, and nothing else.

# The floor `resolve_doi_by_title` already uses. A shorter fragment matches many works, and taking the
# first is how a bibliography parsing error becomes a confident citation of the wrong paper.
MIN_TITLE_CHARS = 15

WORK_SELECT = "id,doi,title,publication_year,primary_location,open_access,cited_by_count"

UNRESOLVED = {"doi": None, "title": "", "url": "", "venue": "", "venue_type": "",
              "year": None, "is_oa": None, "citations": None, "api": ""}


def _work_fields(work: dict[str, Any]) -> dict[str, Any]:
    """An OpenAlex work in the shape the keyword channel's rows already carry.

    Same shape on purpose: `classify` then reads a resolved citation candidate through the same
    predicates, and nothing downstream needs to know which channel a row came through.
    """
    location = work.get("primary_location") or {}
    source = (location.get("source") or {}) if isinstance(location, dict) else {}
    return {
        # Which API's vocabulary `venue_type` is in. A resolved row carries it as its `source_api`,
        # because `classify` refuses to read a venue type without knowing whose word it is — and after
        # resolution the word is OpenAlex's, whatever channel found the reference.
        "api": "openalex",
        "doi": ids.normalize_doi(work.get("doi")),
        "title": str(work.get("title") or "").strip(),
        "url": str(location.get("pdf_url") or location.get("landing_page_url")
                   or work.get("id") or ""),
        "venue": str(source.get("display_name") or ""),
        "venue_type": str(source.get("type") or ""),
        "year": work.get("publication_year"),
        "is_oa": (work.get("open_access") or {}).get("is_oa"),
        "citations": work.get("cited_by_count"),
    }


def resolve_work(
    fetcher: net.FetcherLike, *, title: str, doi: str | None = None
) -> dict[str, Any]:
    """A reference's title and optional DOI, into a work. Never into the wrong work.

    `resolution` says which way it went and is recorded on the candidate: `BY_DOI`, `BY_TITLE`,
    `NO_MATCH`, `TITLE_TOO_SHORT`, `LOOKUP_FAILED`. The last two are distinct from `NO_MATCH` because
    the remedies differ — a swallowed request failure looks exactly like a reference that does not
    exist, and only one of those is worth retrying.

    **A title match is exact on the folded title, on both paths.** Including the DOI path: GROBID
    mis-parses a DOI often enough that a confident lookup can return a real, different paper, and
    attaching the wrong work would attribute its claims to a source that never made them. That is
    worse than a candidate stage 2 refuses, so a DOI whose work does not carry the reference's title
    falls back to the title search rather than being believed.
    """
    folded = ids.normalize_title(title)
    if len(folded) < MIN_TITLE_CHARS:
        return {**UNRESOLVED, "resolution": "TITLE_TOO_SHORT"}

    failed = False

    if doi:
        url = (f"https://api.openalex.org/works/doi:{urllib.parse.quote(doi, safe='/.')}?"
               + urllib.parse.urlencode({"mailto": net.contact_email(), "select": WORK_SELECT}))
        payload, outcome = fetcher.get_json(url)
        if isinstance(payload, dict) and payload:
            if ids.normalize_title(payload.get("title")) == folded:
                return {**_work_fields(payload), "resolution": "BY_DOI"}
        elif not outcome.ok:
            failed = True

    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(
        {"search": title, "per-page": 5, "mailto": net.contact_email(), "select": WORK_SELECT}
    )
    payload, outcome = fetcher.get_json(url)
    if payload is None and not outcome.ok:
        return {**UNRESOLVED, "resolution": "LOOKUP_FAILED"}
    for work in (payload or {}).get("results") or []:
        if ids.normalize_title(work.get("title")) == folded:
            return {**_work_fields(work), "resolution": "BY_TITLE"}
    return {**UNRESOLVED, "resolution": "LOOKUP_FAILED" if failed else "NO_MATCH"}
