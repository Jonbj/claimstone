"""The HTTP transport rules `portal` and `api` share (spec §3.1, 2026-10-06 design).

GET is the only verb; every response carries `no-store`, `nosniff`, `no-referrer` and a
Content-Security-Policy; the Host and Origin checks (with the `--allow-host` authorities a
reverse proxy in front needs) are the DNS-rebinding defence; and path parameters are looked
up in ledgers, never used as paths. No HTML, no JSON payloads and no routing live here —
`portal.py` renders pages and `api.py` speaks JSON on top of this base. Read-only is
structural here, exactly as it is in `dashboard.py`: there is no code path that writes.
"""

from __future__ import annotations

import json
import pathlib
import re
from http.server import BaseHTTPRequestHandler
from typing import Any

from claimstone import flows, portal_state
from claimstone.config import check_registry_drift, discover_projects, load_project
from claimstone.store import Store

FLOW_ID = re.compile(r"^[0-9a-f]{64}$")

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class BaseHandler(BaseHTTPRequestHandler):
    """GET only, and everything a GET answers is derived, never written."""

    projects_dir: pathlib.Path
    store_dir: pathlib.Path
    allowed_hosts: frozenset[str]
    allowed_authorities: frozenset[str] = frozenset()
    bind_port: int
    code_revision: str | None
    code_dirty: bool | None
    csp: str  # the Content-Security-Policy value every response of this server carries

    def log_message(self, fmt: str, *args: Any) -> None:  # quiet by default
        pass

    # --- plumbing -------------------------------------------------------------

    def _send(self, body: bytes, code: int, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", self.csp)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _plain(self, code: int, text: str) -> None:
        self._send((text + "\n").encode("utf-8"), code, "text/plain; charset=utf-8")

    def _html(self, text: str) -> None:
        self._send(text.encode("utf-8"), 200, "text/html; charset=utf-8")

    def _json(self, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=1, default=str).encode("utf-8")
        self._send(body, 200, "application/json; charset=utf-8")

    @staticmethod
    def _split_host(header: str) -> tuple[str, str | None]:
        """(name, port) of a Host value: `name`, `name:port`, `[v6]` or `[v6]:port`."""
        if header.startswith("["):
            if "]" not in header:
                return "", None
            name, rest = header[1:header.index("]")], header[header.index("]") + 1:]
            return name, (rest[1:] if rest.startswith(":") else None)
        if ":" in header:
            name, port = header.rsplit(":", 1)
            return name, port
        return header, None

    def _authority_ok(self, authority: str) -> bool:
        """An authority this server answers for: a loopback name on the bound port, or an
        explicitly allowed `name[:port]` (`--allow-host`, for a reverse proxy in front)."""
        if authority.lower() in self.allowed_authorities:
            return True
        name, port = self._split_host(authority)
        if name.lower() not in self.allowed_hosts:
            return False
        return port is None or (port.isdigit() and int(port) == self.bind_port)

    def _host_ok(self) -> bool:
        """The DNS-rebinding defence: only the names this bind answers for (spec §4.3)."""
        return self._authority_ok(self.headers.get("Host", ""))

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        for scheme in ("http://", "https://"):
            if origin.startswith(scheme):
                return self._authority_ok(origin[len(scheme):].rstrip("/"))
        return False

    def _refuse(self) -> None:
        body = b"405: not a routed GET\n"
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", self.csp)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _refuse

    def __getattr__(self, name: str) -> Any:
        if name.startswith("do_"):
            return self._refuse
        raise AttributeError(name)

    # --- lookups: parameters are looked up, never used as paths ---------------

    def _project_root(self, name: str) -> pathlib.Path:
        for root in discover_projects(self.projects_dir):
            if root.name == name:
                return root
        raise portal_state.NotFound(f"unknown project: {name}")

    def _loaded(self, name: str) -> tuple[Any, Store, pathlib.Path]:
        root = self._project_root(name)
        store = Store(root.name, base=self.store_dir)
        project = load_project(root)  # per request, never cached (F9)
        check_registry_drift(project, store, record=False)
        return project, store, root

    def _flow(self, store: Store, flow_id: str) -> dict[str, Any]:
        if not FLOW_ID.match(flow_id):
            raise portal_state.NotFound(f"not a flow id: {flow_id}")
        row = flows.flows(store).get(flow_id)
        if row is None:
            raise portal_state.NotFound(f"unknown flow: {flow_id}")
        return row
