#!/usr/bin/env python3
"""One bounded, recorded Durham-copy campaign for the frozen L02 UK press case.

The default is an offline preview. Execution requires an operator-approved campaign
and writes requests plus an isolated audit only; it never imports a source.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
from urllib.parse import urljoin, urlsplit

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import fulltext, net
from claimstone.config import load_project
from claimstone.request_log import RecordingFetcher
from claimstone.store import Store
from tools.complete_question_round import load_environment

ROOT = Path("store/alembic-s4-lungo/audits/source-selection/l02-v2")
AUDIT = "audits/source-selection/l02-v2/durham-recovery-2026-10-06/outcomes.jsonl"
EXPECTED_PLAN_SHA256 = "cd24c34b62c4f2f541bedbf9797a4978ccd93fc66f569a96fbf43ae51b2a7356"
INPUTS = {
    "selection_scope_sha256": ROOT / "selection-scope.json",
    "packet_sha256": ROOT / "human-reference-packets/b991c6a06218e1778ab93e8550c3e2ee095ac3f7933a2dc55b85fe8182517904.json",
    "ai_screening_sha256": ROOT / "ai-screening-claude-2026-10-05/l02-ai-screening.json",
    "sources_sha256": Path("store/alembic-s4-lungo/audits/source-selection/population-policies/v1-sources-97cea1ebe253343d8c864833b3ecf85d3a2130bccc6706c8219b7d2fb5e4c59d.yaml"),
    "openalex_payload_sha256": Path("store/alembic-s4-lungo/requests/raw/29ba3ca9b2c74e40732983e076c8ee4d74276bbada0c83ad388221f5d7156b04.bin"),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_plan(path: Path) -> dict:
    if sha(path) != EXPECTED_PLAN_SHA256:
        raise ValueError("campaign plan changed from the authorized version")
    plan = json.loads(path.read_text(encoding="utf-8"))
    if (plan.get("version") != 1 or plan.get("candidate_key") != "doi:10.17578/19-1-1"
            or plan.get("project") != "projects/alembic-s4-lungo"
            or plan.get("campaign") != "l02-uk-press-durham-recovery-2026-10-06"
            or set(plan.get("allowed_institutional_hosts", [])) != {
                "dro.dur.ac.uk", "durham-repository.worktribe.com"}
            or plan.get("ceilings", {}).get("landing_page_requests") != 2
            or plan.get("ceilings", {}).get("candidate_copy_requests") != 1):
        raise ValueError("unexpected campaign plan")
    for field, source in INPUTS.items():
        if sha(source) != plan["frozen_inputs"][field]:
            raise ValueError(f"frozen input changed: {field}")
    cached = json.loads(INPUTS["openalex_payload_sha256"].read_text())
    if cached.get("doi", "").lower().removeprefix("https://doi.org/") != plan["candidate_key"][4:]:
        raise ValueError("cached metadata DOI differs from target")
    recorded_urls = {r.get("landing_page_url") for r in cached.get("locations", [])}
    if not set(plan["landing_urls"]) <= recorded_urls:
        raise ValueError("landing URL absent from retained OpenAlex metadata")
    return plan


class CampaignStop(RuntimeError):
    """A guard stopped the next transfer before it was attempted."""


class GuardedSession(requests.Session):
    def __init__(self, hosts: set[str], *, max_pages: int = 3, max_robots: int = 4):
        super().__init__()
        self.hosts = hosts
        self.max_pages = max_pages
        self.max_robots = max_robots
        self.pages = 0
        self.robots = 0

    def get(self, url, **kwargs):
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in self.hosts:
            raise CampaignStop(f"destination outside approved Durham hosts: {parsed.hostname}")
        if parsed.path == "/robots.txt":
            if self.robots >= self.max_robots:
                raise CampaignStop("robots transfer ceiling reached")
            self.robots += 1
        else:
            if self.pages >= self.max_pages:
                raise CampaignStop("page/copy transfer ceiling reached")
            self.pages += 1
        return super().get(url, **kwargs)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.extend(v for k, v in attrs if k == "href" and v)


def run(path: Path, *, execute: bool = False, retry_dns: bool = False,
        resume_second: bool = False) -> dict:
    plan = load_plan(path)
    project = load_project(plan["project"])
    store = Store(project.name)
    prior = [r for r in store.read(AUDIT) if r.get("campaign") == plan["campaign"]]
    if prior:
        dns_retry_allowed = (retry_dns and execute and len(prior) == 1
                             and all(r.get("failure_class") == net.CONNECTION
                                     for r in prior[0].get("landing_outcomes", [])))
        second_route_allowed = (resume_second and execute and len(prior) == 2
                                and prior[-1].get("status") == "STOPPED_BY_GUARD"
                                and prior[-1].get("stop_reason") ==
                                "destination outside approved Durham hosts: palimpsest.dur.ac.uk"
                                and prior[-1].get("transfers", {}).get("pages_or_copies") == 0)
        if not (dns_retry_allowed or second_route_allowed):
            return {"campaign": plan["campaign"], "status": "ALREADY_ATTEMPTED", "prior": prior[-1]}
        request_rows = [r for r in store.read("requests.jsonl")
                        if r.get("campaign") == plan["campaign"]]
        if dns_retry_allowed and (not request_rows or any(
                r.get("http_status") is not None
                or r.get("failure_class") != net.CONNECTION
                or "NameResolutionError" not in r.get("detail", "")
                for r in request_rows)):
            raise ValueError("retry refused: prior campaign included a non-DNS outcome")
        if second_route_allowed and any(
                "durham-repository.worktribe.com" in r.get("url", "")
                and r.get("http_status") is not None for r in request_rows):
            raise ValueError("second route has already received an HTTP response")
    summary = {
        "campaign": plan["campaign"], "candidate_key": plan["candidate_key"],
        "source_class": "UNCLASSIFIED", "adopted": False,
        "plan_sha256": sha(path), "landing_urls": plan["landing_urls"],
        "max_page_or_copy_transfers": 3,
    }
    if retry_dns and prior:
        summary["retry_after_recorded_dns_failure"] = True
    if resume_second:
        summary["resume_after_blocked_robots_redirect"] = True
    if not execute:
        return summary | {"status": "PREVIEW_ONLY"}

    guard = GuardedSession(set(plan["allowed_institutional_hosts"]))
    transport = net.Fetcher(excluded_hosts=frozenset(project.excluded_hosts))
    transport._session = guard
    recorded = RecordingFetcher(transport, store, purpose="l02_durham_recovery",
                                campaign=plan["campaign"], candidate_key=plan["candidate_key"],
                                source_class="UNCLASSIFIED")
    findings: list[dict] = []
    candidates: list[str] = []
    try:
        for landing in plan["landing_urls"][1:] if resume_second else plan["landing_urls"]:
            if guard.pages >= 2:
                break
            outcome = recorded.get(landing, expect=("text/html", "application/pdf"))
            findings.append({"url": landing, "final_url": outcome.url,
                             "http_status": outcome.status, "failure_class": outcome.failure_class,
                             "raw_sha256": hashlib.sha256(outcome.body).hexdigest() if outcome.body else None})
            if not outcome.ok or not outcome.body:
                continue
            if "pdf" in outcome.content_type.lower():
                digest = hashlib.sha256(outcome.body).hexdigest()
                summary["copy_url"] = outcome.url
                summary["copy_raw_sha256"] = digest
                summary["gate"] = fulltext.classify(outcome.body, outcome.content_type, outcome.url).as_row(
                    fulltext.DEFAULT_THRESHOLDS)
                summary["status"] = "COPY_REQUIRES_IDENTITY_REVIEW"
                break
            page = outcome.body.decode("utf-8", "replace")
            if "media content and stock returns" not in page.lower():
                continue
            parser = Links()
            parser.feed(page)
            for href in parser.hrefs:
                url = urljoin(outcome.url, href)
                parsed = urlsplit(url)
                if (parsed.hostname in guard.hosts
                        and (parsed.path.lower().endswith(".pdf") or "/download" in parsed.path.lower())
                        and url not in candidates):
                    candidates.append(url)
        summary["landing_outcomes"] = findings
        summary["candidate_links"] = candidates
        if summary.get("status") == "COPY_REQUIRES_IDENTITY_REVIEW":
            pass
        elif len(candidates) == 1 and guard.pages < 3:
            url = candidates[0]
            outcome = recorded.get(url, expect=("application/pdf",))
            summary["copy_url"] = url
            summary["copy_http_status"] = outcome.status
            summary["copy_failure_class"] = outcome.failure_class
            if outcome.ok and outcome.body:
                digest = hashlib.sha256(outcome.body).hexdigest()
                summary["copy_raw_sha256"] = digest
                summary["gate"] = fulltext.classify(outcome.body, outcome.content_type, outcome.url).as_row(
                    fulltext.DEFAULT_THRESHOLDS)
                summary["status"] = "COPY_REQUIRES_IDENTITY_REVIEW"
            else:
                summary["status"] = "COPY_FAILED"
        else:
            summary["status"] = "LINK_REVIEW_REQUIRED" if candidates else "NO_COPY_LINK"
    except CampaignStop as exc:
        summary["status"] = "STOPPED_BY_GUARD"
        summary["stop_reason"] = str(exc)
    summary["transfers"] = {"pages_or_copies": guard.pages, "robots": guard.robots}
    summary["recorded_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    store.append(AUDIT, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--retry-dns", action="store_true",
                        help="one retry only after a recorded sandbox DNS failure")
    parser.add_argument("--resume-second", action="store_true",
                        help="try only the second approved landing after first-host robots redirect")
    args = parser.parse_args()
    if args.execute:
        load_environment(Path(".env"))
    print(json.dumps(run(args.plan, execute=args.execute, retry_dns=args.retry_dns,
                         resume_second=args.resume_second), indent=2))


if __name__ == "__main__":
    main()
