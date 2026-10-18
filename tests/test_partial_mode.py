"""D146: a project that declared `floor_mode: partial` gets labelled partial profiles below its floor;
every other project keeps the refusal of invariant 3 exactly as it was."""
import dataclasses

import pytest

from claimstone import admissibility, synthesize
from tests.test_adjudicate import RATIONALE
from tests.test_synthesize import _project, _store, claim, review


def partial_project(tmp_path, floor=0.8):
    return dataclasses.replace(_project(tmp_path, floor=floor), floor_mode="partial", floor_mode_declared=True)


def below_floor_store(tmp_path):
    return _store(tmp_path, obtained=1, found=4, claims=[claim()], reviews=[review()])


def test_the_default_mode_is_still_a_refusal_and_writes_nothing(tmp_path):
    store = below_floor_store(tmp_path)
    assert _project(tmp_path).floor_mode == "gate"
    with pytest.raises(synthesize.NotAdmissible):
        synthesize.build(_project(tmp_path, floor=0.8), store)
    assert list(store.read(synthesize.PROFILES)) == []


def test_a_partial_project_below_the_floor_gets_profiles_that_say_so_and_carry_the_coverage(tmp_path):
    store = below_floor_store(tmp_path)
    assert admissibility.admit(partial_project(tmp_path), store)["status"] == admissibility.INSUFFICIENT
    synthesize.build(partial_project(tmp_path), store)
    profile = synthesize.latest_profiles(store)["H02"]
    assert profile["partial"] is True
    assert profile["partial_coverage"]["found"] == 4 and profile["partial_coverage"]["confirmed"] == 1
    assert profile["partial_coverage"]["floor"] == 0.8 and profile["partial_coverage"]["rate"] == 0.25
    operational = synthesize.latest_profiles(store)["H11"]
    assert "partial" not in operational, "an operational question receives no verdict, partial or not"


def test_a_complete_round_is_untouched_by_the_mode_so_no_signature_goes_stale(tmp_path):
    store = _store(tmp_path, obtained=2, found=2, claims=[claim()], reviews=[review()])
    synthesize.build(_project(tmp_path), store)
    plain = synthesize.latest_profiles(store)["H02"]
    again, _ = synthesize.preview(partial_project(tmp_path, floor=0.5), store)
    mine = next(r for r in again if r["question_id"] == "H02")
    assert "partial" not in plain and "partial_coverage" not in plain
    assert mine["profile_sha256"] == plain["profile_sha256"], "above the floor the mode changes no byte"


def test_a_partial_verdict_carries_its_coverage_and_cannot_say_unanswered(tmp_path):
    store = below_floor_store(tmp_path)
    project = partial_project(tmp_path)
    synthesize.build(project, store)
    digest = synthesize.latest_profiles(store)["H02"]["profile_sha256"]
    with pytest.raises(ValueError, match="cannot be signed on a partial profile"):
        synthesize.adjudicate(store, "H02", project=project, verdict="UNANSWERED_IN_LITERATURE", rationale=RATIONALE,
                              by="x", signer_auth="cli-declared", actor=None, profile_sha256=digest)
    assert list(store.read(synthesize.ADJUDICATIONS)) == []
    for verdict in ("SUPPORTED", "CONTRADICTED", "CONTESTED_IN_LITERATURE"):
        row = synthesize.adjudicate(store, "H02", project=project, verdict=verdict, rationale=RATIONALE, by="x",
                                    signer_auth="cli-declared", actor=None, profile_sha256=digest)
        assert row["partial"] is True and row["partial_coverage"]["confirmed"] == 1 and row["partial_coverage"]["found"] == 4


def test_a_complete_verdict_has_no_partial_marker(tmp_path):
    store = _store(tmp_path, obtained=2, found=2, claims=[claim()], reviews=[review()])
    project = partial_project(tmp_path, floor=0.5)
    synthesize.build(project, store)
    digest = synthesize.latest_profiles(store)["H02"]["profile_sha256"]
    row = synthesize.adjudicate(store, "H02", project=project, verdict="UNANSWERED_IN_LITERATURE", rationale=RATIONALE,
                                by="x", signer_auth="cli-declared", actor=None, profile_sha256=digest)
    assert "partial" not in row and "partial_coverage" not in row


def test_the_verdict_listing_works_below_the_floor_in_partial_mode(tmp_path):
    store = below_floor_store(tmp_path)
    project = partial_project(tmp_path)
    synthesize.build(project, store)
    listing = synthesize.verdicts(store, project=project)
    assert all(not r["unavailable"] for r in listing["rows"])


def test_the_mode_is_validated_and_enters_the_protocol_only_when_declared(tmp_path):
    from claimstone import config, flows

    root = tmp_path / "p"
    root.mkdir()
    (root / "sources.yaml").write_text("floor_mode: sometimes\n")
    with pytest.raises(config.ConfigError, match="floor_mode"):
        config.load_floor_mode(root)
    (root / "sources.yaml").write_text("acquisition_floor: 0.8\n")
    assert config.load_floor_mode(root) == ("gate", False)
    (root / "sources.yaml").write_text("floor_mode: partial\n")
    assert config.load_floor_mode(root) == ("partial", True)
    (tmp_path / "sources.yaml").write_text("acquisition_floor: 0.8\n")
    base = _project(tmp_path)
    assert flows.protocol_digest(base) == flows.protocol_digest(dataclasses.replace(base, floor_mode="gate"))
    assert flows.protocol_digest(base) != flows.protocol_digest(partial_project(tmp_path))
