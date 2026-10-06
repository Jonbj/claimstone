#!/usr/bin/env python3
"""Bounded L02 university-copy inspection; default is an offline preview.

Execution records every request and an isolated outcome. It cannot admit a source,
write a screening observation, or move an existing candidate into the new round.
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
from claimstone import fulltext, ids, net, population
from claimstone.config import load_project
from claimstone.request_log import RecordingFetcher
from claimstone.store import Store
from tools.complete_question_round import load_environment

ROOT = Path("store/alembic-s4-lungo/audits/source-selection")
PLAN_SHA256 = "07f1176800b6fc940dfe78aa0a386dcc4ccbf125b1d2e002613527a9f0e9d72f"
ROUND = "s4-l02-repository-copies-2026-10-06-v2"
CAMPAIGN = "l02-v2-southampton-hannover-copy-check-2026-10-06"
AUDIT = "audits/source-selection/l02-v2/repository-copy-check-2026-10-06/outcomes.jsonl"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class CampaignStop(RuntimeError):
    """Refuse the next physical transfer before opening a socket."""


class GuardedSession(requests.Session):
    def __init__(self, hosts: set[str], *, max_pages: int, max_robots: int):
        super().__init__()
        self.hosts = hosts
        self.max_pages = max_pages
        self.max_robots = max_robots
        self.pages = 0
        self.robots = 0

    def get(self, url, **kwargs):
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in self.hosts:
            raise CampaignStop(f"destination outside approved hosts: {parsed.hostname}")
        if parsed.path == "/robots.txt":
            if self.robots >= self.max_robots:
                raise CampaignStop("robots transfer ceiling reached")
            self.robots += 1
        else:
            if self.pages >= self.max_pages:
                raise CampaignStop("page/copy transfer ceiling reached")
            self.pages += 1
        return super().get(url, **kwargs)


class PageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.words: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(value for name, value in attrs if name == "href" and value)

    def handle_data(self, data):
        self.words.append(data)


def prepare(plan_path: Path, *, store_base="store"):
    data = plan_path.read_bytes()
    if sha(data) != PLAN_SHA256:
        raise ValueError("copy plan differs from frozen approved bytes")
    plan = json.loads(data)
    ceilings = plan.get("ceilings", {})
    if (plan.get("version") != 1 or plan.get("project") != "projects/alembic-s4-lungo"
            or plan.get("round") != ROUND or plan.get("campaign") != CAMPAIGN
            or plan.get("question_id") != "L02" or plan.get("adoption") is not False
            or plan.get("selection_change") is not False or plan.get("admission_change") is not False
            or ceilings != {"candidate_routes": 2, "page_or_copy_transfers": 5,
                            "robots_transfers": 4, "max_pdf_followups_from_landing": 1}):
        raise ValueError("unexpected L02 repository campaign scope")
    hosts = {"diskussionspapiere.wiwi.uni-hannover.de", "eprints.soton.ac.uk"}
    if set(plan.get("allowed_hosts", [])) != hosts or len(plan.get("targets", [])) != 2:
        raise ValueError("unexpected repository hosts or target count")
    project = load_project(plan["project"])
    sources_path = project.root / "sources.yaml"
    scope_path = ROOT / "l02-v2/selection-scope.json"
    inventory_path = ROOT / "l02-v1/inventory.json"
    if (sha(sources_path.read_bytes()) != plan["frozen_inputs"]["sources_sha256"]
            or population.digest(project.population) != plan["frozen_inputs"]["population_policy_sha256"]
            or sha(scope_path.read_bytes()) != plan["frozen_inputs"]["selection_scope_sha256"]
            or sha(inventory_path.read_bytes()) != plan["frozen_inputs"]["inventory_sha256"]):
        raise ValueError("frozen policy, scope or inventory changed")
    store = Store(project.name, base=store_base)
    held = store.latest_by("populations.jsonl", "round").get(ROUND)
    if not held or held["policy_sha256"] != plan["frozen_inputs"]["population_policy_sha256"]:
        raise ValueError("new round does not have the frozen population")
    inventory = {row["candidate_key"] for row in json.loads(inventory_path.read_bytes())}
    expected = {
        "doi:10.1016/j.jempfin.2009.01.002": ("direct_pdf", "diskussionspapiere.wiwi.uni-hannover.de"),
        "doi:10.1016/j.jcorpfin.2015.12.014": ("institution_landing", "eprints.soton.ac.uk"),
    }
    if {t.get("candidate_key"): (t.get("route"), t.get("allowed_host"))
            for t in plan["targets"]} != expected:
        raise ValueError("repository targets differ from approved pair")
    for target in plan["targets"]:
        key = target["candidate_key"]
        if key not in inventory or net.host_of(target["copy_url"]) != target["allowed_host"]:
            raise ValueError("copy route differs from frozen candidate or host")
        raw_sha = target["cached_openalex_sha256"]
        raw = store.path(f"requests/raw/{raw_sha}.bin").read_bytes()
        if sha(raw) != raw_sha:
            raise ValueError("cached OpenAlex metadata changed")
        metadata = json.loads(raw)
        if ids.normalize_doi(metadata.get("doi")) != key[4:] or metadata.get("title") != target["title"]:
            raise ValueError("cached metadata identity differs from target")
        if not any(a.get("author", {}).get("display_name") == target["author"] and
                   target["institution"] in {i.get("display_name") for i in a.get("institutions", [])}
                   for a in metadata.get("authorships", [])):
            raise ValueError("author and university relation is absent from cached metadata")
        field = "pdf_url" if target["route"] == "direct_pdf" else "landing_page_url"
        locations = [loc for loc in metadata.get("locations", [])
                     if loc.get(field) == target["copy_url"] and loc.get("version") == "submittedVersion"]
        if not locations:
            raise ValueError("institutional route is absent from cached metadata")
        target["licence"] = locations[0].get("license")
        target["oa_status"] = "openalex-oa" if locations[0].get("is_oa") else "openalex-not-confirmed-oa"
    return plan, project, store


def _pdf_row(outcome):
    row = {"copy_url": outcome.url, "http_status": outcome.status,
           "failure_class": outcome.failure_class, "final_url": outcome.url}
    if outcome.ok and outcome.body:
        gate = fulltext.classify(outcome.body, outcome.content_type, outcome.url)
        row["raw_sha256"] = sha(outcome.body)
        row["gate"] = gate.as_row(fulltext.DEFAULT_THRESHOLDS)
        row["status"] = "COPY_REQUIRES_IDENTITY_REVIEW" if gate.accepted else "COPY_NOT_CONFIRMED"
    else:
        row["status"] = "COPY_FAILED"
    return row


def run(plan_path: Path, *, execute=False, store_base="store") -> dict:
    plan, project, store = prepare(plan_path, store_base=store_base)
    previous = {r["candidate_key"]: r for r in store.read(AUDIT)
                if r.get("campaign") == plan["campaign"]}
    pending = [t for t in plan["targets"] if t["candidate_key"] not in previous]
    summary = {"campaign": plan["campaign"], "plan_sha256": PLAN_SHA256,
               "round": plan["round"], "completed": len(previous),
               "pending": [t["candidate_key"] for t in pending],
               "ceilings": plan["ceilings"], "admitted_candidates": 0}
    if not execute or not pending:
        return summary | {"status": "PREVIEW_ONLY" if not execute else "ALREADY_ATTEMPTED"}

    guard = GuardedSession(set(plan["allowed_hosts"]),
                           max_pages=plan["ceilings"]["page_or_copy_transfers"],
                           max_robots=plan["ceilings"]["robots_transfers"])
    guard.headers["User-Agent"] = net.USER_AGENT.format(contact=net.contact_email())
    transport = net.Fetcher(excluded_hosts=frozenset(project.excluded_hosts))
    transport._session = guard
    results = []
    for target in pending:
        row = {"campaign": plan["campaign"], "plan_sha256": PLAN_SHA256,
               "candidate_key": target["candidate_key"], "source_class": "UNCLASSIFIED",
               "adopted": False, "identity_status": "NOT_VERIFIED",
               "route": target["route"], "copy_url": target["copy_url"],
               "licence": target["licence"], "oa_status": target["oa_status"]}
        recorded = RecordingFetcher(transport, store, purpose="l02_repository_copy_check",
                                    campaign=plan["campaign"], candidate_key=target["candidate_key"],
                                    source_class="UNCLASSIFIED", licence=target["licence"],
                                    oa_status=target["oa_status"], provenance="cached_openalex_institution")
        try:
            if target["route"] == "direct_pdf":
                row.update(_pdf_row(recorded.get(target["copy_url"], expect=("application/pdf",))))
            else:
                outcome = recorded.get(target["copy_url"], expect=("text/html", "application/pdf"))
                row.update(landing_status=outcome.status, landing_failure_class=outcome.failure_class,
                           landing_final_url=outcome.url)
                if not outcome.ok or not outcome.body:
                    row["status"] = "LANDING_FAILED"
                elif "pdf" in outcome.content_type.lower():
                    row.update(_pdf_row(outcome))
                else:
                    parser = PageLinks()
                    parser.feed(outcome.body.decode("utf-8", "replace"))
                    page_text = " ".join(parser.words).lower()
                    if "media-expressed negative tone" not in page_text:
                        row["status"] = "LANDING_IDENTITY_UNCLEAR"
                    else:
                        pdf_links = sorted({urljoin(outcome.url, href) for href in parser.links
                                            if urlsplit(urljoin(outcome.url, href)).hostname == target["allowed_host"]
                                            and urlsplit(urljoin(outcome.url, href)).path.lower().endswith(".pdf")})
                        row["candidate_pdf_links"] = pdf_links
                        if len(pdf_links) == 1:
                            row.update(_pdf_row(recorded.get(pdf_links[0], expect=("application/pdf",))))
                        else:
                            row["status"] = "PDF_LINK_REVIEW_REQUIRED"
        except CampaignStop as exc:
            row["status"] = "STOPPED_BY_GUARD"
            row["stop_reason"] = str(exc)
        row["transfers_so_far"] = {"pages_or_copies": guard.pages, "robots": guard.robots}
        row["recorded_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        store.append(AUDIT, row)
        results.append(row)
    return summary | {"status": "EXECUTED", "outcomes": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.execute:
        load_environment(Path(".env"))
    print(json.dumps(run(args.plan, execute=args.execute), indent=2))


if __name__ == "__main__":
    main()
