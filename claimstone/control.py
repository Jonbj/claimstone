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

import hashlib
import ipaddress
import json
import re
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
import urllib.parse
from urllib.parse import unquote, urlparse

from claimstone import (admin, decisions, drafts, export, flows, intake, operations,
                        operations_view, operators, portal_state, scope, synthesize, today)
from claimstone.config import ConfigError, RegistryDrift
from claimstone.store import LedgerCorrupt, Store
from claimstone.transport import LOOPBACK_HOSTS, BaseHandler

CONTROL_VERSION = 1

CSP = "default-src 'none'; frame-ancestors 'none'"

PREFIX = ("control", "v1")

SESSION_COOKIE = "claimstone_control"

MAX_BODY = 64 * 1024  # §1.3 rule 3; B7b's upload is the one later exception

SESSION_IDLE_SECONDS = 12 * 60 * 60   # 12 hours of inactivity
LOGIN_WINDOW_SECONDS = 15 * 60        # per operator id
LOGIN_FAILURE_LIMIT = 5

IDEMPOTENCY_SECONDS = 24 * 60 * 60   # a replayed key is answered from memory for a day
IDEMPOTENCY_MAX = 10_000             # oldest entries are dropped beyond this

PROFILE_SHA = re.compile(r"^[0-9a-f]{64}$")

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


