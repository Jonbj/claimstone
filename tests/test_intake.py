"""B7a: proposed DOIs, links and references are recorded and routed, never counted.

Every name resolution goes through a fake resolver: no test looks up a real name or contacts
anything.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager

import pytest

from claimstone import control, flows, intake, operators, scope
from tests.test_control import _cookie, _login, _request
from tests.test_portal_state import build_workspace

PUBLIC = "93.184.216.34"


def _resolver(mapping):
    def resolve(host, port, type=None):  # noqa: A002 - getaddrinfo's own keyword
        address = mapping.get(host, PUBLIC)
        if address is None:
            raise OSError("no such name")
        return [(None, None, None, None, (address, 0))]
    return resolve


@pytest.fixture()
def ws(tmp_path):
    projects_dir, store_dir, project, store = build_workspace(tmp_path)
    state = tmp_path / "state"
    operators.add_operator(state, "op1", "Op One", "correct horse")
    # One candidate carries a DOI and a URL the tests can match against.
    held = store.latest_by("candidates.jsonl", "candidate_key")["r1-a"]
    store.append("candidates.jsonl", {**held, "doi": "10.1234/study.one"})
    flow_id = next(iter(flows.flows(store)))
    return {"projects": projects_dir, "store_dir": store_dir, "project": project,
            "store": store, "state": state, "flow_id": flow_id}


@contextmanager
def _served(ws, mapping=None):
    httpd = control.make_server(ws["projects"], ws["store_dir"], host="127.0.0.1", port=0,
                                state_dir=ws["state"], resolver=_resolver(mapping or {}))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        status, headers, body = _login(base)
        assert status == 200
        yield base, _cookie(headers), body["csrf_token"]
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _path(ws, flow_id=None):
    return f"/control/v1/p/{ws['project'].name}/flows/{flow_id or ws['flow_id']}/intake"


def _submit(served, ws, payload, flow_id=None):
    base, cookie, csrf = served
    return _request(base + _path(ws, flow_id), method="POST", payload=payload,
                    headers={"Cookie": cookie, "Origin": base, "X-CSRF-Token": csrf})


def _ledger(ws):
    return list(ws["store"].read(intake.LEDGER))


def test_a_doi_already_in_the_flow_is_a_duplicate_of_that_candidate(ws):
    with _served(ws) as served:
        status, _h, body = _submit(served, ws, {"kind": "doi",
                                                "value": "https://doi.org/10.1234/STUDY.ONE"})
    assert status == 201, body
    row = body["intake"]
    assert row["value"] == "10.1234/study.one"
    assert row["state"] == "DUPLICATE"
    assert row["links"] == {"candidate_key": "r1-a"}
    assert row["actor"] == "op1" and row["signer_auth"] == "portal-session"


def test_the_same_doi_twice_is_recognised_and_adds_nothing(ws):
    with _served(ws) as served:
        first = _submit(served, ws, {"kind": "doi", "value": "10.9999/new.work"})[2]["intake"]
        second = _submit(served, ws, {"kind": "doi", "value": "doi:10.9999/NEW.WORK"})[2]["intake"]
    assert first["state"] == "READY"
    assert second["state"] == "DUPLICATE"
    assert second["links"] == {"intake_id": first["intake_id"]}
    # the first item keeps its own state: the duplicate is a new row, not an edit of it
    assert intake.latest(ws["store"])[first["intake_id"]]["state"] == "READY"


def test_a_new_work_in_an_open_round_is_ready_for_its_next_discover(ws):
    before = list(ws["store"].read("candidates.jsonl"))
    with _served(ws) as served:
        row = _submit(served, ws, {"kind": "doi", "value": "10.9999/other",
                                   "note": "cited in the review"})[2]["intake"]
    assert row["state"] == "READY" and "r1" in row["reason"]
    assert row["note"] == "cited in the review"
    assert list(ws["store"].read("candidates.jsonl")) == before  # no candidate is created


def test_a_new_work_cannot_join_a_fixed_candidate_set(ws):
    manifest_row, _created = flows.create(ws["project"], ws["store"],
                                          selector=scope.Selector("r1", True),
                                          title="manifest population")
    before = list(ws["store"].read("candidates.jsonl"))
    with _served(ws) as served:
        status, _h, body = _submit(served, ws, {"kind": "doi", "value": "10.9999/new"},
                                   flow_id=manifest_row["flow_id"])
    assert status == 201
    row = body["intake"]
    assert row["state"] == "NEEDS_NEW_ROUND"
    assert {f["flow_id"] for f in row["links"]["open_flows"]} == {ws["flow_id"]}
    assert list(ws["store"].read("candidates.jsonl")) == before


def test_a_reference_matching_a_title_is_a_possible_version_for_a_person(ws):
    held = ws["store"].latest_by("candidates.jsonl", "candidate_key")["r1-b"]
    ws["store"].append("candidates.jsonl",
                       {**held, "title": "Information events and abnormal returns"})
    with _served(ws) as served:
        row = _submit(served, ws, {
            "kind": "reference",
            "value": "Doe, J. (2019). Information events and abnormal returns. Working paper."}
        )[2]["intake"]
    assert row["state"] == "POSSIBLE_VERSION"
    assert row["links"] == {"candidate_key": "r1-b"}


def test_a_short_title_inside_a_reference_is_not_taken_for_a_match(ws):
    """"Study two" is a candidate title; a reference merely containing those words is not
    evidence of the same work, so it is routed as new rather than flagged."""
    with _served(ws) as served:
        row = _submit(served, ws, {"kind": "reference",
                                   "value": "Roe, K. (2021). A study two decades on."}
                      )[2]["intake"]
    assert row["state"] == "READY"


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.8", "169.254.169.254", "::1",
                                     "192.168.1.4", None])
def test_a_link_to_a_non_public_destination_is_refused_and_not_recorded(ws, address):
    with _served(ws, {"internal.example": address}) as served:
        status, _h, body = _submit(served, ws, {"kind": "url",
                                                "value": "http://internal.example/paper.pdf"})
    assert status == 422 and body["error"]["code"] == "VALIDATION"
    assert _ledger(ws) == []


def test_a_link_is_normalised_and_matched_against_candidate_urls(ws):
    with _served(ws) as served:
        row = _submit(served, ws, {"kind": "url",
                                   "value": "https://www.example.org/S01.pdf?utm_source=x"}
                      )[2]["intake"]
    assert row["state"] == "DUPLICATE" and row["links"] == {"candidate_key": "r1-a"}


@pytest.mark.parametrize("payload", [
    {"kind": "pdf", "value": "x"},
    {"kind": "doi", "value": "not a doi"},
    {"kind": "url", "value": "ftp://example.org/x"},
    {"kind": "url", "value": "file:///etc/passwd"},
    {"kind": "doi", "value": ""},
    {"kind": "doi"},
])
def test_malformed_items_are_refused(ws, payload):
    with _served(ws) as served:
        status, _h, _b = _submit(served, ws, payload)
    assert status == 422
    assert _ledger(ws) == []


def test_the_list_gives_each_item_its_latest_state_newest_first(ws):
    with _served(ws) as served:
        first = _submit(served, ws, {"kind": "doi", "value": "10.9999/a"})[2]["intake"]
        second = _submit(served, ws, {"kind": "doi", "value": "10.9999/b"})[2]["intake"]
        base, cookie, _csrf = served
        status, _h, listed = _request(base + _path(ws), headers={"Cookie": cookie})
    assert status == 200
    assert [item["intake_id"] for item in listed["items"]] == [second["intake_id"],
                                                               first["intake_id"]]


def test_intake_routes_need_a_session(ws):
    with _served(ws) as served:
        base, _cookie_value, _csrf = served
        assert _request(base + _path(ws))[0] == 401
        assert _request(base + _path(ws), method="POST", payload={"kind": "doi", "value": "x"},
                        headers={"Origin": base})[0] == 401
