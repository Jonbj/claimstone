"""B12: the scheduler's operations through the control server.

Reading replays the scheduler's own ledger; authorizing records the session's operator and must
repeat the exact limits shown; pause and resume are not built, because the ledger has no event
for them yet. Planning stays with the scheduler and the CLI.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager

import pytest

from claimstone import control, operations, operators, today
from tests.test_control import _cookie, _login, _request
from tests.test_operations import _fixture


@pytest.fixture()
def ws(tmp_path):
    project, store, flow = _fixture(tmp_path)
    state = tmp_path / "state"
    operators.add_operator(state, "op1", "Op One", "correct horse")
    plan = operations.plan(project, store, flow["flow_id"], "extract-build", batch="e1")
    return {"projects": tmp_path, "store_dir": tmp_path / "store", "project": project,
            "store": store, "state": state, "flow_id": flow["flow_id"],
            "operation_id": operations._digest(plan)}


@contextmanager
def _served(ws):
    httpd = control.make_server(ws["projects"], ws["store_dir"], host="127.0.0.1", port=0,
                                state_dir=ws["state"])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        status, headers, body = _login(base)
        prefix = f"/control/v1/p/{ws['project'].name}/flows/{ws['flow_id']}/operations"
        yield base, prefix, {"Cookie": _cookie(headers), "Origin": base,
                             "X-CSRF-Token": body["csrf_token"]}
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _list(base, prefix, headers):
    return _request(base + prefix, headers={"Cookie": headers["Cookie"]})


def test_the_list_reads_the_schedulers_ledger_and_claims_no_heartbeat(ws):
    with _served(ws) as (base, prefix, headers):
        status, _h, body = _list(base, prefix, headers)
    assert status == 200
    [item] = body["operations"]
    assert item["operation_id"] == ws["operation_id"] and item["state"] == "PLANNED"
    assert item["worker_last_seen"] is None and "no heartbeat" in item["worker_note"]
    assert item["limits"] == {"network_requests": 0, "model_calls": 0, "spend_usd": 0}


def test_authorizing_records_the_session_operator_and_the_exact_limits(ws):
    with _served(ws) as (base, prefix, headers):
        limits = _list(base, prefix, headers)[2]["operations"][0]["limits"]
        path = f"{prefix}/{ws['operation_id']}/authorize"
        status, _h, body = _request(base + path, method="POST", headers=headers,
                                    payload={"limits": limits})
        again = _request(base + path, method="POST", headers=headers, payload={"limits": limits})
        listed = _list(base, prefix, headers)[2]["operations"][0]
    assert status == 201 and body["already_authorized"] is False
    identity = body["authorized"]["identity"]
    assert identity == {"signer_auth": "portal-session", "operator": "op1", "name": "Op One"}
    assert again[0] == 200 and again[2]["already_authorized"] is True
    assert listed["state"] == "AUTHORIZED" and listed["authorized_by"] == identity
    # The worker accepts what the portal authorized: the ledger replays cleanly and executes.
    assert operations.execute(ws["project"], ws["store"], ws["operation_id"])["units"] > 0


def test_limits_that_differ_from_the_plan_are_refused(ws):
    with _served(ws) as (base, prefix, headers):
        path = f"{prefix}/{ws['operation_id']}/authorize"
        status, _h, body = _request(base + path, method="POST", headers=headers, payload={
            "limits": {"network_requests": 10, "model_calls": 0, "spend_usd": 0}})
        missing = _request(base + path, method="POST", headers=headers, payload={})
    assert status == 409 and body["error"]["code"] == "PLAN_DIFFERS"
    assert missing[0] == 409
    assert [row["event"] for row in ws["store"].read(operations.LEDGER)] == ["planned"]


def test_unknown_operation_and_unbuilt_pause(ws):
    with _served(ws) as (base, prefix, headers):
        assert _request(base + f"{prefix}/{'0' * 64}/authorize", method="POST", headers=headers,
                        payload={"limits": {}})[0] == 404
        status, _h, body = _request(base + f"{prefix}/{ws['operation_id']}/pause",
                                    method="POST", headers=headers, payload={})
    assert status == 501 and "stopping event" in body["error"]["message"]
    assert [row["event"] for row in ws["store"].read(operations.LEDGER)] == ["planned"]


def test_today_lists_what_continues_without_a_person(ws):
    operations.authorize(ws["store"], ws["operation_id"])
    payload = today.today(ws["projects"], ws["store_dir"], ws["state"], actor="op1")
    entry = next(p for p in payload["projects"] if p["project"] == ws["project"].name)
    assert [op["operation_id"] for op in entry["continues_without_you"]] == [ws["operation_id"]]
