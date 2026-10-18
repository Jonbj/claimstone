#!/usr/bin/env python
"""Record what Crossref says about each candidate DOI: notices, licences, text-mining links (D142).

Default is a preview that makes no request. `--execute` is for after the operator approved the exact plan: one
host (`api.crossref.org`), two requests per DOI (the work, and the records that update it), a ceiling given on the
command line and checked against the count before anything is sent, USD 0. A candidate observed within
`--min-age-days` is not asked again. A refusal (403, 429, robots, budget) stops the run.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import net, status  # noqa: E402
from claimstone.request_log import RecordingFetcher  # noqa: E402
from claimstone.store import Store  # noqa: E402
from tools.complete_question_round import load_environment  # noqa: E402

HOSTS = frozenset({"api.crossref.org"})
CAMPAIGN = "status-observation-v1"


def doi_candidates(store: Store) -> list[dict]:
    rows: dict[str, dict] = {}
    for row in store.read("candidates.jsonl"):
        key = row.get("candidate_key") or ""
        if key.startswith("doi:"):
            rows[key] = row
    return [{"candidate_key": k, "doi": k[4:]} for k in rows]


def pending(store: Store, min_age_days: int, now: dt.datetime) -> list[dict]:
    seen = status.latest(store)
    out = []
    for target in doi_candidates(store):
        last = seen.get(target["candidate_key"])
        if last and last.get("state") != status.LOOKUP_FAILED:
            age = now - dt.datetime.fromisoformat(last["observed_at"])
            if age < dt.timedelta(days=min_age_days):
                continue
        out.append(target)
    return out


def run(project: str, *, execute: bool = False, max_dois: int = 10, min_age_days: int = 7,
        store_base: str = "store", fetcher=None, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    store = Store(project, base=store_base)
    todo = pending(store, min_age_days, now)
    summary = {"campaign": CAMPAIGN, "host": "api.crossref.org", "dois_pending": len(todo),
               "max_dois": max_dois, "requests": 2 * min(len(todo), max_dois) if todo else 0, "usd": 0}
    if len(todo) > max_dois:
        summary["note"] = f"{len(todo)} pending exceed the approved {max_dois}; narrow the plan or raise the ceiling"
        if execute:
            raise ValueError(summary["note"])
    if not execute or not todo:
        return summary
    fetcher = fetcher or net.Fetcher(allowed_hosts=HOSTS, enforce_global_addresses=True,
                                     max_physical_requests=2 * max_dois + 2)
    done = 0
    for target in todo:
        recorded = RecordingFetcher(fetcher, store, purpose="status_observation", campaign=CAMPAIGN,
                                    candidate_key=target["candidate_key"])
        work, work_outcome = recorded.get_json(status.work_url(target["doi"]))
        refused = work_outcome.status in (403, 429) or work_outcome.failure_class in (
            "ROBOTS_DISALLOWED", "ROBOTS_UNREACHABLE", "DOMAIN_BUDGET_EXHAUSTED", "REQUEST_LIMIT_REACHED")
        updates, updates_outcome = (None, work_outcome) if refused else recorded.get_json(
            status.updates_url(target["doi"]))
        # A 404 on the work is a fact about Crossref's coverage of that DOI, not a failed lookup.
        work_ok = work_outcome.ok or work_outcome.status == 404
        row = status.observation(target["candidate_key"], target["doi"], work=work, updates=updates,
                                 work_ok=work_ok, updates_ok=updates_outcome.ok, campaign=CAMPAIGN)
        store.append(status.LEDGER, row)
        done += 1
        if refused or updates_outcome.status in (403, 429):
            summary["stopped_on_refusal"] = {"status": work_outcome.status or updates_outcome.status,
                                             "failure_class": work_outcome.failure_class or updates_outcome.failure_class}
            break
    summary["dois_observed"] = done
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("project")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-dois", type=int, default=10)
    parser.add_argument("--min-age-days", type=int, default=7)
    args = parser.parse_args()
    load_environment(Path(".env"))
    print(json.dumps(run(args.project, execute=args.execute, max_dois=args.max_dois,
                         min_age_days=args.min_age_days), indent=1))


if __name__ == "__main__":
    main()
