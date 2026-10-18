"""The read API's server-side gate (issue #7): a session cookie is required for every
read route except an explicit allow-list, and the session is the control server's.

The read API holds no sessions. It asks the control server's `GET /control/v1/session`
with the one cookie and believes a 200; its 401 is a refusal. Any other answer — a 500,
a timeout, no server at all — is not a refusal and is not served: `503
SESSION_AUTHORITY_UNAVAILABLE`, because a server that cannot check is not a server that
can say "nobody is signed in".

`--open-reads` is the local single-user opt-out. It is off by default, loopback-only and
printed loudly. The route sweep below enumerates `api_schema.ROUTES`, the registry the
contract already walks, so a route added to the read API is gated the moment it exists:
the default is deny.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from claimstone import api, api_schema, cli
from tests.test_api import PROJECT, _served as _open_served, workspace  # noqa: F401 - fixtures
from tests.test_control import state  # noqa: F401 - the control server's operator fixture


class _Authority:
    """A control server's session probe, reduced to the one answer this client reads."""

    def __init__(self, valid_token: str = "good", status: int = 200):
        self.requests: list[dict[str, str | None]] = []
        authority = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - http.server's naming
                cookie = self.headers.get("Cookie") or ""
                token = cookie.split("=", 1)[1] if cookie.startswith("claimstone_control=") else ""
                authority.requests.append({
                    "path": self.path,
                    "cookie": self.headers.get("Cookie"),
                    "host": self.headers.get("Host"),
                })
                code = status if (status != 200 or token == valid_token) else 401
                body = b"{}" if code == 200 else b'{"error": {"code": "UNAUTHORIZED"}}'
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):  # noqa: D401 - silence the stub's stderr
                return

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        return self

    def __exit__(self, *_exc):
        self.httpd.shutdown()
        self.thread.join(timeout=5)


@contextmanager
def _gated(workspace, authority):
    projects_dir, store_dir, _project, _store = workspace
    httpd = api.make_server(projects_dir, store_dir, host="127.0.0.1", port=0,
                            session_authority=authority)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _read(url, cookie: str | None = None):
    """(status, parsed JSON body)."""
    headers = {"Cookie": cookie} if cookie else {}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as raised:
        return raised.code, json.loads(raised.read().decode("utf-8"))


def _sample(template: str) -> str:
    """One concrete path for a registry template. The values need not exist: a gated
    route refuses before it is dispatched, and that is the point of the sweep."""
    concrete = (template
                .replace("{p}", PROJECT)
                .replace("{sel}", "flows/abc")
                .replace("{flow_id}", "abc")
                .replace("{schedule_id}", "schedule-id")
                .replace("{qid}", "Q02")
                .replace("{claim_id}", "c1")
                .replace("{candidate_key}", "r1-a"))
    return "/api/v1" + concrete


def test_every_registered_read_route_refuses_an_anonymous_request(workspace):
    """The sweep over the read API's registry: every route but the allow-list answers
    401 UNAUTHORIZED, and the answer is the §3.3 envelope, not a bare status."""
    assert set(api_schema.ROUTES) - {"/error"}
    with _Authority() as authority, _gated(workspace, authority.url) as base:
        for template in sorted(set(api_schema.ROUTES) - {"/error"}):
            if template == "/meta":
                status, body = _read(base + _sample(template))
                assert status == 200, template
                assert body["api_version"] == 1
                continue
            status, body = _read(base + _sample(template))
            assert status == 401, (template, status, body)
            assert body["api_version"] == 1
            assert body["error"]["code"] == "UNAUTHORIZED"


def test_the_anonymous_allow_list_names_only_registered_routes():
    """`--open-reads` aside, the allow-list is the whole of what serves a stranger. A
    path that is not a registered route in that set is a typo that would gate the wrong
    thing; one that is registered and not listed is gated by default."""
    registered = {"/api/v1" + template for template in api_schema.ROUTES}
    assert api.ANONYMOUS_READS
    assert api.ANONYMOUS_READS <= registered
    assert api.ANONYMOUS_READS == frozenset({"/api/v1/meta"})


def test_a_live_session_is_accepted_and_only_its_cookie_is_forwarded(workspace):
    with _Authority() as authority, _gated(workspace, authority.url) as base:
        status, body = _read(base + "/api/v1/projects",
                             cookie="other=ignored; claimstone_control=good")
        assert status == 200, body
        assert body["api_version"] == 1
        assert authority.requests == [{
            "path": "/control/v1/session",
            "cookie": "claimstone_control=good",
            "host": authority.url.split("//", 1)[1],
        }]


def test_a_refused_session_is_a_401_and_no_read_is_computed(workspace):
    with _Authority() as authority, _gated(workspace, authority.url) as base:
        status, body = _read(base + "/api/v1/projects",
                             cookie="claimstone_control=stale")
        assert status == 401
        assert body["error"]["code"] == "UNAUTHORIZED"
        assert len(authority.requests) == 1


def test_no_cookie_never_asks_the_authority(workspace):
    with _Authority() as authority, _gated(workspace, authority.url) as base:
        status, body = _read(base + "/api/v1/projects")
        assert status == 401
        assert body["error"]["code"] == "UNAUTHORIZED"
        assert authority.requests == []


