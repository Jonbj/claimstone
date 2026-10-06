"""flows: binding a selector to protocol digests, and detecting drift — spec §3.7.

Everything runs against a copied project in tmp_path with a tmp store: no ledger under the real
`store/` is opened for writing anywhere in this file.
"""

from __future__ import annotations

import hashlib
import shutil

import pytest

from claimstone import cli, flows
from claimstone.config import load_project
from claimstone.scope import Selector
from claimstone.store import Store

SOURCE_PROJECT = "projects/example-news-and-returns"


@pytest.fixture()
def workspace(tmp_path):
    """A copied project plus its store, and the paths to reach them."""
    root = tmp_path / "example-news-and-returns"
    shutil.copytree(SOURCE_PROJECT, root)
    return root, Store(root.name, base=tmp_path / "store")


def _store_hashes(store: Store) -> dict[str, str]:
    return {
        str(path.relative_to(store.root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(store.root.rglob("*")) if path.is_file()
    }


def test_create_twice_is_one_flow(workspace):
    """F-T1: the same binding twice gives the same flow_id, one ledger row, created_now False."""
    root, store = workspace
    project = load_project(root)
    row, created = flows.create(project, store, selector=Selector("r1"), title="one")
    assert created is True
    again, created_now = flows.create(project, store, selector=Selector("r1"), title="one")
    assert created_now is False
    assert again["flow_id"] == row["flow_id"]
    rows = [r for r in store.read("flows.jsonl") if r.get("event") == "created"]
    assert len(rows) == 1


def test_a_title_change_does_not_change_identity(workspace):
    """F-T2: the title is metadata; the flow_id hashes the binding alone."""
    root, store = workspace
    project = load_project(root)
    row, _ = flows.create(project, store, selector=Selector("r1"), title="before")
    flows.set_title(store, row["flow_id"], "after", by="a person")
    held = flows.flows(store)
    assert held[row["flow_id"]]["title"] == "after"
    row_again, created = flows.create(project, store, selector=Selector("r1"), title="before")
    assert created is False
    assert row_again["flow_id"] == row["flow_id"]


def test_whitespace_is_not_drift_but_semantic_edits_are(workspace):
    """F-T3: comments and whitespace keep CURRENT; a question text under the same version is
    REGISTRY_DRIFTED; a floor change is PROTOCOL_DRIFTED."""
    root, store = workspace
    project = load_project(root)
    row, _ = flows.create(project, store, selector=Selector("r1"), title="t")

    questions = root / "questions.yaml"
    text = questions.read_text(encoding="utf-8")
    questions.write_text("# a comment the digest must ignore\n" + text, encoding="utf-8")
    assert flows.binding_state(load_project(root), store, row)["state"] == "CURRENT"

    marker = "A future return is neither semantic ground truth"
    original_questions = questions.read_text(encoding="utf-8")
    questions.write_text(original_questions.replace(marker, "An edited variant — " + marker),
                         encoding="utf-8")
    assert flows.binding_state(load_project(root), store, row)["state"] == "REGISTRY_DRIFTED"

    questions.write_text(original_questions, encoding="utf-8")  # registry checked before protocol
    assert flows.binding_state(load_project(root), store, row)["state"] == "CURRENT"
    sources = root / "sources.yaml"
    sources.write_text(
        sources.read_text(encoding="utf-8").replace("acquisition_floor: 0.80",
                                                    "acquisition_floor: 0.75"),
        encoding="utf-8")
    state = flows.binding_state(load_project(root), store, row)
    assert state["state"] == "PROTOCOL_DRIFTED"
    assert state["differences"] == ["protocol_sha256"]


def test_bound_after_data_follows_candidates(workspace):
    """F-T4: a round with candidates binds after data; an empty one does not."""
    root, store = workspace
    project = load_project(root)
    store.append("candidates.jsonl", {
        "candidate_key": "k1", "source_id": "S01", "round": "r1", "channel": "keyword"})
    row, _ = flows.create(project, store, selector=Selector("r1"), title="t")
    assert row["bound_after_data"] is True
    assert row["candidates_at_binding"] == 1
    row2, _ = flows.create(project, store, selector=Selector("r-empty"), title="t")
    assert row2["bound_after_data"] is False
    assert row2["candidates_at_binding"] == 0


def test_legacy_selectors_list_unbound_rounds(workspace):
    """F-T5: rounds with candidates and no flow are legacy, sorted, manifest_only False."""
    root, store = workspace
    project = load_project(root)
    store.append("candidates.jsonl", {
        "candidate_key": "k1", "source_id": "S01", "round": "r2", "channel": "keyword"})
    store.append("candidates.jsonl", {
        "candidate_key": "k2", "source_id": "S02", "round": "r1", "channel": "keyword"})
    flows.create(project, store, selector=Selector("r1"), title="t")
    legacy = flows.legacy_selectors(store, flows.flows(store).values())
    assert legacy == [Selector("r2", False)]


def test_unknown_derived_from_exits_2_and_writes_nothing(workspace, capsys):
    """F-T6: an unknown --derived-from is a usage error, and no ledger row appears."""
    root, store = workspace
    code = cli.main(["flow", "create", str(root), "--store", str(store.root.parent),
                     "--title", "t", "--round", "r1",
                     "--derived-from", "f" * 64, "--relation", "supersedes"])
    assert code == 2
    assert not store.path("flows.jsonl").exists()
    assert "unknown flow" in capsys.readouterr().err


def test_flow_check_exit_codes(workspace, capsys):
    """F-T7: CURRENT exits 0, drift exits 4, an unknown id exits 2."""
    root, store = workspace
    project = load_project(root)
    row, _ = flows.create(project, store, selector=Selector("r1"), title="t")
    base = ["flow", "check", str(root), "--store", str(store.root.parent)]
    assert cli.main(base + [row["flow_id"]]) == 0

    sources = root / "sources.yaml"
    sources.write_text(
        sources.read_text(encoding="utf-8").replace("acquisition_floor: 0.80",
                                                    "acquisition_floor: 0.75"),
        encoding="utf-8")
    assert cli.main(base + [row["flow_id"]]) == 4

    assert cli.main(base + ["0" * 64]) == 2
    assert "unknown flow id" in capsys.readouterr().err


def test_list_and_check_write_nothing(workspace, capsys):
    """F-T8: the read commands leave every file under the store byte-identical."""
    root, store = workspace
    project = load_project(root)
    store.append("candidates.jsonl", {
        "candidate_key": "k1", "source_id": "S01", "round": "r1", "channel": "keyword"})
    row, _ = flows.create(project, store, selector=Selector("r1"), title="t")
    before = _store_hashes(store)

    base = ["--store", str(store.root.parent)]
    assert cli.main(["flow", "list", str(root)] + base + ["--json"]) == 0
    assert cli.main(["flow", "check", str(root)] + base + [row["flow_id"]]) == 0
    assert cli.main(["flow", "list", str(root)] + base) == 0
    capsys.readouterr()
    assert _store_hashes(store) == before