class Idempotency:
    """`Idempotency-Key` for authenticated POSTs (§1.3 rule 7), in memory like the sessions.

    Keyed by (operator id, key). The same key with the same request replays the first
    successful answer; with a different request it is a conflict; while the first is still
    running it is a conflict too, so a double click can never execute twice. Only successes
    are kept: a refused request leaves the key free, because nothing happened. A restart
    forgets the keys — the same window in which every session ends.
    """

    def __init__(self, ttl_seconds: int = IDEMPOTENCY_SECONDS, limit: int = IDEMPOTENCY_MAX,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = float(ttl_seconds)
        self._limit = limit
        self._clock = clock
        self._lock = threading.Lock()
        # (operator, key) -> (fingerprint, stored_at, result or None while pending)
        self._held: dict[tuple[str, str], tuple[str, float, tuple[Any, int] | None]] = {}

    def begin(self, operator_id: str, key: str, fingerprint: str) -> tuple[Any, int] | None:
        """The stored result to replay, or None after marking the key as running."""
        with self._lock:
            now = self._clock()
            for held in [k for k, (_f, at, _r) in self._held.items() if at + self._ttl <= now]:
                self._held.pop(held, None)
            found = self._held.get((operator_id, key))
            if found is not None:
                held_fingerprint, _at, result = found
                if held_fingerprint != fingerprint:
                    raise ControlError(409, "IDEMPOTENCY_CONFLICT",
                                       "this Idempotency-Key was used for a different request")
                if result is None:
                    raise ControlError(409, "IDEMPOTENCY_IN_PROGRESS",
                                       "a request with this Idempotency-Key is still running")
                return result
            while len(self._held) >= self._limit:
                self._held.pop(next(iter(self._held)))
            self._held[(operator_id, key)] = (fingerprint, now, None)
            return None

    def finish(self, operator_id: str, key: str, result: tuple[Any, int] | None) -> None:
        """Keep a success for replay; forget the key after a refusal."""
        with self._lock:
            found = self._held.get((operator_id, key))
            if found is None:
                return
            if result is None:
                self._held.pop((operator_id, key), None)
            else:
                self._held[(operator_id, key)] = (found[0], found[1], result)


# --- the route registry ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Route:
    method: str                # "GET" or "POST"; PUT and DELETE are never used (spec B5)
    template: tuple[str, ...]  # segments below /control/v1; "{name}" marks a parameter
    handler: str               # the _Handler method name
    public: bool = False       # True only for the session-create route
    raw: bool = False          # the handler reads the body stream itself (B7b's file upload)


ROUTES: tuple[Route, ...] = (
    Route("POST", ("session",), "_session_create", public=True),
    Route("GET", ("session",), "_session_read"),
    Route("POST", ("session", "end"), "_session_end"),
    # B5: signing and drafts. `{question_id}` is looked up in the registry, `{flow_id}` in
    # flows.jsonl, `{project}` among the discovered projects — never used as a path.
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "q", "{question_id}", "adjudicate"),
          "_adjudicate"),
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "q", "{question_id}", "draft"),
          "_draft_save"),
    Route("GET", ("p", "{project}", "flows", "{flow_id}", "q", "{question_id}", "draft"),
          "_draft_read"),
    # B7a: material intake (references, DOIs, links). Recording and routing only.
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "intake"), "_intake_submit"),
    Route("GET", ("p", "{project}", "flows", "{flow_id}", "intake"), "_intake_list"),
    # B7b: a file for one candidate; the body is the file itself, not JSON.
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "intake", "file"), "_intake_file",
          raw=True),
    # B8: decisions. The preview route precedes the state route: same length, fixed segment first.
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "intake", "{intake_id}", "resolve"),
          "_identity_resolve"),
    Route("GET", ("p", "{project}", "flows", "{flow_id}", "decisions"), "_decisions_list"),
    Route("GET", ("p", "{project}", "flows", "{flow_id}", "decisions", "retry-campaign",
                  "preview"), "_retry_preview"),
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "decisions", "retry-campaign"),
          "_retry_approve"),
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "decisions", "{decision_id}", "state"),
          "_decision_state"),
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "offers"), "_offer_record"),
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "offers", "{offer_id}", "stage"),
          "_offer_stage"),
    # B9: Today, and the operator's "seen up to" markers.
    Route("GET", ("today",), "_today"),
    Route("POST", ("seen",), "_seen"),
    # B10: export from the web. The list is the read API's (BR); these two are actions.
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "exports"), "_export_create"),
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "exports", "{export_id}", "verify"),
          "_export_verify"),
    # B11: administration. Opening the admin view sends no request anywhere; each check is a POST.
    Route("GET", ("admin",), "_admin_read"),
    Route("POST", ("admin", "check"), "_admin_check"),
    Route("POST", ("admin", "credential"), "_admin_credential"),
    Route("POST", ("admin", "paid-test"), "_admin_paid_test"),
    # B12: the scheduler's operations. Planning stays with the scheduler and the CLI.
    Route("GET", ("p", "{project}", "flows", "{flow_id}", "operations"), "_operations_list"),
    Route("GET", ("p", "{project}", "flows", "{flow_id}", "batches"), "_batches_list"),
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "batches", "{batch_id}",
                   "authorize"), "_batch_authorize"),
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "operations", "{operation_id}",
                   "authorize"), "_operation_authorize"),
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "operations", "{operation_id}",
                   "pause"), "_operation_not_built"),
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "operations", "{operation_id}",
                   "resume"), "_operation_not_built"),
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
    idempotency: Idempotency
    state_dir: pathlib.Path
    # Name resolution for the intake URL check. None is the system resolver; tests pass a
    # fake one so no real name is ever looked up (the hook exists for nothing else).
    resolver: Any = None
    # Text extraction for the upload identity check. None is `pdftotext`; tests may pass a fake.
    extract_text: Any = None
    # The reachability check's transport, and the `.env` it may write: test hooks only.
    http_get: Any = None
    env_file: Any = None

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
            result = getattr(self, route.handler)(params, None, {})
            if result is not None:
                payload, status = result
                self._json(payload, status)
        except BrokenPipeError:
            pass
        except Exception as exc:  # noqa: BLE001 - mapped to a named answer below
            self._answer_exception(exc)

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
            body = {} if route.raw else self._read_body()
            if route.public:
                getattr(self, route.handler)(params, None, body)  # writes its own answer
                return
            self._post_authenticated(route, params, body)
        except BrokenPipeError:
            pass
        except Exception as exc:  # noqa: BLE001 - mapped to a named answer below
            self._answer_exception(exc)

    def _post_authenticated(self, route: Route, params: dict[str, str],
                            body: dict[str, Any]) -> None:
        """Run one authenticated POST, honouring `Idempotency-Key` (§1.3 rule 7). Routes
        that answer for themselves (the session routes) return None and are not replayed."""
        session = self._require_session()
        key = self.headers.get("Idempotency-Key")
        if route.raw:
            # A raw body is not part of the fingerprint, so a key could not tell two files apart.
            # A file is idempotent by its hash instead: the same bytes twice are a DUPLICATE.
            key = None
        if key is None:
            result = getattr(self, route.handler)(params, None, body)
            if result is not None:
                self._json(result[0], result[1])
            return
        if not key.strip() or len(key) > 200:
            raise ControlError(400, "BAD_REQUEST", "Idempotency-Key must be 1-200 characters")
        fingerprint = hashlib.sha256(json.dumps(
            [route.handler, params, body], sort_keys=True, ensure_ascii=False,
            default=str).encode("utf-8")).hexdigest()
        replay = self.idempotency.begin(session.operator_id, key, fingerprint)
        if replay is not None:
            self._json(replay[0], replay[1])
            return
        result: tuple[Any, int] | None = None
        try:
            result = getattr(self, route.handler)(params, None, body)
        finally:
            self.idempotency.finish(session.operator_id, key, result)
        if result is not None:
            self._json(result[0], result[1])

    def _answer_exception(self, exc: Exception) -> None:
        """One mapping from what the engine and the lookups raise to the envelope."""
        if isinstance(exc, ControlError):
            self._error(exc.status, exc.code, exc.message)
        elif isinstance(exc, portal_state.NotFound):
            self._error(404, "NOT_FOUND", str(exc))
        elif isinstance(exc, RegistryDrift):  # a ConfigError subclass: the named state first
            self._error(409, "REGISTRY_DRIFT", str(exc))
        elif isinstance(exc, ConfigError):
            self._error(409, "CONFIG_ERROR", str(exc))
        elif isinstance(exc, LedgerCorrupt):
            self._error(500, "LEDGER_CORRUPT", str(exc))
        else:  # the class name alone, never the payload
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


