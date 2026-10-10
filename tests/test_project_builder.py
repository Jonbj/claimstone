"""The project builder: no domain knowledge, no network, one atomic write."""

from __future__ import annotations

import pathlib

import pytest

from claimstone import project_builder as pb

REPO = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "templates" / "project"


def test_the_shipped_template_loads_and_lists():
    template = pb.load_template(TEMPLATES, "general")
    assert template["id"] == "general"
    assert [c["id"] for c in template["classes"]][:2] == ["ACA", "WP"]
    assert "sci-hub.se" in template["excluded_hosts"]
    assert [t["id"] for t in pb.list_templates(TEMPLATES)] == ["general"]


@pytest.mark.parametrize("bad", ["", "../etc/passwd", "General", "a" * 41, "no-such-template"])
def test_an_unknown_or_unsafe_template_id_is_refused(bad):
    with pytest.raises(pb.DraftInvalid) as raised:
        pb.load_template(TEMPLATES, bad)
    assert raised.value.problems[0].path == "template"


STEP1 = {"name": "news-tone", "description": "In scope: firm-level news.",
         "topics": [{"label": "News and returns", "terms": ["news sentiment returns", " event study "]}]}
STEP2 = {"questions": [{"text": "Does news carry information about returns?", "kind": "effect"},
                       {"text": "Which datasets cover 2000?", "kind": "operational"}]}
STEP3 = {"template": "general", "classes": ["ACA", "WP"], "acquisition_floor": 0.8,
         "floor_rationale": "Set before the first measured round; below it coverage is uninterpretable.",
         "supplied_copies": "separate", "notation": "none", "custom_value_labels": [],
         "extra_excluded_hosts": []}


def _problems(step, data):
    with pytest.raises(pb.DraftInvalid) as raised:
        pb.normalize_step(step, data, TEMPLATES)
    return {(p.path) for p in raised.value.problems}


def test_step_1_assigns_ids_and_trims_terms():
    out = pb.normalize_step(1, STEP1, TEMPLATES)
    assert out["name"] == "news-tone"
    assert out["topics"] == [{"id": "T01", "label": "News and returns",
                              "terms": ["news sentiment returns", "event study"]}]


@pytest.mark.parametrize("bad", ["", "A", "Has Space", "-lead", "x" * 64, "../up", "a_b"])
def test_step_1_refuses_an_unsafe_project_name(bad):
    assert "name" in _problems(1, {**STEP1, "name": bad})


def test_step_1_needs_a_topic_with_terms_and_unique_ids():
    assert "topics" in _problems(1, {**STEP1, "topics": []})
    assert "topics[0].terms" in _problems(1, {**STEP1, "topics": [{"label": "x", "terms": []}]})
    dup = [{"id": "T01", "label": "a", "terms": ["t"]}, {"id": "T01", "label": "b", "terms": ["u"]}]
    assert "topics[1].id" in _problems(1, {**STEP1, "topics": dup})


def test_step_2_requires_a_known_kind_and_text():
    out = pb.normalize_step(2, STEP2, TEMPLATES)
    assert [q["id"] for q in out["questions"]] == ["Q01", "Q02"]
    assert "questions[0].kind" in _problems(2, {"questions": [{"text": "x?", "kind": ""}]})
    assert "questions[0].kind" in _problems(2, {"questions": [{"text": "x?", "kind": "vibes"}]})
    assert "questions[0].text" in _problems(2, {"questions": [{"text": "  ", "kind": "effect"}]})
    assert "questions" in _problems(2, {"questions": []})


def test_step_2_does_not_judge_wording():
    vague = {"questions": [{"text": "News works.", "kind": "effect"}]}
    assert pb.normalize_step(2, vague, TEMPLATES)["questions"][0]["text"] == "News works."


def test_step_3_normalizes_against_the_template():
    out = pb.normalize_step(3, {**STEP3, "classes": ["WP", "ACA"], "notation": "health"}, TEMPLATES)
    assert out["classes"] == ["ACA", "WP"]  # template order: most authoritative first
    assert out["acquisition_floor"] == 0.8 and out["supplied_copies"] == "separate"
    assert "OR" in out["value_labels"]


@pytest.mark.parametrize("field,value", [
    ("acquisition_floor", 0), ("acquisition_floor", 1.5), ("acquisition_floor", True),
    ("acquisition_floor", "0.8"), ("floor_rationale", "short"), ("floor_rationale", ""),
    ("supplied_copies", "maybe"), ("classes", []), ("classes", ["ZZZ"]),
    ("notation", "astrology"), ("extra_excluded_hosts", ["https://x.org/path"]),
    ("extra_excluded_hosts", ["*.example.org"]),
])
def test_step_3_refusals(field, value):
    # A list item is reported at its own index (`extra_excluded_hosts[0]`); match the field it belongs to.
    assert field in {p.split("[")[0] for p in _problems(3, {**STEP3, field: value})}


def test_step_3_has_no_override_field_and_names_unknown_keys():
    # Invariant 3: there is no flag that waives the floor, so a stray key is refused by name.
    assert "override" in _problems(3, {**STEP3, "override": True})


def test_a_custom_notation_is_taken_as_typed():
    out = pb.normalize_step(3, {**STEP3, "notation": "custom", "custom_value_labels": ["Sharpe", " alpha "]}, TEMPLATES)
    assert out["value_labels"] == ["Sharpe", "alpha"]
