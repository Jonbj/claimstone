from __future__ import annotations

import pathlib
import shutil

import pytest

from claimstone import new_project_service as svc
from claimstone.config import load_project

REPO = pathlib.Path(__file__).resolve().parents[1]

STEP1 = {"name": "news-tone", "description": "scope", "topics": [{"label": "News", "terms": ["a b", "c d"]}]}
STEP2 = {"questions": [{"text": "Does news carry information?", "kind": "effect"},
                       {"text": "Which datasets exist?", "kind": "operational"}]}
STEP3 = {"template": "general", "classes": ["ACA"], "acquisition_floor": 0.8,
         "floor_rationale": "Set before the first measured round; below it coverage is uninterpretable.",
         "supplied_copies": "separate", "notation": "none", "custom_value_labels": [],
         "extra_excluded_hosts": []}


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    (tmp_path / "projects").mkdir()
    shutil.copytree(REPO / "templates", tmp_path / "templates")
    monkeypatch.setattr(svc, "_today", lambda: "2026-10-10")
    return {"projects": tmp_path / "projects", "store": tmp_path / "store"}


def _call(fn, ws, *args, **kw):
    return fn(ws["projects"], ws["store"], "op1", "rev", *args, **kw)


def _fill(ws):
    draft = _call(svc.start, ws)[0]["draft_id"]
    rev = 1
    for step, data in ((1, STEP1), (2, STEP2), (3, STEP3)):
        payload, _ = _call(svc.save_step, ws, draft, step, rev, data)
        rev = payload["revision"]
    return draft, rev


def _shown(ws, draft):
    """The digest the review page would have displayed."""
    return _call(svc.preview, ws, draft)[0]["protocol_sha256"]


def _refused(fn, ws, *args):
    with pytest.raises(svc.ServiceError) as raised:
        _call(fn, ws, *args)
    return raised.value


def test_a_saved_step_returns_normalized_data_and_figures(ws):
    draft = _call(svc.start, ws)[0]["draft_id"]
    payload, status = _call(svc.save_step, ws, draft, 1, 1, STEP1)
    assert status == 200 and payload["revision"] == 2
    assert payload["data"]["topics"][0]["id"] == "T01"
    assert payload["figures"] == {"topics": 1, "terms": 2, "searches_per_index": 2,
                                  "searches_all_indexes": 6}


def test_an_invalid_step_is_422_with_paths_and_writes_nothing(ws):
    draft = _call(svc.start, ws)[0]["draft_id"]
    error = _refused(svc.save_step, ws, draft, 1, 1, {**STEP1, "name": "Bad Name"})
    assert (error.status, error.code) == (422, "VALIDATION")
    assert error.details == [{"path": "name", "message": error.details[0]["message"]}]
    assert _call(svc.read, ws, draft)[0]["revision"] == 1


def test_a_taken_name_is_refused_at_step_1(ws):
    (ws["projects"] / "news-tone").mkdir()
    draft = _call(svc.start, ws)[0]["draft_id"]
    error = _refused(svc.save_step, ws, draft, 1, 1, STEP1)
    assert error.status == 422 and error.details[0]["path"] == "name"


def test_reading_a_draft_returns_the_figures_of_its_saved_steps(ws):
    draft, _ = _fill(ws)
    payload, _ = _call(svc.read, ws, draft)
    assert set(payload["steps"]) == {"1", "2", "3"}
    assert payload["figures"]["1"]["searches_per_index"] == 2
    assert payload["figures"]["2"]["questions_operational"] == 1
    assert payload["figures"]["3"]["classes"] == ["ACA"]


def test_the_preview_needs_all_three_steps_then_shows_files_and_figures(ws):
    draft = _call(svc.start, ws)[0]["draft_id"]
    assert _refused(svc.preview, ws, draft).status == 409
    draft, _ = _fill(ws)
    payload, _ = _call(svc.preview, ws, draft)
    assert payload["figures"]["questions_operational"] == 1
    assert set(payload["files"]) == {"topics.yaml", "questions.yaml", "sources.yaml"}
    assert len(payload["protocol_sha256"]) == 64


def test_advanced_text_is_validated_and_shown_in_the_preview(ws):
    draft, rev = _fill(ws)
    files = _call(svc.preview, ws, draft)[0]["files"]
    edited = files["sources.yaml"].replace("acquisition_floor: 0.8", "acquisition_floor: 0.9")
    payload, status = _call(svc.save_advanced, ws, draft, rev, {"sources.yaml": edited})
    assert status == 200
    assert _call(svc.preview, ws, draft)[0]["figures"]["acquisition_floor"] == 0.9
    error = _refused(svc.save_advanced, ws, draft, payload["revision"], {"sources.yaml": "classes: []\n"})
    assert error.status == 422 and error.details[0]["path"] == "sources.yaml"


def test_create_makes_a_frozen_project_and_closes_the_draft(ws):
    draft, _ = _fill(ws)
    payload, status = _call(svc.create, ws, draft, True, _shown(ws, draft))
    assert status == 201 and payload["project"] == "news-tone"
    project = load_project(ws["projects"] / "news-tone")
    assert (project.registry_version, project.frozen_at, project.floor_version) == (1, "2026-10-10", 1)
    assert _call(svc.read, ws, draft)[0]["status"] == "created"
    assert _refused(svc.create, ws, draft, True, "0" * 64).code == "DRAFT_CLOSED"


def test_create_refuses_a_project_that_changed_since_it_was_reviewed(ws):
    draft, rev = _fill(ws)
    shown = _shown(ws, draft)
    _call(svc.save_step, ws, draft, 2, rev, {"questions": [{"text": "A different question?", "kind": "effect"}]})
    error = _refused(svc.create, ws, draft, True, shown)
    assert (error.status, error.code) == (409, "PREVIEW_CHANGED")
    assert not (ws["projects"] / "news-tone").exists()


def test_create_needs_the_literal_confirmation(ws):
    draft, _ = _fill(ws)
    assert _refused(svc.create, ws, draft, False, _shown(ws, draft)).status == 422
    assert not (ws["projects"] / "news-tone").exists()


def test_a_name_taken_after_step_1_is_a_409_and_recorded(ws):
    draft, _ = _fill(ws)
    shown = _shown(ws, draft)
    (ws["projects"] / "news-tone").mkdir()
    error = _refused(svc.create, ws, draft, True, shown)
    assert (error.status, error.code) == (409, "NAME_TAKEN")
    assert _call(svc.read, ws, draft)[0]["last_failure"]
    assert _call(svc.read, ws, draft)[0]["status"] == "open"
    assert not [p for p in ws["projects"].iterdir() if p.name.startswith(".incoming")]


def test_templates_are_listed_and_read(ws):
    listed, _ = _call(svc.templates, ws)
    assert [t["id"] for t in listed["templates"]] == ["general"]
    one, _ = _call(svc.template, ws, "general")
    assert [c["id"] for c in one["classes"]][:2] == ["ACA", "WP"]
    assert any(p["id"] == "health" for p in one["notation_presets"])
    assert _refused(svc.template, ws, "nope").status == 404