# --- B5: signing and drafts ---------------------------------------------------------------------


@dataclass(frozen=True)
class _FlowContext:
    project: Any
    store: Store
    flow_row: dict[str, Any]
    selector: scope.Selector
    question_id: str


def _flow_only(handler: _Handler, params: dict[str, str]
               ) -> tuple[Any, Store, dict[str, Any], scope.Selector]:
    """Project reloaded with registry drift checked, and the flow looked up (no question)."""
    project, store, _root = handler._loaded(params["project"])
    row = handler._flow(store, params["flow_id"])
    return project, store, row, portal_state._selector_of(row, scope.Selector(None))


def _flow_context(handler: _Handler, params: dict[str, str], *,
                  require_current: bool) -> _FlowContext:
    """Project reloaded and registry drift checked on every request (§1.3 rule 5, F9), the
    flow looked up in its ledger, the question in the registry.

    `require_current` is for signing: a flow whose binding drifted no longer names the
    protocol the engine is judging with, so a signature "in this flow" would bind to a
    meaning the operator did not select. The refusal says which part drifted."""
    project, store, _root = handler._loaded(params["project"])
    row = handler._flow(store, params["flow_id"])
    if require_current:
        binding = flows.binding_state(project, store, row)
        if binding["state"] != "CURRENT":
            raise ControlError(
                409, "FLOW_DRIFTED",
                f"this flow's binding is {binding['state']} "
                f"({', '.join(binding['differences'])}): it no longer describes the live "
                "protocol, so nothing can be signed under it; bind a new flow first")
    question_id = params["question_id"]
    if question_id not in project.question_ids:
        raise portal_state.NotFound(f"unknown question id: {question_id}")
    selector = portal_state._selector_of(row, scope.Selector(None))
    return _FlowContext(project, store, row, selector, question_id)


def _profile_hash(body: dict[str, Any]) -> str:
    value = body.get("profile_sha256")
    if not isinstance(value, str) or not PROFILE_SHA.match(value):
        raise ControlError(422, "VALIDATION",
                           "profile_sha256 must be the 64-hex hash of the profile you read")
    return value


def _current_hash(context: _FlowContext) -> str | None:
    profile = synthesize.latest_profiles(
        context.store, round_name=context.selector.round,
        manifest_only=context.selector.manifest_only).get(context.question_id)
    return str(profile["profile_sha256"]) if profile else None


def _adjudicate(self: _Handler, params: dict[str, str], query: Any,
                body: dict[str, Any]) -> tuple[Any, int]:
    """Sign one verdict as the session's operator (spec B5). Every scientific refusal is the
    engine's own: this route adds only the request rules, the attestation and the flow's
    binding check, and never fills in a verdict for anyone."""
    self._only_keys(body, frozenset({"verdict", "rationale", "profile_sha256", "attest"}))
    session = self._require_session()
    verdict = body.get("verdict")
    if verdict not in synthesize.VERDICTS:
        raise ControlError(422, "VALIDATION",
                           f"verdict must be one of {', '.join(synthesize.VERDICTS)}")
    if body.get("attest") is not True:
        raise ControlError(422, "VALIDATION",
                           "attest must be the literal true: the signer states they read "
                           "the evidence profile this verdict binds to")
    rationale = body.get("rationale")
    if not isinstance(rationale, str):
        raise ControlError(422, "VALIDATION", "rationale must be text")
    trimmed = rationale.strip()
    if len(trimmed) < synthesize.MIN_RATIONALE_CHARS:
        raise ControlError(
            422, "VALIDATION",
            f"a rationale of {len(trimmed)} characters is below the declared minimum of "
            f"{synthesize.MIN_RATIONALE_CHARS}: the reasoning is the verdict's only defence")
    shown = _profile_hash(body)
    context = _flow_context(self, params, require_current=True)
    try:
        row = synthesize.adjudicate(
            context.store, context.question_id, project=context.project,
            round_name=context.selector.round, manifest_only=context.selector.manifest_only,
            verdict=verdict, rationale=rationale, by=session.operator_name,
            signer_auth="portal-session", actor=session.operator_id, profile_sha256=shown)
    except KeyError as exc:
        raise ControlError(409, "NO_PROFILE", str(exc.args[0] if exc.args else exc)) from None
    except synthesize.Provisional as exc:
        raise ControlError(409, "PROVISIONAL", str(exc)) from None
    except synthesize.StaleProfile as exc:
        raise ControlError(409, "STALE_PROFILE", str(exc)) from None
    except ValueError as exc:  # the request rules passed above: what remains is a state refusal
        raise ControlError(409, "REFUSED", str(exc)) from None
    return {"adjudication": row}, 201


