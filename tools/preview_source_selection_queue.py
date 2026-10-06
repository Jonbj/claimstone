#!/usr/bin/env python3
"""Offline selection work queue; ordering never changes eligibility or admission."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import source_selection
from claimstone.store import Store


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(store: Store, inventory_path: Path, metadata_queue_path: Path,
          scope_id: str, question_id: str) -> dict:
    inventory_bytes = inventory_path.read_bytes()
    inventory = json.loads(inventory_bytes)
    keys = {row["candidate_key"] for row in inventory}
    if len(keys) != len(inventory):
        raise ValueError("frozen inventory contains duplicate identities")
    metadata_bytes = metadata_queue_path.read_bytes()
    metadata_queue = json.loads(metadata_bytes)
    if metadata_queue["inventory_sha256"] != sha(inventory_bytes):
        raise ValueError("cached metadata queue belongs to another inventory")
    cached = {row["candidate"]["candidate_key"]: row for row in metadata_queue["records"]}
    source_rows = [row for row in store.read(source_selection.SCREENING_LEDGER)
                   if row.get("scope_id") == scope_id and row.get("question_id") == question_id]
    latest = {}
    for row in source_rows:
        source_selection.validate_screening(row)
        old = latest.get(row["candidate_key"])
        if row.get("supersedes") != (old["assessment_id"] if old else None):
            raise ValueError("screening chain is broken")
        latest[row["candidate_key"]] = row
    if not set(latest) <= keys:
        raise ValueError("screening contains a candidate outside the frozen inventory")
    source_selection.preview(store, scope_id, question_id, keys)
    identity, _ = source_selection._replay(store.read(source_selection.IDENTITY_LEDGER), [], identity=True)
    linked = {}
    for relation in identity.values():
        if (relation.get("scope_id") == scope_id and
                relation.get("related_kind") == "CANDIDATE" and
                relation.get("status") == "VERIFIED_SAME_WORK"):
            left, right = relation["candidate_key"], relation["related_key"]
            linked.setdefault(left, []).append(right)
            linked.setdefault(right, []).append(left)
    documents = store.latest_by("documents.jsonl", "source_id")
    recorded_abstracts = {row["candidate_key"]: row for row in store.read("screening_metadata.jsonl")
                          if row.get("status") == "ABSTRACT_AVAILABLE" and row.get("abstract")}
    tasks = []
    for row in inventory:
        key = row["candidate_key"]
        observation = latest.get(key)
        if observation and observation["decision"] != "UNCERTAIN":
            continue
        old_queue = cached.get(key, {})
        has_cached_metadata = bool(old_queue.get("cached_metadata"))
        linked_observed = sorted(counterpart for counterpart in linked.get(key, [])
                                 if counterpart in latest)
        if not observation and linked_observed:
            reason = "verified_relation_needs_controlled_reuse"
            next_action = "inspect_linked_dossier_before_any_new_request"
            tier = 0
        elif observation:
            reason = "provisional_uncertain"
            next_action = "resolve_lawful_copy_or_missing_specification"
            tier = 1
        elif row.get("source_id") and documents.get(row["source_id"], {}).get("fulltext_confirmed"):
            reason = "held_source_unobserved"
            next_action = "read_held_fulltext_offline"
            tier = 0
        elif key in recorded_abstracts:
            reason = "recorded_abstract_needs_validation"
            next_action = "recheck_retained_metadata_bytes_then_screen_offline"
            tier = 0
        elif has_cached_metadata:
            reason = "cached_metadata_needs_authoritative_abstract"
            next_action = "verify_or_fetch_authoritative_abstract"
            tier = 2
        else:
            reason = "metadata_lookup_needed"
            next_action = "plan_recorded_metadata_lookup"
            tier = 3
        tasks.append({"candidate_key": key, "title": row.get("title"),
                      "source_id": row.get("source_id"), "reason": reason,
                      "related_observed_keys": linked_observed,
                      "tier": tier, "next_action": next_action,
                      "ordering_cues": old_queue.get("priority_cues", []),
                      "ordering_score": old_queue.get("ordering_score", 0),
                      "selection_decision": None})
    tasks.sort(key=lambda row: (row["tier"], -row["ordering_score"], row["candidate_key"]))
    return {"kind": "offline_source_selection_queue", "scope_id": scope_id,
            "question_id": question_id, "inventory_sha256": sha(inventory_bytes),
            "metadata_queue_sha256": sha(metadata_bytes), "inventory_count": len(keys),
            "observed_count": len(latest), "unobserved_count": len(keys - set(latest)),
            "task_count": len(tasks), "task_reasons": dict(Counter(t["reason"] for t in tasks)),
            "tasks": tasks, "network_requests": 0, "model_calls": 0,
            "selection_decisions_written": 0, "admitted_candidates": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--metadata-queue", type=Path, required=True)
    parser.add_argument("--scope-id", required=True)
    parser.add_argument("--question-id", required=True)
    parser.add_argument("--store-project", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.limit < 0:
        raise ValueError("limit must be nonnegative")
    store = Store(args.store_project)
    report = build(store, args.inventory, args.metadata_queue,
                   args.scope_id, args.question_id)
    output = {key: value for key, value in report.items() if key != "tasks"}
    output["next_tasks"] = report["tasks"][:args.limit]
    if args.write:
        body = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
        path = store.path(f'audits/source-selection/queues/{sha(body)}.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != body:
            raise ValueError("existing queue snapshot bytes changed")
        if not path.exists():
            path.write_bytes(body)
        output["queue_path"] = str(path)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
