#!/usr/bin/env python3
"""Build an offline, source-level selection dossier from current retained ledgers.

The output is an evidence index, not a selection decision, profile or verdict.
It never changes a production ledger or treats model reviews as human labels.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import chunk_sets, claim_records, review
from claimstone.config import load_project
from claimstone.store import Store


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(project_path: str, source_id: str, question_id: str, inventory_path: Path,
          identity_audit_path: Path) -> dict:
    project = load_project(project_path)
    if question_id not in {q.id for q in project.questions}:
        raise ValueError("question is not in the project registry")
    store = Store(project.name)
    documents = store.latest_by("documents.jsonl", "source_id")
    document = documents.get(source_id)
    if not document or not document.get("fulltext_confirmed"):
        raise ValueError("source has no confirmed active document")
    raw = store.path(f'raw/{document["sha256"]}.pdf')
    if not raw.is_file() or digest(raw.read_bytes()) != document["sha256"]:
        raise ValueError("held PDF bytes differ from active document")
    inventory_bytes = inventory_path.read_bytes()
    inventory = json.loads(inventory_bytes)
    candidates = [row for row in inventory if row.get("source_id") == source_id]
    if len(candidates) != 1:
        raise ValueError("source must map to exactly one frozen inventory key")
    audit_bytes = identity_audit_path.read_bytes()
    audit = json.loads(audit_bytes)
    if audit.get("inventory_sha256") != digest(inventory_bytes):
        raise ValueError("identity audit and inventory differ")
    source_key = candidates[0]["candidate_key"]
    relationships = [row for row in audit.get("reviewed_relationships", [])
                     if source_key in row.get("candidate_keys", [])]
    chunks = chunk_sets.current(store)
    active = {key: chunks[key] for key in document.get("chunk_ids", [])}
    current_claims = [row for row in claim_records.current(store)[0].values()
                      if row.get("source_id") == source_id and row.get("question_id") == question_id]
    current_reviews = review.current(store)
    findings = []
    for claim in sorted(current_claims, key=lambda row: row["claim_id"]):
        chunk = active.get(claim.get("chunk_id"))
        quote = claim.get("evidence_quote")
        if chunk is None or not isinstance(quote, str) or quote not in chunk["text"]:
            raise ValueError(f'claim quote is absent from active chunk: {claim["claim_id"]}')
        reviewed = current_reviews.get(claim["claim_id"])
        findings.append({"claim_id": claim["claim_id"], "chunk_id": claim["chunk_id"],
                         "chunk_text_sha256": digest(chunk["text"].encode()),
                         "claim": claim.get("claim"), "quote": quote,
                         "review_verdict": reviewed.get("verdict") if reviewed else None,
                         "review_reason": reviewed.get("reason") if reviewed else None})
    return {"kind": "offline_source_selection_dossier", "project": project.name,
            "question_id": question_id, "registry_sha256": project.registry_sha256,
            "source_id": source_id, "source_class": document["source_class"],
            "source_key": source_key, "document_sha256": document["sha256"],
            "generation_sha256": document.get("generation_sha256"),
            "inventory_sha256": digest(inventory_bytes),
            "identity_audit_sha256": digest(audit_bytes),
            "relationships": relationships, "active_chunk_count": len(active),
            "current_claim_count": len(findings),
            "review_counts": dict(Counter(x["review_verdict"] or "UNREVIEWED" for x in findings)),
            "claims": findings, "selection_decision": None,
            "admitted_by_this_tool": False, "network_requests": 0, "model_calls": 0}


def markdown(report: dict) -> str:
    lines = [f'# Source selection dossier: {report["source_id"]} / {report["question_id"]}', '',
             'Offline evidence index. No selection, admission, profile or human verdict.', '',
             f'Held PDF SHA-256: `{report["document_sha256"]}`; class: `{report["source_class"]}`.',
             f'Frozen inventory key: `{report["source_key"]}`.',
             f'Active chunks: {report["active_chunk_count"]}; current claims: {report["current_claim_count"]}.',
             f'Reviews: {report["review_counts"]}.', '', '## Identity relationships', '']
    for relation in report["relationships"]:
        lines.append(f'- {relation["relation"]} / {relation["status"]}: '
                     + ', '.join(f'`{key}`' for key in relation["candidate_keys"])
                     + f'. {relation["reason"]}')
    lines.extend(['', '## Current claim and review index', ''])
    for item in report["claims"]:
        lines.extend([f'### `{item["claim_id"]}` — {item["review_verdict"] or "UNREVIEWED"}', '',
                      item["claim"] or '', '', '> ' + item["quote"].replace('\n', '\n> '), '',
                      f'Chunk: `{item["chunk_id"]}`; review reason: {item["review_reason"] or "—"}.', ''])
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--question-id", required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--identity-audit", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build(args.project, args.source_id, args.question_id,
                   args.inventory, args.identity_audit)
    canonical = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    summary = {key: value for key, value in report.items() if key not in {"claims", "relationships"}}
    if args.write:
        store = Store(report["project"])
        path = store.path(f'audits/source-selection/dossiers/{digest(canonical)}.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        for target, content in ((path, canonical), (path.with_suffix('.md'), markdown(report).encode())):
            if target.exists() and target.read_bytes() != content:
                raise ValueError("existing content-addressed dossier changed")
            if not target.exists():
                target.write_bytes(content)
        summary["dossier_path"] = str(path)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