def _draft_save(self: _Handler, params: dict[str, str], query: Any,
                body: dict[str, Any]) -> tuple[Any, int]:
    """Keep the operator's unfinished reasoning. Not a signature, not evidence."""
    self._only_keys(body, frozenset({"rationale", "profile_sha256"}))
    session = self._require_session()
    rationale = body.get("rationale")
    if not isinstance(rationale, str):
        raise ControlError(422, "VALIDATION", "rationale must be text")
    shown = _profile_hash(body)
    context = _flow_context(self, params, require_current=False)
    try:
        row = drafts.append(context.store, actor=session.operator_id,
                            flow_id=str(context.flow_row["flow_id"]),
                            question_id=context.question_id, rationale=rationale,
                            profile_sha256=shown, code_revision=self.code_revision)
    except ValueError as exc:
        raise ControlError(422, "VALIDATION", str(exc)) from None
    current = _current_hash(context)
    return {"draft": row, "current": shown == current, "current_profile_sha256": current}, 201


def _draft_read(self: _Handler, params: dict[str, str], query: Any,
                body: dict[str, Any]) -> tuple[Any, int]:
    """This operator's latest draft, and whether the profile it was written against is still
    the current one. `current` is null when there is no draft to compare."""
    session = self._require_session()
    context = _flow_context(self, params, require_current=False)
    row = drafts.latest(context.store, actor=session.operator_id,
                        flow_id=str(context.flow_row["flow_id"]),
                        question_id=context.question_id)
    current = _current_hash(context)
    return {"draft": row,
            "current": (row["profile_sha256"] == current) if row else None,
            "current_profile_sha256": current}, 200


def _intake_submit(self: _Handler, params: dict[str, str], query: Any,
                   body: dict[str, Any]) -> tuple[Any, int]:
    """Record one proposed DOI, link or reference and say where it was routed (spec B7a).
    Nothing is fetched and nothing counts: the answer is the routing, before any use."""
    self._only_keys(body, frozenset({"kind", "value", "note"}))
    session = self._require_session()
    kind, value, note = body.get("kind"), body.get("value"), body.get("note")
    if not isinstance(kind, str) or not isinstance(value, str):
        raise ControlError(422, "VALIDATION", "kind and value must be text")
    if note is not None and not isinstance(note, str):
        raise ControlError(422, "VALIDATION", "note must be text when given")
    project, store, row, selector = _flow_only(self, params)
    try:
        recorded = intake.submit(store, project, row, selector, kind=kind, value=value,
                                 note=note, actor=session.operator_id,
                                 code_revision=self.code_revision, resolver=self.resolver)
    except intake.IntakeRefused as exc:
        raise ControlError(422, "VALIDATION", str(exc)) from None
    return {"intake": recorded}, 201


def _intake_list(self: _Handler, params: dict[str, str], query: Any,
                 body: dict[str, Any]) -> tuple[Any, int]:
    _project, store, row, _selector = _flow_only(self, params)
    return {"flow_id": str(row["flow_id"]),
            "items": intake.for_flow(store, str(row["flow_id"]))}, 200


