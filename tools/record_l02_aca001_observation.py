#!/usr/bin/env python3
"""Record the held ACA001 L02 v2 reading as advisory, never as cohort admission."""

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

ROOT = Path("store/alembic-s4-lungo")
INVENTORY = ROOT / "audits/source-selection/l02-v1/inventory.json"
SCOPE = ROOT / "audits/source-selection/l02-v2/selection-scope.json"
DOSSIER = ROOT / "audits/source-selection/dossiers/b9b19c8be81ef35e51ed912c1b4017a195010983d118e0072cb6b71070d881e5.json"
IDENTITY_AUDIT = ROOT / "audits/source-selection/l02-v1/identity-audits/4fa62215350e483f49b92c0664d5d95772c04c5f8bfc4ecaa349279ebcdbac53.json"
METADATA_SHA = "e79d6adffdeefa0b0dd156e2e3b4487797928064b591c59748652d7a277d726b"
COPY_SHA = "1bba428e22229769eff8cd54f68c4344f08c2517ec34c7994ba818214e2a4551"
TITLE_KEY = "title:news versus sentiment predicting stock returns from news stories"
DOI_KEY = "doi:10.17016/feds.2016.048"
SCOPE_ID = "l02-v2-ai-selection-2026-10-05"
QUOTES = {
    "c2": "Our empirical analysis uses 900,754 articles tagged with firm identifiers from the Thomson-Reuters news system over the calendar years 2003 to 2010.",
    "c6": "However, negative news predicts low stock returns for up to one quarter.",
    "n17": "For a given lag k ranging from 0 to 13, we regress stock returns on sentiment ratings",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare() -> tuple[Store, set[str], dict, dict]:
    project = load_project("projects/alembic-s4-lungo")
    store = Store(project.name)
    inventory_bytes = INVENTORY.read_bytes()
    inventory = json.loads(inventory_bytes)
    keys = {row["candidate_key"] for row in inventory}
    title = next(row for row in inventory if row["candidate_key"] == TITLE_KEY)
    doi = next(row for row in inventory if row["candidate_key"] == DOI_KEY)
    if title.get("source_id") != "ACA001" or title.get("source_class") != "WP" or \
            doi.get("doi", "").lower() != DOI_KEY[4:]:
        raise ValueError("frozen candidate identity or source class changed")
    scope_bytes = SCOPE.read_bytes()
    if sha(scope_bytes) != "89ba1bfc304e6fbdd63b961d9c43e554c9400b589d62db6f808a349a85075773":
        raise ValueError("frozen v2 selection scope changed")
    scope = json.loads(scope_bytes)
    if (scope["registry_sha256"] != project.registry_sha256 or
            scope["selection_protocol_version"] != 2 or
            set(("E1", "H1", "T1", "I1")) - set(scope["criteria"])):
        raise ValueError("L02 v2 selection criteria or registry changed")
    dossier_bytes = DOSSIER.read_bytes()
    if sha(dossier_bytes) != DOSSIER.stem:
        raise ValueError("frozen dossier changed")
    dossier = json.loads(dossier_bytes)
    if (dossier["inventory_sha256"] != sha(inventory_bytes) or
            dossier["identity_audit_sha256"] != sha(IDENTITY_AUDIT.read_bytes()) or
            dossier["source_key"] != TITLE_KEY or dossier["document_sha256"] != COPY_SHA or
            dossier["registry_sha256"] != project.registry_sha256):
        raise ValueError("dossier no longer matches frozen inputs")
    relationship = [r for r in dossier["relationships"]
                    if set(r["candidate_keys"]) == {TITLE_KEY, DOI_KEY} and
                    r["relation"] == "SAME_WORK" and r["status"] == "VERIFIED"]
    if len(relationship) != 1 or len(relationship[0]["evidence"]) < 2:
        raise ValueError("verified same-work relation is absent")
    metadata_raw = store.path(f"requests/raw/{METADATA_SHA}.bin").read_bytes()
    metadata = json.loads(metadata_raw)
    if sha(metadata_raw) != METADATA_SHA or \
            metadata.get("doi", "").lower().removeprefix("https://doi.org/") != DOI_KEY[4:] or \
            metadata.get("title") != title["title"]:
        raise ValueError("retained authority metadata differs")
    copy = store.path(f"raw/{COPY_SHA}.pdf").read_bytes()
    if sha(copy) != COPY_SHA:
        raise ValueError("held PDF changed")
    chunks = chunk_sets.current(store)
    document = store.latest_by("documents.jsonl", "source_id")["ACA001"]
    if (document.get("sha256") != COPY_SHA or
            document.get("generation_sha256") != dossier["generation_sha256"]):
        raise ValueError("active document differs from the frozen dossier")
    active = {key.rsplit("#", 1)[-1]: chunks[key]
              for key in document["chunk_ids"]}
    evidence = []
    for suffix, quote in QUOTES.items():
        chunk = active[suffix]
        if chunk["source_id"] != "ACA001" or quote not in chunk["text"]:
            raise ValueError(f"screening quote absent from active {suffix} chunk")
        evidence.append({"quote": quote, "locator": f'chunk:{chunk["chunk_id"]}',
                         "text_sha256": sha(chunk["text"].encode()), "copy_sha256": COPY_SHA})
    screening = source_selection.identified({
        "selection_version": 1, "scope_id": SCOPE_ID, "question_id": "L02",
        "registry_sha256": project.registry_sha256, "candidate_key": TITLE_KEY,
        "source_class": "WP", "assessment_status": "AI_PROVISIONAL",
        "decision": "INCLUDE", "role": "DIRECT_CANDIDATE", "screening_level": "FULLTEXT",
        "criterion_ids": ["T1", "E1", "H1"],
        "reason": "Held Federal Reserve working paper measures firm-tagged Reuters news-text sentiment and tests subsequent weekly stock returns; Table 5 separates news incidence, positive and negative sentiment. Direct candidate only; no cohort admission or human label.",
        "assessed_by": "Codex interactive full-text inspection (AI_PROVISIONAL)",
        "identity_status": "VERIFIED_SAME_WORK", "input_sha256": sha(dossier_bytes),
        "evidence": evidence, "model": "unknown", "backend": "codex-interactive",
        "harness_version": "unknown", "prompt_sha256": None, "supersedes": None,
    }, "assessment_id")
    source_selection.validate_screening(screening)
    identity = source_selection.identified({
        "selection_version": 2, "scope_id": SCOPE_ID, "candidate_key": TITLE_KEY,
        "source_class": "WP", "status": "VERIFIED_SAME_WORK", "related_kind": "CANDIDATE",
        "related_key": DOI_KEY, "canonical_work_key": DOI_KEY,
        "metadata_sha256": METADATA_SHA, "copy_sha256": COPY_SHA,
        "reason": relationship[0]["reason"],
        "assessed_by": "Codex interactive identity audit (AI_PROVISIONAL)",
        "observations": [f'{e["locator"]}: {e["observation"]}' for e in relationship[0]["evidence"]],
        "supersedes": None,
    }, "observation_id")
    source_selection.validate_identity(identity)
    return store, keys, screening, identity


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    store, keys, screening, identity = prepare()
    before = source_selection.preview(store, SCOPE_ID, "L02", keys,
                                      [screening], [identity])
    result = source_selection.append_observations(
        store, [screening], [identity], scope_id=SCOPE_ID,
        question_id="L02", inventory_keys=keys) if args.apply else None
    after = source_selection.preview(store, SCOPE_ID, "L02", keys)
    print(json.dumps({"status": "APPLIED" if args.apply else "PREVIEW_ONLY",
                      "proposed_assessment_id": screening["assessment_id"],
                      "proposed_relation_id": identity["observation_id"],
                      "would_write": {"screening": before["new_screening_rows"],
                                      "identity": before["new_identity_rows"]},
                      "written": result, "current_view": {
                          key: after[key] for key in ("inventory_count", "screened_count",
                              "unobserved_count", "provisional_direct_candidates",
                              "provisional_uncertain", "cohort_closed", "admitted_candidates")}}, indent=2))


if __name__ == "__main__":
    main()
