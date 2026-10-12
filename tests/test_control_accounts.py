"""Accounts and sign-in on the control server (design 2026-10-12): session unit tests."""

import json

import pytest

from claimstone import auth_events, control, operators
from tests.test_control import _cookie, _login, _request, _served


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_sessions_have_ids_methods_and_an_absolute_lifetime():
    clock = Clock()
    sessions = control.Sessions(idle_seconds=100, absolute_seconds=1000, clock=clock)
    token, s = sessions.create("a", "Alpha", role="admin", method="password")
    idle_token, _ = sessions.create("b", "Beta")
    assert s.session_id and s.session_id != token and s.method == "password" and s.role == "admin"
    # activity every 90 s keeps it alive far past the 100 s idle window...
    for step in range(1, 11):
        clock.now = 90.0 * step
        assert sessions.get(token) is not None, f"died at {clock.now}"
    assert clock.now == 900.0
    assert sessions.get(idle_token) is None          # ...which an untouched session did not survive
    clock.now = 990.0
    assert sessions.get(token) is not None
    # ...but never past the absolute one, though the idle window was refreshed 11 s ago
    clock.now = 1001.0
    assert sessions.get(token) is None


def test_the_idle_window_alone_still_expires_a_session():
    clock = Clock()
    sessions = control.Sessions(idle_seconds=100, absolute_seconds=1000, clock=clock)
    token, _ = sessions.create("a", "Alpha")
    clock.now = 101.0
    assert sessions.get(token) is None


def test_old_call_shape_defaults_to_an_operator_password_session():
    token, s = control.Sessions().create("a", "Alpha")
    assert (s.role, s.method, s.must_change_password) == ("operator", "password", False)
    assert s.created_at and s.csrf_token and s.csrf_token != token


def test_list_end_others_and_end_operator():
    sessions = control.Sessions()
    t1, _ = sessions.create("a", "Alpha", role="operator", method="password")
    t2, _ = sessions.create("a", "Alpha", role="operator", method="google")
    t3, _ = sessions.create("b", "Beta", role="operator", method="password")
    listed = sessions.list_for("a", current_token=t1)
    assert {x["method"] for x in listed} == {"password", "google"}
    assert [x["current"] for x in listed].count(True) == 1
    assert sessions.end_others("a", keep_token=t1) == 1
    assert sessions.get(t2) is None and sessions.get(t1) is not None and sessions.get(t3) is not None
    assert sessions.end_operator("a") == 1 and sessions.get(t1) is None


def test_list_for_never_exposes_a_token():
    sessions = control.Sessions()
    t1, s1 = sessions.create("a", "Alpha")
    t2, s2 = sessions.create("a", "Alpha", method="google")
    listed = sessions.list_for("a", current_token=t1)
    blob = repr(listed)
    assert t1 not in blob and t2 not in blob
    assert s1.csrf_token not in blob and s2.csrf_token not in blob
    assert {x["session_id"] for x in listed} == {s1.session_id, s2.session_id}
    assert all(set(x) == {"session_id", "created_at", "last_seen", "method", "current"}
               for x in listed)


def test_ended_and_expired_sessions_leave_no_state_behind():
    clock = Clock()
    sessions = control.Sessions(idle_seconds=100, absolute_seconds=1000, clock=clock)
    gone, _ = sessions.create("a", "Alpha")
    kept, _ = sessions.create("b", "Beta")
    sessions.end(gone)
    clock.now = 101.0                       # `kept` is now idle-expired; create prunes it
    sessions.create("c", "Gamma")
    tables = (sessions._expires, sessions._dies, sessions._rows, sessions._seen)
    assert all(gone not in t and kept not in t for t in tables)
    assert all(len(t) == 1 for t in tables)


def test_must_change_password_can_be_cleared():
    sessions = control.Sessions()
    token, s = sessions.create("a", "Alpha", role="operator", method="password", must_change=True)
    assert s.must_change_password is True
    sessions.clear_must_change(token)
    assert sessions.get(token).must_change_password is False


# --- the routes, against one real server ------------------------------------------------------------

PW = "correct horse battery"
BASE = "/control/v1"


@pytest.fixture()
def state(tmp_path):
    d = tmp_path / "state"
    operators.add_operator(d, "adm", "Admin", PW, email="adm@example.org")
    operators.add_operator(d, "ann", "Ann", PW, email="ann@example.org")
    return d


