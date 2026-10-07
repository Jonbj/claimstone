"""control: the write boundary's own promises — spec B4's test list.

One real server on a port-0 bind against a tmp state dir: login and logout, the wrong
password, the rate limit, CSRF, Origin, the cookie flags, the refused non-loopback
bind, and the anonymous-access sweep over `control.ROUTES` — the registry every later
step registers its POST routes in, so a new route is covered the moment it appears.
No socket opens against anything but 127.0.0.1; nothing real is contacted.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager

import pytest

from claimstone import cli, control, operators


@pytest.fixture()
def state(tmp_path):
    """A state dir with one enabled operator and one disabled one."""
    directory = tmp_path / "state"
    operators.add_operator(directory, "op1", "Op One", "correct horse")
    operators.add_operator(directory, "gone", "Gone Operator", "battery staple")
    operators.disable_operator(directory, "gone")
    return directory


@contextmanager
def _served(tmp_path, state):
    httpd = control.make_server(tmp_path / "projects", tmp_path / "store",
                                host="127.0.0.1", port=0, state_dir=state)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _request(url, method="GET", payload=None, raw_body=None, headers=None):
    """(status, headers, parsed-body-or-text). `raw_body` sends exact bytes with the
    given Content-Type; `payload` sends JSON."""
    if raw_body is not None:
        data, sent = raw_body, {"Content-Type": "application/json"}
    elif payload is not None:
        data, sent = json.dumps(payload).encode(), {"Content-Type": "application/json"}
    else:
        data, sent = None, {}
    sent.update(headers or {})
    request = urllib.request.Request(url, data=data, headers=sent, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status, head, body = response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as raised:
        status, head, body = raised.code, dict(raised.headers), raised.read()
    text = body.decode("utf-8")
    return status, head, (json.loads(text) if text.strip().startswith("{") else text)


def _login(base, operator_id="op1", password="correct horse", headers=None):
    sent = {"Origin": base}
    sent.update(headers or {})
    return _request(f"{base}/control/v1/session", method="POST",
                    payload={"id": operator_id, "password": password}, headers=sent)


def _cookie(headers):
    return (headers.get("Set-Cookie") or "").split(";")[0]


# --- the operators ledger, no socket --------------------------------------------------------------


def test_operator_rows_add_disable_verify(tmp_path):
    directory = tmp_path / "st"
    row = operators.add_operator(directory, "a", "Alpha", "pw")
    assert row["operator_version"] == 1
    assert row["scrypt"] == {"n": 32768, "r": 8, "p": 1}
    assert operators.verify(operators.load(directory)["a"], "pw")
    assert not operators.verify(operators.load(directory)["a"], "other")
    operators.disable_operator(directory, "a")
    assert operators.load(directory) == {}
    with pytest.raises(operators.OperatorError):
        operators.add_operator(directory, "a", "Again", "pw2")  # any row refuses a re-add
    with pytest.raises(operators.OperatorError):
        operators.disable_operator(directory, "nobody")


def test_no_password_or_hash_leaks_into_a_row(tmp_path):
    row = operators.add_operator(tmp_path, "a", "Alpha", "secret-password")
    dumped = json.dumps(row)
    assert "secret-password" not in dumped
    text = (tmp_path / operators.LEDGER).read_text(encoding="utf-8")
    assert "secret-password" not in text


# --- login, logout, and the session routes --------------------------------------------------------


def test_login_and_logout_round_trip(tmp_path, state):
    with _served(tmp_path, state) as (_httpd, base):
        status, headers, body = _login(base)
        assert status == 200
        assert body["operator"] == {"id": "op1", "name": "Op One"}
        assert len(body["csrf_token"]) == 64
        cookie = _cookie(headers)

        status, headers, body = _request(f"{base}/control/v1/session",
                                         headers={"Cookie": cookie})
        assert status == 200 and body["csrf_token"]
        csrf = body["csrf_token"]

        status, _headers, body = _request(
            f"{base}/control/v1/session/end", method="POST", payload={},
            headers={"Cookie": cookie, "Origin": base, "X-CSRF-Token": csrf})
        assert status == 200 and body == {"ended": True}

        # after logout the token is dead and the cookie was expired
        assert _request(f"{base}/control/v1/session",
                        headers={"Cookie": cookie})[0] == 401


def test_wrong_password_and_unknown_id_answer_one_sentence(tmp_path, state):
    with _served(tmp_path, state) as (_httpd, base):
        wrong = _login(base, password="nope")
        unknown = _login(base, operator_id="who")
        assert wrong[0] == 401 and unknown[0] == 401
        assert wrong[2] == unknown[2]  # the same envelope: which failed is not told


def test_disabled_operator_cannot_log_in(tmp_path, state):
    with _served(tmp_path, state) as (_httpd, base):
        status, _headers, _body = _login(base, operator_id="gone",
                                         password="battery staple")
        assert status == 401


def test_a_restart_logs_everyone_out(tmp_path, state):
    with _served(tmp_path, state) as (_httpd, base):
        cookie = _cookie(_login(base)[1])
    with _served(tmp_path, state) as (_httpd2, base2):
        status = _request(f"{base2}/control/v1/session", headers={"Cookie": cookie})[0]
        assert status == 401


# --- the rate limit --------------------------------------------------------------------------------


def test_five_failures_then_refusal_even_with_the_right_password(tmp_path, state):
    with _served(tmp_path, state) as (_httpd, base):
        for _ in range(5):
            assert _login(base, password="nope")[0] == 401
        status, _headers, body = _login(base)  # the correct password, still refused
        assert status == 429
        assert body["error"]["code"] == "RATE_LIMITED"


# --- CSRF and Origin -------------------------------------------------------------------------------


def test_logout_requires_the_csrf_header(tmp_path, state):
    with _served(tmp_path, state) as (_httpd, base):
        cookie = _cookie(_login(base)[1])
        _, headers, body = _request(f"{base}/control/v1/session",
                                    headers={"Cookie": cookie})
        csrf = body["csrf_token"]
        end = f"{base}/control/v1/session/end"
        missing = _request(end, method="POST", payload={},
                           headers={"Cookie": cookie, "Origin": base})
        wrong = _request(end, method="POST", payload={},
                         headers={"Cookie": cookie, "Origin": base,
                                  "X-CSRF-Token": "0" * 64})
        assert missing[0] == 403 and missing[2]["error"]["code"] == "CSRF"
        assert wrong[0] == 403 and wrong[2]["error"]["code"] == "CSRF"


def test_post_requires_a_present_same_origin_origin(tmp_path, state):
    with _served(tmp_path, state) as (_httpd, base):
        absent = _request(f"{base}/control/v1/session", method="POST",
                          payload={"id": "op1", "password": "correct horse"})
        foreign = _login(base, headers={"Origin": "http://evil.example"})
        assert absent[0] == 403 and absent[2]["error"]["code"] == "NO_ORIGIN"
        assert foreign[0] == 403 and foreign[2]["error"]["code"] == "CROSS_ORIGIN"


# --- the cookie ------------------------------------------------------------------------------------


def test_cookie_flags(tmp_path, state):
    with _served(tmp_path, state) as (_httpd, base):
        cookie = _login(base)[1]["Set-Cookie"]
        assert cookie.startswith("claimstone_control=")
        for flag in ("HttpOnly", "SameSite=Strict", "Path=/"):
            assert flag in cookie
        assert "Secure" not in cookie  # plain HTTP: the flag would drop the session

        proxied = _login(base, headers={"X-Forwarded-Proto": "https"})[1]["Set-Cookie"]
        assert "Secure" in proxied


# --- the bind --------------------------------------------------------------------------------------


def test_non_loopback_bind_refused(tmp_path, state):
    with pytest.raises(ValueError):
        control.make_server(tmp_path / "projects", tmp_path / "store",
                            host="0.0.0.0", port=0, state_dir=state)
    with pytest.raises(ValueError):
        control.make_server(tmp_path / "projects", tmp_path / "store",
                            host="192.168.1.10", port=0, state_dir=state)
    # naming the proxy's authority authorizes the bind it fronts
    httpd = control.make_server(tmp_path / "projects", tmp_path / "store",
                                host="0.0.0.0", port=0,
                                allow_hosts=("portal.example",), state_dir=state)
    httpd.server_close()


def test_cli_refuses_the_non_loopback_bind(tmp_path, capsys):
    assert cli.main(["control", "--projects", str(tmp_path / "projects"),
                     "--store", str(tmp_path / "store"),
                     "--bind", "0.0.0.0", "--port", "0"]) == 2
    assert "refusing a non-loopback bind" in capsys.readouterr().err


# --- every POST refuses an anonymous request ------------------------------------------------------


def _path(route: control.Route) -> str:
    parts = ["control", "v1"]
    for part in route.template:
        parts.append(f"x-{part[1:-1]}" if part.startswith("{") else part)
    return "/" + "/".join(parts)


def test_every_post_route_refuses_an_anonymous_request(tmp_path, state):
    """The spec's last B4 test: anonymous means no session cookie. Non-public POST
    routes answer 401; the public login answers 400 for an empty body and mints no
    session. Enumerating `ROUTES` covers routes added by later steps automatically."""
    assert any(r.method == "POST" and not r.public for r in control.ROUTES)
    with _served(tmp_path, state) as (_httpd, base):
        for route in control.ROUTES:
            if route.method != "POST":
                continue
            status, headers, body = _request(
                base + _path(route), method="POST", raw_body=b"",
                headers={"Origin": base, "Content-Type": "application/json"})
            if route.public:
                # the login itself: an anonymous empty body is a validation refusal
                # (422 — no keys at all), never a session
                assert status in (400, 422), (route, status, body)
                assert "Set-Cookie" not in headers
            else:
                assert status == 401, (route, status, body)
                assert body["error"]["code"] == "UNAUTHORIZED"


# --- the body rules of §1.3 ------------------------------------------------------------------------


def test_body_rules(tmp_path, state):
    with _served(tmp_path, state) as (_httpd, base):
        url = f"{base}/control/v1/session"
        wrong_type = _request(url, method="POST", raw_body=b"{}",
                              headers={"Origin": base, "Content-Type": "text/plain"})
        assert wrong_type[0] == 400

        extra = _request(url, method="POST", raw_body=json.dumps(
            {"id": "op1", "password": "correct horse", "extra": 1}).encode(),
            headers={"Origin": base})
        assert extra[0] == 400 and "extra" in extra[2]["error"]["message"]

        missing = _request(url, method="POST", raw_body=b'{"id": "op1"}',
                           headers={"Origin": base})
        assert missing[0] == 422 and missing[2]["error"]["code"] == "VALIDATION"

        not_object = _request(url, method="POST", raw_body=b"[1, 2]",
                              headers={"Origin": base})
        assert not_object[0] == 400

        too_large = _request(url, method="POST", raw_body=b'{"id": "op1", "password": "' +
                             b"x" * (control.MAX_BODY + 1) + b'"}',
                             headers={"Origin": base})
        assert too_large[0] == 413 and too_large[2]["error"]["code"] == "TOO_LARGE"

        # an empty body is the empty object: the no-keys logout goes through bare
        cookie = _cookie(_login(base)[1])
        _, headers, body = _request(f"{base}/control/v1/session",
                                    headers={"Cookie": cookie})
        bare = _request(f"{base}/control/v1/session/end", method="POST", raw_body=b"",
                        headers={"Cookie": cookie, "Origin": base,
                                 "X-CSRF-Token": body["csrf_token"],
                                 "Content-Type": "application/json"})
        assert bare[0] == 200


# --- routing edges ---------------------------------------------------------------------------------


def test_unknown_route_and_wrong_verb(tmp_path, state):
    with _served(tmp_path, state) as (_httpd, base):
        assert _request(f"{base}/control/v1/nope")[0] == 404
        assert _request(f"{base}/control/v1/session/end")[0] == 405
        assert _request(f"{base}/control/v1/session", method="PUT",
                        raw_body=b"", headers={"Origin": base})[0] == 405
        assert _request(f"{base}/api/v1/meta")[0] == 404  # the read prefix is not here
        foreign_host = _request(f"{base}/control/v1/session", method="POST",
                                payload={"id": "op1", "password": "correct horse"},
                                headers={"Origin": base, "Host": "evil.example"})
        assert foreign_host[0] == 421


# --- the clocks, injected --------------------------------------------------------------------------


def test_sessions_expire_after_twelve_hours_of_inactivity():
    now = 1000.0
    clock = lambda: now  # noqa: E731
    sessions = control.Sessions(clock=clock)
    token, session = sessions.create("op1", "Op One")
    assert sessions.get(token) == session
    now += 12 * 60 * 60 + 1
    assert sessions.get(token) is None


def test_the_failure_window_slides():
    now = 1000.0
    clock = lambda: now  # noqa: E731
    budget = control.LoginBudget(clock=clock)
    for _ in range(5):
        budget.record_failure("op1")
    assert budget.blocked("op1")
    now += 15 * 60 + 1
    assert not budget.blocked("op1")


# --- the CLI ---------------------------------------------------------------------------------------


def test_cli_operator_add_and_disable(tmp_path, monkeypatch, capsys):
    import getpass

    monkeypatch.setenv("CLAIMSTONE_STATE_DIR", str(tmp_path / "st"))
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": "a-new-password")
    assert cli.main(["operator", "add", "op2", "--name", "Second"]) == 0
    assert "op2" in operators.load(tmp_path / "st")

    assert cli.main(["operator", "disable", "op2"]) == 0
    assert operators.load(tmp_path / "st") == {}

    assert cli.main(["operator", "disable", "op2"]) == 2  # already disabled
    assert cli.main(["operator", "disable", "nobody"]) == 2  # unknown


def test_cli_operator_add_refuses_mismatched_passwords(tmp_path, monkeypatch, capsys):
    import getpass

    monkeypatch.setenv("CLAIMSTONE_STATE_DIR", str(tmp_path / "st"))
    answers = iter(["first", "second"])
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": next(answers))
    assert cli.main(["operator", "add", "op3", "--name", "Third"]) == 2
    assert not (tmp_path / "st" / operators.LEDGER).exists()
