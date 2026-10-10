from __future__ import annotations

import pytest

from claimstone import wizard_drafts as wd


@pytest.fixture()
def store(tmp_path):
    return wd.open_store(tmp_path / "store")


def _start(store, actor="op1"):
    return wd.start(store, actor=actor, code_revision="abc")["draft_id"]


def test_a_started_draft_is_open_at_revision_1(store):
    draft = _start(store)
    state = wd.state(store, draft, "op1")
    assert (state["status"], state["revision"], state["steps"]) == ("open", 1, {})


def test_saving_a_step_needs_the_current_revision(store):
    draft = _start(store)
    row = wd.save_step(store, actor="op1", draft_id=draft, step=1, base_revision=1,
                       data={"name": "x"}, code_revision="abc")
    assert row["revision"] == 2 and row["event"] == "step_saved" and row["signer_auth"] == "portal-session"
    with pytest.raises(wd.DraftRefused) as raised:
        wd.save_step(store, actor="op1", draft_id=draft, step=1, base_revision=1,
                     data={"name": "y"}, code_revision="abc")
    assert (raised.value.status, raised.value.code) == (409, "STALE_REVISION")
    assert wd.state(store, draft, "op1")["steps"][1]["data"] == {"name": "x"}


def test_the_latest_row_per_step_is_the_state(store):
    draft = _start(store)
    wd.save_step(store, actor="op1", draft_id=draft, step=2, base_revision=1, data={"a": 1}, code_revision=None)
    wd.save_step(store, actor="op1", draft_id=draft, step=2, base_revision=2, data={"a": 2}, code_revision=None)
    assert wd.state(store, draft, "op1")["steps"][2] == {"data": {"a": 2}, "revision": 3}


def test_another_operators_draft_does_not_exist(store):
    draft = _start(store, "op1")
    with pytest.raises(wd.DraftRefused) as raised:
        wd.state(store, draft, "op2")
    assert raised.value.status == 404
    assert wd.list_drafts(store, "op2") == []


def test_a_discarded_or_created_draft_is_closed(store):
    draft = _start(store)
    wd.discard(store, actor="op1", draft_id=draft, base_revision=1, code_revision=None)
    assert wd.state(store, draft, "op1")["status"] == "discarded"
    with pytest.raises(wd.DraftRefused) as raised:
        wd.save_step(store, actor="op1", draft_id=draft, step=1, base_revision=2, data={}, code_revision=None)
    assert (raised.value.status, raised.value.code) == (409, "DRAFT_CLOSED")


def test_advanced_overrides_are_replaced_as_a_whole(store):
    draft = _start(store)
    wd.save_advanced(store, actor="op1", draft_id=draft, base_revision=1,
                     files={"sources.yaml": "a"}, code_revision=None)
    wd.save_advanced(store, actor="op1", draft_id=draft, base_revision=2, files={}, code_revision=None)
    assert wd.state(store, draft, "op1")["advanced"] == {}


def test_created_and_failed_are_recorded_without_a_revision_check(store):
    draft = _start(store)
    wd.mark_failed(store, actor="op1", draft_id=draft, reason="name taken", code_revision=None)
    assert wd.state(store, draft, "op1")["status"] == "open"
    assert wd.state(store, draft, "op1")["last_failure"] == "name taken"
    wd.mark_created(store, actor="op1", draft_id=draft, project="news-tone",
                    files={"topics.yaml": "h"}, code_revision=None)
    state = wd.state(store, draft, "op1")
    assert (state["status"], state["project"]) == ("created", "news-tone")


def test_the_list_summarizes_only_my_drafts_newest_first(store):
    first, second = _start(store), _start(store)
    wd.save_step(store, actor="op1", draft_id=first, step=1, base_revision=1,
                 data={"name": "news-tone"}, code_revision=None)
    _start(store, "op2")
    listed = wd.list_drafts(store, "op1")
    assert [d["draft_id"] for d in listed] == [first, second]  # first was updated last
    assert listed[0]["project_name"] == "news-tone" and listed[0]["steps_saved"] == [1]
