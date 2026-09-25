"""A question's text cannot change under the same registry version without being noticed.

Invariant 5 says a registry change is a dated bump, never a silent insert — otherwise every
round-over-round figure and every multiplicity correction loses its meaning. The loader validated
the version, the date and the uniqueness of ids, and would accept rewritten question text under an
unchanged version. This closes that.
"""

import pytest

from claimstone import config
from claimstone.store import Store


def project_at(tmp_path, questions, *, version=1, frozen="2026-09-22"):
    (tmp_path / "sources.yaml").write_text(
        "classes:\n  - id: ACA\n    name: a\n    weight_hint: highest\n"
        "acquisition_floor: 0.8\n", encoding="utf-8")
    (tmp_path / "topics.yaml").write_text(
        "topics:\n  - id: T01\n    label: t\n    terms: [a]\n", encoding="utf-8")
    body = "".join(f"  - id: {qid}\n    text: {text}\n" for qid, text in questions)
    (tmp_path / "questions.yaml").write_text(
        f"registry_version: {version}\nfrozen_at: {frozen}\nquestions:\n{body}",
        encoding="utf-8")
    return config.load_project(tmp_path)


def test_the_registry_carries_a_hash_of_its_questions(tmp_path):
    loaded = project_at(tmp_path, [("Q01", "An effect exists.")])
    assert len(loaded.registry_sha256) == 64


def test_the_hash_changes_when_a_question_text_changes(tmp_path):
    first = project_at(tmp_path, [("Q01", "An effect exists.")]).registry_sha256
    second = project_at(tmp_path, [("Q01", "An effect exists at some horizon.")]).registry_sha256
    assert first != second


def test_the_hash_changes_when_a_question_is_added(tmp_path):
    first = project_at(tmp_path, [("Q01", "An effect exists.")]).registry_sha256
    second = project_at(tmp_path, [("Q01", "An effect exists."), ("Q02", "And another.")])
    assert first != second.registry_sha256


def test_the_hash_does_not_change_when_only_the_frozen_date_does(tmp_path):
    # The hash covers the questions, not the file. Otherwise every cosmetic edit reads as drift
    # and the check stops being believed.
    first = project_at(tmp_path, [("Q01", "An effect exists.")]).registry_sha256
    (tmp_path / "questions.yaml").write_text(
        (tmp_path / "questions.yaml").read_text().replace("2026-09-22", "2026-10-01"),
        encoding="utf-8")
    assert config.load_project(tmp_path).registry_sha256 == first


def test_a_first_sighting_is_recorded_not_refused(tmp_path):
    loaded = project_at(tmp_path, [("Q01", "An effect exists.")])
    store = Store("t", base=tmp_path / "store")
    config.check_registry_drift(loaded, store)
    rows = list(store.read("registry.jsonl"))
    assert rows[0]["registry_version"] == 1
    assert rows[0]["registry_sha256"] == loaded.registry_sha256


def test_seeing_the_same_registry_again_adds_no_row(tmp_path):
    loaded = project_at(tmp_path, [("Q01", "An effect exists.")])
    store = Store("t", base=tmp_path / "store")
    config.check_registry_drift(loaded, store)
    config.check_registry_drift(loaded, store)
    assert len(list(store.read("registry.jsonl"))) == 1


def test_changed_text_under_the_same_version_is_refused(tmp_path):
    loaded = project_at(tmp_path, [("Q01", "An effect exists.")])
    store = Store("t", base=tmp_path / "store")
    config.check_registry_drift(loaded, store)

    rewritten = project_at(tmp_path, [("Q01", "An effect exists at some horizon.")])
    with pytest.raises(config.RegistryDrift, match="registry_version 1"):
        config.check_registry_drift(rewritten, store)


def test_a_bumped_version_is_accepted_and_recorded(tmp_path):
    loaded = project_at(tmp_path, [("Q01", "An effect exists.")])
    store = Store("t", base=tmp_path / "store")
    config.check_registry_drift(loaded, store)

    # A bump moves the version and the date: "dated" is half of what invariant 5 asks for.
    bumped = project_at(tmp_path, [("Q01", "An effect exists at some horizon.")],
                        version=2, frozen="2026-09-26")
    config.check_registry_drift(bumped, store)
    versions = [row["registry_version"] for row in store.read("registry.jsonl")]
    assert versions == [1, 2]


