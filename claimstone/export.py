"""A verifiable snapshot of one flow: consistent because it is recomputable from a prefix.

The snapshot problem is that stage writers share no lock with this module (review F5): a ledger
can gain rows while an export reads it. So the export never trusts the file to be quiescent —
it takes the only lock that exists (`.flows.lock`, the flow writers' lock, held briefly around
the byte snapshot), cuts every ledger at its last newline (excluding and recording a torn tail),
and derives **every** output from the frozen prefix rebuilt in a temporary directory.

The export's identity is `sha256(canonical_json({"flow_id", "selector", "prefixes"}))`, so the
same ledgers under the same flow always produce the same id, and `export-verify` can check a
third party's copy two ways: the live files must still *begin with* the recorded bytes (rewritten
history breaks this), and the outputs must recompute byte-identically from those bytes (a
changed instrument or project breaks this). `created_at` and `created_by` are excluded from
both the id and the verification, because a timestamp is not evidence.
"""

from __future__ import annotations

import csv
import dataclasses
import datetime as _dt
import getpass
import hashlib
import io
import json
import pathlib
import tempfile
from typing import Any

from claimstone import admissibility, claim_records, chunk_sets, flows, portal_state, review, scope, synthesize
from claimstone.config import Project, discover_projects, load_project
from claimstone.store import Store

EXPORT_VERSION = 1

EXPORTS_LEDGER = "exports.jsonl"


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _dump(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, indent=1, ensure_ascii=False,
                      default=str).encode("utf-8")


# F19: one implementation, in portal_state, for every view and the export.
_failure_display = portal_state.failure_display


def snapshot(store: Store) -> tuple[list[dict[str, Any]], list[str]]:
    """(prefixes, torn_tails) for every ledger an export covers.

    `exports.jsonl` itself is excluded: it is bookkeeping about exports, not evidence, and
    including it would make every export a new identity however unchanged the ledgers are
    (E-T5 is the test that forces this reading). `audits/` and `exports/` directories are not
    matched by the globs and never were evidence for the outputs.
    """
    paths = sorted(store.root.glob("*.jsonl")) + sorted(store.root.glob("calls/**/*.jsonl"))
    prefixes: list[dict[str, Any]] = []
    torn: list[str] = []
    with flows._flows_lock(store):
        for path in paths:
            relative = str(path.relative_to(store.root))
            if relative.startswith(("audits/", "exports/")) or relative == EXPORTS_LEDGER:
                continue
            data = path.read_bytes()
            cut = data.rfind(b"\n")
            prefix = data[: cut + 1] if cut >= 0 else b""
            if cut != len(data) - 1:
                torn.append(relative)
            prefixes.append({
                "path": relative,
                "bytes": len(prefix),
                "rows": prefix.count(b"\n"),
                "sha256": hashlib.sha256(prefix).hexdigest(),
                "content": prefix,
            })
    return prefixes, torn


def _selector_of(flow_row: dict[str, Any]) -> scope.Selector:
    held = (flow_row.get("binding") or {}).get("selector") or {}
    return scope.Selector(held.get("round"), bool(held.get("manifest_only")))


def _csv(columns: list[str], rows: list[list[Any]]) -> bytes:
    """Deterministic CSV: sorted by the first column then the second, `\n` line ends, UTF-8."""
    ordered = sorted(rows, key=lambda row: (str(row[0]), str(row[1])))
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(ordered)
    return buffer.getvalue().encode("utf-8")


