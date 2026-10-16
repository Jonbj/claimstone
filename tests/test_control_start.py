"""Starting research from the portal: the first flow of a project, and its first network batch.

Both routes only *record*: a flow binds a round to the protocol, a batch freezes plans in
`planned` state. Neither contacts a host. Authorizing stays the separate, exact act of a person.
"""

from __future__ import annotations

import shutil
import threading
from contextlib import contextmanager

import pytest

from claimstone import control, flows, operations, operators
from claimstone.config import load_project
from claimstone.store import Store
from tests.test_control import _cookie, _login, _request


@pytest.fixture()
def ws(tmp_path):
    root = tmp_path / "example-news-and-returns"
    shutil.copytree("projects/example-news-and-returns", root)
    state = tmp_path / "state"
    operators.add_operator(state, "op1", "Op One", "correct horse")
    project = load_project(root)
    return {"projects": tmp_path, "store_dir": tmp_path / "store", "project": project,
            "store": Store(project.name, base=tmp_path / "store"), "state": state}


@contextmanager
def _served(ws):
    httpd = control.make_server(ws["projects"], ws["store_dir"], host="127.0.0.1", port=0,
                                state_dir=ws["state"])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        _status, headers, body = _login(base)
        yield base, f"/control/v1/p/{ws['project'].name}", {
            "Cookie": _cookie(headers), "Origin": base, "X-CSRF-Token": body["csrf_token"]}
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _start(base, prefix, headers, **overrides):
    payload = {"title": "First search", "round": "first-2026-10-16"} | overrides
    return _request(base + prefix + "/flows", method="POST", headers=headers, payload=payload)


def test_the_first_flow_binds_a_named_round_and_a_repeat_is_not_a_second_flow(ws):
    with _served(ws) as (base, prefix, headers):
        status, _h, body = _start(base, prefix, headers)
        again = _start(base, prefix, headers)
    assert status == 201 and body["created"] is True
    assert again[0] == 200 and again[2]["created"] is False
    assert again[2]["flow_id"] == body["flow_id"]
    held = flows.flows(ws["store"])
    assert list(held) == [body["flow_id"]]
    assert held[body["flow_id"]]["binding"]["selector"]["round"] == "first-2026-10-16"


@pytest.mark.parametrize("overrides", [
    {"round": ""}, {"round": "has space"}, {"round": "../escape"}, {"round": "x" * 200},
    {"title": ""}, {"title": "t" * 500}, {"title": 7}, {"round": None},
])
def test_a_bad_title_or_round_name_is_refused_and_records_nothing(ws, overrides):
    with _served(ws) as (base, prefix, headers):
        status, _h, body = _start(base, prefix, headers, **overrides)
    assert status == 422 and body["error"]["code"] == "VALIDATION"
    assert flows.flows(ws["store"]) == {}


def test_unknown_fields_and_unknown_projects_are_refused(ws):
    with _served(ws) as (base, prefix, headers):
        extra = _request(base + prefix + "/flows", method="POST", headers=headers,
                         payload={"title": "t", "round": "r-1", "manifest_only": True})
        missing = _request(base + "/control/v1/p/nope/flows", method="POST", headers=headers,
                           payload={"title": "t", "round": "r-1"})
    assert extra[0] in (400, 422) and missing[0] == 404
    assert flows.flows(ws["store"]) == {}


def _plan(base, prefix, headers, flow_id, **overrides):
    payload = {"stage": "discover", "apis": ["openalex"], "allowed_hosts": ["api.openalex.org"],
               "max_units": 1, "max_requests_each": 3, "per_query": 10} | overrides
    return _request(f"{base}{prefix}/flows/{flow_id}/batches", method="POST", headers=headers,
                    payload=payload)


def test_a_discovery_batch_is_frozen_planned_and_contacts_no_host(ws):
    with _served(ws) as (base, prefix, headers):
        flow_id = _start(base, prefix, headers)[2]["flow_id"]
        status, _h, batch = _plan(base, prefix, headers, flow_id)
        listed = _request(f"{base}{prefix}/flows/{flow_id}/batches",
                          headers={"Cookie": headers["Cookie"]})[2]["batches"]
    assert status == 201 and batch["selected"] == 1 and batch["max_total_requests"] == 3
    assert [item["batch_id"] for item in listed] == [batch["batch_id"]]
    assert listed[0]["awaiting_approval"] == 1
    events = [row["event"] for row in ws["store"].read(operations.LEDGER)]
    assert events == ["planned"]
    assert not ws["store"].path("requests.jsonl").exists()


def test_planning_needs_exact_hosts_and_a_known_flow(ws):
    with _served(ws) as (base, prefix, headers):
        flow_id = _start(base, prefix, headers)[2]["flow_id"]
        no_hosts = _plan(base, prefix, headers, flow_id, allowed_hosts=[])
        bad_stage = _plan(base, prefix, headers, flow_id, stage="extract")
        unknown = _plan(base, prefix, headers, "0" * 64)
        extra = _plan(base, prefix, headers, flow_id, use_apis=True)
    assert no_hosts[0] == 422 and bad_stage[0] == 422
    assert unknown[0] == 404 and extra[0] in (400, 422)
    assert not ws["store"].path(operations.LEDGER).exists()


def test_planning_and_starting_require_a_session(ws):
    with _served(ws) as (base, prefix, _headers):
        started = _request(base + prefix + "/flows", method="POST",
                           payload={"title": "t", "round": "r-1"})
    assert started[0] in (401, 403)
    assert flows.flows(ws["store"]) == {}
