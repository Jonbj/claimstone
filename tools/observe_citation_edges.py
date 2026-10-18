#!/usr/bin/env python
"""Citation edges around the candidates we hold, from OpenCitations, and titles for the works they point to (D143).

Default is a preview that makes no request. `--execute` is for after the operator approved the exact plan:
`api.opencitations.net` (two requests per seed: who cites it, what it cites), then `api.openalex.org` (one request per
50 suggested DOIs, only to learn titles), ceilings given on the command line and checked first, USD 0. A seed observed
within `--min-age-days` is not asked again. A refusal stops the run. Nothing is written to `candidates.jsonl`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import net, snowball  # noqa: E402
from claimstone.request_log import RecordingFetcher  # noqa: E402
from claimstone.store import Store  # noqa: E402
from tools.complete_question_round import load_environment  # noqa: E402

HOSTS = frozenset({"api.opencitations.net", "api.openalex.org"})
CAMPAIGN = "citation-edges-v1"
# Its own campaign: the recording fetcher counts physical requests per campaign, so the titles must not inherit the
# edge requests already spent.
TITLES_CAMPAIGN = "citation-titles-v1"
TITLE_BATCH = 50


def get_list(recorded, url: str):
    """OpenCitations answers a JSON **array**, which `get_json` refuses (it wants an object): found on the first
    live run (D143). Fetch the bytes and read the array here; anything that is not a list is a failed answer."""
    outcome = recorded.get(url, as_json=True)
    if not outcome.ok or not outcome.body:
        return None, outcome
    try:
        payload = json.loads(outcome.body.decode("utf-8", "replace"))
    except ValueError:
        return None, outcome
    return (payload if isinstance(payload, list) else None), outcome


def reparse_from_raw(project: str, *, store_base: str = "store") -> int:
    """Rebuild edge rows from the bytes a first run already stored, with no request. Append-only: the corrected
    row supersedes the failed one. Returns how many rows were written."""
    store = Store(project, base=store_base)
    latest = snowball.latest_edges(store)
    written = 0
    for row in store.read("requests.jsonl"):
        if row.get("campaign") != CAMPAIGN or row.get("event") != "validated_response" or not row.get("raw_path"):
            continue
        url = str(row.get("url") or "")
        direction = snowball.CITED_BY if "/citations/" in url else snowball.CITES if "/references/" in url else None
        key = row.get("candidate_key")
        if direction is None or not key:
            continue
        held = latest.get((key, direction))
        if held and held.get("ok"):
            continue
        try:
            payload = json.loads(Path(row["raw_path"]).read_bytes().decode("utf-8", "replace"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, list):
            continue
        doi = key[4:] if str(key).startswith("doi:") else ""
        edges, truncated = snowball.parse_edges(payload, doi, direction)
        store.append(snowball.EDGES, snowball.edge_row(key, doi, direction, edges, ok=True, truncated=truncated,
                                                        campaign=CAMPAIGN) | {"reparsed_from_raw": row["raw_sha256"]})
        written += 1
    return written


def seeds(store: Store) -> list[dict]:
    held: dict[str, dict] = {}
    for row in store.read("candidates.jsonl"):
        key = row.get("candidate_key") or ""
        if key.startswith("doi:"):
            held[key] = row
    return [{"candidate_key": k, "doi": k[4:]} for k in held]


def pending(store: Store, min_age_days: int, now: dt.datetime) -> list[tuple[dict, str]]:
    try:
        seen = snowball.latest_edges(store)
    except FileNotFoundError:
        seen = {}
    out = []
    for seed in seeds(store):
        for direction in (snowball.CITED_BY, snowball.CITES):
            last = seen.get((seed["candidate_key"], direction))
            if last and last.get("ok") and now - dt.datetime.fromisoformat(last["observed_at"]) < dt.timedelta(days=min_age_days):
                continue
            out.append((seed, direction))
    return out


def titles_url(dois: list[str]) -> str:
    return "https://api.openalex.org/works?" + urllib.parse.urlencode({
        "filter": "doi:" + "|".join(dois), "per-page": TITLE_BATCH, "mailto": net.contact_email(),
        "select": "doi,title,publication_year,primary_location"})


def run(project: str, *, execute: bool = False, max_seeds: int = 10, min_links: int = 2, min_age_days: int = 14,
        store_base: str = "store", fetcher=None, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    store = Store(project, base=store_base)
    todo = pending(store, min_age_days, now)
    seed_keys = {s["candidate_key"] for s, _ in todo}
    summary = {"campaign": CAMPAIGN, "hosts": sorted(HOSTS), "seeds_pending": len(seed_keys), "max_seeds": max_seeds,
               "edge_requests": len(todo), "usd": 0}
    if len(seed_keys) > max_seeds:
        summary["note"] = f"{len(seed_keys)} seeds exceed the approved {max_seeds}; narrow the plan or raise the ceiling"
        if execute:
            raise ValueError(summary["note"])
    if not execute:
        return summary
    fetcher = fetcher or net.Fetcher(allowed_hosts=HOSTS, enforce_global_addresses=True,
                                     max_physical_requests=len(todo) + 12)
    done, stopped = 0, None
    for seed, direction in todo:
        recorded = RecordingFetcher(fetcher, store, purpose="citation_edges", campaign=CAMPAIGN,
                                    candidate_key=seed["candidate_key"])
        payload, outcome = get_list(recorded, snowball.edges_url(seed["doi"], direction))
        # OpenCitations answers an unknown DOI with an empty list: that is "no edges known", not a failure.
        ok = payload is not None
        edges, truncated = snowball.parse_edges(payload, seed["doi"], direction) if ok else ([], False)
        store.append(snowball.EDGES, snowball.edge_row(seed["candidate_key"], seed["doi"], direction, edges,
                                                        ok=ok, truncated=truncated, campaign=CAMPAIGN))
        done += 1
        if outcome.status in (403, 429) or outcome.failure_class in (
                "ROBOTS_DISALLOWED", "ROBOTS_UNREACHABLE", "DOMAIN_BUDGET_EXHAUSTED", "REQUEST_LIMIT_REACHED"):
            stopped = {"status": outcome.status, "failure_class": outcome.failure_class}
            break
    summary["edge_requests_made"] = done
    if stopped:
        summary["stopped_on_refusal"] = stopped
        return summary
    wanted = [s["doi"] for s in snowball.suggestions(store, min_links=min_links, limit=TITLE_BATCH)
              if not s.get("title")]
    if wanted:
        recorded = RecordingFetcher(fetcher, store, purpose="citation_titles", campaign=TITLES_CAMPAIGN)
        payload, outcome = recorded.get_json(titles_url(wanted))
        for work in ((payload or {}).get("results") or []) if outcome.ok and isinstance(payload, dict) else []:
            from claimstone import ids
            doi = ids.normalize_doi(work.get("doi"))
            if not doi:
                continue
            source = ((work.get("primary_location") or {}).get("source") or {})
            store.append(snowball.TITLES, {"doi": doi, "title": work.get("title"), "year": work.get("publication_year"),
                                           "venue": source.get("display_name"), "campaign": CAMPAIGN,
                                           "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")})
        summary["title_request_ok"] = bool(outcome.ok)
    summary["suggestions"] = len(snowball.suggestions(store, min_links=min_links))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("project")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-seeds", type=int, default=10)
    parser.add_argument("--min-links", type=int, default=2)
    parser.add_argument("--min-age-days", type=int, default=14)
    parser.add_argument("--report", action="store_true", help="print the suggestions; no request")
    parser.add_argument("--reparse", action="store_true", help="rebuild edge rows from stored bytes; no request")
    args = parser.parse_args()
    if args.report:
        print(json.dumps(snowball.suggestions(Store(args.project), min_links=args.min_links), indent=1, ensure_ascii=False))
        return
    if args.reparse:
        print(json.dumps({"rows_rebuilt": reparse_from_raw(args.project)}))
        return
    load_environment(Path(".env"))
    print(json.dumps(run(args.project, execute=args.execute, max_seeds=args.max_seeds,
                         min_links=args.min_links, min_age_days=args.min_age_days), indent=1))


if __name__ == "__main__":
    main()