def _compute_outputs(project: Project, store: Store, selector: scope.Selector,
                     flow_row: dict[str, Any]) -> dict[str, bytes]:
    """Every output file except the manifest, derived from `store` alone."""
    outputs: dict[str, bytes] = {}

    verdicts = synthesize.verdicts(store, project=project, round_name=selector.round,
                                   manifest_only=selector.manifest_only)
    outputs["profiles.json"] = _dump(verdicts)

    admitted = admissibility.admit(project, store, round_name=selector.round,
                                   manifest_only=selector.manifest_only)
    outputs["floor.json"] = _dump(admitted)

    matrix = portal_state.question_matrix(project, store, selector)["rows"]
    outputs["questions.csv"] = _csv(
        ["id", "kind", "text", "claims_by_class", "claims", "coverage_sources",
         "coverage_examined", "direction_count", "gate_rejected_total", "awaiting_review",
         "state", "provisional", "verdict", "verdict_stale"],
        [[row["id"], row["kind"], row["text"],
          " ".join(f"{name}:{count}" for name, count in row["claims_by_class"].items()),
          row["claims"], row["coverage"].get("sources"), row["coverage"].get("examined"),
          " ".join(f"{name}:{count}" for name, count in row["direction_count"].items()),
          row["gate_rejected_total"], row["awaiting_review"], row["state"] or "",
          row["provisional"], row["verdict"] or "", row["verdict_stale"]]
         for row in matrix])

    sources = scope.source_ids(store, selector)
    scoped_candidates = scope.candidates(store, selector)
    claims, rejections = claim_records.current(store)
    claims = {key: row for key, row in claims.items() if str(row.get("source_id")) in sources}
    rejections = {key: row for key, row in rejections.items()
                  if str(row.get("source_id")) in sources}
    reviews = review.current(store)
    documents = store.latest_by("documents.jsonl", "source_id")
    chunks = chunk_sets.current(store)
    collapsed = admissibility.collapse(store)
    by_source = {str(row.get("source_id") or key): key
                 for key, row in scoped_candidates.items()}

    claim_rows = []
    for claim_id, row in claims.items():
        source_id = str(row.get("source_id"))
        chunk = chunks.get(str(row.get("chunk_id") or "")) if row.get("chunk_id") else None
        quote = str(row.get("evidence_quote") or "")
        document = documents.get(source_id) or {}
        acquisition = collapsed.get(by_source.get(source_id) or "") or {}
        claim_rows.append([
            claim_id, row.get("question_id"), source_id, row.get("source_class"),
            row.get("stance"), quote, row.get("chunk_id"),
            (chunk or {}).get("generation_sha256") or (document.get("generation_sha256")),
            document.get("html_parser_version"), document.get("jats_parser_version"),
            acquisition.get("sha256"), acquisition.get("licence"),
            (reviews.get(claim_id) or {}).get("verdict"),
            quote in str((chunk or {}).get("text") or "") if chunk is not None else "",
        ])
    outputs["claims.csv"] = _csv(
        ["claim_id", "question_id", "source_id", "source_class", "stance", "evidence_quote",
         "chunk_id", "generation_sha256", "html_parser_version", "jats_parser_version",
         "acquisition_sha256", "licence", "review_verdict", "quote_found"],
        claim_rows)

    outputs["rejections.csv"] = _csv(
        ["claim_id", "source_id", "failure", "detail"],
        [[key, row.get("source_id"), row.get("failure"), row.get("detail")]
         for key, row in rejections.items()])

    outputs["acquisition.csv"] = _csv(
        ["candidate_key", "source_id", "source_class", "counted_acquired", "failure_class",
         "failure_display", "provenance", "licence"],
        [[key, row.get("source_id") or key, row.get("source_class"),
          bool((collapsed.get(key) or {}).get("acquired")),
          (collapsed.get(key) or {}).get("failure_class"),
          _failure_display((collapsed.get(key) or {}).get("failure_class")),
          (collapsed.get(key) or {}).get("provenance"),
          (collapsed.get(key) or {}).get("licence")]
         for key, row in scoped_candidates.items()])

    outputs["report.md"] = _report(project, selector, flow_row, admitted, matrix, verdicts,
                                   flows.binding_state(project, store, flow_row))
    return outputs


