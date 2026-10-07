"""B11: administration actions — reachability on request, write-only credentials, no paid test."""

from __future__ import annotations

import http.server
import json
import os
import stat
import threading
from contextlib import contextmanager

import pytest

from claimstone import admin, control, operators
from tests.test_control import _cookie, _login, _request

SECRET = "sk-test-0123456789abcdef"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAIMSTONE_CONTACT_EMAIL", "ops@example.org")
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    (tmp_path / "projects").mkdir()
    state = tmp_path / "state"
    operators.add_operator(state, "op1", "Op One", "correct horse")
    (tmp_path / ".env").write_text("# kept\nCLAIMSTONE_CONTACT_EMAIL=ops@example.org\n",
                                   encoding="utf-8")
    return {"root": tmp_path, "state": state, "env_file": tmp_path / ".env"}


@contextmanager
def _served(env, http_get=None):
    httpd = control.make_server(env["root"] / "projects", env["root"] / "store",
                                host="127.0.0.1", port=0, state_dir=env["state"],
                                http_get=http_get, env_file=env["env_file"])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        status, headers, body = _login(base)
        yield base, {"Cookie": _cookie(headers), "Origin": base,
                     "X-CSRF-Token": body["csrf_token"]}
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _post(base, path, headers, payload):
    return _request(base + "/control/v1/admin" + path, method="POST", payload=payload,
                    headers=headers)


def test_reading_the_admin_view_contacts_nothing(env):
    calls = []
    with _served(env, http_get=lambda *a: calls.append(a) or 200) as (base, headers):
        status, _h, body = _request(base + "/control/v1/admin",
                                    headers={"Cookie": headers["Cookie"]})
    assert status == 200 and calls == []
    assert body["checks"] == {} and set(body["check_targets"]) == {"llamacpp", "ollama-cloud",
                                                                   "grobid"}


def test_a_check_is_one_recorded_request_whatever_its_outcome(env):
    def refuse(url, headers, timeout):
        raise ConnectionError("refused")
    with _served(env, http_get=lambda url, headers, timeout: 200) as (base, headers):
        status, _h, ok = _post(base, "/check", headers, {"target": "grobid"})
    assert status == 201 and ok["check"]["ok"] is True and ok["check"]["status"] == 200
    with _served(env, http_get=refuse) as (base, headers):
        failed = _post(base, "/check", headers, {"target": "llamacpp"})[2]["check"]
        _s, _h, view = _request(base + "/control/v1/admin", headers={"Cookie": headers["Cookie"]})
    assert failed["ok"] is False and failed["detail"] == "ConnectionError"
    assert set(view["checks"]) == {"grobid", "llamacpp"}


def test_a_check_against_a_real_local_stub(env, monkeypatch):
    class Stub(http.server.BaseHTTPRequestHandler):
        seen: list[str] = []

        def do_GET(self):  # noqa: N802
            Stub.seen.append(self.headers.get("User-Agent", ""))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    stub = http.server.HTTPServer(("127.0.0.1", 0), Stub)
    thread = threading.Thread(target=stub.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setattr(admin, "targets", lambda: {
            "llamacpp": f"http://127.0.0.1:{stub.server_address[1]}/health"})
        row = admin.check(env["state"], target="llamacpp", actor="op1")
    finally:
        stub.shutdown()
        thread.join(timeout=5)
    assert row["ok"] is True
    assert "ops@example.org" in Stub.seen[0]  # descriptive agent with contact


def test_targets_are_names_never_addresses_and_contact_is_required(env, monkeypatch):
    with _served(env, http_get=lambda *a: 200) as (base, headers):
        assert _post(base, "/check", headers, {"target": "http://169.254.169.254/"})[0] == 422
        monkeypatch.delenv("CLAIMSTONE_CONTACT_EMAIL")
        assert _post(base, "/check", headers, {"target": "grobid"})[0] == 422


def test_a_credential_is_written_once_and_never_read_back(env):
    with _served(env) as (base, headers):
        status, _h, body = _post(base, "/credential", headers, {
            "name": "OPENALEX_API_KEY", "value": SECRET, "password": "correct horse"})
        _s, _h, view = _request(base + "/control/v1/admin", headers={"Cookie": headers["Cookie"]})
    assert status == 201 and body == {"credential": {"name": "OPENALEX_API_KEY", "set": True,
                                                     "note": body["credential"]["note"]}}
    text = env["env_file"].read_text(encoding="utf-8")
    assert text.splitlines() == ["# kept", "CLAIMSTONE_CONTACT_EMAIL=ops@example.org",
                                 f"OPENALEX_API_KEY={SECRET}"]
    assert stat.S_IMODE(os.stat(env["env_file"]).st_mode) == 0o600
    assert view["credentials"]["OPENALEX_API_KEY"] is True
    assert SECRET not in json.dumps(view) and SECRET not in json.dumps(body)
    assert SECRET not in (env["state"] / admin.LEDGER).read_text(encoding="utf-8")


def test_replacing_keeps_one_line_per_name(env):
    with _served(env) as (base, headers):
        for value in ("first-value", "second-value"):
            assert _post(base, "/credential", headers, {
                "name": "OPENALEX_API_KEY", "value": value, "password": "correct horse"})[0] == 201
    lines = env["env_file"].read_text(encoding="utf-8").splitlines()
    assert [line for line in lines if line.startswith("OPENALEX_API_KEY=")] == [
        "OPENALEX_API_KEY=second-value"]


def test_the_password_is_asked_again_and_failures_are_rate_limited(env):
    before = env["env_file"].read_bytes()
    with _served(env) as (base, headers):
        for _ in range(5):
            status, _h, body = _post(base, "/credential", headers, {
                "name": "OPENALEX_API_KEY", "value": SECRET, "password": "wrong"})
            assert status == 403 and body["error"]["code"] == "REAUTH"
        assert _post(base, "/credential", headers, {
            "name": "OPENALEX_API_KEY", "value": SECRET, "password": "correct horse"})[0] == 429
    assert env["env_file"].read_bytes() == before


@pytest.mark.parametrize("payload", [
    {"name": "PATH", "value": "x", "password": "correct horse"},
    {"name": "OPENALEX_API_KEY", "value": "a\nB=c", "password": "correct horse"},
    {"name": "OPENALEX_API_KEY", "value": "", "password": "correct horse"},
])
def test_credential_rules(env, payload):
    with _served(env) as (base, headers):
        assert _post(base, "/credential", headers, payload)[0] == 422


def test_the_paid_test_call_is_not_built_and_says_why(env):
    with _served(env) as (base, headers):
        status, _h, body = _post(base, "/paid-test", headers, {})
    assert status == 501 and "scheduler" in body["error"]["message"]
