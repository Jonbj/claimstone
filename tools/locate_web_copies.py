#!/usr/bin/env python
"""Look for open-web copies of works we found but could not read, and record the leads (D145, issue #4).

For each candidate not yet obtained, one exact-title web search through the Brave Search API (a second, bare-title
query only when the first returned nothing). Every result is recorded in `web_locator.jsonl` with the project's host
policy's decision on it. **Nothing is downloaded and nothing is added to `candidates.jsonl`**: the portal shows the
leads and a person may open one and upload the PDF; Claimstone fetches one only when the project declared
`web_locator` *and* an authorised plan named that exact host.

The host policy comes from the project's `sources.yaml: web_locator`. A project that has not declared one can pass
`--policy-file` for an exploratory run; that policy is recorded by digest, labelled `file`, and never makes
Claimstone fetch anything (only a declared project policy does).

Default is a preview that makes no request. `--execute` is for after the operator approved the exact plan: one host
(`api.search.brave.com`), at most two requests per candidate, a candidate ceiling checked first, a hard physical ceiling,
and the provider's own price which this tool cannot know (the operator confirms it holds the plan they want).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yaml  # noqa: E402

from claimstone import admissibility, net, web_locator  # noqa: E402
from claimstone.config import load_project  # noqa: E402
from claimstone.request_log import RecordingFetcher  # noqa: E402
from claimstone.store import Store  # noqa: E402
from tools.complete_question_round import load_environment  # noqa: E402

HOSTS = frozenset({"api.search.brave.com"})
CAMPAIGN = "web-locator-v1"


def unobtained(store: Store) -> list[dict]:
    held = {key for key, row in admissibility.collapse(store).items() if row.get("acquired")}
    latest = store.latest_by("candidates.jsonl", "candidate_key")
    return [row for key, row in latest.items() if key not in held and row.get("title")]


def pending(store: Store) -> list[dict]:
    seen = web_locator.latest_by_candidate(store)
    return [c for c in unobtained(store) if not any(r.get("ok") for r in seen.get(str(c["candidate_key"]), []))]


def resolve_policy(project, policy_file: str | None) -> tuple[dict, str]:
    if project.web_locator_declared:
        return project.web_locator, "project"
    if policy_file:
        raw = yaml.safe_load(Path(policy_file).read_text()) or {}
        return web_locator.validate_policy(raw.get("web_locator", raw)), "file"
    raise SystemExit("this project declares no web_locator policy: add one to sources.yaml or pass --policy-file")


def run(project_name: str, *, execute: bool = False, max_candidates: int = 10, policy_file: str | None = None,
        store_base: str = "store", fetcher=None, project=None) -> dict:
    project = project or load_project(project_name)
    policy, source = resolve_policy(project, policy_file)
    store = Store(project.name, base=store_base)
    todo = pending(store)
    summary = {"campaign": CAMPAIGN, "host": "api.search.brave.com", "policy_source": source,
               "policy_sha256": web_locator.policy_digest(policy), "candidates_pending": len(todo),
               "max_candidates": max_candidates, "requests_min": min(len(todo), max_candidates),
               "requests_max": 2 * min(len(todo), max_candidates)}
    if len(todo) > max_candidates:
        summary["note"] = f"{len(todo)} pending exceed the approved {max_candidates}; narrow the plan or raise the ceiling"
        if execute:
            raise ValueError(summary["note"])
    if not execute or not todo:
        return summary
    fetcher = fetcher or net.Fetcher(allowed_hosts=HOSTS, enforce_global_addresses=True,
                                     excluded_hosts=frozenset(project.excluded_hosts),
                                     max_physical_requests=2 * max_candidates + 2)
    made, stopped = 0, None
    for candidate in todo:
        recorded = RecordingFetcher(fetcher, store, purpose="web_locator", campaign=CAMPAIGN,
                                    candidate_key=candidate["candidate_key"])
        for query in web_locator.queries_for(candidate):
            payload, outcome = recorded.get_json(web_locator.search_url(query, int(policy.get("max_results", 5))))
            made += 1
            results = web_locator.parse_results(payload) if outcome.ok else []
            store.append(web_locator.LEDGER, web_locator.observation(
                candidate, query, results, policy, project.excluded_hosts, ok=outcome.ok,
                failure_class=outcome.failure_class, policy_source=source, campaign=CAMPAIGN))
            if outcome.status in (403, 429) or outcome.failure_class in (
                    "ROBOTS_DISALLOWED", "ROBOTS_UNREACHABLE", "DOMAIN_BUDGET_EXHAUSTED", "REQUEST_LIMIT_REACHED"):
                stopped = {"status": outcome.status, "failure_class": outcome.failure_class}
                break
            if results:  # the second, bare-title query is only for a first one that returned nothing
                break
        if stopped:
            break
    summary["requests_made"] = made
    if stopped:
        summary["stopped_on_refusal"] = stopped
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("project")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-candidates", type=int, default=10)
    parser.add_argument("--policy-file")
    args = parser.parse_args()
    load_environment(Path(".env"))
    print(json.dumps(run(args.project, execute=args.execute, max_candidates=args.max_candidates,
                         policy_file=args.policy_file), indent=1))


if __name__ == "__main__":
    main()
