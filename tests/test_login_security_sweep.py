"""No secret in a ledger, a response or a log line (design 2026-10-12 §Security checks).

One real server is driven through: login, a wrong login, the person's own password change, an admin
creating a person with a temporary password, the admin disabling them, and the session listing. Every
response (status, headers, body), both ledgers and the server's stderr are collected, then searched.

What is promised, and what is not: a password sent in the `password` field is never stored or echoed.
`auth_events.jsonl` DOES keep the id exactly as typed on a failed attempt (an investigation needs it), so
a person who types a password into the *id* field leaves it there. That is documented in
docs/contracts/operators.md; this test asserts only what is promised.
"""

import json

import pytest

from claimstone import operators
from tests.test_control import _cookie, _login, _request, _served

BASE = "/control/v1"
ADMIN_PW = "admin long password 1"
ADMIN_NEW = "admin brand new password 2"
TEMP_PW = "temporary secret value 3"
BOB_NEW = "bob chosen password 4"
WRONG_PW = "definitely not a password 5"


@pytest.fixture()
def state(tmp_path):
    directory = tmp_path / "state"
    operators.add_operator(directory, "adm", "Admin", ADMIN_PW, email="adm@example.org")
    return directory


def test_nothing_secret_reaches_a_response_a_ledger_or_a_log(tmp_path, state, capsys):
    seen = []          # (label, status, headers-without-set-cookie, body-text-without-the-owner's-csrf)
    cookies = set()    # session cookie values
    csrfs = set()      # CSRF tokens

    def call(label, url, method="GET", payload=None, headers=None):
        status, head, body = _request(url, method, payload, headers=headers)
        shown = {k: v for k, v in head.items() if k.lower() != "set-cookie"}  # the cookie goes to its owner
        if isinstance(body, dict) and "csrf_token" in body:
            csrfs.add(body["csrf_token"])          # returned to its owner in the login / GET session body
            body = {k: v for k, v in body.items() if k != "csrf_token"}
        cookie = _cookie(head)
        if cookie:
            cookies.add(cookie.split("=", 1)[1])
        seen.append((label, status, shown, body if isinstance(body, str) else json.dumps(body)))
        return status, head, body

    def sign_in(who, password):
        status, head, body = call(f"login {who}", f"{base}{BASE}/session", "POST",
                                  {"id": who, "password": password}, {"Origin": base})
        assert status == 200, body
        return {"Cookie": _cookie(head), "Origin": base,
                "X-CSRF-Token": next(iter(csrfs - known))}

    with _served(tmp_path, state) as (_h, base):
        known = set()
        adm = sign_in("adm", ADMIN_PW)
        known |= csrfs
        wrong = call("wrong login", f"{base}{BASE}/session", "POST",
                     {"id": "adm", "password": WRONG_PW}, {"Origin": base})
        unknown = call("unknown id", f"{base}{BASE}/session", "POST",
                       {"id": "nobody", "password": WRONG_PW}, {"Origin": base})
        assert wrong[0] == unknown[0] == 401 and wrong[2] == unknown[2]   # indistinguishable

        call("session", f"{base}{BASE}/session", headers=adm)
        assert call("change own password", f"{base}{BASE}/account/password", "POST",
                    {"current": ADMIN_PW, "new": ADMIN_NEW}, adm)[0] == 200
        assert call("create person", f"{base}{BASE}/people", "POST", {
            "password": ADMIN_NEW, "id": "bob", "name": "Bob", "email": "bob@example.org",
            "role": "operator", "temporary_password": TEMP_PW}, adm)[0] == 201
        call("people", f"{base}{BASE}/people", headers=adm)
        bob = sign_in("bob", TEMP_PW)
        assert call("bob changes it", f"{base}{BASE}/account/password", "POST",
                    {"current": TEMP_PW, "new": BOB_NEW}, bob)[0] == 200
        call("sessions", f"{base}{BASE}/account/sessions", headers=adm)
        call("bob sessions", f"{base}{BASE}/account/sessions", headers=bob)
        assert call("disable bob", f"{base}{BASE}/people/bob/disable", "POST",
                    {"password": ADMIN_NEW}, adm)[0] == 200
        assert call("bob after disable", f"{base}{BASE}/account", headers=bob)[0] == 401
        disabled = call("disabled login", f"{base}{BASE}/session", "POST",
                        {"id": "bob", "password": BOB_NEW}, {"Origin": base})
        unknown_again = call("unknown id again", f"{base}{BASE}/session", "POST",
                             {"id": "nobody", "password": BOB_NEW}, {"Origin": base})
        assert disabled[0] == unknown_again[0] == 401 and disabled[2] == unknown_again[2]
        call("sessions after", f"{base}{BASE}/account/sessions", headers=adm)

    stderr = capsys.readouterr().err
    passwords = [ADMIN_PW, ADMIN_NEW, TEMP_PW, BOB_NEW, WRONG_PW]
    tokens = cookies | csrfs
    assert len(cookies) == 2 and len(csrfs) == 2     # the sweep searched for something
    ledgers = {name: (state / name).read_text(encoding="utf-8")
               for name in (operators.LEDGER, "auth_events.jsonl")}
    haystacks = {f"{label} ({status})": json.dumps(headers) + body for label, status, headers, body in seen}
    haystacks.update(ledgers)
    haystacks["stderr"] = stderr

    for where, text in haystacks.items():
        for secret in passwords + sorted(tokens):
            assert secret not in text, f"a secret appears in {where}"
    for label, status, headers, body in seen:
        assert '"hash"' not in body and '"salt"' not in body, f"credential material in {label}"
    # and the events that were promised did get recorded
    events = [json.loads(line)["event"] for line in ledgers["auth_events.jsonl"].splitlines()]
    for expected in ("login_ok", "login_failed", "password_changed", "person_created", "person_disabled"):
        assert expected in events
