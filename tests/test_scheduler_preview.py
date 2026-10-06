"""The scheduler preview must remain read-only and refuse misleading work."""

from __future__ import annotations

import hashlib
import json
import shutil

from claimstone import cli, flows, scheduler_preview
from claimstone.config import load_project
from claimstone.scope import Selector
from claimstone.store import Store


def _fixture(tmp_path):
    root = tmp_path / "example-news-and-returns"
    shutil.copytree("projects/example-news-and-returns", root)
    return root, load_project(root), Store(root.name, base=tmp_path / "store")


def _hashes(store):
    return {str(p.relative_to(store.root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in store.root.rglob("*") if p.is_file()}


def test_empty_new_round_is_work_proposed_without_any_write(tmp_path, capsys):
    root, project, store = _fixture(tmp_path)
    flow, _ = flows.create(project, store, selector=Selector("new"), title="new round")
    before = _hashes(store)
    assert cli.main(["scheduler-preview", str(root), flow["flow_id"],
                     "--store", str(tmp_path / "store")]) == 0
    row = json.loads(capsys.readouterr().out)
    assert row["candidate_count"] == 0
    assert row["candidate_scope_state"] == "EMPTY_NOT_A_CLOSED_COHORT"
    assert row["floor"] is None
    assert row["state"] == "WORK_PROPOSED"
    assert row["proposals"][0]["category"] == "DISCOVERY"
    assert row["authorized"] is False
    assert row["execution"] == "PREVIEW_ONLY"
    assert _hashes(store) == before


def test_other_round_candidate_does_not_make_new_round_complete(tmp_path):
    root, project, store = _fixture(tmp_path)
    store.append("candidates.jsonl", {"candidate_key": "doi:10.1/old", "round": "old",
                                      "source_id": "S01", "source_class": "ACA"})
    flow, _ = flows.create(project, store, selector=Selector("new"), title="new")
    row = scheduler_preview.preview(project, store, flow["flow_id"])
    assert row["candidate_count"] == 0
    assert row["proposals"][0]["category"] == "DISCOVERY"


def test_late_binding_and_corrupt_acquisition_are_blockers(tmp_path):
    root, project, store = _fixture(tmp_path)
    store.append("candidates.jsonl", {"candidate_key": "doi:10.1/a", "round": "r1",
                                      "source_id": "S01", "source_class": "ACA"})
    flow, _ = flows.create(project, store, selector=Selector("r1"), title="late")
    row = scheduler_preview.preview(project, store, flow["flow_id"])
    assert row["state"] == "BLOCKED"
    assert any(b["code"] == "LATE_FLOW_BINDING" for b in row["blockers"])

    store.path("acquisitions.jsonl").write_text('{"broken":\n{"valid":true}\n')
    row = scheduler_preview.preview(project, store, flow["flow_id"])
    assert row["state"] == "BLOCKED"
    assert any(b["code"] in {"LEDGER_CORRUPT", "INTEGRITY"} for b in row["blockers"])


def test_protocol_change_blocks_preview(tmp_path):
    root, project, store = _fixture(tmp_path)
    flow, _ = flows.create(project, store, selector=Selector("r1"), title="one")
    sources = root / "sources.yaml"
    sources.write_text(sources.read_text().replace("acquisition_floor: 0.80",
                                                   "acquisition_floor: 0.75"))
    row = scheduler_preview.preview(load_project(root), store, flow["flow_id"])
    assert row["state"] == "BLOCKED"
    assert any(b["code"] == "PROTOCOL_DRIFT" for b in row["blockers"])
