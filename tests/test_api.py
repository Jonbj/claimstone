"""api: the JSON read model's own promises — spec §3.5, tests A1 and A3–A7.

A2 (payloads against `docs/contracts/portal-api.schema.json`) lands with the schema in S3.
One real server on a port-0 bind around the same workspace `test_portal_state` builds, like
`test_portal.py`: every route answers, the error envelope is exact, `/projects` stays cheap,
`/admin` leaks no credential value, the transport defences hold over the wire, and everything
runs unchanged against a store chmod'ed read-only.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import os
import pathlib
import socket
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager

import pytest

from claimstone import api, flows
from claimstone.store import Store
from tests.test_portal_state import build_workspace

PROJECT = "example-news-and-returns"


@pytest.fixture()
def workspace(tmp_path):
    return build_workspace(tmp_path)


@contextmanager
def _served(workspace, **kwargs):
    projects_dir, store_dir, _project, store = workspace
    httpd = api.make_server(projects_dir, store_dir, host="127.0.0.1", port=0, **kwargs)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_address[1]}", store
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _get(url, headers=None):
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.status, dict(response.headers), response.read().decode("utf-8")


def _get_json(url, headers=None):
    status, headers_, body = _get(url, headers)
    return status, headers_, json.loads(body)


def _error_json(url, headers=None):
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status, body = response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as raised:
        status, body = raised.code, raised.read().decode("utf-8")
    return status, json.loads(body)


def _raw(port: int, verb: str, path: str, host: str, origin: str | None = None) -> bytes:
    lines = [f"{verb} {path} HTTP/1.1", f"Host: {host}", "Connection: close"]
    if origin is not None:
        lines.append(f"Origin: {origin}")
    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        chunks = []
        while True:
            data = sock.recv(65536)
            if not data:
                break
            chunks.append(data)
    return b"".join(chunks)


def _raw_json(port: int, path: str, host: str, origin: str | None = None):
    raw = _raw(port, "GET", path, host, origin)
    head, _, body = raw.partition(b"\r\n\r\n")
    return int(head.split(b" ", 2)[1]), json.loads(body.decode("utf-8"))


def _store_hashes(store: Store) -> dict[str, str]:
    return {str(path.relative_to(store.root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(store.root.rglob("*")) if path.is_file()}


def _routes(flow_id: str) -> list[str]:
    base = f"/api/v1/projects/{PROJECT}"
    return [
        "/api/v1/meta",
        "/api/v1/projects",
        "/api/v1/admin",
        f"{base}/integrity",
        f"{base}/activity",
        f"{base}/activity?limit=10",
        f"{base}/poll",
        f"{base}/flows/{flow_id}/summary",
        f"{base}/flows/{flow_id}/overview",
        f"{base}/flows/{flow_id}/inbox",
        f"{base}/flows/{flow_id}/questions/Q02",
        f"{base}/flows/{flow_id}/claims/c1",
        f"{base}/flows/{flow_id}/sources/r1-a",
        f"{base}/unbound/r2/summary",
        f"{base}/unbound/r2/overview",
        f"{base}/unbound/r2/inbox",
        f"{base}/unbound/r2/questions/Q02",
        f"{base}/unbound/r2/claims/c9",
        f"{base}/unbound/r2/sources/r2-w",
        f"{base}/unbound/-/overview",
    ]


def test_every_route_answers_and_writes_nothing(workspace):
    """A1: every §3.2 route answers 200 on the build_workspace fixture — JSON, `api_version`
    1, the §3.1 headers — and the store is byte-identical afterwards."""
    with _served(workspace) as (_httpd, base, store):
        flow_id = next(iter(flows.flows(store)))
        before = _store_hashes(store)
        for route in _routes(flow_id):
            status, headers, payload = _get_json(base + route)
            assert status == 200, route
            assert payload["api_version"] == 1, route
            assert headers["Content-Type"] == "application/json; charset=utf-8", route
            assert headers["Cache-Control"] == "no-store", route
            assert headers["X-Content-Type-Options"] == "nosniff", route
            assert headers["Content-Security-Policy"] == api.CSP, route
        assert _store_hashes(store) == before


def test_error_envelope_unknown_flow(workspace):
    """A3: an unknown flow is a 404 with the NOT_FOUND envelope."""
    with _served(workspace) as (_httpd, base, _store):
        status, payload = _error_json(
            base + f"/api/v1/projects/{PROJECT}/flows/{'a' * 64}/overview")
    assert status == 404
    assert payload["api_version"] == 1
    assert payload["error"]["code"] == "NOT_FOUND"
    assert "unknown flow" in payload["error"]["message"]


def test_error_envelope_registry_drift(workspace):
    """A3: a question edited under the same registry version is a 409 REGISTRY_DRIFT envelope."""
    _projects_dir, _store_dir, project, _store = workspace
    questions = project.root / "questions.yaml"
    questions.write_text(
        questions.read_text(encoding="utf-8").replace(
            "Novelty and staleness of a news item change the size of the price reaction.",
            "A different question text, edited without the dated bump."),
        encoding="utf-8")
    with _served(workspace) as (_httpd, base, store):
        flow_id = next(iter(flows.flows(store)))
        status, payload = _error_json(
            base + f"/api/v1/projects/{PROJECT}/flows/{flow_id}/overview")
    assert status == 409
    assert payload["error"]["code"] == "REGISTRY_DRIFT"
    assert payload["error"]["message"]


def test_error_envelope_config_error(workspace):
    """A3: a project whose inputs fail their contract is a 409 CONFIG_ERROR envelope."""
    _projects_dir, _store_dir, project, _store = workspace
    (project.root / "sources.yaml").write_text("acquisition_floor: 7\n", encoding="utf-8")
    with _served(workspace) as (_httpd, base, _store):
        status, payload = _error_json(base + f"/api/v1/projects/{PROJECT}/integrity")
    assert status == 409
    assert payload["error"]["code"] == "CONFIG_ERROR"
    assert payload["error"]["message"]


def test_error_envelope_ledger_corrupt(workspace):
    """A3: an interior-corrupt ledger is a 500 LEDGER_CORRUPT envelope naming ledger and line."""
    _projects_dir, _store_dir, _project, store = workspace
    target = store.path("flows.jsonl")
    target.write_bytes(b"{bad interior line\n" + target.read_bytes())
    with _served(workspace) as (_httpd, base, _store):
        status, payload = _error_json(
            base + f"/api/v1/projects/{PROJECT}/flows/{'a' * 64}/overview")
    assert status == 500
    assert payload["error"]["code"] == "LEDGER_CORRUPT"
    assert "flows.jsonl" in payload["error"]["message"]
    assert "line 1" in payload["error"]["message"]


def test_error_envelope_internal_is_the_class_name_alone(workspace, monkeypatch):
    """A3: any other failure is a 500 INTERNAL whose message is the exception class name only
    — never a body that could be read as data."""
    from claimstone import portal_state

    def boom(*args, **kwargs):
        raise RuntimeError("a detail no client should read")

    monkeypatch.setattr(portal_state, "flow_overview", boom)
    with _served(workspace) as (_httpd, base, store):
        flow_id = next(iter(flows.flows(store)))
        status, payload = _error_json(
            base + f"/api/v1/projects/{PROJECT}/flows/{flow_id}/overview")
    assert status == 500
    assert payload["error"] == {"code": "INTERNAL", "message": "RuntimeError"}
    assert "detail" not in json.dumps(payload)


def test_projects_performs_no_compute(workspace, monkeypatch):
    """A4: the cheap `/projects` route runs no `compute()` — that is what fixes I4 — and still
    names the flows, their binding states and the unbound selectors."""
    from claimstone import portal_state

    calls: list[tuple] = []
    original = portal_state.compute

    def counting(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(portal_state, "compute", counting)
    with _served(workspace) as (_httpd, base, _store):
        _status, _headers, payload = _get_json(base + "/api/v1/projects")
    assert calls == []
    assert len(payload["projects"]) == 1
    entry = payload["projects"][0]
    assert entry["name"] == PROJECT
    assert entry["config"] == "OK" and entry["config_error"] is None
    assert entry["registry_version"] == 2 and len(entry["registry_sha256"]) == 12
    assert entry["registry_drift"] is None
    assert [flow["selector"]["round"] for flow in entry["flows"]] == ["r1"]
    assert entry["flows"][0]["binding_state"] == "CURRENT"
    # The fixture binds r1 after its data existed, so the flag a reader must see is True.
    assert entry["flows"][0]["bound_after_data"] is True
    assert entry["flows"][0]["selector_label"] == "round r1"
    assert [unbound["slug"] for unbound in entry["unbound_selectors"]] == ["-", "r2"]
    assert entry["unbound_selectors"][1]["label"] == "round r2"


def test_admin_never_leaks_a_credential_value(workspace, monkeypatch, tmp_path):
    """A5: `/admin` carries presence booleans only — the A-T1 assertions over the wire."""
    monkeypatch.setenv("OLLAMA_API_KEY", "secret-value-123")
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.delenv("CLAIMSTONE_CONTACT_EMAIL", raising=False)
    (tmp_path / ".env").write_text("CLAIMSTONE_CONTACT_EMAIL=me@example.org\n", encoding="utf-8")
    with _served(workspace) as (_httpd, base, _store):
        _status, _headers, payload = _get_json(base + "/api/v1/admin")
    dumped = json.dumps(payload)
    assert "secret-value-123" not in dumped
    assert "secret" not in dumped
    assert "me@example.org" not in dumped and "example.org" not in dumped
    # The secret is 16 characters long; the credentials block holds booleans and nothing else.
    assert len("secret-value-123") == 16
    assert all(value is True or value is False for value in payload["credentials"].values())
    assert "16" not in json.dumps(payload["credentials"])
    assert payload["credentials"] == {"CLAIMSTONE_CONTACT_EMAIL": True,
                                      "OLLAMA_API_KEY": True,
                                      "OPENALEX_API_KEY": False}


def test_verb_and_authority_defences(workspace):
    """A6: non-GET → 405; a foreign Host → 421 MISDIRECTED; a foreign Origin → 403
    CROSS_ORIGIN."""
    with _served(workspace) as (httpd, base, _store):
        port = httpd.server_address[1]
        for verb in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS"):
            request = urllib.request.Request(base + "/api/v1/meta", data=b"x", method=verb)
            with pytest.raises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request, timeout=10)
            assert raised.value.code == 405, verb
        status, payload = _raw_json(port, "/api/v1/meta", f"evil.example:{port}")
        assert status == 421
        assert payload["error"]["code"] == "MISDIRECTED"
        status, payload = _raw_json(port, "/api/v1/meta", f"127.0.0.1:{port}",
                                    origin="http://evil.example")
        assert status == 403
        assert payload["error"]["code"] == "CROSS_ORIGIN"


def test_allow_host_admits_exactly_that_authority(workspace):
    """A6: `--allow-host api:8788` admits that authority — as Host and as Origin — and no
    other port on the same name."""
    projects_dir, store_dir, _project, _store = workspace
    httpd = api.make_server(projects_dir, store_dir, host="127.0.0.1", port=0,
                            allow_hosts=("api:8788",))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        status, _payload = _raw_json(port, "/api/v1/meta", "api:8788")
        assert status == 200
        assert _raw(port, "GET", "/api/v1/meta", "api:9090").startswith(b"HTTP/1.0 421")
        status, _payload = _raw_json(port, "/api/v1/meta", "api:8788", origin="http://api:8788")
        assert status == 200
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def test_every_route_answers_against_a_read_only_store(workspace):
    """A7: read-only is structural — every route answers 200 with all store files and
    directories chmod'ed read-only (modes restored in `finally`)."""
    if os.geteuid() == 0:
        # Permission bits do not bind root, so the test would pass without proving anything.
        pytest.skip("read-only modes do not restrict root")
    _projects_dir, store_dir, _project, store = workspace
    changes: list[tuple[pathlib.Path, int]] = []
    try:
        for path in sorted(store_dir.rglob("*")):
            changes.append((path, path.stat().st_mode & 0o777))
            path.chmod(0o555 if path.is_dir() else 0o444)
        changes.append((store_dir, store_dir.stat().st_mode & 0o777))
        store_dir.chmod(0o555)
        with _served(workspace) as (_httpd, base, _s):
            flow_id = next(iter(flows.flows(store)))
            for route in _routes(flow_id):
                status, _headers, payload = _get_json(base + route)
                assert status == 200, route
                assert payload["api_version"] == 1, route
    finally:
        for path, mode in reversed(changes):
            path.chmod(mode)


