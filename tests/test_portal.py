"""portal: the transport's own promises — spec §4.13, the handler table.

One real server on a port-0 bind around the same workspace `test_portal_state` builds: verb
refusals, the Host/Origin defences, the security headers, lookup-never-path parameters, escaping
and read-only-ness over the wire.
"""

from __future__ import annotations

import hashlib
import json
import socket
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager

import pytest

from claimstone import flows, portal, scope
from claimstone.store import Store
from tests.test_portal_state import build_workspace


@pytest.fixture()
def workspace(tmp_path):
    return build_workspace(tmp_path)


@contextmanager
def _served(workspace):
    projects_dir, store_dir, _project, store = workspace
    httpd = portal.make_server(projects_dir, store_dir, host="127.0.0.1", port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_address[1]}", store
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _get(url: str, headers: dict[str, str] | None = None):
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, dict(response.headers), response.read().decode("utf-8")


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


def _store_hashes(store: Store) -> dict[str, str]:
    return {str(path.relative_to(store.root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(store.root.rglob("*")) if path.is_file()}


def test_every_non_get_is_refused(workspace):
    """H-T1: POST, PUT, DELETE, PATCH, OPTIONS and HEAD answer 405; HEAD carries no body."""
    with _served(workspace) as (_httpd, _base, _store):
        port = _httpd.server_address[1]
        for verb in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS"):
            request = urllib.request.Request(f"http://127.0.0.1:{port}/", data=b"x",
                                             method=verb)
            with pytest.raises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request, timeout=10)
            assert raised.value.code == 405, verb
        raw = _raw(port, "HEAD", "/", f"127.0.0.1:{port}")
        head, _, body = raw.partition(b"\r\n\r\n")
        assert raw.startswith(b"HTTP/1.0 405")
        assert b"Allow: GET" in head
        assert body == b""


def test_host_and_origin_are_refused(workspace):
    """H-T2: a foreign Host is a 421; a foreign Origin is a 403 — the DNS-rebinding defence."""
    with _served(workspace) as (httpd, _base, _store):
        port = httpd.server_address[1]
        assert _raw(port, "GET", "/", f"evil.example:{port}").startswith(b"HTTP/1.0 421")
        assert _raw(port, "GET", "/", f"127.0.0.1:{port}",
                    origin="http://evil.example").startswith(b"HTTP/1.0 403")
        # And the honest headers still answer.
        assert _raw(port, "GET", "/", f"127.0.0.1:{port}").startswith(b"HTTP/1.0 200")
        assert _raw(port, "GET", "/", f"localhost:{port}").startswith(b"HTTP/1.0 200")


def test_security_headers_on_html_and_json(workspace):
    """H-T3: CSP, nosniff and no-store ride on every response."""
    with _served(workspace) as (_httpd, base, _store):
        for path in ("/", "/api/index"):
            _status, headers, _body = _get(base + path)
            assert headers["Cache-Control"] == "no-store", path
            assert headers["X-Content-Type-Options"] == "nosniff", path
            assert headers["Referrer-Policy"] == "no-referrer", path
            assert "default-src 'none'" in headers["Content-Security-Policy"], path
            assert "form-action 'none'" in headers["Content-Security-Policy"], path


def test_path_parameters_are_looked_up_never_used_as_paths(workspace):
    """H-T4: traversal, unknown projects and malformed flow ids are all plain 404s."""
    with _served(workspace) as (_httpd, base, _store):
        for path in ("/p/../etc/", "/p/unknown/", "/p/../etc/passwd",
                     f"/p/example-news-and-returns/f/{'a' * 63}/"):
            with pytest.raises(urllib.error.HTTPError) as raised:
                _get(base + path)
            assert raised.value.code == 404, path


def test_question_text_is_escaped(workspace):
    """H-T5: a hostile question text renders escaped, in the matrix and on the question page."""
    _projects_dir, _store_dir, project, _store = workspace
    questions = project.root / "questions.yaml"
    # A changed question text is a dated registry bump (invariant 5); without the bump the
    # store's recorded registry refuses the page, which is right but tests nothing here.
    questions.write_text(
        questions.read_text(encoding="utf-8").replace(
            "Novelty and staleness of a news item change the size of the price reaction.",
            "Is <script>alert(1)</script> part of the question?")
        .replace("registry_version: 2", "registry_version: 3")
        .replace("frozen_at: 2026-09-25", "frozen_at: 2026-10-06"),
        encoding="utf-8")
    with _served(workspace) as (_httpd, base, store):
        flow_id = next(iter(flows.flows(store)))
        _status, _headers, page = _get(
            base + f"/p/example-news-and-returns/f/{flow_id}/")
        assert "<script>alert(1)</script>" not in page
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
        _status, _headers, qpage = _get(
            base + f"/p/example-news-and-returns/f/{flow_id}/q/Q05")
        assert "<script>alert(1)</script>" not in qpage
        assert "&lt;script&gt;" in qpage


def test_serving_every_route_writes_nothing(workspace):
    """H-T6: after every route answers once, the store is byte-identical."""
    with _served(workspace) as (_httpd, base, store):
        flow_id = next(iter(flows.flows(store)))
        name = "example-news-and-returns"
        routes = [
            "/", "/inbox", "/admin",
            f"/p/{name}/",
            f"/p/{name}/f/{flow_id}/",
            f"/p/{name}/f/{flow_id}/q/Q02",
            f"/p/{name}/f/{flow_id}/claim/c1",
            f"/p/{name}/f/{flow_id}/source/r1-a",
            f"/p/{name}/legacy/r2/",
            f"/p/{name}/legacy/r2/q/Q02",
            f"/p/{name}/legacy/r2/claim/c9",
            f"/p/{name}/legacy/r2/source/r2-w",
            "/api/index", "/api/inbox",
            f"/api/p/{name}/f/{flow_id}",
            f"/api/p/{name}/f/{flow_id}/q/Q02",
            f"/api/poll?project={name}",
        ]
        before = _store_hashes(store)
        for route in routes:
            status, _headers, body = _get(base + route)
            assert status == 200, route
            assert body, route
        assert _store_hashes(store) == before


def test_host_and_origin_ports_are_checked(workspace):
    """R6: a loopback name on another port is refused for Host (IPv6 too) and for Origin."""
    with _served(workspace) as (httpd, _base, _store):
        port = httpd.server_address[1]
        other = port + 1 if port < 65535 else port - 1
        assert _raw(port, "GET", "/admin", f"127.0.0.1:{other}").startswith(b"HTTP/1.0 421")
        assert _raw(port, "GET", "/admin", f"[::1]:{other}").startswith(b"HTTP/1.0 421")
        assert _raw(port, "GET", "/admin", f"[::1]:{port}").startswith(b"HTTP/1.0 200")
        refused = _raw(port, "GET", "/admin", f"127.0.0.1:{port}",
                       origin=f"http://localhost:{other}")
        assert refused.startswith(b"HTTP/1.0 403")


def test_allow_host_admits_a_named_proxy_authority(workspace):
    """R7: `--allow-host web:8080` admits exactly that authority, as a reverse proxy sends it."""
    projects_dir, store_dir, _project, _store = workspace
    httpd = portal.make_server(projects_dir, store_dir, host="127.0.0.1", port=0,
                               allow_hosts=("web:8080",))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        assert _raw(port, "GET", "/admin", "web:8080").startswith(b"HTTP/1.0 200")
        assert _raw(port, "GET", "/admin", "web:9090").startswith(b"HTTP/1.0 421")
        assert _raw(port, "GET", "/admin", "web:8080",
                    origin="http://web:8080").startswith(b"HTTP/1.0 200")
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def test_whole_store_and_invented_legacy_routes(workspace):
    """R8: `/legacy/-/` serves the whole-store selector; an invented round is a 404."""
    with _served(workspace) as (httpd, base, _store):
        port = httpd.server_address[1]
        ok = _raw(port, "GET", "/p/example-news-and-returns/legacy/-/", f"127.0.0.1:{port}")
        assert ok.startswith(b"HTTP/1.0 200")
        missing = _raw(port, "GET", "/p/example-news-and-returns/legacy/invented/",
                       f"127.0.0.1:{port}")
        assert missing.startswith(b"HTTP/1.0 404")


def test_inbox_names_a_project_whose_config_fails(workspace):
    """R9: a broken project is an INTEGRITY card in the inbox, not silently absent."""
    projects_dir, _store_dir, project, _store = workspace
    (project.root / "sources.yaml").write_text("acquisition_floor: 7\n", encoding="utf-8")
    with _served(workspace) as (_httpd, base, _store):
        _status, _headers, body = _get(base + "/api/inbox")
    data = json.loads(body)
    entry = next(p for p in data["projects"] if p["name"] == "example-news-and-returns")
    assert entry["cards"] and entry["cards"][0]["category"] == "INTEGRITY"