def test_a_malformed_cookie_is_anonymous_not_a_crash(workspace):
    with _Authority() as authority, _gated(workspace, authority.url) as base:
        status, body = _read(base + "/api/v1/projects",
                             cookie="claimstone_control=\"unterminated")
        assert status == 401
        assert body["error"]["code"] == "UNAUTHORIZED"


def test_an_authority_error_is_503_not_a_false_401(workspace):
    """A broken control server must not be reported as "nobody is signed in": the
    difference between a refusal and an outage is the difference between a state and a
    bug."""
    with _Authority(status=500) as authority, _gated(workspace, authority.url) as base:
        status, body = _read(base + "/api/v1/projects",
                             cookie="claimstone_control=good")
        assert status == 503
        assert body["error"]["code"] == "SESSION_AUTHORITY_UNAVAILABLE"


def test_an_unreachable_authority_is_503(workspace):
    closed = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = closed.server_address[1]
    closed.server_close()
    with _gated(workspace, f"http://127.0.0.1:{port}") as base:
        status, body = _read(base + "/api/v1/projects",
                             cookie="claimstone_control=good")
        assert status == 503
        assert body["error"]["code"] == "SESSION_AUTHORITY_UNAVAILABLE"


def test_the_real_control_server_is_the_authority(tmp_path, state):
    """The stub above pins this client's request; this pins the two servers' agreement:
    control answers the forwarded probe, its 401 refuses, and its minted cookie is enough
    for a read without any second consent step."""
    from tests.test_api import build_workspace
    from tests.test_control import _cookie, _login, _served as _control_served

    workspace = build_workspace(tmp_path)
    with _control_served(tmp_path, state) as (_control_httpd, control_base):
        with _gated(workspace, control_base) as base:
            status, body = _read(base + "/api/v1/projects",
                                 cookie="claimstone_control=not-a-session")
            assert status == 401
            assert body["error"]["code"] == "UNAUTHORIZED"
            status, headers, login = _login(control_base)
            assert status == 200, login
            status, body = _read(base + "/api/v1/projects", cookie=_cookie(headers))
            assert status == 200, body


def test_open_reads_serves_without_a_session_and_does_not_need_an_authority(workspace):
    """`--open-reads` is the local single-user case: the same route, no cookie, no
    control server, 200."""
    with _open_served(workspace, open_reads=True) as (_httpd, base, _store):
        status, body = _read(base + "/api/v1/projects")
        assert status == 200
        assert body["api_version"] == 1


def test_read_configuration_names_exactly_one_mode_and_open_reads_is_loopback_only():
    assert api.check_read_configuration("127.0.0.1", open_reads=True,
                                        session_authority=None) is None
    assert api.check_read_configuration("127.0.0.2", open_reads=True,
                                        session_authority=None) is None
    assert api.check_read_configuration("0.0.0.0", open_reads=False,
                                        session_authority="http://control:8790") is None
    with pytest.raises(ValueError, match="exactly one"):
        api.check_read_configuration("127.0.0.1", open_reads=False, session_authority=None)
    with pytest.raises(ValueError, match="exactly one"):
        api.check_read_configuration("127.0.0.1", open_reads=True,
                                     session_authority="http://control:8790")
    with pytest.raises(ValueError, match="loopback"):
        api.check_read_configuration("0.0.0.0", open_reads=True, session_authority=None)
    with pytest.raises(ValueError, match="base URL"):
        api.check_read_configuration("127.0.0.1", open_reads=False,
                                     session_authority="http://control:8790/control/v1")
    with pytest.raises(ValueError, match="http"):
        api.check_read_configuration("127.0.0.1", open_reads=False,
                                     session_authority="control:8790")


def test_cli_refuses_neither_mode_and_both_modes(tmp_path, capsys):
    common = ["api", "--projects-dir", str(tmp_path / "projects"),
              "--store", str(tmp_path / "store"), "--port", "0"]
    assert cli.main(common) == 2
    assert "exactly one" in capsys.readouterr().err
    assert cli.main(common + ["--open-reads", "--session-authority", "http://control:8790"]) == 2
    assert "exactly one" in capsys.readouterr().err


def test_cli_refuses_a_non_loopback_open_reads_bind(tmp_path, capsys):
    assert cli.main(["api", "--projects-dir", str(tmp_path / "projects"),
                     "--store", str(tmp_path / "store"), "--port", "0",
                     "--host", "0.0.0.0", "--open-reads"]) == 2
    assert "loopback" in capsys.readouterr().err


def test_open_reads_is_announced_loudly_at_start_up(tmp_path, capsys, monkeypatch):
    class _Fake:
        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            return

    monkeypatch.setattr(api, "make_server", lambda *_a, **_k: _Fake())
    api.serve(tmp_path / "projects", tmp_path / "store", open_reads=True)
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "--open-reads" in err
    assert "without a session" in err


def test_the_gated_start_up_line_names_the_authority(tmp_path, capsys, monkeypatch):
    class _Fake:
        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            return

    monkeypatch.setattr(api, "make_server", lambda *_a, **_k: _Fake())
    api.serve(tmp_path / "projects", tmp_path / "store",
              session_authority="http://control:8790")
    out, err = capsys.readouterr()
    assert "control:8790" in out + err
    assert "WARNING" not in err