def test_one_corrupt_project_does_not_empty_the_project_list(workspace, tmp_path):
    """Review of S2: a damaged ledger in one project is that project's `integrity_error`;
    `/projects` still answers 200 and still lists every other project."""
    projects_dir, _store_dir, _project, store = workspace
    shutil.copytree(projects_dir / PROJECT, projects_dir / "second-project")
    target = store.path("flows.jsonl")
    target.write_bytes(b"{bad interior line\n" + target.read_bytes())
    with _served(workspace) as (_httpd, base, _store):
        status, _headers, payload = _get_json(base + "/api/v1/projects")
    assert status == 200
    by_name = {entry["name"]: entry for entry in payload["projects"]}
    assert by_name[PROJECT]["integrity_error"].startswith("LEDGER_CORRUPT")
    assert by_name[PROJECT]["flows"] == [] and by_name[PROJECT]["unbound_selectors"] == []
    assert by_name["second-project"]["integrity_error"] is None


def test_malformed_limit_is_a_bad_request(workspace):
    """Review of S2: a non-integer `limit` is the caller's error, 400 BAD_REQUEST, not 404."""
    with _served(workspace) as (_httpd, base, _store):
        status, payload = _error_json(base + f"/api/v1/projects/{PROJECT}/activity?limit=x")
    assert status == 400
    assert payload["error"]["code"] == "BAD_REQUEST"
