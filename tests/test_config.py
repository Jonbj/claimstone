"""The contract is the product: these tests pin what a project must satisfy."""

from __future__ import annotations

import pathlib

import pytest

from claimstone import config
from claimstone.config import ConfigError, discover_projects, load_project

REPO = pathlib.Path(__file__).resolve().parents[1]


def _write(root: pathlib.Path, **files: str) -> pathlib.Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (root / f"{name}.yaml").write_text(body, encoding="utf-8")
    return root


GOOD_SOURCES = """
classes:
  - {id: ACA, name: academic, weight_hint: highest}
acquisition_floor: 0.8
excluded_hosts: [sci-hub.se]
"""
GOOD_TOPICS = """
topics:
  - {id: T01, label: a topic, terms: [some search term]}
"""
GOOD_QUESTIONS = """
registry_version: 1
frozen_at: 2026-09-22
questions:
  - {id: Q01, text: "Does the effect exist?"}
"""


def test_shipped_projects_all_validate():
    roots = discover_projects(REPO / "projects")
    assert roots, "expected at least one project instance in the repo"
    for root in roots:
        load_project(root)


def test_loads_a_minimal_project(tmp_path):
    root = _write(
        tmp_path / "p", sources=GOOD_SOURCES, topics=GOOD_TOPICS, questions=GOOD_QUESTIONS
    )
    project = load_project(root)
    assert project.question_ids == {"Q01"}
    assert project.class_ids == {"ACA"}
    assert project.acquisition_floor == 0.8
    assert project.frozen_at == "2026-09-22"


def test_missing_file_is_an_error(tmp_path):
    root = _write(tmp_path / "p", sources=GOOD_SOURCES, topics=GOOD_TOPICS)
    with pytest.raises(ConfigError, match="questions.yaml"):
        load_project(root)


def test_duplicate_question_ids_rejected(tmp_path):
    root = _write(
        tmp_path / "p",
        sources=GOOD_SOURCES,
        topics=GOOD_TOPICS,
        questions="""
registry_version: 1
frozen_at: 2026-09-22
questions:
  - {id: Q01, text: first}
  - {id: Q01, text: second}
""",
    )
    with pytest.raises(ConfigError, match="duplicate question"):
        load_project(root)


@pytest.mark.parametrize("floor", ["0", "-0.1", "1.5", "'0.8'"])
def test_acquisition_floor_must_be_a_usable_fraction(tmp_path, floor):
    """The floor gates whether a round may produce verdicts, so a nonsense value must not load."""
    root = _write(
        tmp_path / "p",
        sources=f"""
classes:
  - {{id: ACA, name: academic, weight_hint: highest}}
acquisition_floor: {floor}
""",
        topics=GOOD_TOPICS,
        questions=GOOD_QUESTIONS,
    )
    with pytest.raises(ConfigError, match="acquisition_floor"):
        load_project(root)


def test_topic_without_terms_rejected(tmp_path):
    root = _write(
        tmp_path / "p",
        sources=GOOD_SOURCES,
        topics="topics:\n  - {id: T01, label: empty, terms: []}\n",
        questions=GOOD_QUESTIONS,
    )
    with pytest.raises(ConfigError, match="terms"):
        load_project(root)


def test_registry_version_must_be_an_integer(tmp_path):
    root = _write(
        tmp_path / "p",
        sources=GOOD_SOURCES,
        topics=GOOD_TOPICS,
        questions="""
registry_version: draft
frozen_at: 2026-09-22
questions:
  - {id: Q01, text: first}
""",
    )
    with pytest.raises(ConfigError, match="registry_version"):
        load_project(root)


# --- the extraction vocabulary --------------------------------------------------------------------

def _sources(tmp_path, body):
    root = tmp_path / "p"
    root.mkdir()
    (root / "sources.yaml").write_text(body, encoding="utf-8")
    return root


def test_a_project_declares_its_own_value_labels(tmp_path):
    root = _sources(tmp_path, "extraction:\n  value_labels: [AOR, 'ß', Sharpe]\n")
    assert config.load_extraction(root)["value_labels"] == ("AOR", "ß", "Sharpe")


def test_the_declaration_is_what_the_project_wrote_and_not_the_engine_s_defaults(tmp_path):
    """The engine merges its generic set in at use, so neither module holds the other's business."""
    root = _sources(tmp_path, "extraction:\n  value_labels: [AOR]\n")
    assert config.load_extraction(root)["value_labels"] == ("AOR",)


def test_no_extraction_section_means_the_engine_s_defaults(tmp_path):
    assert config.load_extraction(_sources(tmp_path, "classes: []\n")) == {}


def test_a_misspelt_extraction_key_is_refused(tmp_path):
    """A vocabulary the operator believed they had declared produces a rejection they would misread as a
    fact about the literature."""
    root = _sources(tmp_path, "extraction:\n  value_lables: [AOR]\n")
    with pytest.raises(ConfigError) as raised:
        config.load_extraction(root)
    assert "value_lables" in str(raised.value)


def test_value_labels_must_be_strings(tmp_path):
    root = _sources(tmp_path, "extraction:\n  value_labels: [1.66]\n")
    with pytest.raises(ConfigError):
        config.load_extraction(root)


def test_comparatives_replace_rather_than_extend(tmp_path):
    """A project declaring these says which comparisons its field makes, and keeping the engine's would
    put back the stems it chose to leave out."""
    root = _sources(tmp_path, "extraction:\n  comparatives:\n    '>': [exceeds]\n")
    assert config.load_extraction(root)["comparatives"] == {">": ("exceeds",)}
