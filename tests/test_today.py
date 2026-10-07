"""B9: Today — what changed since the operator last looked, and what waits for them."""

from __future__ import annotations

import datetime as dt
import threading
from contextlib import contextmanager

import pytest

from claimstone import control, intake, operators, today
from tests.test_control import _cookie, _login, _request
from tests.test_decisions import ws  # noqa: F401 - the shared workspace fixture
from tests.test_decisions import _offer, _possible_version_file


def _project(payload, name):
    return next(p for p in payload["projects"] if p["project"] == name)


def test_a_first_visit_sees_everything_dated_and_says_it_is_a_first_visit(ws):  # noqa: F811
    payload = today.today(ws["projects"], ws["store_dir"], ws["state"], actor="op1")
    entry = _project(payload, ws["project"].name)
    assert entry["first_visit"] is True and entry["since"] is None
    assert entry["changed"]["counts"]["acquire"] >= 1
    assert payload["continues_without_you"] is None and "B12" in payload["continues_note"]


def test_a_marker_hides_what_came_before_it(ws):  # noqa: F811
    today.mark_seen(ws["state"], actor="op1", project=None, until=None)
    later = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=1)).isoformat()
    ws["store"].append(intake.LEDGER, {"intake_id": "x1", "flow_id": ws["flow_id"],
                                       "kind": "doi", "state": "READY", "recorded_at": later})
    entry = _project(today.today(ws["projects"], ws["store_dir"], ws["state"], actor="op1"),
                     ws["project"].name)
    assert entry["first_visit"] is False
    assert entry["changed"]["counts"] == {"intake": 1}
    assert entry["changed"]["newest"][0]["row"]["intake_id"] == "x1"


def test_markers_belong_to_one_operator_and_the_latest_covering_one_wins(ws):  # noqa: F811
    early = "2026-10-01T00:00:00+00:00"
    late = "2026-10-05T00:00:00+00:00"
    today.mark_seen(ws["state"], actor="op1", project=None, until=early)
    today.mark_seen(ws["state"], actor="op1", project=ws["project"].name, until=late)
    today.mark_seen(ws["state"], actor="op2", project=None, until=None)
    assert today.seen_until(ws["state"], actor="op1", project=ws["project"].name) == \
        dt.datetime.fromisoformat(late)
    assert today.seen_until(ws["state"], actor="op1", project="other") == \
        dt.datetime.fromisoformat(early)


def test_what_needs_you_is_split_into_required_and_optional(ws):  # noqa: F811
    _possible_version_file(ws)
    _offer(ws)
    entry = _project(today.today(ws["projects"], ws["store_dir"], ws["state"], actor="op1"),
                     ws["project"].name)
    required_types = {item["type"] for item in entry["needs_you"]["required"]}
    optional_types = {item["type"] for item in entry["needs_you"]["optional"]}
    assert "identity" in required_types
    assert optional_types == {"purchase_offer"}


def test_markers_cannot_be_in_the_future_and_are_owner_only(ws):  # noqa: F811
    with pytest.raises(ValueError, match="future"):
        today.mark_seen(ws["state"], actor="op1", project=None, until="2999-01-01T00:00:00+00:00")
    with pytest.raises(ValueError):
        today.mark_seen(ws["state"], actor="op1", project=None, until="2026-10-01")  # no zone
    today.mark_seen(ws["state"], actor="op1", project=None, until=None)
    import os
    import stat
    assert stat.S_IMODE(os.stat(ws["state"] / today.LEDGER).st_mode) == 0o600


@contextmanager
def _served(ws):  # noqa: F811
    httpd = control.make_server(ws["projects"], ws["store_dir"], host="127.0.0.1", port=0,
                                state_dir=ws["state"])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        status, headers, body = _login(base)
        yield base, _cookie(headers), body["csrf_token"]
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def test_the_routes(ws):  # noqa: F811
    with _served(ws) as (base, cookie, csrf):
        headers = {"Cookie": cookie, "Origin": base, "X-CSRF-Token": csrf}
        status, _h, payload = _request(base + "/control/v1/today", headers={"Cookie": cookie})
        assert status == 200 and payload["operator"] == "op1"
        assert _request(base + "/control/v1/seen", method="POST", headers=headers,
                        payload={"project": ws["project"].name})[0] == 201
        assert _request(base + "/control/v1/seen", method="POST", headers=headers,
                        payload={"project": "nope"})[0] == 404
        assert _request(base + "/control/v1/seen", method="POST", headers=headers,
                        payload={"until": "2999-01-01T00:00:00+00:00"})[0] == 422
        status, _h, payload = _request(base + "/control/v1/today", headers={"Cookie": cookie})
        assert _project(payload, ws["project"].name)["first_visit"] is False
        assert _request(base + "/control/v1/today")[0] == 401
