#!/usr/bin/env python
"""Phase 1 of the full-text route measurement (issue #14): metadata only, no document is downloaded.

For each candidate that has a DOI, ask two services whether a legal full text exists and where:

* Europe PMC REST (`www.ebi.ac.uk`): is it open access, in Europe PMC, in PMC, with a PDF, under what licence;
* OpenAlex (`api.openalex.org`): the open-access status, the alternative locations and their licences, and
  whether OpenAlex holds a cached copy.

The denominator is the project's candidates as they stand, frozen by the run's own count. The tool never edits a
production stage ledger: it appends to `audits/fulltext-route-probe/v1/outcomes.jsonl` and, through
`RecordingFetcher`, to `requests.jsonl`. Default is a preview that makes no request. `--execute` is for after the
operator approved the exact plan: two hosts, at most 20 data requests (one per DOI per service) plus the robots.txt
of each host, a hard physical ceiling of 22, USD 0.

A refusal by a host (403, 429, robots, budget) stops the run; the failure budget is not reset to continue.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import net  # noqa: E402
from claimstone.request_log import RecordingFetcher  # noqa: E402
from claimstone.store import Store  # noqa: E402
from tools.complete_question_round import load_environment  # noqa: E402

LEDGER = "audits/fulltext-route-probe/v1/outcomes.jsonl"
HOSTS = frozenset({"www.ebi.ac.uk", "api.openalex.org"})
MAX_DATA_REQUESTS = 20
MAX_PHYSICAL = 22
CAMPAIGN = "fulltext-route-probe-v1"
OPENALEX_SELECT = ("id,doi,open_access,best_oa_location,locations,has_content,primary_location")


def europe_pmc_url(doi: str) -> str:
    query = urllib.parse.quote(f'DOI:"{doi}"')
    return ("https://www.ebi.ac.uk/europepmc/webservices/rest/search"
            f"?query={query}&resultType=core&format=json&pageSize=2")


def openalex_url(doi: str) -> str:
    return (f"https://api.openalex.org/works/doi:{urllib.parse.quote(doi, safe='/')}"
            f"?select={OPENALEX_SELECT}")


def summarize_europe_pmc(payload: dict | None) -> dict:
    results = ((payload or {}).get("resultList") or {}).get("result") or []
    if not results:
        return {"found": False}
    top = results[0]
    return {"found": True, "hits": len(results), "pmcid": top.get("pmcid"),
            "isOpenAccess": top.get("isOpenAccess"), "inEPMC": top.get("inEPMC"),
            "inPMC": top.get("inPMC"), "hasPDF": top.get("hasPDF"),
            "license": top.get("license"), "fullTextUrlList": [
                {k: u.get(k) for k in ("availability", "documentStyle", "site", "url")}
                for u in ((top.get("fullTextUrlList") or {}).get("fullTextUrl") or [])][:8]}


def summarize_openalex(payload: dict | None) -> dict:
    if not payload:
        return {"found": False}
    oa = payload.get("open_access") or {}
    locations = [{"is_oa": loc.get("is_oa"), "version": loc.get("version"), "license": loc.get("license"),
                  "landing_page_url": loc.get("landing_page_url"), "pdf_url": loc.get("pdf_url"),
                  "source": (loc.get("source") or {}).get("display_name")}
                 for loc in (payload.get("locations") or [])][:8]
    return {"found": True, "is_oa": oa.get("is_oa"), "oa_status": oa.get("oa_status"),
            "oa_url": oa.get("oa_url"), "has_content": payload.get("has_content"),
            "best_oa_location": payload.get("best_oa_location"), "locations": locations}


def candidates_with_doi(store: Store) -> list[dict]:
    rows: dict[str, dict] = {}
    for row in store.read("candidates.jsonl"):
        key = row.get("candidate_key") or ""
        if key.startswith("doi:"):
            rows[key] = row
    return [{"candidate_key": k, "doi": k[4:], "title": r.get("title")} for k, r in rows.items()]


def run(project: str, *, execute: bool = False, store_base: str = "store", fetcher=None) -> dict:
    store = Store(project, base=store_base)
    targets = candidates_with_doi(store)
    prior = {(r["candidate_key"], r["service"]) for r in store.read(LEDGER)} if store.path(LEDGER).exists() else set()
    pending = [(t, s) for t in targets for s in ("europe_pmc", "openalex") if (t["candidate_key"], s) not in prior]
    if len(pending) > MAX_DATA_REQUESTS:
        raise ValueError(f"{len(pending)} requests exceed the approved {MAX_DATA_REQUESTS}")
    summary = {"campaign": CAMPAIGN, "candidates": len(targets), "pending_requests": len(pending),
               "hosts": sorted(HOSTS), "max_data_requests": MAX_DATA_REQUESTS,
               "max_physical_requests": MAX_PHYSICAL, "usd": 0}
    if not execute or not pending:
        return summary
    fetcher = fetcher or net.Fetcher(allowed_hosts=HOSTS, enforce_global_addresses=True,
                                     max_physical_requests=MAX_PHYSICAL)
    done = 0
    for target, service in pending:
        recorded = RecordingFetcher(fetcher, store, purpose="fulltext_route_probe", campaign=CAMPAIGN,
                                    candidate_key=target["candidate_key"])
        url = europe_pmc_url(target["doi"]) if service == "europe_pmc" else openalex_url(target["doi"])
        payload, outcome = recorded.get_json(url)
        result = {"candidate_key": target["candidate_key"], "doi": target["doi"], "service": service,
                  "campaign": CAMPAIGN, "url": url, "http_status": outcome.status,
                  "failure_class": outcome.failure_class,
                  "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                  "summary": (summarize_europe_pmc(payload) if service == "europe_pmc"
                              else summarize_openalex(payload)) if outcome.ok else None}
        store.append(LEDGER, result)
        done += 1
        if (outcome.status in (403, 429) or outcome.failure_class in
                {"ROBOTS_DISALLOWED", "ROBOTS_UNREACHABLE", "DOMAIN_BUDGET_EXHAUSTED", "REQUEST_LIMIT_REACHED"}):
            summary["stopped_on_refusal"] = {"service": service, "failure_class": outcome.failure_class,
                                             "status": outcome.status}
            break
    summary["data_requests_made"] = done
    return summary


def report(project: str, store_base: str = "store") -> list[dict]:
    store = Store(project, base=store_base)
    by: dict[str, dict] = {}
    for row in store.read(LEDGER):
        by.setdefault(row["candidate_key"], {})[row["service"]] = row
    out = []
    for key, services in by.items():
        epmc = (services.get("europe_pmc") or {}).get("summary") or {}
        oal = (services.get("openalex") or {}).get("summary") or {}
        out.append({"candidate_key": key,
                    "europe_pmc": {k: epmc.get(k) for k in ("found", "pmcid", "isOpenAccess", "inEPMC", "hasPDF", "license")},
                    "openalex": {"is_oa": oal.get("is_oa"), "oa_status": oal.get("oa_status"),
                                 "has_content": oal.get("has_content"),
                                 "oa_locations": [loc for loc in oal.get("locations") or [] if loc.get("is_oa")]}})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("project")
    parser.add_argument("--execute", action="store_true", help="make the requests (only after approval)")
    parser.add_argument("--report", action="store_true", help="print the recorded outcomes; no request")
    args = parser.parse_args()
    if args.report:
        print(json.dumps(report(args.project), indent=1, ensure_ascii=False))
        return
    load_environment(Path(".env"))
    print(json.dumps(run(args.project, execute=args.execute), indent=1))


if __name__ == "__main__":
    main()
