"""Accounts and sign-in on the control server (design 2026-10-12): session unit tests."""

import contextlib
import json
import threading

import pytest

from claimstone import auth_events, control, operators
from tests.test_control import _cookie, _login, _request, _served as _served_default


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


@contextlib.contextmanager
def _served(tmp_path, state, **options):
    if not options:
        with _served_default(tmp_path, state) as pair:
            yield pair
        return
    httpd = control.make_server(tmp_path / "projects", tmp_path / "store", host="127.0.0.1",
                                port=0, state_dir=state, **options)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


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
        body = {"password": PW, "new_password": "temporary secret 2"}
        assert _post(base, "/people/ann/password", body, key)[0] == 200
        # the IDENTICAL request again: a replay would answer from memory; this executes
        assert _post(base, "/people/ann/password", body, key)[0] == 200
        # and a different body under the same key is executed (a replay would answer 409)
        bad = _post(base, "/people/ann/password", {**body, "password": "nope nope nope!"}, key)
        assert bad[0] == 403
    events = [json.loads(line) for line in (state / "auth_events.jsonl").read_text().splitlines()]
    assert [e["event"] for e in events].count("password_set_by_admin") == 2


def test_every_route_that_reads_a_password_is_no_replay():
    import inspect
    import re
    reads = re.compile(r"""_only_keys\([^)]*["'](password|current|new_password|temporary_password)["']""")
    found = set()
    for route in control.ROUTES:
        if route.public or route.method != "POST":
            continue
        source = inspect.getsource(getattr(control._Handler, route.handler))
        if reads.search(source):
            found.add(route.handler)
            assert route.no_replay, route
    assert {"_account_password", "_people_create", "_people_password", "_people_disable",
            "_people_enable", "_people_email", "_people_role", "_admin_credential"} <= found


