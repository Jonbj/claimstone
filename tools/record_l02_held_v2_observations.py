#!/usr/bin/env python3
"""Reassess the remaining held L02 sources under v2 as AI-provisional observations.

V1 decisions are reading leads, not transferred labels. Changed exposure cases
have explicit v2 dispositions; all evidence is rechecked against active chunks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import chunk_sets, source_selection
from claimstone.config import load_project
from claimstone.store import Store

ROOT = Path("store/alembic-s4-lungo/audits/source-selection")
INVENTORY = ROOT / "l02-v1/inventory.json"
V1 = ROOT / "l02-v1/decisions.json"
V2 = ROOT / "l02-v2/selection-scope.json"
EXPECTED = {INVENTORY: "fa160b117a84a071e975acb0422f3a6a47a47263b7f0445e4ed455e39c05ab67",
            V1: "dd31957142b286be23580bb784d0d3286836fdd1d54463f2e5739c306a218038",
            V2: "89ba1bfc304e6fbdd63b961d9c43e554c9400b589d62db6f808a349a85075773"}
SCOPE_ID = "l02-v2-ai-selection-2026-10-05"
SKIP = {"ACA001"}
CHANGED = {
    "ACA006": ("EXCLUDE", "CONTEXT", ["E1"],
               "This tests negative-word tone in corporate 10-K filings and twelve-month returns. Filing tone is context under the operator's v2 media/newswire rule.",
               ["Summary Statistics for the 1994 to 2008 10-K Sample"]),
    "ACA012": ("UNCERTAIN", "UNRESOLVED", ["E1"],
               "The held version predicts next-month firm returns from a RavenPack feed that also includes regulatory updates and financial websites. No media/newswire-only return result was located; keep direct exposure unresolved, not included.",
               ["including industry and business publications, regional and local newspapers, government and regulatory updates, and trustworthy financial websites.",
                "We then compute the equally weighted next month"]),
    "ACA015": ("EXCLUDE", "CONTEXT", ["E1"],
               "The tested monthly sentiment change comes from 10-K/10-Q corporate filings, which are context under the v2 media/newswire rule.",
               ["10-K/10-Q", "Stocks are held in the portfolio for 3 months."]),
}
METHOD_QUOTES = {
    "MET001": "event study methodology",
    "MET003": "STEPWISE MULTIPLE TESTING METHOD",
    "MET004": "A Model with Correlations",
    "MET005": "The Delisting Bias in CRSP Data",
    "MET006": "long-run abnormal returns",
    "MET007": "This data-mined strategy forms portfolios",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare() -> tuple[Store, set[str], list[dict]]:
    for path, expected in EXPECTED.items():
        if sha(path.read_bytes()) != expected:
            raise ValueError(f"frozen source-selection input changed: {path}")
    project = load_project("projects/alembic-s4-lungo")
    scope = json.loads(V2.read_text())
    if scope["registry_sha256"] != project.registry_sha256 or \
            scope["selection_protocol_version"] != 2:
        raise ValueError("v2 selection protocol or registry changed")
    store = Store(project.name)
    inventory = json.loads(INVENTORY.read_text())
    keys = {row["candidate_key"] for row in inventory}
    prior = {row["candidate_key"]: row for row in json.loads(V1.read_text())}
    documents = store.latest_by("documents.jsonl", "source_id")
    chunks = chunk_sets.current(store)
    rows = []
    for candidate in inventory:
        sid = candidate.get("source_id")
        if not sid or sid in SKIP:
            continue
        old = prior.get(candidate["candidate_key"])
        document = documents.get(sid)
        if not old or not document or not document.get("fulltext_confirmed") or \
                document.get("source_class") != candidate.get("source_class"):
            raise ValueError(f"held source, class or prior reading missing: {sid}")
        pdf = store.path(f'raw/{document["sha256"]}.pdf')
        if not pdf.is_file() or sha(pdf.read_bytes()) != document["sha256"]:
            raise ValueError(f"held PDF bytes changed: {sid}")
        active = {key: chunks[key] for key in document["chunk_ids"]}
        if sid in CHANGED:
            decision, role, criteria, reason, selected = CHANGED[sid]
        else:
            if old["decision"] != "EXCLUDE":
                raise ValueError(f"unreviewed v1 disposition: {sid}")
            decision, role, criteria = "EXCLUDE", "CONTEXT", old["criterion_ids"]
            reason = ("Under the narrower v2 media/newswire exposure, the held full text remains "
                      "outside direct L02 evidence: " + old["reason"])
            selected = [METHOD_QUOTES[sid]] if sid in METHOD_QUOTES else [
                e["observation"] for e in old["evidence"] if any(
                    e.get("observation") and e["observation"] in chunk["text"]
                    for chunk in active.values())]
        evidence = []
        for quote in selected:
            matching = [(key, chunk) for key, chunk in active.items() if quote in chunk["text"]]
            if not matching:
                raise ValueError(f"selected v2 quote absent from active {sid} chunks: {quote[:45]}")
            key, chunk = matching[0]
            evidence.append({"quote": quote, "locator": f"chunk:{key}",
                             "text_sha256": sha(chunk["text"].encode()),
                             "copy_sha256": document["sha256"]})
        if not evidence or any(criterion not in scope["criteria"] for criterion in criteria):
            raise ValueError(f"evidence or criterion missing: {sid}")
        row = source_selection.identified({
            "selection_version": 1, "scope_id": SCOPE_ID, "question_id": "L02",
            "registry_sha256": project.registry_sha256,
            "candidate_key": candidate["candidate_key"],
            "source_class": candidate["source_class"], "assessment_status": "AI_PROVISIONAL",
            "decision": decision, "role": role, "screening_level": "FULLTEXT",
            "criterion_ids": criteria, "reason": reason,
            "assessed_by": "Codex interactive v2 held-source review (AI_PROVISIONAL)",
            "identity_status": old["identity_status"],
            "input_sha256": EXPECTED[V2], "evidence": evidence,
            "model": "unknown", "backend": "codex-interactive",
            "harness_version": "unknown", "prompt_sha256": None, "supersedes": None,
        }, "assessment_id")
        source_selection.validate_screening(row)
        rows.append(row)
    if len(rows) != 18:
        raise ValueError(f"expected exactly 18 other held sources, found {len(rows)}")
    return store, keys, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    store, keys, rows = prepare()
    before = source_selection.preview(store, SCOPE_ID, "L02", keys, rows)
    result = (source_selection.append_observations(
        store, rows, [], scope_id=SCOPE_ID, question_id="L02", inventory_keys=keys)
        if args.apply else None)
    after = source_selection.preview(store, SCOPE_ID, "L02", keys)
    print(json.dumps({"status": "APPLIED" if args.apply else "PREVIEW_ONLY",
                      "proposed": len(rows), "would_write": before["new_screening_rows"],
                      "written": result, "by_disposition": {
                          f'{d}/{r}': sum(x["decision"] == d and x["role"] == r for x in rows)
                          for d, r in {(x["decision"], x["role"]) for x in rows}},
                      "current": {key: after[key] for key in (
                          "screened_count", "unobserved_count", "provisional_direct_candidates",
                          "provisional_context", "provisional_uncertain", "cohort_closed",
                          "admitted_candidates")}}, indent=2))


if __name__ == "__main__":
    main()