def _report(project: Project, selector: scope.Selector, flow_row: dict[str, Any],
            admitted: dict[str, Any], matrix: list[dict[str, Any]],
            verdicts: dict[str, Any], binding: dict[str, Any]) -> bytes:
    lines: list[str] = []
    lines.append(f"# Export — {project.name}")
    rounds = selector.round or "(whole store)"
    manifest_note = " · manifest-only" if selector.manifest_only else ""
    lines.append(f"Selector: round {rounds}{manifest_note} · flow "
                 f"{str(flow_row.get('flow_id'))[:12]}")
    lines.append(f"Binding state: {binding['state']}"
                 + (f" (differs in {', '.join(binding['differences'])})"
                    if binding["differences"] else ""))
    if flow_row.get("bound_after_data"):
        lines.append("")
        lines.append("Bound after data existed: rows written before binding are not verified "
                     "against this protocol.")
    lines.append("")
    floor = portal_state.floor_panel(admitted) or {}
    overall = floor.get("overall") or {}
    rate = overall.get("rate")
    rate_text = f"{rate:.2f}" if isinstance(rate, (int, float)) else "—"
    lines.append(f"Floor: {overall.get('basis')} {overall.get('basis_count')} of "
                 f"{overall.get('found')} found = {rate_text} against floor "
                 f"{overall.get('floor')} (v{overall.get('floor_version')}, "
                 f"{overall.get('floor_set_at')}) — {overall.get('status')}")
    for name, bucket in (floor.get("by_class") or {}).items():
        lines.append(f"- {name}: {bucket['basis_count']}/{bucket['found']} · needs "
                     f"{bucket['needed']} more · floor {bucket['floor']}")
    for sentence in floor.get("sentences") or []:
        lines.append(f"- {sentence}")
    lines.append("")
    lines.append("## Questions")
    lines.append("")
    lines.append("| id | kind | claims | coverage | state | verdict |")
    lines.append("|---|---|---|---|---|---|")
    for row in matrix:
        coverage = (f"{row['coverage'].get('sources')}/{row['coverage'].get('examined')}"
                    if row["coverage"].get("sources") is not None else "—")
        verdict = row["verdict"] or ("(stale)" if row["verdict_stale"] else "")
        lines.append(f"| {row['id']} | {row['kind']} | {row['claims']} | {coverage} "
                     f"| {row['state'] or ''} | {verdict} |")
    lines.append("")
    lines.append("## Disclosures")
    lines.append("")
    lines.append("- No verdict exists unless a person signed it: `adjudicate` is the only "
                 "command that writes one, and an agent does not sign.")
    lines.append("- NO_VERIFIED_CLAIM is the engine's own categorical outcome, not "
                 "NEVER_ASKED and not a verdict.")
    disclosure = floor.get("disclosure") or (
        "Admission reads confirmations and ledger repairs across the whole project (review F1).")
    lines.append(f"- {disclosure}")
    lines.append(f"- No controlled family-wise error rate across the "
                 f"{verdicts.get('no_controlled_error_rate_across', len(matrix))} questions "
                 "profiled.")
    return ("\n".join(lines) + "\n").encode("utf-8")