def _signed(base, who="adm", password=PW):
    status, headers, body = _login(base, who, password)
    assert status == 200, body
    return {"Cookie": _cookie(headers), "Origin": base, "X-CSRF-Token": body["csrf_token"]}, body


def _post(base, path, payload, headers):
    return _request(f"{base}{BASE}{path}", "POST", payload, headers=headers)


def test_login_answers_role_and_must_change(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        _headers, body = _signed(base)
        assert body["operator"] == {"id": "adm", "name": "Admin", "role": "admin",
                                    "must_change_password": False}


def test_a_new_token_at_every_login(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        assert _cookie(_login(base, "adm", PW)[1]) != _cookie(_login(base, "adm", PW)[1])


def test_unknown_id_and_wrong_password_answer_the_same_401(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        wrong = _login(base, "adm", "wrong wrong wrong")
        unknown = _login(base, "nobody", "wrong wrong wrong")
        assert wrong[0] == unknown[0] == 401 and wrong[2] == unknown[2]


def test_the_address_budget_blocks_many_ids_even_a_correct_password(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        for n in range(20):
            assert _login(base, f"nobody{n}", "wrong wrong wrong")[0] == 401
        assert _login(base, "adm", PW)[0] == 429
    assert "login_blocked" in (state / "auth_events.jsonl").read_text()


def test_login_events_are_recorded_without_the_password_or_a_token(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        _login(base, "adm", "wrong wrong wrong")
        _, headers, body = _login(base, "adm", PW)
    text = (state / "auth_events.jsonl").read_text()
    assert "login_failed" in text and "login_ok" in text
    for secret in ("wrong wrong", PW, _cookie(headers).split("=", 1)[1], body["csrf_token"]):
        assert secret not in text


def test_session_options_is_public_and_says_google_is_off_by_default(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        assert _request(f"{base}{BASE}/session/options")[2] == {"google": False}


def test_change_password_ends_other_sessions_and_keeps_this_one(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        mine, _ = _signed(base)
        other, _ = _signed(base)
        status, _, body = _post(base, "/account/password",
                                {"current": PW, "new": "a brand new password"}, mine)
        assert status == 200 and body == {"changed": True}
        assert _request(f"{base}{BASE}/session", headers=mine)[0] == 200
        assert _request(f"{base}{BASE}/session", headers=other)[0] == 401
        assert _login(base, "adm", PW)[0] == 401
        assert _login(base, "adm", "a brand new password")[0] == 200
    assert "a brand new password" not in (state / "auth_events.jsonl").read_text()


def test_change_password_refuses_wrong_current_and_weak_new(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        mine, _ = _signed(base)
        wrong = _post(base, "/account/password", {"current": "nope nope nope!", "new": "a brand new password"}, mine)
        assert wrong[0] == 403 and wrong[2]["error"]["code"] == "REAUTH"
        assert _post(base, "/account/password", {"current": PW, "new": "short"}, mine)[0] == 422
        assert _post(base, "/account/password", {"current": PW, "new": "x" * 20, "extra": 1}, mine)[0] == 400


def test_a_wrong_current_password_spends_the_login_budget(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        mine, _ = _signed(base)
        for _ in range(5):
            assert _post(base, "/account/password", {"current": "nope nope nope!", "new": "a brand new password"}, mine)[0] == 403
        assert _post(base, "/account/password", {"current": PW, "new": "a brand new password"}, mine)[0] == 429


def test_sessions_listing_and_end_others(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        mine, _ = _signed(base)
        other, _ = _signed(base)
        listed = _request(f"{base}{BASE}/account/sessions", headers=mine)[2]["sessions"]
        assert len(listed) == 2 and [s["current"] for s in listed].count(True) == 1
        assert "token" not in json.dumps(listed)
        assert _post(base, "/account/sessions/end-others", {}, mine)[2] == {"ended": 1}
        assert _request(f"{base}{BASE}/session", headers=other)[0] == 401
        assert _post(base, "/account/sessions/end-others", {"x": 1}, mine)[0] == 400


def test_account_read_shows_email_and_link_state_and_no_secret(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        mine, _ = _signed(base)
        body = _request(f"{base}{BASE}/account", headers=mine)[2]
        assert body["operator"]["email"] == "adm@example.org"
        assert body["operator"]["google_linked"] is False and body["operator"]["role"] == "admin"
        assert "hash" not in json.dumps(body) and "salt" not in json.dumps(body)
