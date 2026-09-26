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
import urllib.parse
from typing import Any, Iterator

from claimstone import ids, net
from claimstone.store import sha256_text


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
) -> dict[str, Any]:
    doi = ids.normalize_doi(doi)
    return {
        "candidate_key": ids.candidate_key(doi=doi, title=title, url=url),
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


def search_openalex(
    fetcher: net.FetcherLike, term: str, topic_id: str, *, per_page: int = 25
) -> Iterator[dict[str, Any]]:
    email = net.contact_email()
    url = (
        "https://api.openalex.org/works?"
        + urllib.parse.urlencode(
            {
                "search": term,
                "per-page": per_page,
                "mailto": email,
                "select": "id,doi,title,publication_year,primary_location,open_access,cited_by_count",
            }
        )
    )
    payload, _ = fetcher.get_json(url)
    for work in (payload or {}).get("results") or []:
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
        )


def search_crossref(
    fetcher: net.FetcherLike, term: str, topic_id: str, *, rows: int = 25
) -> Iterator[dict[str, Any]]:
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(
        {"query.bibliographic": term, "rows": rows, "mailto": net.contact_email(),
         "select": "DOI,title,issued,container-title,URL,type,is-referenced-by-count"}
    )
    payload, _ = fetcher.get_json(url)
    for item in ((payload or {}).get("message") or {}).get("items") or []:
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
        return
    ns = {"a": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(outcome.body)
    except ET.ParseError:
        return
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        link = entry.findtext("a:id", default="", namespaces=ns) or ""
        published = entry.findtext("a:published", default="", namespaces=ns) or ""
        arxiv = ids.arxiv_id(link)
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
        )


SEARCHERS = {"openalex": search_openalex, "crossref": search_crossref, "arxiv": search_arxiv}


def _limit_kw(api: str) -> str:
    return {"openalex": "per_page", "crossref": "rows", "arxiv": "max_results"}[api]
