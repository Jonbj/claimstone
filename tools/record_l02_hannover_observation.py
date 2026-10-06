#!/usr/bin/env python3
"""Record the held Hannover draft as an advisory L02 observation.

Default is an offline preview. The script verifies the frozen campaign, raw
metadata, PDF bytes and extracted quotes before its append-only write.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import source_selection
from claimstone.config import load_project
from claimstone.store import Store

ROOT = Path("store/alembic-s4-lungo/audits/source-selection")
PLAN = ROOT / "l02-v2/repository-copy-check-2026-10-06/plan.json"
PLAN_SHA256 = "07f1176800b6fc940dfe78aa0a386dcc4ccbf125b1d2e002613527a9f0e9d72f"
SCOPE = ROOT / "l02-v2/selection-scope.json"
SCOPE_SHA256 = "89ba1bfc304e6fbdd63b961d9c43e554c9400b589d62db6f808a349a85075773"
INVENTORY = ROOT / "l02-v1/inventory.json"
INVENTORY_SHA256 = "fa160b117a84a071e975acb0422f3a6a47a47263b7f0445e4ed455e39c05ab67"
SCOPE_ID = "l02-v2-ai-selection-2026-10-05"
KEY = "doi:10.1016/j.jempfin.2009.01.002"
METADATA_SHA256 = "a131a42092de5491e13943a1be86c4f487d2d47a340a7f3200886ef1db8d9a1f"
PDF_SHA256 = "a1ff57d0107ab97ed5dec497ec313147561ccc04460ea9b7e052358021896385"
CAMPAIGN = "l02-v2-southampton-hannover-copy-check-2026-10-06"
AUDIT = "audits/source-selection/l02-v2/repository-copy-check-2026-10-06/outcomes.jsonl"
QUOTES = (
    "consumer confidence – as a proxy for individual investor sentiment –",
    "sentiment negatively forecasts aggregate stock market\nreturns on average across countries.",
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare():
    if sha(PLAN.read_bytes()) != PLAN_SHA256 or sha(SCOPE.read_bytes()) != SCOPE_SHA256 or \
            sha(INVENTORY.read_bytes()) != INVENTORY_SHA256:
        raise ValueError("frozen L02 screening or copy plan changed")
    project = load_project("projects/alembic-s4-lungo")
    scope = json.loads(SCOPE.read_bytes())
    if scope["registry_sha256"] != project.registry_sha256:
        raise ValueError("question registry changed")
    plan = json.loads(PLAN.read_bytes())
    target = next((t for t in plan["targets"] if t["candidate_key"] == KEY), None)
    if not target or target["cached_openalex_sha256"] != METADATA_SHA256 or \
            plan["campaign"] != CAMPAIGN:
        raise ValueError("Hannover target differs from frozen campaign")
    store = Store(project.name)
    inventory = json.loads(INVENTORY.read_bytes())
    keys = {row["candidate_key"] for row in inventory}
    if len(keys) != len(inventory) or KEY not in keys:
        raise ValueError("candidate identity absent from frozen inventory")
    outcome = [row for row in store.read(AUDIT) if row.get("campaign") == CAMPAIGN
               and row.get("candidate_key") == KEY]
    if len(outcome) != 1 or outcome[0].get("status") != "COPY_REQUIRES_IDENTITY_REVIEW" or \
            outcome[0].get("raw_sha256") != PDF_SHA256 or outcome[0].get("adopted") is not False:
        raise ValueError("recorded copy outcome does not match frozen PDF")
    meta_path = store.path(f"requests/raw/{METADATA_SHA256}.bin")
    pdf_path = store.path(f"requests/raw/{PDF_SHA256}.bin")
    if sha(meta_path.read_bytes()) != METADATA_SHA256 or sha(pdf_path.read_bytes()) != PDF_SHA256:
        raise ValueError("retained metadata or PDF bytes changed")
    metadata = json.loads(meta_path.read_bytes())
    if metadata.get("doi", "").lower().removeprefix("https://doi.org/") != KEY[4:] or \
            metadata.get("title") != target["title"] or metadata.get("publication_year") != 2009:
        raise ValueError("cached DOI, title or year differs")
    authors = {a.get("author", {}).get("display_name") for a in metadata.get("authorships", [])}
    if "Maik Schmeling" not in authors:
        raise ValueError("cached author differs from PDF lead")
    try:
        extracted = subprocess.run(["pdftotext", "-layout", str(pdf_path), "-"],
                                   capture_output=True, check=True, timeout=60).stdout.decode()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("held PDF cannot be independently extracted") from exc
    for token in ("Investor sentiment and stock returns:", "Some international evidence",
                  "Maik Schmeling", "Discussion Paper No. 407", "November 2008", *QUOTES):
        if token not in extracted:
            raise ValueError(f"held draft identity or quote missing: {token[:35]}")
    text_sha = sha(extracted.encode())
    evidence = [{"quote": quote, "locator": f"pdf:{PDF_SHA256}:page1",
                 "text_sha256": text_sha, "copy_sha256": PDF_SHA256} for quote in QUOTES]
    screening = source_selection.identified({
        "selection_version": source_selection.SOURCE_SELECTION_VERSION,
        "scope_id": SCOPE_ID, "question_id": "L02", "registry_sha256": project.registry_sha256,
        "candidate_key": KEY, "source_class": "UNCLASSIFIED",
        "assessment_status": "AI_PROVISIONAL", "decision": "EXCLUDE", "role": "NOT_DIRECT",
        "screening_level": "FULLTEXT", "criterion_ids": ["E1", "T1"],
        "reason": "The held 2008 discussion-paper version uses consumer confidence as investor sentiment and forecasts aggregate country stock-market returns. It does not test sentiment measured from media/newswire text against future firm-level returns. The 2009 DOI record may be a later version and needs copy-level confirmation.",
        "assessed_by": "Codex interactive L02 draft inspection (AI_PROVISIONAL)",
        "identity_status": "POSSIBLE_VERSION", "input_sha256": PLAN_SHA256,
        "evidence": evidence, "model": "gpt-6-sol", "backend": "codex-interactive",
        "harness_version": "unknown", "prompt_sha256": None, "supersedes": None,
    }, "assessment_id")
    identity = source_selection.identified({
        "selection_version": source_selection.IDENTITY_RELATION_VERSION,
        "scope_id": SCOPE_ID, "candidate_key": KEY, "source_class": "UNCLASSIFIED",
        "related_kind": "HELD_COPY", "related_key": PDF_SHA256,
        "status": "POSSIBLE_VERSION",
        "reason": "Cached DOI metadata names a 2009 journal work; held university PDF names a November 2008 discussion paper with matching title and author. Publication/version relation remains unverified.",
        "assessed_by": "Codex interactive L02 draft identity inspection",
        "metadata_title": metadata["title"],
        "copy_title": "Investor sentiment and stock returns: Some international evidence",
        "metadata_sha256": METADATA_SHA256, "copy_sha256": PDF_SHA256,
        "observations": [
            f"metadata:{METADATA_SHA256}:title, author Maik Schmeling, publication_year 2009",
            f"pdf:{PDF_SHA256}:page1 title, author Maik Schmeling, Discussion Paper No. 407, November 2008",
        ], "supersedes": None,
    }, "observation_id")
    source_selection.validate_screening(screening)
    source_selection.validate_identity(identity)
    return store, keys, screening, identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    store, keys, screening, identity = prepare()
    before = source_selection.preview(store, SCOPE_ID, "L02", keys, [screening], [identity])
    written = ({"screening_rows_written": 0, "identity_rows_written": 0}
               if not args.apply else source_selection.append_observations(
                   store, [screening], [identity], scope_id=SCOPE_ID,
                   question_id="L02", inventory_keys=keys))
    after = source_selection.preview(store, SCOPE_ID, "L02", keys)
    print(json.dumps({"status": "APPLIED" if args.apply else "PREVIEW_ONLY",
                      "would_write": {"screening": before["new_screening_rows"],
                                      "identity": before["new_identity_rows"]},
                      "written": written,
                      "current": {key: after[key] for key in (
                          "screened_count", "unobserved_count", "provisional_direct_candidates",
                          "provisional_uncertain", "admitted_candidates", "cohort_closed")}}, indent=2))


if __name__ == "__main__":
    main()