def test_the_cli_reports_drift_as_an_error_not_a_traceback(tmp_path, capsys):
    from claimstone.cli import main

    loaded = project_at(tmp_path, [("Q01", "An effect exists.")])
    store = Store(loaded.name, base=tmp_path / "store")
    config.check_registry_drift(loaded, store)

    project_at(tmp_path, [("Q01", "An effect exists at some horizon.")])
    code = main(["report", str(tmp_path), "--store", str(tmp_path / "store")])
    assert code == 2
    assert "registry_version 1" in capsys.readouterr().err


def test_a_kind_change_is_drift_even_when_the_wording_is_identical(tmp_path):
    # The kind decides which rule judges the question, so moving one from method to effect
    # changes its answer. Leaving kind out of the digest would let that happen with no trace.
    from claimstone.store import Store

    def with_kind(kind: str):
        (tmp_path / "sources.yaml").write_text(
            "classes:\n  - id: ACA\n    name: a\n    weight_hint: highest\n"
            "acquisition_floor: 0.8\n", encoding="utf-8")
        (tmp_path / "topics.yaml").write_text(
            "topics:\n  - id: T01\n    label: t\n    terms: [a]\n", encoding="utf-8")
        (tmp_path / "questions.yaml").write_text(
            "registry_version: 1\nfrozen_at: 2026-09-25\nquestions:\n"
            f"  - id: Q01\n    text: An effect exists.\n    kind: {kind}\n", encoding="utf-8")
        return config.load_project(tmp_path)

    store = Store("t", base=tmp_path / "store")
    config.check_registry_drift(with_kind("method"), store)
    with pytest.raises(config.RegistryDrift):
        config.check_registry_drift(with_kind("effect"), store)


def test_an_unknown_kind_is_a_configuration_error(tmp_path):
    (tmp_path / "sources.yaml").write_text(
        "classes:\n  - id: ACA\n    name: a\n    weight_hint: highest\n"
        "acquisition_floor: 0.8\n", encoding="utf-8")
    (tmp_path / "topics.yaml").write_text(
        "topics:\n  - id: T01\n    label: t\n    terms: [a]\n", encoding="utf-8")
    (tmp_path / "questions.yaml").write_text(
        "registry_version: 1\nfrozen_at: 2026-09-25\nquestions:\n"
        "  - id: Q01\n    text: An effect exists.\n    kind: vibes\n", encoding="utf-8")
    with pytest.raises(config.ConfigError, match="vibes"):
        config.load_project(tmp_path)


def test_a_registry_version_must_increase(tmp_path):
    # A version recorded once cannot be reused by a different registry, and a later version must
    # be later: accepting v4 with an unchanged freeze date lets a bump be cosmetic.
    from claimstone.store import Store

    def at(version, frozen):
        (tmp_path / "sources.yaml").write_text(
            "classes:\n  - id: ACA\n    name: a\n    weight_hint: highest\n"
            "acquisition_floor: 0.8\n", encoding="utf-8")
        (tmp_path / "topics.yaml").write_text(
            "topics:\n  - id: T01\n    label: t\n    terms: [a]\n", encoding="utf-8")
        (tmp_path / "questions.yaml").write_text(
            f"registry_version: {version}\nfrozen_at: {frozen}\nquestions:\n"
            f"  - id: Q01\n    text: A question at v{version}.\n    kind: effect\n",
            encoding="utf-8")
        return config.load_project(tmp_path)

    store = Store("t", base=tmp_path / "store")
    config.check_registry_drift(at(2, "2026-09-25"), store)
    with pytest.raises(config.RegistryDrift, match="not later"):
        config.check_registry_drift(at(3, "2026-09-25"), store)
    config.check_registry_drift(at(3, "2026-09-26"), store)


def test_a_version_cannot_go_backwards(tmp_path):
    from claimstone.store import Store

    def at(version):
        (tmp_path / "sources.yaml").write_text(
            "classes:\n  - id: ACA\n    name: a\n    weight_hint: highest\n"
            "acquisition_floor: 0.8\n", encoding="utf-8")
        (tmp_path / "topics.yaml").write_text(
            "topics:\n  - id: T01\n    label: t\n    terms: [a]\n", encoding="utf-8")
        (tmp_path / "questions.yaml").write_text(
            f"registry_version: {version}\nfrozen_at: 2026-09-2{version}\nquestions:\n"
            f"  - id: Q01\n    text: A question at v{version}.\n    kind: effect\n",
            encoding="utf-8")
        return config.load_project(tmp_path)

    store = Store("t", base=tmp_path / "store")
    config.check_registry_drift(at(5), store)
    with pytest.raises(config.RegistryDrift, match="below"):
        config.check_registry_drift(at(4), store)
