"""`claimstone control`: the authenticated write boundary (spec B4, D89).

Everything the read API is not, deliberately: it mounts the store read-write, holds
operator sessions, and answers POST. What it shares with `api.py` is the transport's
Host/Origin defences and response headers — by subclassing `transport.BaseHandler`,
which stays GET-only itself; this module adds the verb here and nowhere else.

Sessions live in this process's memory only: a restart logs everyone out, by design
(spec B4). Nothing here writes a project ledger yet — the session routes are the whole
of B4 — but every mutating route this server will ever answer is registered in
`ROUTES`, and the anonymous-access test enumerates that registry, so a route added by
a later step is covered the moment it is registered.
"""

from __future__ import annotations

import ipaddress
import json
import os
import pathlib
import secrets
import ssl
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from claimstone import flows, operators
from claimstone.transport import LOOPBACK_HOSTS, BaseHandler

CONTROL_VERSION = 1

CSP = "default-src 'none'; frame-ancestors 'none'"

PREFIX = ("control", "v1")

SESSION_COOKIE = "claimstone_control"

MAX_BODY = 64 * 1024  # §1.3 rule 3; B7b's upload is the one later exception

SESSION_IDLE_SECONDS = 12 * 60 * 60   # 12 hours of inactivity
LOGIN_WINDOW_SECONDS = 15 * 60        # per operator id
LOGIN_FAILURE_LIMIT = 5

MISDIRECTED_TEXT = "the Host header does not name this server"
NO_ORIGIN_TEXT = "every mutating request must carry a same-origin Origin header"
CROSS_ORIGIN_TEXT = "the Origin header does not name this server"
BAD_LOGIN_TEXT = "unknown operator or wrong password"
LOOPBACK_REFUSAL = ("refusing a non-loopback bind: the control server writes. Pass "
                    "--allow-host naming the proxy authority if one is really in front")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- sessions and the login budget ---------------------------------------------------------------


@dataclass(frozen=True)
class Session:
    operator_id: str
    operator_name: str
    csrf_token: str


