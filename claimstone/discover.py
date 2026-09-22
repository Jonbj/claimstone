"""Stage 1 — discover: topics become candidates.

Deterministic HTTP against scholarly metadata APIs. No model is involved: a model adds
nothing to a keyword query and would make the round irreproducible. Every candidate records
the hash of the query that found it and the channel it came through, because completeness
is later estimated by comparing two *independent* channels — keyword search here, and
citations extracted from acquired texts in stage 3.
"""

from __future__ import annotations

import datetime as _dt
import urllib.parse
from typing import Any, Iterable, Iterator

from claimstone import ids, net
from claimstone.config import Project
from claimstone.store import Store, sha256_text

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
    fetcher: net.Fetcher, term: str, topic_id: str, *, per_page: int = 25
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
            source_api="openalex",
            query=term,
            topic_id=topic_id,
            channel=CHANNEL_KEYWORD,
            is_oa=(work.get("open_access") or {}).get("is_oa"),
            citations=work.get("cited_by_count"),
        )


def search_crossref(
    fetcher: net.Fetcher, term: str, topic_id: str, *, rows: int = 25
) -> Iterator[dict[str, Any]]:
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(
        {"query.bibliographic": term, "rows": rows, "mailto": net.contact_email(),
         "select": "DOI,title,issued,container-title,URL,is-referenced-by-count"}
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
            source_api="crossref",
            query=term,
            topic_id=topic_id,
            channel=CHANNEL_KEYWORD,
            citations=item.get("is-referenced-by-count"),
        )


def search_arxiv(
    fetcher: net.Fetcher, term: str, topic_id: str, *, max_results: int = 25
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
            source_api="arxiv",
            query=term,
            topic_id=topic_id,
            channel=CHANNEL_KEYWORD,
            is_oa=True,
        )


SEARCHERS = {"openalex": search_openalex, "crossref": search_crossref, "arxiv": search_arxiv}


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


def _limit_kw(api: str) -> str:
    return {"openalex": "per_page", "crossref": "rows", "arxiv": "max_results"}[api]


def import_manifest(
    store: Store, tsv_path: str, *, class_of: dict[str, str] | None = None
) -> dict[str, Any]:
    """Seed candidates from an existing curated manifest (source_id, class, format, url, title).

    This exists so acquisition can be measured against a real frozen corpus rather than a
    fresh search: the point of the first milestone is whether the acquisition rate moves on
    the manifest that produced 0.42, holding the source list constant.
    """
    import csv
    import pathlib

    known = set(store.latest_by("candidates.jsonl", "candidate_key"))
    added = 0
    rows = 0
    with pathlib.Path(tsv_path).open(encoding="utf-8") as handle:
        for entry in csv.DictReader(handle, delimiter="\t"):
            url = (entry.get("url") or "").strip()
            title = (entry.get("title") or "").strip()
            if not url and not title:
                continue
            rows += 1
            row = _row(
                title=title,
                url=url,
                doi=ids.normalize_doi(url),
                year=None,
                venue="",
                source_api="manifest",
                query=tsv_path,
                topic_id="",
                channel=CHANNEL_KEYWORD,
                extra={
                    "source_id": (entry.get("source_id") or "").strip(),
                    "source_class": (class_of or {}).get(
                        (entry.get("class") or "").strip(), (entry.get("class") or "").strip()
                    ),
                    "declared_format": (entry.get("format") or "").strip(),
                },
            )
            if row["candidate_key"] in known:
                continue
            known.add(row["candidate_key"])
            store.append("candidates.jsonl", row)
            added += 1
    return {"rows": rows, "new": added, "total": len(known)}
