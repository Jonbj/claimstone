"""export / export-verify: a snapshot is trustworthy because it recomputes — spec §5.4.

The workspace is the same one `test_portal_state` builds: a complete r1 flow and a legacy r2,
under tmp_path only. Nothing here touches the real store.
"""

from __future__ import annotations

import shutil

import pytest

from claimstone import cli, export, flows, scope
from claimstone.config import load_project
from claimstone.store import Store
from tests.test_portal_state import build_workspace


@pytest.fixture()
def workspace(tmp_path):
    return build_workspace(tmp_path)


def _export(workspace, capsys) -> tuple[str, str]:
    _projects_dir, store_dir, _project, _store = workspace
    project = load_project(workspace[2].root)
    flow_id = next(iter(flows.flows(workspace[3])))
    code = cli.main(["export", str(project.root), flow_id, "--store", str(store_dir)])
    captured = capsys.readouterr()
    assert code == 0, captured.out
    export_id = captured.out.splitlines()[0].split()[1]
    return flow_id, export_id


def _export_dir(workspace, export_id):
    _projects_dir, store_dir, _project, _store = workspace
    return store_dir / workspace[2].name / "exports" / export_id


def test_export_then_verify_on_unchanged_fixture(workspace, capsys):
    """E-T1: round-trip on an untouched fixture verifies with exit 0."""
    _flow_id, export_id = _export(workspace, capsys)
    assert len(export_id) == 64
    code = cli.main(["export-verify", str(_export_dir(workspace, export_id)),
                     "--projects-dir", str(workspace[0])])
    assert code == 0, capsys.readouterr().out
    assert "verified" in capsys.readouterr().out


def test_appended_rows_verify_but_change_identity(workspace, capsys):
    """E-T2: append-only growth keeps the prefix (verify 0) and forces a new export id."""
    _flow_id, first = _export(workspace, capsys)
    store = workspace[3]
    store.append("claims.jsonl", {
        "claim_id": "c-new", "question_id": "Q03", "source_id": "S01",
        "source_class": "ACA", "harvested_at": "2026-10-06T10:00:00+00:00",
        "gate_revision": 1})
    code = cli.main(["export-verify", str(_export_dir(workspace, first)),
                     "--projects-dir", str(workspace[0])])
    assert code == 0
    capsys.readouterr()  # consume the verifier's line; the next export reads its own output

    _flow_id, second = _export(workspace, capsys)
    assert second != first
    assert _export_dir(workspace, second).exists()


def test_rewritten_history_fails_verification(workspace, capsys):
    """E-T3: rewriting an early byte reports PREFIX_CHANGED and exits 5."""
    _flow_id, export_id = _export(workspace, capsys)
    target = workspace[3].path("candidates.jsonl")
    data = bytearray(target.read_bytes())
    data[10] = data[10] ^ 0x20  # flip one character inside the recorded prefix
    target.write_bytes(bytes(data))
    code = cli.main(["export-verify", str(_export_dir(workspace, export_id)),
                     "--projects-dir", str(workspace[0])])
    assert code == 5
    out = capsys.readouterr().out
    assert "PREFIX_CHANGED candidates.jsonl" in out


def test_a_torn_tail_is_excluded_and_listed(workspace, capsys):
    """E-T4: a half-written final line is not in the prefix and is named in torn_tails."""
    import json as _json

    store = workspace[3]
    with store.path("reviews.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"claim_id": "c1", "half')
    _flow_id, export_id = _export(workspace, capsys)
    directory = _export_dir(workspace, export_id)
    manifest = _json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["torn_tails"] == ["reviews.jsonl"]
    prefix = next(p for p in manifest["prefixes"] if p["path"] == "reviews.jsonl")
    assert b'{"claim_id": "c1", "half' not in (directory / "manifest.json").read_bytes()
    assert prefix["bytes"] < store.path("reviews.jsonl").read_bytes().__len__()
    # And the frozen outputs never saw the fragment: verification still holds.
    code = cli.main(["export-verify", str(directory), "--projects-dir", str(workspace[0])])
    assert code == 0


def test_export_twice_is_one_directory(workspace, capsys):
    """E-T5: unchanged ledgers give the same id, and the second call writes nothing."""
    _flow_id, first = _export(workspace, capsys)
    directory = _export_dir(workspace, first)
    before = {path: path.read_bytes() for path in sorted(directory.rglob("*"))
              if path.is_file()}
    project = load_project(workspace[2].root)
    code = cli.main(["export", str(project.root), _flow_id,
                     "--store", str(workspace[1])])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.splitlines()[0] == f"exists {first}"
    after = {path: path.read_bytes() for path in sorted(directory.rglob("*"))
             if path.is_file()}
    assert before == after
    exports_ledger = workspace[3].path("exports.jsonl").read_text(encoding="utf-8")
    assert exports_ledger.count("\n") == 1  # one append, not two


def test_no_raw_bytes_reach_the_export(workspace, capsys):
    """E-T6: a sentinel written under raw/ appears in no exported file."""
    store = workspace[3]
    raw = store.root / "raw"
    raw.mkdir(exist_ok=True)
    sentinel = b"SENTINEL-RAW-CONTENT-should-never-export"
    (raw / "deadbeef.pdf").write_bytes(sentinel)
    _flow_id, export_id = _export(workspace, capsys)
    directory = _export_dir(workspace, export_id)
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            assert sentinel not in path.read_bytes(), path.name
            assert b"SENTINEL" not in path.read_bytes(), path.name


def test_an_r1_export_carries_no_r2_source(workspace, capsys):
    """E-T7: the export of the r1 flow contains r2's source id nowhere."""
    _flow_id, export_id = _export(workspace, capsys)
    directory = _export_dir(workspace, export_id)
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            assert "S03" not in path.read_text(encoding="utf-8"), path.name
            assert "r2-a" not in path.read_text(encoding="utf-8"), path.name


def test_a_changed_protocol_is_a_new_export(workspace, capsys):
    """R10: the same bytes under a changed live protocol are a different export, never `exists`."""
    _flow_id, first = _export(workspace, capsys)
    sources = workspace[2].root / "sources.yaml"
    sources.write_text(sources.read_text(encoding="utf-8").replace(
        "acquisition_floor: 0.80", "acquisition_floor: 0.75"), encoding="utf-8")
    assert "acquisition_floor: 0.75" in sources.read_text(encoding="utf-8")
    _flow_id, second = _export(workspace, capsys)
    assert second != first
