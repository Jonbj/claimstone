#!/usr/bin/env python3
"""Check two frozen institutional-copy leads without admitting either L02 source.

Default is an offline preview. Execution writes the request ledger and an isolated
audit only. Every redirect host and transfer is bounded by the approved plan.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import fulltext, net
from claimstone.config import load_project
from claimstone.request_log import RecordingFetcher
from claimstone.store import Store
from tools.complete_question_round import load_environment
from tools.recover_l02_durham import CampaignStop, GuardedSession

ROOT = Path("store/alembic-s4-lungo/audits/source-selection/l02-v2")
RAW = Path("store/alembic-s4-lungo/requests/raw")
AUDIT = "audits/source-selection/l02-v2/exclusion-check-copies-2026-10-06/outcomes.jsonl"
EXPECTED_PLAN_SHA256 = "7c72a0a1d95d4ca44eda42d02ce2b00397171de36eb25a8e50c533c51ea045ee"
FROZEN = {
    "selection_scope_sha256": ROOT / "selection-scope.json",
    "packet_sha256": ROOT / "human-reference-packets/b991c6a06218e1778ab93e8550c3e2ee095ac3f7933a2dc55b85fe8182517904.json",
    "ai_screening_sha256": ROOT / "ai-screening-claude-2026-10-05/l02-ai-screening.json",
    "sources_sha256": Path("store/alembic-s4-lungo/audits/source-selection/population-policies/v1-sources-97cea1ebe253343d8c864833b3ecf85d3a2130bccc6706c8219b7d2fb5e4c59d.yaml"),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_plan(path: Path) -> dict:
    if sha(path) != EXPECTED_PLAN_SHA256:
        raise ValueError("plan differs from approved frozen bytes")
    plan = json.loads(path.read_text(encoding="utf-8"))
    if (plan.get("version") != 1 or plan.get("question_id") != "L02"
            or plan.get("project") != "projects/alembic-s4-lungo"
            or plan.get("campaign") != "l02-v2-exclusion-check-institutional-copies-2026-10-06"
            or plan.get("ceilings", {}).get("candidate_copy_requests") != 2
            or len(plan.get("targets", [])) != 2):
        raise ValueError("unexpected campaign scope")
    for field, source in FROZEN.items():
        if sha(source) != plan["frozen_inputs"][field]:
            raise ValueError(f"frozen input changed: {field}")
    ai = json.loads(FROZEN["ai_screening_sha256"].read_text())
    excluded = {r["candidate_key"] for r in ai["cases"] if r["decision"] == "EXCLUDE"}
    expected = {"doi:10.2308/accr-51865": "utoronto.scholaris.ca",
                "doi:10.1080/23322039.2016.1142847": "iris.unimore.it"}
    targets = plan["targets"]
    if {t["candidate_key"]: t["allowed_host"] for t in targets} != expected:
        raise ValueError("targets or hosts differ from approved pair")
    for target in targets:
        if target["candidate_key"] not in excluded:
            raise ValueError("target is not an AI provisional exclusion")
        raw = RAW / f'{target["cached_openalex_sha256"]}.bin'
        if sha(raw) != target["cached_openalex_sha256"]:
            raise ValueError("cached OpenAlex bytes changed")
        metadata = json.loads(raw.read_text())
        if metadata.get("doi", "").lower().removeprefix("https://doi.org/") != target["candidate_key"][4:]:
            raise ValueError("cached metadata DOI differs")
        if target["copy_url"] not in [x.get("pdf_url") for x in metadata.get("locations", [])]:
            raise ValueError("copy URL absent from cached metadata")
        if net.host_of(target["copy_url"]) != target["allowed_host"]:
            raise ValueError("copy host differs")
    return plan


def second_target_resume_allowed(plan: dict, prior: list[dict], request_rows: list[dict]) -> bool:
    """Resume only the untouched second copy after a redirect spent the local transfer cap."""
    first, second = plan["targets"]
    latest = {row.get("candidate_key"): row for row in prior}
    if (len(prior) != 2 or set(latest) != {first["candidate_key"], second["candidate_key"]}
            or latest[first["candidate_key"]].get("status") != "COPY_REQUIRES_IDENTITY_REVIEW"
            or latest[second["candidate_key"]].get("status") != "STOPPED_BY_GUARD"
            or latest[second["candidate_key"]].get("stop_reason") != "page/copy transfer ceiling reached"
            or latest[second["candidate_key"]].get("transfers_so_far", {}).get("pages_or_copies") != 2):
        return False
    # A robots response is allowed; no page/copy response, including a refusal,
    # may have been recorded for the second candidate.
    return not any(row.get("candidate_key") == second["candidate_key"]
                   and row.get("event") != "robots" for row in request_rows)


def run(path: Path, *, execute: bool = False, resume_second: bool = False) -> dict:
    plan = validate_plan(path)
    project = load_project(plan["project"])
    store = Store(project.name)
    prior_rows = [r for r in store.read(AUDIT) if r.get("campaign") == plan["campaign"]]
    prior = {r["candidate_key"]: r for r in prior_rows}
    if resume_second:
        request_rows = [r for r in store.read("requests.jsonl")
                        if r.get("campaign") == plan["campaign"]]
        if not second_target_resume_allowed(plan, prior_rows, request_rows):
            raise ValueError("second copy resume refused: prior state includes an attempt or changed stop")
        pending = [plan["targets"][1]]
    else:
        pending = [t for t in plan["targets"] if t["candidate_key"] not in prior]
    summary = {"campaign": plan["campaign"], "plan_sha256": sha(path),
               "selected": len(plan["targets"]), "completed": len(prior),
               "pending": [t["candidate_key"] for t in pending]}
    if not execute or not pending:
        return summary | {"status": "PREVIEW_ONLY" if not execute else "ALREADY_ATTEMPTED"}

    guard = GuardedSession({t["allowed_host"] for t in pending},
                           max_pages=2, max_robots=4)
    transport = net.Fetcher(excluded_hosts=frozenset(project.excluded_hosts))
    transport._session = guard
    for target in pending:
        row = {"campaign": plan["campaign"], "plan_sha256": sha(path),
               "candidate_key": target["candidate_key"], "source_class": "UNCLASSIFIED",
               "adopted": False, "copy_url": target["copy_url"],
               "identity_status": "NOT_VERIFIED", "status": "COPY_FAILED"}
        recorded = RecordingFetcher(transport, store, purpose="l02_exclusion_copy_check",
                                    campaign=plan["campaign"], candidate_key=target["candidate_key"],
                                    source_class="UNCLASSIFIED", provenance="cached_openalex_institutional")
        try:
            outcome = recorded.get(target["copy_url"], expect=("application/pdf",))
            row.update(http_status=outcome.status, failure_class=outcome.failure_class,
                       final_url=outcome.url)
            if outcome.ok and outcome.body:
                row["raw_sha256"] = hashlib.sha256(outcome.body).hexdigest()
                row["gate"] = fulltext.classify(outcome.body, outcome.content_type, outcome.url).as_row(
                    fulltext.DEFAULT_THRESHOLDS)
                row["status"] = "COPY_REQUIRES_IDENTITY_REVIEW"
        except CampaignStop as exc:
            row["status"] = "STOPPED_BY_GUARD"
            row["stop_reason"] = str(exc)
        row["transfers_so_far"] = {"pages_or_copies": guard.pages, "robots": guard.robots}
        row["recorded_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        store.append(AUDIT, row)
    return summary | {"status": "EXECUTED", "outcomes": [r for r in store.read(AUDIT)
                                                if r.get("campaign") == plan["campaign"]]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume-second", action="store_true",
                        help="one untouched second target after the first copy redirected locally")
    args = parser.parse_args()
    if args.execute:
        load_environment(Path(".env"))
    print(json.dumps(run(args.plan, execute=args.execute,
                         resume_second=args.resume_second), indent=2))


if __name__ == "__main__":
    main()
