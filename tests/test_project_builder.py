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


def _state():
    return {1: pb.normalize_step(1, STEP1, TEMPLATES), 2: pb.normalize_step(2, STEP2, TEMPLATES),
            3: pb.normalize_step(3, STEP3, TEMPLATES)}


def test_render_freezes_version_1_with_todays_date():
    files = pb.render(_state(), TEMPLATES, today="2026-10-10")
    assert set(files) == set(pb.FILES)
    assert "registry_version: 1" in files["questions.yaml"]
    assert "frozen_at: '2026-10-10'" in files["questions.yaml"]
    assert "floor_version: 1" in files["sources.yaml"]
    assert "floor_set_at: '2026-10-10'" in files["sources.yaml"]
    assert files["topics.yaml"].startswith("description:")


def test_render_needs_all_three_steps():
    with pytest.raises(pb.DraftInvalid) as raised:
        pb.render({1: _state()[1]}, TEMPLATES, today="2026-10-10")
    assert {p.path for p in raised.value.problems} == {"step 2", "step 3"}


def test_inspect_loads_with_the_real_loader_and_derives_figures():
    info = pb.inspect(pb.render(_state(), TEMPLATES, today="2026-10-10"), name="news-tone",
                      templates_dir=TEMPLATES, template_id="general")
    fig = info["figures"]
    assert (fig["topics"], fig["terms"]) == (1, 2)
    assert (fig["searches_per_index"], fig["searches_all_indexes"]) == (2, 6)
    assert (fig["questions_total"], fig["questions_literature"], fig["questions_operational"]) == (2, 1, 1)
    assert fig["questions_by_kind"]["effect"] == 1 and fig["classes"] == ["ACA", "WP"]
    assert fig["acquisition_floor"] == 0.8 and fig["requests_max"] is None
    assert len(info["protocol_sha256"]) == 64


def test_a_description_does_not_change_the_protocol_digest():
    base = _state()
    other = {**base, 1: {**base[1], "description": "a completely different description"}}
    a = pb.inspect(pb.render(base, TEMPLATES, today="2026-10-10"), name="x1",
                   templates_dir=TEMPLATES, template_id="general")
    b = pb.inspect(pb.render(other, TEMPLATES, today="2026-10-10"), name="x1",
                   templates_dir=TEMPLATES, template_id="general")
    assert a["protocol_sha256"] == b["protocol_sha256"]


def test_an_override_must_still_load():
    files = pb.render(_state(), TEMPLATES, today="2026-10-10",
                      overrides={"sources.yaml": "classes: []\n"})
    with pytest.raises(pb.DraftInvalid) as raised:
        pb.inspect(files, name="news-tone", templates_dir=TEMPLATES, template_id="general")
    assert raised.value.problems[0].path == "sources.yaml"


def test_an_override_cannot_remove_a_template_excluded_host():
    state = _state()
    files = pb.render(state, TEMPLATES, today="2026-10-10")
    files["sources.yaml"] = files["sources.yaml"].replace("- sci-hub.se\n", "")
    with pytest.raises(pb.DraftInvalid) as raised:
        pb.inspect(files, name="news-tone", templates_dir=TEMPLATES, template_id="general")
    assert "sci-hub.se" in raised.value.problems[0].message


def test_an_unknown_override_file_is_refused():
    with pytest.raises(pb.DraftInvalid):
        pb.render(_state(), TEMPLATES, today="2026-10-10", overrides={"manifest.tsv": "x"})


def test_a_question_with_no_kind_in_an_override_is_counted_unassigned():
    files = pb.render(_state(), TEMPLATES, today="2026-10-10")
    files["questions.yaml"] = ("registry_version: 1\nfrozen_at: '2026-10-10'\nquestions:\n"
                               "- {id: Q01, text: 'x?'}\n")
    info = pb.inspect(files, name="news-tone", templates_dir=TEMPLATES, template_id="general")
    assert info["figures"]["questions_by_kind"]["unassigned"] == 1
    assert info["figures"]["questions_literature"] == 1
