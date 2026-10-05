"""A cache transfer creates fresh work without importing old answers or using the network."""
import pytest

from claimstone import normalize, tei
from claimstone.store import Store
from tests.test_normalize import PAPER, FakeGrobid
from tests.test_population_reuse import configured, origin
from tools.prepare_research_round import prepare, sha
from tools.replay_answers import files_snapshot


def fixture(tmp_path):
    project = configured(tmp_path)
    manifest = project.root / "manifest.tsv"
    manifest.write_text("source_id\tclass\tformat\turl\ttitle\nS1\tWP\tpdf\thttps://archive.example/a.pdf\tNews versus Sentiment\n")
    old = Store("origin", base=tmp_path / "stores")
    row = origin(tmp_path)
    row.update(source_id="OLD", gate={"kind": "PDF_FULLTEXT"})
    old.append("acquisitions.jsonl", row)
    doc = next(iter(normalize.run(old, FakeGrobid())))
    old.append("claims.jsonl", {"claim_id": "never-transfer", "claim": "old scientific result"})
    plan = {"project": str(project.root), "origin_project": "origin",
            "store_base": str(tmp_path / "stores"), "origin_store_base": str(tmp_path / "stores"),
            "round": "new-round", "campaign": "verified-reuse", "batch": "fresh-reading",
            "input_sha256": {name: sha(project.root / name) for name in
                ("topics.yaml", "questions.yaml", "sources.yaml", "manifest.tsv")},
            "reuse": [{"source_id": "S1", "sha256": row["sha256"],
                "parsed_sha256": sha(doc["tei_path"]), "document_title": tei.parse(PAPER).title,
                "checked_by": "synthetic test", "identity_rationale": "exact synthetic title"}]}
    return plan, old, Store(project.name, base=tmp_path / "stores")


def test_preview_is_read_only_and_apply_creates_new_readings(tmp_path):
    plan, old, target = fixture(tmp_path)
    before = files_snapshot(old)
    assert prepare(plan)["verified_reuse_inputs"] == 1
    assert not target.root.exists()
    result = prepare(plan, apply=True)
    assert result["network_requests"] == result["model_requests"] == 0
    assert result["all_original_bytes_preserved"]
    assert result["normalized"][0]["fulltext_confirmed"]
    assert result["extraction"]["effect"]["units"] > 0
    assert result["extraction"]["method"]["units"] > 0
    assert not list(target.read("claims.jsonl"))
    assert files_snapshot(old) == before
    assert prepare(plan, apply=True)["normalized"] == []
    assert len(list(target.read("acquisitions.jsonl"))) == 1


@pytest.mark.parametrize("damage", ["raw", "parsed", "inputs", "destination"])
def test_mismatch_refuses_before_writing_target_ledgers(tmp_path, damage):
    plan, old, target = fixture(tmp_path)
    if damage == "raw":
        row = next(iter(old.read("acquisitions.jsonl")))
        from pathlib import Path
        Path(row["stored_path"]).write_bytes(b"different")
    elif damage == "parsed":
        plan["reuse"][0]["parsed_sha256"] = "wrong"
    elif damage == "inputs":
        plan["input_sha256"]["questions.yaml"] = "wrong"
    else:
        path = target.root / "tei" / (plan["reuse"][0]["sha256"] + ".xml")
        path.parent.mkdir(parents=True)
        path.write_bytes(b"different cached parsing")
    before = files_snapshot(target)
    with pytest.raises(ValueError):
        prepare(plan, apply=True)
    assert files_snapshot(target) == before
