"""Flows: a round selector bound to the digests of the protocol it is supposed to run under.

A flow never supplies a value to a computation (review F4): floors, registry and population are
always read from the live project, and the binding is only **compared** against them. When the
comparison fails the flow is `*_DRIFTED` — a named state, read-only, never a crash — because a
frozen snapshot that drove computation would make the portal disagree with the CLI on the same
round.

Identity is the binding alone: `flow_id = sha256(canonical_json(binding))`. Titles, timestamps
and creators are display metadata and never change who a flow is, so creating the same binding
twice is the same flow, once. The append-only ledger is `flows.jsonl`, and every write takes an
exclusive `flock` on `.flows.lock` and rereads under it — the pattern `source_selection` uses —
so two concurrent creates cannot both decide they are first.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import getpass
import hashlib
import json
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from claimstone import scope
from claimstone.config import Project, check_registry_drift
from claimstone.store import Store

FLOW_VERSION = 2

FLOWS = "flows.jsonl"

INPUT_FILES = ("topics.yaml", "questions.yaml", "sources.yaml", "manifest.tsv")


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def input_file_digests(project_root: Path) -> dict[str, str | None]:
    """Sha256 of each input file's bytes (symlinks followed), or None where absent.

    Recorded for information only: a whitespace edit must not read as drift, and the semantic
    digest below is what decides. This is the reasoning of `config.registry_digest`'s docstring,
    applied to the whole protocol.
    """
    digests: dict[str, str | None] = {}
    for name in INPUT_FILES:
        path = Path(project_root) / name
        digests[name] = (hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None)
    return digests


def protocol_digest(project: Project) -> str:
    """Sha256 of the canonical JSON of the semantic protocol, built from the loaded Project.

    Everything a round's figures depend on that is not the ledger: classes and their floors, the
    project floor's provenance, topics, the registry, the manifest, the gate and normalize
    thresholds, the extraction vocabulary, the citation channel rule and the population policy.
    """
    def as_list(items: Any) -> list[Any]:
        # dataclasses.asdict recurses; a non-dataclass element would be a contract change worth
        # refusing over guessing. All three lists are frozen dataclasses today (see D82).
        return [dataclasses.asdict(item) if dataclasses.is_dataclass(item) else dict(item)
                for item in items]

    semantic = {
        "classes": as_list(project.classes),
        "acquisition_floor": project.acquisition_floor,
        "floor_version": project.floor_version, "floor_set_at": project.floor_set_at,
        "excluded_hosts": sorted(project.excluded_hosts),
        "topics": as_list(project.topics),
        "registry_version": project.registry_version, "registry_sha256": project.registry_sha256,
        "manifest": as_list(project.manifest),
        "gate_thresholds": project.gate_thresholds, "gate_policy": project.gate_policy,
        "normalize_thresholds": project.normalize_thresholds,
        "extraction": project.extraction, "citation_channel": project.citation_channel,
        "population": project.population,
    }
    return hashlib.sha256(_canonical(semantic).encode("utf-8")).hexdigest()


def _population_sha(store: Store, round_name: str | None) -> str | None:
    """The population predicate digest recorded for the round, or None where none was declared."""
    if round_name is None:
        return None
    held = store.latest_by("populations.jsonl", "round").get(round_name)
    return str(held.get("policy_sha256")) if held else None


def _code_identity(root: Path) -> tuple[str | None, bool | None]:
    """(revision, dirty) from git, or (None, None) when git cannot answer. Never guessed."""
    revision: str | None = None
    dirty: bool | None = None
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, timeout=5,
                              capture_output=True, text=True)
        if head.returncode == 0:
            revision = head.stdout.strip() or None
    except (subprocess.SubprocessError, OSError):
        revision = None
    try:
        status = subprocess.run(["git", "status", "--porcelain"], cwd=root, timeout=5,
                                capture_output=True, text=True)
        if status.returncode == 0:
            dirty = bool(status.stdout.strip())
    except (subprocess.SubprocessError, OSError):
        dirty = None
    return revision, dirty


@contextmanager
def _flows_lock(store: Store):
    """Use the project-wide lock for a flow's read-modify-write transaction."""
    with store.writer_lock():
        yield


def binding_id(binding: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(binding).encode("utf-8")).hexdigest()


def invalid_flows(store: Store) -> list[str]:
    """`created` rows whose `flow_id` is not the hash of their binding. A hand-edited row would
    otherwise keep a trusted id while describing a different protocol; it is excluded from
    `flows()` and named here, never repaired."""
    return [str(row.get("flow_id")) for row in store.read(FLOWS)
            if row.get("event") == "created"
            and str(row.get("flow_id")) != binding_id(row.get("binding") or {})]


def flows(store: Store) -> dict[str, dict[str, Any]]:
    """flow_id -> the created row, with the latest title event merged in as `title`.

    Only rows whose id is the hash of their binding count as flows (see `invalid_flows`)."""
    out: dict[str, dict[str, Any]] = {}
    for row in store.read(FLOWS):
        if (row.get("event") == "created" and row.get("flow_id")
                and str(row["flow_id"]) == binding_id(row.get("binding") or {})):
            out[str(row["flow_id"])] = dict(row)
        elif row.get("event") == "title" and row.get("flow_id") in out:
            out[str(row["flow_id"])]["title"] = row.get("title")
    return out


