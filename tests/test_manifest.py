"""The manifest holds the source list constant, so the rate is comparable round to round."""

import pytest

from claimstone.config import ConfigError, load_gate_thresholds, load_manifest

HEADER = "source_id\tclass\tformat\turl\ttitle\n"


def write(tmp_path, body):
    (tmp_path / "manifest.tsv").write_text(HEADER + body, encoding="utf-8")
    return tmp_path


def test_a_well_formed_manifest_loads(tmp_path):
    root = write(tmp_path, "S01\tACA\tpdf\thttps://x.example/a\tA paper\n")
    entries = load_manifest(root, frozenset({"ACA"}))
    assert entries[0].source_id == "S01"
    assert entries[0].source_class == "ACA"


def test_an_undeclared_class_is_a_configuration_error(tmp_path):
    root = write(tmp_path, "S01\tNOPE\tpdf\thttps://x.example/a\tA paper\n")
    with pytest.raises(ConfigError, match="NOPE"):
        load_manifest(root, frozenset({"ACA"}))


def test_a_duplicate_source_id_is_an_error(tmp_path):
    root = write(tmp_path,
                 "S01\tACA\tpdf\thttps://x.example/a\tA\nS01\tACA\tpdf\thttps://y.example/b\tB\n")
    with pytest.raises(ConfigError, match="S01"):
        load_manifest(root, frozenset({"ACA"}))


def test_a_row_with_neither_url_nor_title_is_an_error(tmp_path):
    root = write(tmp_path, "S01\tACA\tpdf\t\t\n")
    with pytest.raises(ConfigError, match="S01"):
        load_manifest(root, frozenset({"ACA"}))


def test_a_trailing_blank_line_is_not_a_row(tmp_path):
    # The real manifest ends with one. A blank line raised "source_id is required" before.
    root = write(tmp_path, "S01\tACA\tpdf\thttps://x.example/a\tA paper\n\n")
    assert len(load_manifest(root, frozenset({"ACA"}))) == 1


def test_a_missing_manifest_is_not_an_error(tmp_path):
    assert load_manifest(tmp_path, frozenset({"ACA"})) == ()


# --- gate threshold overrides -------------------------------------------------

def test_absent_acquisition_key_means_the_defaults(tmp_path):
    (tmp_path / "sources.yaml").write_text(
        "classes: []\nacquisition_floor: 0.8\n", encoding="utf-8")
    assert load_gate_thresholds(tmp_path) == {}


def test_a_project_may_raise_the_text_threshold(tmp_path):
    (tmp_path / "sources.yaml").write_text(
        "classes: []\nacquisition_floor: 0.8\nacquisition:\n  min_text_chars: 5000\n",
        encoding="utf-8")
    assert load_gate_thresholds(tmp_path) == {"min_text_chars": 5000}


def test_an_unknown_threshold_name_is_an_error(tmp_path):
    # A threshold the operator believed they had raised, and had not, produces a rate they
    # would trust wrongly.
    (tmp_path / "sources.yaml").write_text(
        "classes: []\nacquisition_floor: 0.8\nacquisition:\n  min_chars: 5000\n",
        encoding="utf-8")
    with pytest.raises(ConfigError, match="min_chars"):
        load_gate_thresholds(tmp_path)


# --- declared class aliases ---------------------------------------------------

def test_a_declared_alias_resolves_to_its_class_id(tmp_path):
    # The real manifest is written elsewhere and says "academic", not "ACA".
    root = write(tmp_path, "S01\tacademic\tpdf\thttps://x.example/a\tA paper\n")
    entries = load_manifest(root, frozenset({"ACA"}), {"academic": "ACA"})
    assert entries[0].source_class == "ACA"


def test_an_undeclared_alias_is_still_an_error(tmp_path):
    # The engine never guesses that "scholarly" means ACA: a wrong class is invariant 6
    # violated silently, which is worse than a refused load.
    root = write(tmp_path, "S01\tscholarly\tpdf\thttps://x.example/a\tA paper\n")
    with pytest.raises(ConfigError, match="scholarly"):
        load_manifest(root, frozenset({"ACA"}), {"academic": "ACA"})


def test_the_same_alias_cannot_mean_two_classes(tmp_path):
    from claimstone.config import load_sources

    (tmp_path / "sources.yaml").write_text(
        "acquisition_floor: 0.8\nclasses:\n"
        "  - id: ACA\n    name: a\n    weight_hint: highest\n    aliases: [paper]\n"
        "  - id: WP\n    name: b\n    weight_hint: high\n    aliases: [paper]\n",
        encoding="utf-8")
    with pytest.raises(ConfigError, match="paper"):
        load_sources(tmp_path)


# --- the gate's language policy, declared per project -------------------------

def test_absent_gate_policy_means_the_engine_defaults(tmp_path):
    from claimstone.config import load_gate_policy

    (tmp_path / "sources.yaml").write_text(
        "classes: []\nacquisition_floor: 0.8\n", encoding="utf-8")
    assert load_gate_policy(tmp_path) == {}


def test_a_project_declares_its_own_headings_and_phrases(tmp_path):
    from claimstone.config import load_gate_policy

    (tmp_path / "sources.yaml").write_text(
        "classes: []\nacquisition_floor: 0.8\ngate_policy:\n"
        "  reference_headings: [Bibliografia, Riferimenti]\n"
        "  paywall_phrases: [Acquista il PDF]\n"
        "  structural_signal: reference_list\n", encoding="utf-8")
    policy = load_gate_policy(tmp_path)
    assert policy["reference_headings"] == ("bibliografia", "riferimenti")
    assert policy["paywall_phrases"] == ("acquista il pdf",)


def test_an_unknown_structural_signal_is_a_configuration_error(tmp_path):
    from claimstone.config import load_gate_policy

    (tmp_path / "sources.yaml").write_text(
        "classes: []\nacquisition_floor: 0.8\ngate_policy:\n  structural_signal: vibes\n",
        encoding="utf-8")
    with pytest.raises(ConfigError, match="structural_signal"):
        load_gate_policy(tmp_path)


def test_an_unknown_gate_policy_key_is_an_error(tmp_path):
    from claimstone.config import load_gate_policy

    (tmp_path / "sources.yaml").write_text(
        "classes: []\nacquisition_floor: 0.8\ngate_policy:\n  tone: formal\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="tone"):
        load_gate_policy(tmp_path)


def test_a_manifest_that_points_nowhere_is_an_error_and_not_an_absent_manifest(tmp_path):
    """Found by moving to a container. `projects/alembic-s4/manifest.tsv` is a symlink to a path in another
    repository, so inside the container it dangles — and `validate` printed `OK` with no manifest rows,
    because `Path.exists()` follows a link and a broken one looks exactly like no link at all.

    A project that declares no manifest and a project whose manifest points nowhere are different facts, and
    the second is the one that silently drops 25 sources out of a round.
    """
    broken = tmp_path / "manifest.tsv"
    broken.symlink_to(tmp_path / "somewhere-else.tsv")
    with pytest.raises(ConfigError, match="points nowhere"):
        load_manifest(tmp_path, frozenset({"ACA"}), {})


def test_a_project_with_no_manifest_at_all_is_still_fine(tmp_path):
    assert load_manifest(tmp_path, frozenset({"ACA"}), {}) == ()