def _intake_file(self: _Handler, params: dict[str, str], query: Any,
                 body: dict[str, Any]) -> tuple[Any, int]:
    """Receive one file for one candidate (spec B7b): quarantined, checked by the engine's own
    gates, and recorded with its outcome. Only a file that passes every check leaves quarantine."""
    session = self._require_session()
    target = (urllib.parse.parse_qs(urlparse(self.path).query).get("target") or [""])[0]
    if not target:
        raise ControlError(422, "VALIDATION", "target must name the candidate this file is for")
    content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
    if content_type != "application/pdf":
        self.close_connection = True  # the body is not read; the connection cannot be reused
        raise ControlError(415, "UNSUPPORTED_MEDIA_TYPE", "a file must be sent as application/pdf")
    raw_length = self.headers.get("Content-Length")
    try:
        length = int(raw_length) if raw_length is not None else -1
    except ValueError:
        length = -1
    if length < 0:
        self.close_connection = True
        raise ControlError(411, "LENGTH_REQUIRED", "a file upload needs a Content-Length")
    if length > intake.MAX_FILE_BYTES:
        self.close_connection = True
        raise ControlError(413, "TOO_LARGE", f"a file must be at most {intake.MAX_FILE_BYTES} bytes")
    project, store, row, selector = _flow_only(self, params)
    if str(target) not in scope.candidates(store, selector):
        self.close_connection = True
        raise portal_state.NotFound(f"no candidate {target} in this flow")
    try:
        sha, path, held = intake.quarantine_stream(store, self.rfile, length)
        recorded = intake.receive_file(store, project, row, selector, target=target, sha=sha,
                                       path=path, already_held=held, actor=session.operator_id,
                                       code_revision=self.code_revision,
                                       extract_text=self.extract_text or intake.pdf_text)
    except intake.UnknownTarget as exc:
        raise portal_state.NotFound(str(exc)) from None
    except intake.IntakeRefused as exc:
        raise ControlError(422, "VALIDATION", str(exc)) from None
    return {"intake": recorded}, 201


def _decided(call: Callable[[], Any]) -> Any:
    """One mapping from the decision rules' refusals to the envelope."""
    try:
        return call()
    except decisions.Conflict as exc:
        raise ControlError(409, "CONFLICT", str(exc)) from None
    except (decisions.DecisionRefused, intake.IntakeRefused) as exc:
        raise ControlError(422, "VALIDATION", str(exc)) from None
    except (LookupError, intake.UnknownTarget) as exc:
        raise portal_state.NotFound(str(exc.args[0] if exc.args else exc)) from None


def _identity_resolve(self: _Handler, params: dict[str, str], query: Any,
                      body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset({"answer", "reason"}))
    session = self._require_session()
    project, store, row, selector = _flow_only(self, params)
    result = _decided(lambda: decisions.resolve_identity(
        store, project, row, selector, intake_id=params["intake_id"], answer=body.get("answer"),
        reason=body.get("reason"), actor=session.operator_id, code_revision=self.code_revision))
    return result, 201


def _decisions_list(self: _Handler, params: dict[str, str], query: Any,
                    body: dict[str, Any]) -> tuple[Any, int]:
    """What waits for a person in this flow (F13 order), and what was decided recently."""
    _project, store, row, selector = _flow_only(self, params)
    flow_id = str(row["flow_id"])
    decided = [r for r in decisions.latest(store).values()
               if r.get("flow_id") == flow_id and r.get("state") not in ("proposed",)]
    decided.sort(key=lambda r: str(r.get("recorded_at")), reverse=True)
    return {"flow_id": flow_id, "open": decisions.open_items(store, selector, flow_id),
            "decided_recently": decided[:20]}, 200