class Sessions:
    """In-memory sessions with an inactivity timeout. No token ever touches a disk."""

    def __init__(self, idle_seconds: int = SESSION_IDLE_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._idle = float(idle_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._expires: dict[str, float] = {}
        self._rows: dict[str, Session] = {}

    def create(self, operator_id: str, operator_name: str) -> tuple[str, Session]:
        """(cookie token, session). The cookie token is 32 random bytes, hex-encoded."""
        token = secrets.token_hex(32)
        session = Session(operator_id, operator_name, secrets.token_hex(32))
        with self._lock:
            now = self._clock()
            for held in [t for t, until in self._expires.items() if until <= now]:
                self._expires.pop(held, None)
                self._rows.pop(held, None)
            self._expires[token] = now + self._idle
            self._rows[token] = session
        return token, session

    def get(self, token: str) -> Session | None:
        with self._lock:
            until = self._expires.get(token)
            if until is None:
                return None
            if self._clock() > until:
                self._expires.pop(token, None)
                self._rows.pop(token, None)
                return None
            self._expires[token] = self._clock() + self._idle  # activity refreshes
            return self._rows[token]

    def end(self, token: str) -> None:
        with self._lock:
            self._expires.pop(token, None)
            self._rows.pop(token, None)


class LoginBudget:
    """5 failures per operator id per 15 minutes → 429 (spec B4). Successes do not
    clear the window: the count is of failures, and the window slides on its own."""

    def __init__(self, window_seconds: int = LOGIN_WINDOW_SECONDS,
                 limit: int = LOGIN_FAILURE_LIMIT,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._window = float(window_seconds)
        self._limit = limit
        self._clock = clock
        self._lock = threading.Lock()
        self._failures: dict[str, deque[float]] = {}

    def _prune(self, failures: deque[float], now: float) -> None:
        while failures and failures[0] <= now - self._window:
            failures.popleft()

    def blocked(self, operator_id: str) -> bool:
        with self._lock:
            failures = self._failures.get(operator_id)
            if not failures:
                return False
            self._prune(failures, self._clock())
            return len(failures) >= self._limit

    def record_failure(self, operator_id: str) -> None:
        with self._lock:
            self._failures.setdefault(operator_id, deque()).append(self._clock())


# --- the route registry ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Route:
    method: str                # "GET" or "POST"; PUT and DELETE are never used (spec B5)
    template: tuple[str, ...]  # segments below /control/v1; "{name}" marks a parameter
    handler: str               # the _Handler method name
    public: bool = False       # True only for the session-create route


ROUTES: tuple[Route, ...] = (
    Route("POST", ("session",), "_session_create", public=True),
    Route("GET", ("session",), "_session_read"),
    Route("POST", ("session", "end"), "_session_end"),
)


class ControlError(Exception):
    """A route's named answer: the status, the envelope code and the message."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


# --- the handler ----------------------------------------------------------------------------------


class _Handler(BaseHandler):
    """POST support and sessions on the shared transport base. The base stays
    GET-only; every non-GET verb this server answers is routed here."""

    csp = CSP

    sessions: Sessions
    login_budget: LoginBudget
    state_dir: pathlib.Path

    # --- responses, with the read API's envelope ------------------------------------------------

    def _respond(self, body: bytes, code: int, content_type: str,
                 cookies: tuple[str, ...] = ()) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", self.csp)
        for cookie in cookies:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload: Any, code: int = 200,
              cookies: tuple[str, ...] = ()) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=1, default=str).encode(
            "utf-8")
        self._respond(body, code, "application/json; charset=utf-8", cookies)

    def _error(self, code: int, name: str, message: str,
               cookies: tuple[str, ...] = ()) -> None:
        self._json({"error": {"code": name, "message": message}}, code=code,
                   cookies=cookies)

    def _refuse(self) -> None:  # the base answers unknown verbs; this server allows POST
        body = b"405: not a routed GET or POST\n"
        self._respond(body, 405, "text/plain; charset=utf-8")

    # The base binds its own `_refuse` onto these names at class-creation time; rebind
    # them here so the refusal this server sends names both allowed verbs.
    do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _refuse

    # --- routing ---------------------------------------------------------------------------------

    def _match(self, method: str, segments: list[str]) -> tuple[Route, dict[str, str]]:
        """The one route this request addresses, or a 404/405 answer. Parameters are
        captured, never used as paths."""
        wrong_verb: list[str] = []
        for route in ROUTES:
            if len(route.template) != len(segments):
                continue
            params: dict[str, str] = {}
            for want, got in zip(route.template, segments):
                if want.startswith("{") and want.endswith("}"):
                    params[want[1:-1]] = got
                elif want != got:
                    break
            else:
                if route.method == method:
                    return route, params
                wrong_verb.append(route.method)
        if wrong_verb:
            raise ControlError(405, "METHOD_NOT_ALLOWED",
                               "this path answers " + " and ".join(sorted(set(wrong_verb))))
        raise ControlError(404, "NOT_FOUND", "no such control route")

    def do_GET(self) -> None:  # noqa: N802 - http.server's naming
        try:
            self._common(True)
            route, params = self._match("GET", self._segments())
            if not route.public:
                self._require_session()  # authenticated reads: 401 before the route
            getattr(self, route.handler)(params, None, {})
        except BrokenPipeError:
            pass
        except ControlError as exc:
            self._error(exc.status, exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001 - the class name alone, never the payload
            self._error(500, "INTERNAL", type(exc).__name__)

    def do_POST(self) -> None:  # noqa: N802 - http.server's naming
        try:
            self._common(False)
            route, params = self._match("POST", self._segments())
            if route.public:
                # The one POST without a session is the login itself; Origin still
                # must be present and allowed (§1.3 rule 2).
                self._require_origin()
            else:
                self._require_session()  # §1.3 order: session first, then CSRF
                self._require_origin()
                self._require_csrf()
            body = self._read_body()
            getattr(self, route.handler)(params, None, body)
        except BrokenPipeError:
            pass
        except ControlError as exc:
            self._error(exc.status, exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001 - the class name alone, never the payload
            self._error(500, "INTERNAL", type(exc).__name__)

    def _segments(self) -> list[str]:
        route = urlparse(self.path)
        segments = [unquote(part) for part in route.path.split("/") if part]
        if tuple(segments[:2]) != PREFIX:
            raise ControlError(404, "NOT_FOUND", "no such control route")
        return segments[2:]

    def _common(self, get: bool) -> None:
        if not self._host_ok():
            raise ControlError(421, "MISDIRECTED", MISDIRECTED_TEXT)
        if not self._origin_ok():  # absent is fine for GET; POST re-checks presence
            raise ControlError(403, "CROSS_ORIGIN", CROSS_ORIGIN_TEXT)

    # --- the §1.3 rules --------------------------------------------------------------------------

    def _require_origin(self) -> None:
        if self.headers.get("Origin") is None:
            raise ControlError(403, "NO_ORIGIN", NO_ORIGIN_TEXT)
        if not self._origin_ok():
            raise ControlError(403, "CROSS_ORIGIN", CROSS_ORIGIN_TEXT)

    def _session_token(self) -> str | None:
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel is not None else None

    def _require_session(self) -> Session:
        token = self._session_token()
        session = self.sessions.get(token) if token else None
        if session is None:
            raise ControlError(401, "UNAUTHORIZED", "no session")
        return session

    def _require_csrf(self, session: Session | None = None) -> Session:
        session = session or self._require_session()
        header = self.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(header.encode("utf-8"),
                                      session.csrf_token.encode("utf-8")):
            raise ControlError(403, "CSRF", "the X-CSRF-Token header does not match the session")
        return session

    def _read_body(self) -> dict[str, Any]:
        """§1.3 rule 3: application/json, at most 64 KiB, an object, no unknown keys —
        the unknown-keys check is the route's, which knows its own vocabulary."""
        length = self.headers.get("Content-Length")
        try:
            size = int(length) if length is not None else 0
        except ValueError:
            raise ControlError(400, "BAD_REQUEST", "malformed Content-Length") from None
        if size < 0:
            # rfile.read(-n) reads to end of stream: unbounded, and past the size limit.
            raise ControlError(400, "BAD_REQUEST", "malformed Content-Length") from None
        if size > MAX_BODY:
            raise ControlError(413, "TOO_LARGE",
                               f"body over {MAX_BODY} bytes: {size}")
        content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise ControlError(400, "BAD_REQUEST",
                               "Content-Type must be application/json")
        raw = self.rfile.read(size) if size else b""
        if not raw.strip():
            return {}  # an empty body is the empty object; routes still validate their keys
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ControlError(400, "BAD_REQUEST", "body is not valid JSON") from None
        if not isinstance(parsed, dict):
            raise ControlError(400, "BAD_REQUEST", "body must be a JSON object")
        return parsed

    @staticmethod
    def _only_keys(body: dict[str, Any], allowed: frozenset[str]) -> None:
        unknown = sorted(set(body) - allowed)
        if unknown:
            raise ControlError(400, "BAD_REQUEST",
                               "unknown key(s): " + ", ".join(unknown))

    # --- cookies ---------------------------------------------------------------------------------

    def _secure_request(self) -> bool:
        if isinstance(self.connection, ssl.SSLSocket):
            return True
        # Behind the proxy, the connection the server sees is plain HTTP. Honoring the
        # header can only *add* the Secure flag, never remove it, so the failure mode
        # of a spoofed header is a cookie browsers refuse to send over plain HTTP.
        return self.headers.get("X-Forwarded-Proto", "").strip().lower() == "https"

    def _session_cookie(self, token: str, *, expire: bool = False) -> str:
        parts = [f"{SESSION_COOKIE}={'' if expire else token}", "Path=/", "HttpOnly",
                 "SameSite=Strict"]
        if self._secure_request():
            parts.append("Secure")
        if expire:
            parts.append("Max-Age=0")
        return "; ".join(parts)

    # --- the session routes (B4) -----------------------------------------------------------------

    def _session_create(self, params: dict[str, str], query: Any,
                        body: dict[str, Any]) -> None:
        self._only_keys(body, frozenset({"id", "password"}))
        operator_id = body.get("id")
        password = body.get("password")
        if not isinstance(operator_id, str) or not operator_id.strip():
            raise ControlError(422, "VALIDATION", "id must be a non-empty string")
        if not isinstance(password, str) or not password:
            raise ControlError(422, "VALIDATION", "password must be a non-empty string")
        if self.login_budget.blocked(operator_id):
            raise ControlError(429, "RATE_LIMITED",
                               "too many failed logins for this id; wait 15 minutes")
        row = operators.load(self.state_dir).get(operator_id)
        # An unknown id still pays for one scrypt derivation, so response time does not
        # reveal which ids exist.
        verified = operators.verify(row if row is not None else operators.DUMMY_ROW, password)
        if row is None or not verified:
            # One sentence for an unknown id and a wrong password alike: which of the
            # two failed is not the caller's business.
            self.login_budget.record_failure(operator_id)
            raise ControlError(401, "UNAUTHORIZED", BAD_LOGIN_TEXT)
        token, session = self.sessions.create(str(row["id"]), str(row.get("name") or ""))
        self._json({"operator": {"id": session.operator_id,
                                 "name": session.operator_name},
                    "csrf_token": session.csrf_token},
                   cookies=(self._session_cookie(token),))

    def _session_read(self, params: dict[str, str], query: Any,
                      body: dict[str, Any]) -> None:
        session = self._require_session()
        self._json({"operator": {"id": session.operator_id,
                                 "name": session.operator_name},
                    "csrf_token": session.csrf_token})

    def _session_end(self, params: dict[str, str], query: Any,
                     body: dict[str, Any]) -> None:
        self._only_keys(body, frozenset())
        session = self._require_csrf()
        token = self._session_token()
        if token:
            self.sessions.end(token)
        self._json({"ended": True},
                   cookies=(self._session_cookie("", expire=True),))


# --- the server -----------------------------------------------------------------------------------


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def make_server(projects_dir: str | pathlib.Path = "projects",
                store_dir: str | pathlib.Path = "store", *,
                host: str = "127.0.0.1", port: int = 8790,
                allow_hosts: tuple[str, ...] = (),
                state_dir: str | pathlib.Path | None = None) -> ThreadingHTTPServer:
    """The control server. A non-loopback bind is refused outright — this process
    writes, so it does not proceed on a warning the way the read-only servers do —
    unless `--allow-host` names the authority of the proxy that fronts it."""
    if not _is_loopback(host) and not allow_hosts:
        raise ValueError(LOOPBACK_REFUSAL)
    revision, dirty = flows._code_identity(pathlib.Path(projects_dir))
    if revision is None and os.environ.get("CLAIMSTONE_CODE_REVISION"):
        revision = os.environ["CLAIMSTONE_CODE_REVISION"]
    names = set(LOOPBACK_HOSTS)
    if host not in ("0.0.0.0", "::"):
        names.add(host)
    handler = type("ControlHandler", (_Handler,), {
        "projects_dir": pathlib.Path(projects_dir),
        "store_dir": pathlib.Path(store_dir),
        "allowed_hosts": frozenset(n.lower() for n in names),
        "allowed_authorities": frozenset(a.lower() for a in allow_hosts),
        "bind_port": int(port),
        "code_revision": revision,
        "code_dirty": dirty,
        "state_dir": operators.state_dir(state_dir),
        "sessions": Sessions(),
        "login_budget": LoginBudget(),
        "started_at": _now_iso(),
    })
    httpd = ThreadingHTTPServer((host, port), handler)
    handler.bind_port = int(httpd.server_address[1])
    return httpd


def serve(projects_dir: str | pathlib.Path = "projects",
          store_dir: str | pathlib.Path = "store", *, host: str = "127.0.0.1",
          port: int = 8790, allow_hosts: tuple[str, ...] = (),
          state_dir: str | pathlib.Path | None = None) -> None:
    """Block and serve the control API."""
    httpd = make_server(projects_dir, store_dir, host=host, port=port,
                        allow_hosts=allow_hosts, state_dir=state_dir)
    print(f"claimstone control — http://{host}:{port}/control/v1/session  "
          "(authenticated writes; Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