def binding_state(project: Project, store: Store, flow: dict[str, Any]) -> dict[str, Any]:
    """Compare the binding against the live project. The snapshot is checked, never used (F4)."""
    binding = flow.get("binding") or {}
    differences: list[str] = []
    if binding.get("registry_sha256") != project.registry_sha256:
        differences.append("registry_sha256")
    if binding.get("registry_version") != project.registry_version:
        differences.append("registry_version")
    if binding.get("protocol_sha256") != protocol_digest(project):
        differences.append("protocol_sha256")
    selector = (binding.get("selector") or {})
    if binding.get("population_sha256") != _population_sha(store, selector.get("round")):
        differences.append("population_sha256")
    if "registry_sha256" in differences or "registry_version" in differences:
        state = "REGISTRY_DRIFTED"       # checked first: it invalidates the others' meaning
    elif "protocol_sha256" in differences:
        state = "PROTOCOL_DRIFTED"
    elif "population_sha256" in differences:
        state = "POPULATION_DRIFTED"
    else:
        state = "CURRENT"
    return {"state": state, "differences": differences,
            "bound_after_data": bool(flow.get("bound_after_data"))}


def legacy_selectors(store: Store, flow_rows: list[dict[str, Any]] | Any) -> list[scope.Selector]:
    """Every candidate-bearing round no flow has bound: shown as 'legacy: protocol not verified'."""
    bound = {(row.get("binding") or {}).get("selector", {}).get("round")
             for row in flow_rows}
    rounds = {str(row.get("round")) for row in store.read("candidates.jsonl") if row.get("round")}
    return [scope.Selector(name, False) for name in sorted(rounds - {str(b) for b in bound if b})]


def set_title(store: Store, flow_id: str, title: str, by: str) -> dict[str, Any]:
    """Append a title event. Titles are display metadata and never change the flow's identity."""
    row = {"event": "title", "flow_id": str(flow_id), "title": title,
           "at": _now(), "by": by}
    with _flows_lock(store):
        held = {str(row["flow_id"]) for row in store.read(FLOWS) if row.get("event") == "created"}
        if str(flow_id) not in held:
            raise ValueError(f"unknown flow id: {flow_id}")
        store.append(FLOWS, row)
    return row


def create(project: Project, store: Store, *, selector: scope.Selector, title: str,
           derived_from: str | None = None, relation: str | None = None
           ) -> tuple[dict[str, Any], bool]:
    """Bind a selector to the protocol as it stands. Idempotent on the binding alone.

    Returns (row, created_now). A registry that already drifted from what the store recorded
    refuses here too (invariant 5), without recording anything: the check is the same one every
    store-opening command runs, with `record=False` because a flow is not a stage command.
    """
    check_registry_drift(project, store, record=False)
    if derived_from is not None and relation is None:
        raise ValueError("--derived-from needs --relation supersedes or derived_from")
    if relation is not None and derived_from is None:
        raise ValueError("--relation needs --derived-from: a relation names another flow")
    if relation not in (None, "supersedes", "derived_from"):
        raise ValueError(f"unknown relation: {relation}")

    # A new flow must freeze its declared population before discovery writes
    # candidates. Otherwise the first discovery run creates populations.jsonl
    # and immediately makes the flow appear drifted.
    with store.writer_lock():
        if derived_from is not None and derived_from not in flows(store):
            raise ValueError(f"unknown flow to derive from: {derived_from}")
        if selector.round is not None and not any(
                row.get('round') == selector.round for row in store.read('candidates.jsonl')):
            from claimstone import population as population_mod
            population_mod.check_round(store, project.population, selector.round)
        population = _population_sha(store, selector.round)
    binding = {
        "project": project.name,
        "selector": selector.as_dict(),
        "registry_version": project.registry_version,
        "registry_sha256": project.registry_sha256,
        "protocol_sha256": protocol_digest(project),
        "population_sha256": population,
        "derived_from": derived_from,
        "relation": relation,
    }
    flow_id = binding_id(binding)
    revision, dirty = _code_identity(project.root)
    in_scope = scope.candidates(store, selector)
    row = {
        "event": "created",
        "flow_version": FLOW_VERSION,
        "flow_id": flow_id,
        "binding": binding,
        "input_files": input_file_digests(project.root),
        # Rows written before binding are facts about a protocol nobody froze at the time (F10):
        # recorded, and disclosed wherever the flow is shown.
        "bound_after_data": bool(in_scope),
        "candidates_at_binding": len(in_scope),
        "title": title,
        "created_at": _now(),
        "created_by": getpass.getuser(),
        "code_revision": revision,
        "code_dirty": dirty,
    }
    with _flows_lock(store):
        held = set(flows(store))
        if derived_from is not None and derived_from not in held:
            raise ValueError(f"unknown flow to derive from: {derived_from}")
        if flow_id in held:
            return flows(store)[flow_id], False
        store.append(FLOWS, row)
    return row, True
