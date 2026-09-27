"""Lowering the floor because the number came out awkward is the move this prevents."""

import pytest

from claimstone import admissibility
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


# --- A per-class floor, which can only make admission harder --------------------------------------
#
# Measured: on alembic-s4 obtainability differs by genre — MET 0.83, ACA 0.70, IND 0.33 — because IND is
# commercial vendor research with no open copy in existence. A single floor over a manifest that mixes
# refereed papers with vendor product research measures the proportions of the manifest.
#
# So a class may declare its own floor, and it is an **additional** constraint: the project floor still
# applies to the whole. A declared class floor can never let a round pass that the project floor refused,
# which is the property that keeps this from being "lower the bar until it clears".

def test_a_class_floor_is_declarable_with_a_reason(tmp_path):
    from claimstone.config import load_sources

    (tmp_path / "sources.yaml").write_text(
        "acquisition_floor: 0.8\nfloor_version: 1\nfloor_set_at: 2026-09-28\n"
        "floor_rationale: because\nclasses:\n"
        "  - id: ACA\n    name: a\n    weight_hint: highest\n"
        "  - id: IND\n    name: b\n    weight_hint: medium\n"
        "    acquisition_floor: 0.30\n"
        "    floor_set_at: 2026-09-28\n"
        "    floor_rationale: vendor research has no open copy in existence\n",
        encoding="utf-8")
    classes, floor, _ = load_sources(tmp_path)
    by_id = {c.id: c for c in classes}
    assert by_id["ACA"].acquisition_floor is None
    assert by_id["IND"].acquisition_floor == 0.30
    assert "no open copy" in by_id["IND"].floor_rationale


def test_a_class_floor_without_a_reason_is_refused(tmp_path):
    from claimstone.config import ConfigError, load_sources

    (tmp_path / "sources.yaml").write_text(
        "acquisition_floor: 0.8\nclasses:\n"
        "  - id: IND\n    name: b\n    weight_hint: medium\n    acquisition_floor: 0.30\n",
        encoding="utf-8")
    with pytest.raises(ConfigError, match="floor_rationale"):
        load_sources(tmp_path)


def test_a_class_that_misses_its_own_floor_is_named(tmp_path):
    """Additional, never a rescue: the project floor is still judged over the whole."""
    project = _project(tmp_path, floor=0.50, class_floors={"IND": 0.60})
    store = _store_with(tmp_path, {"ACA": (4, 4), "IND": (4, 1)})
    result = admissibility.admit(project, store)
    assert result["status"] == admissibility.INSUFFICIENT
    assert result["classes_below_floor"] == ["IND"]
    assert result["by_class"]["IND"]["floor"] == 0.60
    assert result["by_class"]["ACA"]["floor"] == 0.50


def test_a_class_floor_cannot_admit_a_round_the_project_floor_refused(tmp_path):
    """The property that keeps this honest. Every class clears its own declared bar and the whole does not."""
    project = _project(tmp_path, floor=0.90, class_floors={"ACA": 0.10, "IND": 0.10})
    store = _store_with(tmp_path, {"ACA": (4, 2), "IND": (4, 2)})
    result = admissibility.admit(project, store)
    assert result["classes_below_floor"] == []
    assert result["status"] == admissibility.INSUFFICIENT


# --- Helpers for the per-class tests above --------------------------------------------------------

def _project(tmp_path, *, floor, class_floors):
    """A minimal project whose classes carry the declared floors."""
    from claimstone.config import SourceClass

    class P:
        name = "t"
        acquisition_floor = floor
        floor_version = 1
        floor_set_at = "2026-09-28"
        floor_rationale = "for the test"
        questions = ()
        registry_version = 1
        registry_sha256 = ""
        frozen_at = "2026-09-28"
        classes = tuple(
            SourceClass(id=cid, name=cid, weight_hint="high",
                        acquisition_floor=class_floors.get(cid),
                        floor_rationale="declared" if cid in class_floors else "")
            for cid in ("ACA", "IND")
        )

    return P()


def _store_with(tmp_path, per_class):
    """`{class: (found, confirmed)}` as candidates, acquisitions and documents."""
    from claimstone.store import Store

    store = Store("t", base=tmp_path)
    for klass, (found, confirmed) in per_class.items():
        for n in range(found):
            key = f"doi:10.1/{klass}{n}"
            store.append("candidates.jsonl", {"candidate_key": key, "source_class": klass,
                                              "source_id": f"{klass}{n:03d}", "round": "r"})
            got = n < confirmed
            store.append("acquisitions.jsonl", {"candidate_key": key, "source_id": f"{klass}{n:03d}",
                                                "acquired": got, "sha256": f"h{klass}{n}",
                                                "source_class": klass,
                                                "failure_class": None if got else "PAYWALL_403"})
            if got:
                store.append("documents.jsonl", {"source_id": f"{klass}{n:03d}",
                                                 "sha256": f"h{klass}{n}",
                                                 "fulltext_confirmed": True})
    return store
