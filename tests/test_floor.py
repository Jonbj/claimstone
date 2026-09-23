"""Lowering the floor because the number came out awkward is the move this prevents."""

import pytest

from claimstone.config import ConfigError, load_project

BASE = """classes:
  - id: ACA
    name: academic
    weight_hint: highest
acquisition_floor: 0.80
"""


def project(tmp_path, sources_extra=""):
    (tmp_path / "sources.yaml").write_text(BASE + sources_extra, encoding="utf-8")
    (tmp_path / "topics.yaml").write_text(
        "topics:\n  - id: T01\n    label: t\n    terms: [a]\n", encoding="utf-8")
    (tmp_path / "questions.yaml").write_text(
        "registry_version: 1\nfrozen_at: 2026-09-22\n"
        "questions:\n  - id: Q01\n    text: a question\n", encoding="utf-8")
    return load_project(tmp_path)


def test_version_one_needs_no_rationale(tmp_path):
    assert project(tmp_path).floor_version == 1


def test_a_bumped_floor_without_a_rationale_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="floor_rationale"):
        project(tmp_path, "floor_version: 2\nfloor_set_at: 2026-10-01\n")


def test_a_bumped_floor_with_a_rationale_loads(tmp_path):
    loaded = project(
        tmp_path,
        "floor_version: 2\nfloor_set_at: 2026-10-01\n"
        "floor_rationale: 4 of 25 are Elsevier with no open copy in any repository.\n",
    )
    assert loaded.floor_version == 2
    assert "Elsevier" in loaded.floor_rationale


def test_a_bumped_floor_needs_a_date(tmp_path):
    with pytest.raises(ConfigError, match="floor_set_at"):
        project(tmp_path, "floor_version: 2\nfloor_rationale: a long enough reason here.\n")


def test_the_report_carries_the_floor_version(tmp_path):
    from claimstone import admissibility
    from claimstone.store import Store

    loaded = project(tmp_path)
    store = Store("t", base=tmp_path / "store")
    store.append("acquisitions.jsonl", {"candidate_key": "a", "source_class": "ACA",
                                        "acquired": True, "url": "https://x.example/a"})
    verdict = admissibility.admit(loaded, store)
    assert verdict["floor_version"] == 1
    assert verdict["floor_set_at"]