def _candidate_ids(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [part for part in value.split(",") if part]
    if (not isinstance(value, list) or not value or len(value) > 200
            or any(not isinstance(v, str) or not v for v in value)):
        raise ControlError(422, "VALIDATION", "candidate_ids must name 1-200 candidates")
    return list(dict.fromkeys(value))


def _retry_preview(self: _Handler, params: dict[str, str], query: Any,
                   body: dict[str, Any]) -> tuple[Any, int]:
    project, store, _row, selector = _flow_only(self, params)
    raw = (urllib.parse.parse_qs(urlparse(self.path).query).get("candidate_ids") or [""])[0]
    keys = _candidate_ids(raw)
    return _decided(lambda: decisions.retry_preview(store, project, selector, keys)), 200


def _retry_approve(self: _Handler, params: dict[str, str], query: Any,
                   body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset({"candidate_ids", "campaign", "max_requests"}))
    session = self._require_session()
    project, store, row, selector = _flow_only(self, params)
    keys = _candidate_ids(body.get("candidate_ids"))
    return {"decision": _decided(lambda: decisions.approve_retry(
        store, project, row, selector, candidate_keys=keys, campaign=body.get("campaign"),
        max_requests=body.get("max_requests"), actor=session.operator_id,
        code_revision=self.code_revision))}, 201


def _decision_state(self: _Handler, params: dict[str, str], query: Any,
                    body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset({"state", "until", "reason"}))
    session = self._require_session()
    _project, store, row, _selector = _flow_only(self, params)
    return {"decision": _decided(lambda: decisions.set_state(
        store, row, decision_id=params["decision_id"], state=body.get("state"),
        until=body.get("until"), reason=body.get("reason"), actor=session.operator_id,
        code_revision=self.code_revision))}, 201


def _offer_record(self: _Handler, params: dict[str, str], query: Any,
                  body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset({"candidate_id", "work_version", "vendor", "price",
                                     "currency", "tax_status", "terms_url", "verified_at",
                                     "resolves"}))
    session = self._require_session()
    _project, store, row, selector = _flow_only(self, params)
    return {"offer": _decided(lambda: decisions.record_offer(
        store, row, selector, body=body, actor=session.operator_id,
        code_revision=self.code_revision))}, 201


def _offer_stage(self: _Handler, params: dict[str, str], query: Any,
                 body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset({"stage"}))
    session = self._require_session()
    _project, store, row, _selector = _flow_only(self, params)
    return {"offer": _decided(lambda: decisions.offer_stage(
        store, row, offer_id=params["offer_id"], stage=body.get("stage"),
        actor=session.operator_id, code_revision=self.code_revision))}, 201


def _today(self: _Handler, params: dict[str, str], query: Any,
           body: dict[str, Any]) -> tuple[Any, int]:
    session = self._require_session()
    return today.today(self.projects_dir, self.store_dir, self.state_dir,
                       actor=session.operator_id), 200


def _seen(self: _Handler, params: dict[str, str], query: Any,
          body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset({"project", "until"}))
    session = self._require_session()
    project = body.get("project")
    if project is not None:
        if not isinstance(project, str):
            raise ControlError(422, "VALIDATION", "project must be a project name")
        self._project_root(project)  # an unknown project is a 404, never a marker for nothing
    until = body.get("until")
    if until is not None and not isinstance(until, str):
        raise ControlError(422, "VALIDATION", "until must be an ISO date-time")
    try:
        row = today.mark_seen(self.state_dir, actor=session.operator_id, project=project,
                              until=until)
    except ValueError as exc:
        raise ControlError(422, "VALIDATION", str(exc)) from None
    return {"seen": row}, 201


EXPORT_ID = re.compile(r"^[0-9a-f]{64}$")


def _export_create(self: _Handler, params: dict[str, str], query: Any,
                   body: dict[str, Any]) -> tuple[Any, int]:
    """Freeze this flow's ledgers into a snapshot (spec B10). The same bytes, instruments and
    protocol give the same export, so asking twice answers `created_now: false`."""
    self._only_keys(body, frozenset({"include_copies"}))
    session = self._require_session()
    include = body.get("include_copies", False)
    if type(include) is not bool:
        raise ControlError(422, "VALIDATION", "include_copies must be true or false")
    project, store, row, _selector = _flow_only(self, params)
    try:
        directory, created = export.export(project, store, str(row["flow_id"]),
                                           include_copies=include, actor=session.operator_id)
    except ValueError as exc:
        raise ControlError(409, "REFUSED", str(exc)) from None
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    return {"export_id": directory.name, "created_now": created,
            "copies": manifest.get("copies")}, 201 if created else 200


def _export_verify(self: _Handler, params: dict[str, str], query: Any,
                   body: dict[str, Any]) -> tuple[Any, int]:
    """Check one export against the live store and project, on request only: the same check
    as `claimstone export-verify`. An empty list means the export still holds."""
    self._only_keys(body, frozenset())
    self._require_session()
    _project, store, row, _selector = _flow_only(self, params)
    export_id = params["export_id"]
    held = {str(r.get("export_id")) for r in store.read(export.EXPORTS_LEDGER)
            if str(r.get("flow_id")) == str(row["flow_id"])}
    if not EXPORT_ID.match(export_id) or export_id not in held:
        raise portal_state.NotFound(f"no export {export_id} for this flow")
    problems = export.verify(store.root / "exports" / export_id, self.projects_dir)
    return {"export_id": export_id, "holds": not problems, "problems": problems}, 200


def _admin_read(self: _Handler, params: dict[str, str], query: Any,
                body: dict[str, Any]) -> tuple[Any, int]:
    """Presence of credentials, configured backends, instruments, and the last recorded check per
    service. Nothing is contacted to answer this."""
    self._require_session()
    state = portal_state.admin_state(pathlib.Path(self.projects_dir).resolve().parent)
    return {**state, "checks": admin.latest_checks(self.state_dir),
            "check_targets": admin.targets()}, 200


def _admin_check(self: _Handler, params: dict[str, str], query: Any,
                 body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset({"target"}))
    session = self._require_session()
    try:
        row = admin.check(self.state_dir, target=body.get("target"), actor=session.operator_id,
                          http_get=self.http_get)
    except admin.AdminRefused as exc:
        raise ControlError(422, "VALIDATION", str(exc)) from None
    return {"check": row}, 201


def _admin_credential(self: _Handler, params: dict[str, str], query: Any,
                      body: dict[str, Any]) -> tuple[Any, int]:
    """Replace one credential, with the password asked again (spec B11). A wrong password counts
    against the same budget as a failed login, so this route is no side door for guessing."""
    self._only_keys(body, frozenset({"name", "value", "password"}))
    session = self._require_session()
    password = body.get("password")
    if self.login_budget.blocked(session.operator_id):
        raise ControlError(429, "RATE_LIMITED", "too many failed attempts; wait 15 minutes")
    row = operators.load(self.state_dir).get(session.operator_id)
    if not isinstance(password, str) or row is None or not operators.verify(row, password):
        self.login_budget.record_failure(session.operator_id)
        raise ControlError(403, "REAUTH", "the password is required again, and it did not match")
    if self.env_file is None:
        raise ControlError(409, "CREDENTIALS_READ_ONLY",
                           "this deployment cannot write credentials: edit .env on the host and "
                           "restart the services that read it")
    try:
        recorded = admin.replace_credential(self.env_file, self.state_dir, name=body.get("name"),
                                            value=body.get("value"), actor=session.operator_id)
    except admin.AdminRefused as exc:
        raise ControlError(422, "VALIDATION", str(exc)) from None
    return {"credential": {"name": recorded["name"], "set": True, "note": recorded["note"]}}, 201


def _admin_paid_test(self: _Handler, params: dict[str, str], query: Any,
                     body: dict[str, Any]) -> tuple[Any, int]:
    self._require_session()
    raise ControlError(
        501, "NOT_IMPLEMENTED",
        "a paid test call needs the model-call boundary and a cost reservation; it belongs to the "
        "scheduler's authorized operations, not to a button here")


def _operations_list(self: _Handler, params: dict[str, str], query: Any,
                     body: dict[str, Any]) -> tuple[Any, int]:
    self._require_session()
    _project, store, row, _selector = _flow_only(self, params)
    try:
        listed = operations_view.for_flow(store, str(row["flow_id"]))
    except operations.OperationError as exc:
        raise ControlError(409, "OPERATIONS_LEDGER", str(exc)) from None
    return {"flow_id": str(row["flow_id"]), "operations": listed}, 200


def _operation_authorize(self: _Handler, params: dict[str, str], query: Any,
                         body: dict[str, Any]) -> tuple[Any, int]:
    """Authorize one planned operation as the session's operator (spec B12). The request must
    repeat the limits the operator was shown; a plan that differs is refused, so an
    authorization can never cover more than what was read."""
    self._only_keys(body, frozenset({"limits"}))
    session = self._require_session()
    _project, store, row, _selector = _flow_only(self, params)
    operation_id = params["operation_id"]
    try:
        grouped = operations._events(store)
    except operations.OperationError as exc:
        raise ControlError(409, "OPERATIONS_LEDGER", str(exc)) from None
    rows = grouped.get(operation_id)
    if rows is None or rows[0]["plan"].get("flow_id") != str(row["flow_id"]):
        raise portal_state.NotFound(f"no operation {operation_id} in this flow")
    shown = body.get("limits")
    planned = operations_view.summary(store, rows)["limits"]
    if not isinstance(shown, dict) or shown != planned:
        raise ControlError(409, "PLAN_DIFFERS",
                           "the limits sent are not this plan's limits; read the plan again "
                           "before authorizing it")
    already = len(rows) > 1 and rows[1]["event"] == "authorized"
    try:
        recorded = operations.authorize(store, operation_id, identity={
            "signer_auth": "portal-session", "operator": session.operator_id,
            "name": session.operator_name})
    except operations.OperationError as exc:
        raise ControlError(409, "REFUSED", str(exc)) from None
    return {"authorized": recorded, "already_authorized": already}, 200 if already else 201


def _batches_list(self: _Handler, params: dict[str, str], query: Any,
                  body: dict[str, Any]) -> tuple[Any, int]:
    self._require_session()
    _project, store, row, _selector = _flow_only(self, params)
    try:
        batches = operations_view.batches_for_flow(store, str(row['flow_id']))
    except operations.OperationError as exc:
        raise ControlError(409, 'OPERATIONS_LEDGER', str(exc)) from None
    return {'flow_id': str(row['flow_id']), 'batches': batches}, 200


def _batch_authorize(self: _Handler, params: dict[str, str], query: Any,
                     body: dict[str, Any]) -> tuple[Any, int]:
    """Authorize exactly the batch and total request ceiling the operator saw."""
    self._only_keys(body, frozenset({'operation_ids', 'max_total_requests'}))
    session = self._require_session()
    _project, store, row, _selector = _flow_only(self, params)
    try:
        batch = next((item for item in operations_view.batches_for_flow(
            store, str(row['flow_id'])) if item['batch_id'] == params['batch_id']), None)
    except operations.OperationError as exc:
        raise ControlError(409, 'OPERATIONS_LEDGER', str(exc)) from None
    if batch is None:
        raise portal_state.NotFound(f"no batch {params['batch_id']} in this flow")
    if (not isinstance(body.get('operation_ids'), list) or
            type(body.get('max_total_requests')) is not int or
            body.get('operation_ids') != batch['operation_ids'] or
            body.get('max_total_requests') != batch['max_total_requests']):
        raise ControlError(409, 'PLAN_DIFFERS',
                           'the batch differs from what was read; read it again before authorizing')
    try:
        recorded = operations.authorize_batch(store, batch['batch_id'], identity={
            'signer_auth': 'portal-session', 'operator': session.operator_id,
            'name': session.operator_name})
    except operations.OperationError as exc:
        raise ControlError(409, 'REFUSED', str(exc)) from None
    return {'batch': recorded}, 201 if recorded['authorized_now'] else 200


def _operation_not_built(self: _Handler, params: dict[str, str], query: Any,
                         body: dict[str, Any]) -> tuple[Any, int]:
    self._require_session()
    raise ControlError(
        501, "NOT_IMPLEMENTED",
        "pause and resume need a stopping event the scheduler's operation ledger does not accept "
        "yet; appending one would make the ledger invalid. They belong to the scheduler track")


for _name, _function in (("_operations_list", _operations_list),
                         ("_batches_list", _batches_list),
                         ("_batch_authorize", _batch_authorize),
                         ("_operation_authorize", _operation_authorize),
                         ("_operation_not_built", _operation_not_built),
                         ("_admin_read", _admin_read), ("_admin_check", _admin_check),
                         ("_admin_credential", _admin_credential),
                         ("_admin_paid_test", _admin_paid_test),
                         ("_export_create", _export_create), ("_export_verify", _export_verify),
                         ("_today", _today), ("_seen", _seen),
                         ("_identity_resolve", _identity_resolve),
                         ("_decisions_list", _decisions_list),
                         ("_retry_preview", _retry_preview), ("_retry_approve", _retry_approve),
                         ("_decision_state", _decision_state), ("_offer_record", _offer_record),
                         ("_offer_stage", _offer_stage)):
    setattr(_Handler, _name, _function)


_Handler._intake_file = _intake_file      # type: ignore[attr-defined]
_Handler._intake_submit = _intake_submit  # type: ignore[attr-defined]
_Handler._intake_list = _intake_list      # type: ignore[attr-defined]
_Handler._adjudicate = _adjudicate      # type: ignore[attr-defined]
_Handler._draft_save = _draft_save      # type: ignore[attr-defined]
_Handler._draft_read = _draft_read      # type: ignore[attr-defined]


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
                state_dir: str | pathlib.Path | None = None,
                resolver: Any = None, extract_text: Any = None, http_get: Any = None,
                env_file: str | pathlib.Path | None = None) -> ThreadingHTTPServer:
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
        "idempotency": Idempotency(),
        "resolver": staticmethod(resolver) if resolver is not None else None,
        "extract_text": staticmethod(extract_text) if extract_text is not None else None,
        "http_get": staticmethod(http_get) if http_get is not None else None,
        # `none` turns credential writes off: in a container `.env` belongs to the host, and the
        # deployment says so rather than writing a copy nobody reads.
        "env_file": (None if str(env_file) == "none" else pathlib.Path(env_file))
        if env_file is not None else pathlib.Path(projects_dir).resolve().parent / ".env",
        "started_at": _now_iso(),
    })
    httpd = ThreadingHTTPServer((host, port), handler)
    handler.bind_port = int(httpd.server_address[1])
    return httpd


def serve(projects_dir: str | pathlib.Path = "projects",
          store_dir: str | pathlib.Path = "store", *, host: str = "127.0.0.1",
          port: int = 8790, allow_hosts: tuple[str, ...] = (),
          state_dir: str | pathlib.Path | None = None,
          env_file: str | pathlib.Path | None = None) -> None:
    """Block and serve the control API."""
    httpd = make_server(projects_dir, store_dir, host=host, port=port,
                        allow_hosts=allow_hosts, state_dir=state_dir, env_file=env_file)
    print(f"claimstone control — http://{host}:{port}/control/v1/session  "
          "(authenticated writes; Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
