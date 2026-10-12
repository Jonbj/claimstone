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


def test_people_listing_is_admin_only_and_exposes_no_secrets(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        adm, _ = _signed(base)
        ann, _ = _signed(base, "ann")
        denied = _request(f"{base}{BASE}/people", headers=ann)
        assert denied[0] == 403 and denied[2]["error"]["code"] == "FORBIDDEN"
        people = _request(f"{base}{BASE}/people", headers=adm)[2]["people"]
        assert {p["id"] for p in people} == {"adm", "ann"}
        text = json.dumps(people)
        assert "hash" not in text and "salt" not in text and "sub" not in text.replace("google", "")


def test_a_non_admin_cannot_burn_the_budget_through_people_routes(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        ann, _ = _signed(base, "ann")
        for _ in range(7):
            status, _, body = _post(base, "/people/adm/disable", {"password": "nope nope nope!"}, ann)
            assert status == 403 and body["error"]["code"] == "FORBIDDEN"
        assert _login(base, "ann", PW)[0] == 200  # still not locked out


def test_admin_creates_a_person_who_must_change_the_temporary_password(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        adm, _ = _signed(base)
        status, _, body = _post(base, "/people", {
            "password": PW, "id": "bob", "name": "Bob", "email": "bob@example.org",
            "role": "operator", "temporary_password": "temporary secret 1"}, adm)
        assert status == 201 and body["person"]["id"] == "bob"
        assert "hash" not in json.dumps(body)
        bob, login = _signed(base, "bob", "temporary secret 1")
        assert login["operator"]["must_change_password"] is True
        # the guard covers GET and POST; the allowed routes stay open
        assert _request(f"{base}{BASE}/today", headers=bob)[2]["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"
        blocked = _post(base, "/seen", {}, bob)
        assert blocked[0] == 403 and blocked[2]["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"
        assert _request(f"{base}{BASE}/account/sessions", headers=bob)[0] == 403
        assert _request(f"{base}{BASE}/account", headers=bob)[0] == 200
        assert _request(f"{base}{BASE}/session", headers=bob)[0] == 200
        assert _post(base, "/account/password",
                     {"current": "temporary secret 1", "new": "my own long password"}, bob)[0] == 200
        assert _request(f"{base}{BASE}/today", headers=bob)[0] == 200
    assert "temporary secret 1" not in (state / "auth_events.jsonl").read_text()


def test_admin_actions_need_the_admins_password_again(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        adm, _ = _signed(base)
        status, _, body = _post(base, "/people/ann/disable", {"password": "not my password!"}, adm)
        assert status == 403 and body["error"]["code"] == "REAUTH"
        assert _post(base, "/people/ann/disable", {}, adm)[0] == 403
        assert _post(base, "/people/ann/disable", {"password": PW, "x": 1}, adm)[0] == 400
    assert "reauth_failed" in (state / "auth_events.jsonl").read_text()


def test_admin_reauth_shares_the_login_budget(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        adm, _ = _signed(base)
        for _ in range(5):
            assert _post(base, "/people/ann/disable", {"password": "not my password!"}, adm)[0] == 403
        assert _post(base, "/people/ann/disable", {"password": PW}, adm)[0] == 429


def test_disabling_a_person_ends_their_sessions_at_once(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        adm, _ = _signed(base)
        ann, _ = _signed(base, "ann")
        assert _post(base, "/people/ann/disable", {"password": PW}, adm)[0] == 200
        assert _request(f"{base}{BASE}/session", headers=ann)[0] == 401
        assert _login(base, "ann", PW)[0] == 401
        assert _post(base, "/people/ann/enable", {"password": PW}, adm)[0] == 200
        assert _login(base, "ann", PW)[0] == 200


def test_the_last_admin_cannot_be_disabled_through_the_portal(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        adm, _ = _signed(base)
        status, _, body = _post(base, "/people/adm/disable", {"password": PW}, adm)
        assert status == 422 and "last admin" in body["error"]["message"]
        assert _post(base, "/people/ghost/disable", {"password": PW}, adm)[0] == 404


def test_an_admin_set_password_ends_the_persons_sessions_and_demands_a_change(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        adm, _ = _signed(base)
        ann, _ = _signed(base, "ann")
        assert _post(base, "/people/ann/password",
                     {"password": PW, "new_password": "temporary secret 2"}, adm)[2] == {"changed": True}
        assert _request(f"{base}{BASE}/session", headers=ann)[0] == 401
        assert _login(base, "ann", "temporary secret 2")[2]["operator"]["must_change_password"] is True


def test_email_and_role_changes_and_a_demoted_admin_loses_the_power_at_once(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        adm, _ = _signed(base)
        ann, _ = _signed(base, "ann")
        assert _post(base, "/people/ann/role", {"password": PW, "role": "admin"}, adm)[2]["person"]["role"] == "admin"
        assert _request(f"{base}{BASE}/people", headers=ann)[0] == 200   # ann's live session, read from the ledger
        assert _post(base, "/people/ann/role", {"password": PW, "role": "operator"}, adm)[0] == 200
        assert _request(f"{base}{BASE}/people", headers=ann)[0] == 403    # demoted: gone at once
        assert _post(base, "/people/ann/email", {"password": PW, "email": "new@example.org"}, adm)[2]["person"]["email"] == "new@example.org"
        assert _post(base, "/people/ann/role", {"password": PW, "role": "root"}, adm)[0] == 422


def test_password_routes_ignore_the_idempotency_key(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        adm, _ = _signed(base)
        key = {**adm, "Idempotency-Key": "k-1"}
        first = _post(base, "/people/ann/password", {"password": PW, "new_password": "temporary secret 2"}, key)
        assert first[0] == 200
        # same key, same body: executed again, not replayed from memory (re-authentication is checked)
        bad = _post(base, "/people/ann/password", {"password": "nope nope nope!", "new_password": "temporary secret 2"}, key)
        assert bad[0] == 403
        again = _post(base, "/people/ann/password", {"password": PW, "new_password": "temporary secret 2"}, key)
        assert again[0] == 200


# --- revocation holds: the credential stamp is checked on every request --------------------------------


def test_the_stamp_follows_the_credential_only():
    d = None
    import tempfile, pathlib
    d = pathlib.Path(tempfile.mkdtemp()) / "st"
    operators.add_operator(d, "a", "Alpha", PW)
    first = operators.stamp(operators.load(d)["a"])
    assert len(first) == 16 and first == operators.stamp(operators.load(d)["a"])
    operators.set_email(d, "a", "a@example.org", by="cli")
    assert operators.stamp(operators.load(d)["a"]) == first
    operators.set_password(d, "a", "another long password", by="cli")
    assert operators.stamp(operators.load(d)["a"]) != first


def _alive(base, headers):
    return _request(f"{base}{BASE}/session", headers=headers)[0]


def test_a_cli_style_disable_ends_a_live_session_on_its_next_request(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        ann, _ = _signed(base, "ann")
        assert _alive(base, ann) == 200
        operators.disable_operator(state, "ann", by="cli")          # another process, no server involved
        assert _alive(base, ann) == 401
        operators.enable_operator(state, "ann", by="cli")
        assert _alive(base, ann) == 401                              # and it stays dead


def test_a_cli_style_password_change_ends_other_sessions(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        ann, _ = _signed(base, "ann")
        operators.set_password(state, "ann", "set from the command line", by="cli")
        assert _alive(base, ann) == 401


def test_own_password_change_keeps_the_current_session_alive_by_refreshing_its_stamp(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        mine, _ = _signed(base)
        other, _ = _signed(base)
        assert _post(base, "/account/password", {"current": PW, "new": "a brand new password"}, mine)[0] == 200
        assert _alive(base, mine) == 200 and _alive(base, other) == 401
        assert _post(base, "/account/password", {"current": "a brand new password", "new": "and a third password"}, mine)[0] == 200


def test_a_login_verified_before_a_change_and_created_after_it_dies_on_first_use(tmp_path, state):
    """The reviewer's interleaving: verify, then the change lands, then the session is created."""
    with _served(tmp_path, state) as (httpd, base):
        handler = httpd.RequestHandlerClass
        row = operators.load(state)["ann"]
        assert operators.verify(row, PW)                              # the login thread verified...
        operators.disable_operator(state, "ann", by="adm")            # ...a disable lands...
        handler.sessions.end_operator("ann")
        operators.enable_operator(state, "ann", by="adm")
        operators.set_password(state, "ann", "reset by the admin", by="adm", must_change=True)
        token, session = handler.sessions.create("ann", "Ann", stamp=operators.stamp(row))
        headers = {"Cookie": f"{control.SESSION_COOKIE}={token}"}
        assert _alive(base, headers) == 401                           # ...and the late session is dead
