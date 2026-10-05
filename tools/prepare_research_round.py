#!/usr/bin/env python
"""Validate a scoped reuse plan, optionally import/re-gate cached bytes and measure local work.

No network and no model answers. Default is read-only; --apply is append-only and preserves the
entire original store. An explicit identity assessment links each abbreviated manifest title
to the cached primary document title; matching source ids alone never imports a file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from claimstone import acquire, admissibility, discover, extract, html_doc, normalize, population, tei
from claimstone.config import check_registry_drift, load_project
from claimstone.store import Store
from tools.replay_answers import files_snapshot


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(plan, *, apply=False):
    project = load_project(plan["project"])
    target = Store(project.name, base=plan.get("store_base", "store"))
    origin = Store(plan["origin_project"], base=plan.get("origin_store_base", "store"))
    if target.root.resolve() == origin.root.resolve():
        raise ValueError("origin and target must differ")
    for name, digest in plan["input_sha256"].items():
        if name not in {"topics.yaml", "questions.yaml", "sources.yaml", "manifest.tsv"}:
            raise ValueError("unexpected project input")
        if sha(project.root / name) != digest:
            raise ValueError(f"project input changed: {name}")
    if set(plan["input_sha256"]) != {"topics.yaml", "questions.yaml", "sources.yaml", "manifest.tsv"}:
        raise ValueError("plan must freeze all four inputs")
    if not project.population:
        raise ValueError("research round requires a declared metadata population")
    check_registry_drift(project, target, record=False)
    population.check_round(target, project.population, plan["round"], record=False)
    if not plan.get("campaign") or plan["campaign"] == acquire.ROUTINE:
        raise ValueError("reuse requires a named campaign")
    if any(kind not in extract.KINDS for kind in plan.get("kinds", ["effect", "method"])):
        raise ValueError("unknown extraction kind")
    for store in (origin, target):
        for path in store.root.rglob("*.jsonl"):
            list(store.read(str(path.relative_to(store.root))))
        if store.torn_tail:
            raise ValueError("complete ledger tails required before reuse")
    origin_before, target_before = files_snapshot(origin), files_snapshot(target)
    source_rows = admissibility.collapse(origin)
    documents = origin.latest_by("documents.jsonl", "source_id")
    manifests = {e.source_id: e for e in project.manifest}
    checked = []
    ids = [one["source_id"] for one in plan["reuse"]]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate reuse source")
    for one in plan["reuse"]:
        entry = manifests[one["source_id"]]
        matches = [r for r in source_rows.values() if r.get("acquired") and r.get("url") == entry.url]
        if len(matches) != 1:
            raise ValueError(f"ambiguous/missing exact cached URL: {entry.source_id}")
        row = matches[0]
        if sha(row["stored_path"]) != one["sha256"] or row.get("sha256") != one["sha256"]:
            raise ValueError("cached raw bytes changed")
        docrow = documents[row["source_id"]]
        if docrow.get("sha256") != one["sha256"] or not docrow.get("fulltext_confirmed"):
            raise ValueError("cached normalization does not describe these bytes")
        parsed_path = Path(docrow["tei_path"])
        if sha(parsed_path) != one["parsed_sha256"]:
            raise ValueError("cached parsed bytes changed")
        doc = (html_doc.parse if docrow.get("format") == "html" else tei.parse)(parsed_path.read_bytes())
        if doc.title != one["document_title"] or not one.get("checked_by") or not one.get("identity_rationale"):
            raise ValueError("reuse identity assessment is incomplete or mismatched")
        if docrow["format"] == "pdf":
            destination = target.root / "tei" / f"{one['sha256']}.xml"
            if destination.exists() and sha(destination) != one["parsed_sha256"]:
                raise ValueError("target parsed cache differs; refusing overwrite")
        checked.append((one, entry, row, docrow))
    result = {"apply": apply, "project": project.name, "round": plan["round"],
              "manifest_sources": len(project.manifest), "verified_reuse_inputs": len(checked),
              "network_requests": 0, "model_requests": 0, "registry_sha256": project.registry_sha256}
    if apply:
        check_registry_drift(project, target)
        seeded = discover.import_manifest(target, project.manifest, round_name=plan["round"],
                                          population_policy=project.population)
        candidates = {r["source_id"]: r for r in target.latest_by("candidates.jsonl", "candidate_key").values()
                      if r.get("source_id")}
        reused = []
        for one, entry, row, docrow in checked:
            new = acquire.reuse_cached(target, candidates[entry.source_id], row,
                origin_store=origin.root, expected_sha256=one["sha256"], campaign=plan["campaign"],
                identity={k: one[k] for k in ("document_title", "checked_by", "identity_rationale", "parsed_sha256")},
                thresholds=project.gate_thresholds, policy=project.gate_policy, classes=project.classes)
            reused.append({"source_id": entry.source_id, "acquired": new["acquired"]})
            if new["acquired"] and docrow["format"] == "pdf":
                destination = target.root / "tei" / f"{one['sha256']}.xml"
                payload = Path(docrow["tei_path"]).read_bytes()
                if destination.exists() and destination.read_bytes() != payload:
                    raise ValueError("target parsed cache differs; refusing overwrite")
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not destination.exists():
                    destination.write_bytes(payload)
        class OfflineGrobid:
            def full_text(self, *args, **kwargs):
                raise RuntimeError("network parsing is forbidden in this preparatory tool")
        normalized = list(normalize.run(target, OfflineGrobid(), thresholds=project.normalize_thresholds))
        built = {}
        for kind in plan.get("kinds", ["effect", "method"]):
            built[kind] = extract.build(project, target, batch=plan["batch"], kind=kind)
        result.update(seed=seeded, reuse=reused, normalized=normalized, extraction=built,
                      admission=admissibility.admit(project, target, round_name=plan["round"]))
    if files_snapshot(origin) != origin_before:
        raise RuntimeError("original store changed")
    for name, old in target_before.items():
        path = target.path(name)
        with path.open("rb") as stream:
            if hashlib.sha256(stream.read(old["bytes"])).hexdigest() != old["sha256"]:
                raise RuntimeError(f"original target bytes changed: {name}")
    result["all_original_bytes_preserved"] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text())
    result = prepare(plan, apply=args.apply)
    if args.apply:
        root = Store(load_project(plan["project"]).name, base=plan.get("store_base", "store")).root / "audits/research-preparation"
        root.mkdir(parents=True, exist_ok=True)
        data = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False, default=str) + "\n"
        path = root / (hashlib.sha256(data.encode()).hexdigest() + ".json")
        if not path.exists():
            path.write_text(data)
        result["audit_path"] = str(path)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