def test_credentials_and_outbound_checks_are_admin_powers(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        ann, _ = _signed(base, "ann")
        adm, _ = _signed(base)
        for method, path, payload in (("GET", "/admin", None),
                                      ("POST", "/admin/check", {"target": "openalex"}),
                                      ("POST", "/admin/credential", {"name": "X", "value": "y", "password": PW}),
                                      ("POST", "/admin/paid-test", {})):
            denied = _request(f"{base}{BASE}{path}", method, payload, headers=ann)
            assert denied[0] == 403 and denied[2]["error"]["code"] == "FORBIDDEN", (path, denied)
        assert _request(f"{base}{BASE}/admin", headers=adm)[0] == 200
        assert _post(base, "/admin/paid-test", {}, adm)[0] == 501


def test_a_spoofed_x_real_ip_is_ignored_without_the_flag(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        for n in range(20):
            assert _login(base, f"nobody{n}", "wrong wrong wrong", headers={"X-Real-IP": f"10.0.0.{n}"})[0] == 401
        assert _login(base, "adm", PW, headers={"X-Real-IP": "10.9.9.9"})[0] == 429


def test_with_trust_forwarded_each_real_ip_has_its_own_address_budget(tmp_path, state):
    with _served(tmp_path, state, trust_forwarded=True) as (_h, base):
        for n in range(20):
            assert _login(base, f"nobody{n}", "wrong wrong wrong", headers={"X-Real-IP": "10.0.0.1"})[0] == 401
        assert _login(base, "adm", PW, headers={"X-Real-IP": "10.0.0.1"})[0] == 429
        assert _login(base, "adm", PW, headers={"X-Real-IP": "10.0.0.2"})[0] == 200
        # a header that is not an address is ignored: the peer's own address is the key
        assert _login(base, "ann", PW, headers={"X-Real-IP": "not an address"})[0] == 200
    assert "10.0.0.1" in (state / "auth_events.jsonl").read_text()


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


# --- the budget is reserved before scrypt; verifies are bounded; input is hardened ----------------------


def test_concurrent_wrong_logins_for_one_id_cannot_exceed_the_budget(tmp_path, state, monkeypatch):
    verifies = []
    real = operators.verify
    monkeypatch.setattr(operators, "verify", lambda row, pw: (verifies.append(1), real(row, pw))[1])
    with _served(tmp_path, state) as (_h, base):
        statuses = []
        lock = threading.Lock()

        def attempt():
            status = _login(base, "adm", "wrong wrong wrong")[0]
            with lock:
                statuses.append(status)

        threads = [threading.Thread(target=attempt) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        assert len(statuses) == 50
        assert statuses.count(401) == control.LOGIN_FAILURE_LIMIT and statuses.count(429) == 45
        assert len(verifies) == control.LOGIN_FAILURE_LIMIT      # a blocked attempt never pays scrypt


def test_the_budget_forgives_only_its_own_reservation():
    budget = control.LoginBudget(limit=2)
    assert budget.reserve("a") and budget.reserve("a") and not budget.reserve("a")
    budget.forgive("a")
    assert budget.reserve("a")
    budget.forgive("nobody")                                     # harmless


def test_a_success_gives_its_reservation_back(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        for _ in range(12):
            assert _login(base, "adm", PW)[0] == 200             # more successes than the failure limit


def test_a_too_long_password_is_refused_before_scrypt_with_the_same_sentence(tmp_path, state, monkeypatch):
    calls = []
    real = operators.verify
    monkeypatch.setattr(operators, "verify", lambda row, pw: (calls.append(1), real(row, pw))[1])
    with _served(tmp_path, state) as (_h, base):
        wrong = _login(base, "adm", "wrong wrong wrong")
        long = _login(base, "adm", "x" * (operators.PASSWORD_MAX + 1))
        assert long[0] == 401 and long[2] == wrong[2]
        assert len(calls) == 1                                   # only the short one was verified
        adm, _ = _signed(base)
        calls.clear()
        refused = _post(base, "/people/ann/disable", {"password": "x" * 500}, adm)
        assert refused[0] == 403 and refused[2]["error"]["code"] == "REAUTH" and not calls


def test_get_session_reads_the_role_from_the_ledger(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        operators.add_operator(state, "zed", "Zed", PW, role="admin")
        zed, _ = _signed(base, "zed")
        operators.set_role(state, "zed", "operator", by="cli")
        assert _request(f"{base}{BASE}/session", headers=zed)[2]["operator"]["role"] == "operator"


def test_a_new_password_equal_to_the_current_one_is_refused(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        mine, _ = _signed(base)
        refused = _post(base, "/account/password", {"current": PW, "new": PW}, mine)
        assert refused[0] == 422 and "different password" in refused[2]["error"]["message"]


def test_people_fields_must_be_strings(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        adm, _ = _signed(base)
        good = {"password": PW, "id": "bob", "name": "Bob", "temporary_password": "temporary secret 1"}
        for patch in ({"email": 5}, {"email": ["a@b.c"]}, {"name": 7}, {"name": ""}, {"name": "n" * 101},
                      {"role": 1}, {"role": ["admin"]}):
            assert _post(base, "/people", {**good, **patch}, adm)[0] == 422, patch
        assert _post(base, "/people/ann/email", {"password": PW, "email": 5}, adm)[0] == 422
        assert _post(base, "/people/ann/role", {"password": PW, "role": ["admin"]}, adm)[0] == 422
        assert _post(base, "/people", good, adm)[0] == 201


def test_sessions_past_their_expiry_are_not_listed_or_counted():
    clock = Clock()
    sessions = control.Sessions(idle_seconds=100, absolute_seconds=1000, clock=clock)
    old, _ = sessions.create("a", "Alpha")
    clock.now = 90.0
    keep, _ = sessions.create("a", "Alpha")
    clock.now = 150.0                                            # `old` idled out, `keep` has not
    assert len(sessions.list_for("a", keep)) == 1
    assert sessions.end_others("a", keep) == 0
    assert sessions.end_operator("a") == 1


def test_logout_is_recorded_as_an_event(tmp_path, state):
    with _served(tmp_path, state) as (_h, base):
        mine, _ = _signed(base)
        assert _request(f"{base}/control/v1/session/end", "POST", {}, headers=mine)[0] == 200
    events = [json.loads(line) for line in (state / "auth_events.jsonl").read_text().splitlines()]
    assert any(e["event"] == "logout" and e["id"] == "adm" for e in events)