def export(project: Project, store: Store, flow_id: str) -> tuple[pathlib.Path, bool]:
    """Freeze one flow's ledgers and derive every output from the frozen bytes.

    Returns (directory, created_now). An existing identical export is returned untouched.
    Only flows can be exported: a legacy selector must be bound with `flow create` first,
    because an export is a claim about a protocol as well as about bytes.
    """
    flow_row = flows.flows(store).get(str(flow_id))
    if flow_row is None:
        raise ValueError(f"unknown flow id: {flow_id}")
    selector = _selector_of(flow_row)

    prefixes, torn = snapshot(store)
    instruments = portal_state.instrument_versions()
    identity_payload = {"flow_id": str(flow_id), "selector": selector.as_dict(),
                        "prefixes": [{key: prefix[key] for key in
                                      ("path", "bytes", "rows", "sha256")}
                                     for prefix in sorted(prefixes, key=lambda p: p["path"])]}
    # The same bytes read by a different instrument or under a different live protocol are a
    # different export: without these, a re-export after a gate change answered "exists" with
    # outputs the current code would no longer produce.
    export_id = hashlib.sha256(_canonical({
        **identity_payload, "export_version": EXPORT_VERSION, "instrument_versions": instruments,
        "protocol_sha256": flows.protocol_digest(project),
        "registry_sha256": project.registry_sha256,
    }).encode("utf-8")).hexdigest()
    directory = store.root / "exports" / export_id
    if directory.exists():
        return directory, False

    with tempfile.TemporaryDirectory() as tmp:
        frozen_root = pathlib.Path(tmp) / project.name
        for prefix in prefixes:
            target = frozen_root / prefix["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(prefix["content"])
        frozen = Store(project.name, base=tmp)
        outputs = _compute_outputs(project, frozen, selector, flow_row)
        binding = flows.binding_state(project, frozen, flow_row)

        revision, dirty = flows._code_identity(project.root)
        manifest = {
            "export_version": EXPORT_VERSION,
            "flow_id": str(flow_id),
            "flow": flow_row,
            "binding_state": binding,
            "selector": selector.as_dict(),
            "prefixes": identity_payload["prefixes"],
            "torn_tails": sorted(torn),
            "code_revision": revision,
            "code_dirty": dirty,
            "instrument_versions": instruments,
            "protocol_sha256": flows.protocol_digest(project),
            "registry_sha256": project.registry_sha256,
            "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "created_by": getpass.getuser(),
        }
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "manifest.json").write_bytes(_dump(manifest))
        for name, payload in outputs.items():
            (directory / name).write_bytes(payload)

    row = {"export_id": export_id, "flow_id": str(flow_id), "path": str(directory),
           "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")}
    with flows._flows_lock(store):
        store.append(EXPORTS_LEDGER, row)
    return directory, True


def verify(directory: pathlib.Path | str, projects_dir: pathlib.Path | str) -> list[str]:
    """Check an export against the live store and the live project. Problems, as lines.

    Empty list means the export still holds: the live ledgers begin with the recorded bytes,
    and every output recomputes identically from those bytes under the current instruments.
    """
    directory = pathlib.Path(directory)
    problems: list[str] = []
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        return [f"MANIFEST_MISSING {directory}"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    store_root = directory.parent.parent
    flow_row = manifest.get("flow") or {}
    project_name = str((flow_row.get("binding") or {}).get("project")
                       or store_root.name)
    selector = scope.Selector((manifest.get("selector") or {}).get("round"),
                              bool((manifest.get("selector") or {}).get("manifest_only")))

    for prefix in manifest.get("prefixes") or []:
        live = store_root / prefix["path"]
        if not live.exists():
            problems.append(f"PREFIX_CHANGED {prefix['path']}")
            continue
        data = live.read_bytes()
        if (len(data) < prefix["bytes"]
                or hashlib.sha256(data[:prefix["bytes"]]).hexdigest() != prefix["sha256"]):
            problems.append(f"PREFIX_CHANGED {prefix['path']}")

    roots = {root.name: root for root in discover_projects(projects_dir)}
    root = roots.get(project_name)
    if root is None:
        problems.append(f"PROJECT_NOT_FOUND {project_name}")
        return problems
    project = load_project(root)

    with tempfile.TemporaryDirectory() as tmp:
        frozen_root = pathlib.Path(tmp) / project_name
        for prefix in manifest.get("prefixes") or []:
            target = frozen_root / prefix["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            source = store_root / prefix["path"]
            if source.exists():
                target.write_bytes(source.read_bytes()[:prefix["bytes"]])
            else:
                target.write_bytes(b"")
        frozen = Store(project_name, base=tmp)
        outputs = _compute_outputs(project, frozen, selector, flow_row)
        for name, payload in outputs.items():
            held = directory / name
            if not held.exists() or held.read_bytes() != payload:
                problems.append(f"OUTPUT_DIFFERS {name}")
    return problems
