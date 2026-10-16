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
import base64
import binascii
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
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
from typing import Any, Callable
import urllib.parse
from urllib.parse import unquote, urlparse

from claimstone import (account_service, admin, auth_events, autopilot, copy_policy, decisions,
                        drafts, export, flows, intake, network_schedule, new_project_service, operations,
                        net, operations_view, operators, periodic, periodic_export, portal_state, scope,
                        synthesize, today, worker_runtime)
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
SESSION_ABSOLUTE_SECONDS = 7 * 24 * 60 * 60   # a session never outlives a week, activity or not
ADDRESS_FAILURE_LIMIT = 20                    # failed logins per remote address per window

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
    session_id: str = ""
    role: str = "operator"
    method: str = "password"
    must_change_password: bool = False
    created_at: str = ""
    stamp: str = ""            # operators.stamp() of the credential this session was minted under


class Sessions:
    """In-memory sessions: an inactivity timeout and an absolute lifetime. No token ever touches
    a disk. `session_id` is public (listed to its owner); the token is the secret."""

    def __init__(self, idle_seconds: int = SESSION_IDLE_SECONDS,
                 absolute_seconds: int = SESSION_ABSOLUTE_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._idle = float(idle_seconds)
        self._absolute = float(absolute_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._expires: dict[str, float] = {}
        self._dies: dict[str, float] = {}
        self._rows: dict[str, Session] = {}
        self._seen: dict[str, str] = {}

    def _drop(self, token: str) -> None:
        for table in (self._expires, self._dies, self._rows, self._seen):
            table.pop(token, None)

    def create(self, operator_id: str, operator_name: str, *, role: str = "operator",
               method: str = "password", must_change: bool = False,
               stamp: str = "") -> tuple[str, Session]:
        """(cookie token, session). A new token every time: no session fixation."""
        token = secrets.token_hex(32)
        session = Session(operator_id, operator_name, secrets.token_hex(32),
                          session_id=secrets.token_hex(8), role=role, method=method,
                          must_change_password=must_change, created_at=_now_iso(), stamp=stamp)
        with self._lock:
            now = self._clock()
            for held in [t for t, until in self._expires.items()
                         if until <= now or self._dies[t] <= now]:
                self._drop(held)
            self._expires[token] = now + self._idle
            self._dies[token] = now + self._absolute
            self._rows[token] = session
            self._seen[token] = session.created_at
        return token, session

    def get(self, token: str) -> Session | None:
        """The session if both the idle window and the absolute lifetime still hold."""
        with self._lock:
            until = self._expires.get(token)
            if until is None:
                return None
            now = self._clock()
            if now > until or now > self._dies[token]:
                self._drop(token)
                return None
            self._expires[token] = now + self._idle   # activity refreshes the idle window only
            self._seen[token] = _now_iso()
            return self._rows[token]

    def end(self, token: str) -> None:
        with self._lock:
            self._drop(token)

    def clear_must_change(self, token: str) -> None:
        with self._lock:
            if token in self._rows:
                self._rows[token] = replace(self._rows[token], must_change_password=False)

    def set_stamp(self, token: str, stamp: str) -> None:
        """The current session of a person who just changed their own password stays valid."""
        with self._lock:
            if token in self._rows:
                self._rows[token] = replace(self._rows[token], stamp=stamp)

    def _prune_locked(self) -> None:
        """Forget sessions already past their idle window or absolute lifetime (lock held)."""
        now = self._clock()
        for token in [t for t, until in self._expires.items()
                      if now > until or now > self._dies[t]]:
            self._drop(token)

    def list_for(self, operator_id: str, current_token: str | None) -> list[dict[str, Any]]:
        with self._lock:
            self._prune_locked()
            return [{"session_id": s.session_id, "created_at": s.created_at,
                     "last_seen": self._seen.get(t, s.created_at), "method": s.method,
                     "current": t == current_token}
                    for t, s in self._rows.items() if s.operator_id == operator_id]

    def end_others(self, operator_id: str, keep_token: str | None) -> int:
        return self._end_where(operator_id, keep_token)

    def end_operator(self, operator_id: str) -> int:
        return self._end_where(operator_id, None)

    def _end_where(self, operator_id: str, keep: str | None) -> int:
        with self._lock:
            self._prune_locked()
            doomed = [t for t, s in self._rows.items() if s.operator_id == operator_id and t != keep]
            for token in doomed:
                self._drop(token)
            return len(doomed)


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

    def reserve(self, operator_id: str) -> bool:
        """Book a failure BEFORE the password is verified, atomically with the limit check: however
        many attempts run at once, no more than `limit` ever reach the verification. A success
        gives its booking back with `forgive`."""
        with self._lock:
            failures = self._failures.setdefault(operator_id, deque())
            self._prune(failures, self._clock())
            if len(failures) >= self._limit:
                return False
            failures.append(self._clock())
            return True

    def forgive(self, operator_id: str) -> None:
        """Remove the newest booked failure: the attempt that just succeeded."""
        with self._lock:
            failures = self._failures.get(operator_id)
            if failures:
                failures.pop()


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
    no_replay: bool = False    # carries a password: Idempotency-Key is ignored, never replayed


ROUTES: tuple[Route, ...] = (
    Route("POST", ("session",), "_session_create", public=True),
    Route("GET", ("session",), "_session_read"),
    Route("POST", ("session", "end"), "_session_end"),
    Route("GET", ("session", "options"), "_session_options", public=True),
    # Accounts: a person's own password and sessions; then the admin's people routes. Every route
    # that takes a password is `no_replay`: an answer to a password is never kept in memory.
    Route("GET", ("account",), "_account_read"),
    Route("POST", ("account", "password"), "_account_password", no_replay=True),
    Route("GET", ("account", "sessions"), "_account_sessions"),
    Route("POST", ("account", "sessions", "end-others"), "_account_end_others"),
    Route("GET", ("people",), "_people_list"),
    Route("POST", ("people",), "_people_create", no_replay=True),
    Route("POST", ("people", "{person_id}", "password"), "_people_password", no_replay=True),
    Route("POST", ("people", "{person_id}", "disable"), "_people_disable", no_replay=True),
    Route("POST", ("people", "{person_id}", "enable"), "_people_enable", no_replay=True),
    Route("POST", ("people", "{person_id}", "email"), "_people_email", no_replay=True),
    Route("POST", ("people", "{person_id}", "role"), "_people_role", no_replay=True),
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
    Route("POST", ("admin", "credential"), "_admin_credential", no_replay=True),
    Route("POST", ("admin", "paid-test"), "_admin_paid_test"),
    # B12: the scheduler's operations. Planning stays with the scheduler and the CLI.
    Route("GET", ("p", "{project}", "flows", "{flow_id}", "operations"), "_operations_list"),
    Route("GET", ("p", "{project}", "flows", "{flow_id}", "batches"), "_batches_list"),
    Route("GET", ("p", "{project}", "flows", "{flow_id}", "acquire-hosts"), "_acquire_hosts"),
    Route("POST", ("p", "{project}", "flows"), "_flow_start"),
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "batches"), "_batch_plan"),
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "batches", "{batch_id}",
                   "authorize"), "_batch_authorize"),
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "operations", "{operation_id}",
                   "authorize"), "_operation_authorize"),
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "operations", "{operation_id}",
                   "pause"), "_operation_not_built"),
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "operations", "{operation_id}",
                   "resume"), "_operation_not_built"),
    # Finite scheduler permissions and one shared local cap for dated child flows.
    Route("GET", ("p", "{project}", "scheduler"), "_scheduler_index"),
    Route("POST", ("p", "{project}", "periodic-plans"), "_periodic_plan"),
    Route("GET", ("p", "{project}", "schedules", "{schedule_id}"), "_schedule_read"),
    Route("POST", ("p", "{project}", "schedules", "{schedule_id}", "authorize"),
          "_schedule_authorize"),
    Route("POST", ("p", "{project}", "schedules", "{schedule_id}", "revoke"),
          "_schedule_revoke"),
    Route("POST", ("p", "{project}", "schedules", "{schedule_id}", "export"),
          "_periodic_export_create"),
    Route("GET", ("p", "{project}", "periodic-exports", "{export_id}"),
          "_periodic_export_read"),
    Route("GET", ("p", "{project}", "periodic-exports", "{export_id}", "download"),
          "_periodic_export_download"),
    Route("POST", ("p", "{project}", "periodic-exports", "{export_id}", "verify"),
          "_periodic_export_verify"),
    Route("POST", ("p", "{project}", "copy-policies"), "_copy_policy_plan"),
    Route("GET", ("p", "{project}", "copy-policies", "{policy_id}"),
          "_copy_policy_read"),
    Route("POST", ("p", "{project}", "copy-policies", "{policy_id}", "authorize"),
          "_copy_policy_authorize"),
    Route("POST", ("p", "{project}", "copy-policies", "{policy_id}", "revoke"),
          "_copy_policy_revoke"),
    Route("GET", ("p", "{project}", "local-mandates", "{mandate_id}"),
          "_local_mandate_read"),
    Route("POST", ("p", "{project}", "local-mandates", "series"),
          "_local_mandate_series"),
    Route("POST", ("p", "{project}", "flows", "{flow_id}", "local-mandates"),
          "_local_mandate_single"),
    Route("POST", ("p", "{project}", "local-mandates", "{mandate_id}", "disable"),
          "_local_mandate_disable"),
    # New project: drafts, preview and creation. Nothing here starts a stage or any request; the
    # only write outside `store/` is `project_builder.create_project`, which creates one directory.
    Route("POST", ("new",), "_new_start"),
    Route("GET", ("new",), "_new_list"),
    Route("GET", ("new-templates",), "_new_templates"),
    Route("GET", ("new-templates", "{template_id}"), "_new_template"),
    Route("GET", ("new", "{draft_id}"), "_new_read"),
    Route("POST", ("new", "{draft_id}", "steps", "{step}"), "_new_step"),
    Route("POST", ("new", "{draft_id}", "advanced"), "_new_advanced"),
    Route("GET", ("new", "{draft_id}", "preview"), "_new_preview"),
    Route("POST", ("new", "{draft_id}", "discard"), "_new_discard"),
    Route("POST", ("new", "{draft_id}", "create"), "_new_create"),
)


class ControlError(Exception):
    """A route's named answer: the status, the envelope code and the message. `details` is an
    optional list of `{path, message}` for a 422 that names form fields."""

    def __init__(self, status: int, code: str, message: str,
                 details: list[dict[str, str]] | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


# --- the handler ----------------------------------------------------------------------------------


class _Handler(BaseHandler):
    """POST support and sessions on the shared transport base. The base stays
    GET-only; every non-GET verb this server answers is routed here."""

    csp = CSP

    sessions: Sessions
    login_budget: LoginBudget
    address_budget: LoginBudget
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
    # Google sign-in, once configured (Task 7 sets it); None answers `{"google": false}`.
    google: Any = None
    # Trust X-Real-IP for the address budget. Only for a server whose single peer is the proxy.
    trust_forwarded: bool = False
    # At most this many scrypt derivations (32 MiB each) at once on the unauthenticated path.
    verify_slots: Any = threading.BoundedSemaphore(4)

    # While a person must set a new password, only these (and the public routes) answer.
    ALLOWED_WHILE_CHANGING = frozenset({"_session_read", "_session_end", "_account_password",
                                        "_session_options", "_account_read"})

    # --- responses, with the read API's envelope ------------------------------------------------

    def _respond(self, body: bytes, code: int, content_type: str,
                 cookies: tuple[str, ...] = (), download_name: str | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", self.csp)
        if download_name is not None:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
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
               cookies: tuple[str, ...] = (), details: list[dict[str, str]] | None = None) -> None:
        envelope: dict[str, Any] = {"code": name, "message": message}
        if details:
            envelope["details"] = details
        self._json({"error": envelope}, code=code, cookies=cookies)

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
                session = self._require_session()  # authenticated reads: 401 before the route
                self._guard_change_required(route, session)
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
                session = self._require_session()  # §1.3 order: session first, then CSRF
                self._require_origin()
                self._require_csrf()
                self._guard_change_required(route, session)
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
        if route.no_replay:
            # A body that carries a password is neither fingerprinted nor kept: a replay would
            # answer a password change or a re-authentication without checking anything.
            key = None
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
            self._error(exc.status, exc.code, exc.message, details=exc.details)
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
        # Revocation is durable: the ledger is read at every request, so a disable, a password
        # change or a reset made by ANY process (the CLI included) ends the session here, and so
        # does a login that verified an old credential and created its session after the change.
        person = operators.load(self.state_dir).get(session.operator_id)
        if person is None or operators.stamp(person) != session.stamp:
            self.sessions.end(token)
            raise ControlError(401, "UNAUTHORIZED", "no session")
        return session

    def _guard_change_required(self, route: Route, session: Session) -> None:
        """A session that must change its password reaches only the routes that let it."""
        if route.public or route.handler in self.ALLOWED_WHILE_CHANGING:
            return
        if session.must_change_password:
            raise ControlError(403, "PASSWORD_CHANGE_REQUIRED", "set a new password first")

    def _verify(self, row: dict[str, Any], password: str) -> bool:
        """`operators.verify`, bounded: a flood of logins cannot run unbounded scrypt at once."""
        if not self.verify_slots.acquire(timeout=5):
            raise ControlError(429, "RATE_LIMITED", "busy, try again")
        try:
            return operators.verify(row, password)
        finally:
            self.verify_slots.release()

    def _remote(self) -> str:
        """The address the budgets key on: the peer's, or — only behind a proxy that overwrites
        X-Real-IP, and only with `trust_forwarded` — the address that header names."""
        if self.trust_forwarded:
            claimed = (self.headers.get("X-Real-IP") or "").strip()
            try:
                return str(ipaddress.ip_address(claimed))
            except ValueError:
                pass
        return str(self.client_address[0])

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
        remote = self._remote()
        # Book the failure first, atomically with the limit check, and give it back on success:
        # concurrent attempts cannot all slip under the limit before any has failed.
        if not self.address_budget.reserve(remote):
            auth_events.record(self.state_dir, "login_blocked", id=operator_id,
                               method="password", remote=remote)
            raise ControlError(429, "RATE_LIMITED", "too many failed logins; wait 15 minutes")
        if not self.login_budget.reserve(operator_id):
            self.address_budget.forgive(remote)
            auth_events.record(self.state_dir, "login_blocked", id=operator_id,
                               method="password", remote=remote)
            raise ControlError(429, "RATE_LIMITED", "too many failed logins; wait 15 minutes")
        row = operators.load(self.state_dir).get(operator_id)
        if len(password) > operators.PASSWORD_MAX:
            verified = False   # no password that long exists: refuse before paying for scrypt
        else:
            # An unknown id still pays for one scrypt derivation, so response time does not
            # reveal which ids exist.
            verified = self._verify(row if row is not None else operators.DUMMY_ROW, password)
        if row is None or not verified:
            # One sentence for an unknown id and a wrong password alike: which of the
            # two failed is not the caller's business. The failure is already booked.
            auth_events.record(self.state_dir, "login_failed", id=operator_id,
                               method="password", remote=remote)
            raise ControlError(401, "UNAUTHORIZED", BAD_LOGIN_TEXT)
        self.login_budget.forgive(operator_id)
        self.address_budget.forgive(remote)
        token, session = self.sessions.create(str(row["id"]), str(row.get("name") or ""),
                                              role=str(row["role"]), method="password",
                                              must_change=bool(row["must_change_password"]),
                                              stamp=operators.stamp(row))
        auth_events.record(self.state_dir, "login_ok", id=session.operator_id,
                           method="password", remote=remote)
        self._json({"operator": _operator_view(session), "csrf_token": session.csrf_token},
                   cookies=(self._session_cookie(token),))

    def _session_read(self, params: dict[str, str], query: Any,
                      body: dict[str, Any]) -> None:
        session = self._require_session()
        person = operators.load(self.state_dir).get(session.operator_id) or {}
        view = {**_operator_view(session), "role": person.get("role", session.role)}
        self._json({"operator": view, "csrf_token": session.csrf_token})

    def _session_options(self, params: dict[str, str], query: Any,
                         body: dict[str, Any]) -> None:
        self._json({"google": bool(self.google)})

    def _session_end(self, params: dict[str, str], query: Any,
                     body: dict[str, Any]) -> None:
        self._only_keys(body, frozenset())
        session = self._require_csrf()
        token = self._session_token()
        if token:
            self.sessions.end(token)
        auth_events.record(self.state_dir, "logout", id=session.operator_id,
                           remote=self._remote())
        self._json({"ended": True},
                   cookies=(self._session_cookie("", expire=True),))


def _operator_view(session: Session) -> dict[str, Any]:
    return {"id": session.operator_id, "name": session.operator_name, "role": session.role,
            "must_change_password": session.must_change_password}


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
    service. Nothing is contacted to answer this.

    2026-10-12: the B11 routes are open to every operator. An admin differs from an operator in one
    thing only: creating, disabling and otherwise managing people (`/people`)."""
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


def _reauth(self: _Handler, session: Session, password: object) -> None:
    """The password again, on the login's own budget: no side door for guessing. The attempt is
    booked as a failure before it is verified and given back if it matches."""
    if not self.login_budget.reserve(session.operator_id):
        raise ControlError(429, "RATE_LIMITED", "too many failed attempts; wait 15 minutes")
    row = operators.load(self.state_dir).get(session.operator_id)
    if (isinstance(password, str) and len(password) <= operators.PASSWORD_MAX
            and row is not None and self._verify(row, password)):
        self.login_budget.forgive(session.operator_id)
        return
    auth_events.record(self.state_dir, "reauth_failed", id=session.operator_id,
                       remote=self._remote())
    raise ControlError(403, "REAUTH", "the password is required again, and it did not match")


def _admin_credential(self: _Handler, params: dict[str, str], query: Any,
                      body: dict[str, Any]) -> tuple[Any, int]:
    """Replace one credential, with the password asked again (spec B11). A wrong password counts
    against the same budget as a failed login, so this route is no side door for guessing."""
    self._only_keys(body, frozenset({"name", "value", "password"}))
    session = self._require_session()
    _reauth(self, session, body.get("password"))
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


_ROUND_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _flow_start(self: _Handler, params: dict[str, str], query: Any,
                body: dict[str, Any]) -> tuple[Any, int]:
    """Bind a named round to the project's protocol: the first act of a research flow.

    It records a binding and, for a project that declares a population, freezes that population
    for the round. It sends no request; a flow with no candidates is an empty scope, not a
    closed cohort."""
    _required_body(self, body, {'title', 'round'})
    title, round_name = body['title'], body['round']
    if not isinstance(title, str) or not title.strip() or len(title) > 120:
        raise ControlError(422, 'VALIDATION', 'title must be 1 to 120 characters')
    if not isinstance(round_name, str) or not _ROUND_NAME.match(round_name):
        raise ControlError(422, 'VALIDATION',
                           'round must be 1 to 64 letters, digits, dots, dashes or underscores, '
                           'starting with a letter or digit')
    project, store = _scheduler_context(self, params)
    try:
        row, created = flows.create(project, store, selector=scope.Selector(round_name, False),
                                    title=title.strip())
    except (ValueError, ConfigError) as exc:
        raise ControlError(409, 'REFUSED', str(exc)) from None
    return {'flow_id': row['flow_id'], 'created': created, 'title': row.get('title'),
            'round': round_name}, 201 if created else 200


def _acquire_hosts(self: _Handler, params: dict[str, str], query: Any,
                   body: dict[str, Any]) -> tuple[Any, int]:
    """The hosts an `acquire` plan for this flow would need, read from what is recorded: the hosts
    of the URLs of candidates not yet attempted, and the hosts earlier attempts were refused at
    because the plan did not list them. A suggestion, never a grant: the person edits the list and
    the plan still needs its own authorization. Hosts the project excludes are never suggested."""
    self._require_session()
    project, store, _row, selector = _flow_only(self, params)
    attempted = store.latest_by('acquisitions.jsonl', 'candidate_key')
    excluded = tuple(project.excluded_hosts)

    def allowed(host: str) -> bool:
        return bool(host) and not any(host == h or host.endswith('.' + h) for h in excluded)

    pending = [row for key, row in scope.candidates(store, selector).items()
               if key not in attempted and row.get('source_class')
               and str(row.get('url') or '').startswith(('http://', 'https://'))
               and allowed(net.host_of(str(row['url'])))]
    from_candidates: dict[str, int] = {}
    for row in pending:
        host = net.host_of(str(row['url']))
        if allowed(host):
            from_candidates[host] = from_candidates.get(host, 0) + 1
    refused: dict[str, set[str]] = {}
    for key, acquisition in attempted.items():
        for attempt in acquisition.get('attempts') or []:
            detail = str(attempt.get('detail') or '')
            if attempt.get('failure_class') == net.EXCLUDED and detail.endswith(' is outside this plan'):
                host = detail.split(' ', 1)[0].lower()
                if allowed(host):
                    refused.setdefault(host, set()).add(key)
    in_scope = scope.candidates(store, selector)
    retryable: dict[str, int] = {}
    for key, acquisition in attempted.items():
        failure = acquisition.get('failure_class')
        if key in in_scope and failure in net.TERMINAL and allowed(net.host_of(str(in_scope[key].get('url') or ''))):
            retryable[failure] = retryable.get(failure, 0) + 1
    # A plain-http URL spends one request on the redirect to https before the document; a
    # candidate that already hit the ceiling says the same. Both are recorded facts.
    plain_http = sum(str(row['url']).startswith('http://') for row in pending)
    limit_hit = retryable.get(net.REQUEST_LIMIT, 0)
    return {'pending_candidates': len(pending),
            'candidate_hosts': [{'host': host, 'candidates': n}
                                for host, n in sorted(from_candidates.items())],
            'refused_hosts': [{'host': host, 'candidates': len(keys)}
                              for host, keys in sorted(refused.items())],
            'retryable_classes': [{'failure_class': name, 'candidates': n}
                                  for name, n in sorted(retryable.items())],
            'plain_http_candidates': plain_http,
            'suggested_max_requests_each': 5 if (plain_http or limit_hit) else 3}, 200


def _batch_plan(self: _Handler, params: dict[str, str], query: Any,
                body: dict[str, Any]) -> tuple[Any, int]:
    """Freeze a bounded set of one-query or one-candidate plans, in the `planned` state.

    Planning executes nothing and asks no host anything; the batch still needs the separate,
    exact authorization of a person before any worker may start it."""
    use_apis = body.get('use_apis', False)
    if type(use_apis) is not bool:
        raise ControlError(422, 'VALIDATION', 'use_apis must be true or false')
    retry_classes = body.get('retry_classes')
    retry_reason = body.get('retry_reason')
    if retry_classes is not None:
        if body.get('stage') != 'acquire':
            raise ControlError(422, 'VALIDATION', 'retry applies only to acquire')
        retry_classes = _strings(retry_classes, 'retry_classes')
        if not isinstance(retry_reason, str) or not retry_reason.strip() or len(retry_reason) > 400:
            raise ControlError(422, 'VALIDATION', 'a retry needs a stated reason (1-400 characters)')
    elif retry_reason is not None:
        raise ControlError(422, 'VALIDATION', 'retry_reason without retry_classes')
    _required_body(self, {key: value for key, value in body.items()
                          if key not in {'use_apis', 'retry_classes', 'retry_reason'}},
                   {'stage', 'apis', 'allowed_hosts', 'max_units', 'max_requests_each', 'per_query'})
    if body['stage'] not in {'discover', 'acquire'}:
        raise ControlError(422, 'VALIDATION', 'stage must be discover or acquire')
    if use_apis and body['stage'] != 'acquire':
        raise ControlError(422, 'VALIDATION', 'use_apis applies only to acquire')
    apis = body['apis'] if body['stage'] == 'discover' else []
    if body['stage'] == 'discover':
        apis = _strings(body['apis'], 'apis')
    hosts = _strings(body['allowed_hosts'], 'allowed_hosts')
    project, store, row, _selector = _flow_only(self, params)
    try:
        result = operations.plan_batch(
            project, store, str(row['flow_id']), body['stage'], apis=apis, allowed_hosts=hosts,
            max_units=_integer(body['max_units'], 'max_units'),
            max_requests_each=_integer(body['max_requests_each'], 'max_requests_each'),
            per_query=_integer(body['per_query'], 'per_query'), use_apis=use_apis,
            retry_classes=retry_classes, retry_reason=retry_reason)
    except operations.OperationError as exc:
        raise _scheduler_refusal(exc) from None
    return result, 201


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


def _scheduler_context(self: _Handler, params: dict[str, str]) -> tuple[Any, Store]:
    project, store, _root = self._loaded(params['project'])
    return project, store


def _operator_identity(self: _Handler) -> dict[str, str]:
    session = self._require_session()
    return {'signer_auth': 'portal-session', 'operator': session.operator_id,
            'name': session.operator_name}


def _scheduler_refusal(exc: operations.OperationError) -> ControlError:
    return ControlError(409, 'REFUSED', str(exc))


def _required_body(self: _Handler, body: dict[str, Any], fields: set[str]) -> None:
    self._only_keys(body, frozenset(fields))
    if set(body) != fields:
        raise ControlError(422, 'VALIDATION',
                           'required fields: ' + ', '.join(sorted(fields)))


def _strings(value: Any, name: str) -> list[str]:
    if (not isinstance(value, list) or not value or
            any(not isinstance(item, str) or not item for item in value)):
        raise ControlError(422, 'VALIDATION', f'{name} must be a nonempty list of strings')
    return value


def _integer(value: Any, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ControlError(422, 'VALIDATION', f'{name} must be a positive integer')
    return value


def _scheduler_index(self: _Handler, params: dict[str, str], query: Any,
                     body: dict[str, Any]) -> tuple[Any, int]:
    project, store = _scheduler_context(self, params)
    try:
        keys = {'schedules': sorted(network_schedule._read(store)),
                'copy_policies': sorted(copy_policy._read(store)),
                'local_mandates': sorted(autopilot._rows(store))}
        requested = urllib.parse.parse_qs(urlparse(self.path).query, keep_blank_values=True)
        if set(requested) - {'limit', 'cursor'} or any(len(v) != 1 for v in requested.values()):
            raise ControlError(400, 'BAD_REQUEST', 'scheduler accepts only one limit and cursor')
        raw_limit = (requested.get('limit') or ['25'])[0]
        if not raw_limit.isdigit() or not 1 <= int(raw_limit) <= 100:
            raise ControlError(400, 'BAD_REQUEST', 'limit must be 1-100')
        limit = int(raw_limit)
        revision = operations._digest(keys)
        offset = 0
        if 'cursor' in requested:
            try:
                token = requested['cursor'][0]
                if len(token) > 256:
                    raise ValueError('long cursor')
                decoded = json.loads(base64.urlsafe_b64decode(token + '=' * (-len(token) % 4)))
                if (not isinstance(decoded, dict) or set(decoded) != {'revision', 'offset'} or
                        type(decoded['offset']) is not int or decoded['offset'] < 0 or
                        not isinstance(decoded['revision'], str)):
                    raise ValueError('invalid cursor')
            except (ValueError, UnicodeError, TypeError, binascii.Error) as exc:
                raise ControlError(400, 'BAD_REQUEST', 'invalid scheduler cursor') from exc
            if decoded['revision'] != revision:
                raise ControlError(409, 'ARCHIVE_CHANGED', 'scheduler archive changed; restart paging')
            offset = decoded['offset']
        selected = {name: values[offset:offset + limit] for name, values in keys.items()}
        schedules = [network_schedule.status(store, key) for key in selected['schedules']]
        policies = [copy_policy.status(store, key) for key in selected['copy_policies']]
        mandates = [autopilot.status(store, key) for key in selected['local_mandates']]
    except operations.OperationError as exc:
        raise _scheduler_refusal(exc) from None
    next_offset = offset + limit
    has_more = any(len(values) > next_offset for values in keys.values())
    next_cursor = (base64.urlsafe_b64encode(json.dumps(
        {'revision': revision, 'offset': next_offset}, sort_keys=True).encode('utf-8'))
        .decode('ascii').rstrip('=') if has_more else None)
    return {'project': project.name, 'schedules': schedules,
            'copy_policies': policies, 'local_mandates': mandates,
            'workers': {'supervisor': worker_runtime.status(
                            Store('_installation', base=store.root.parent), 'supervisor'),
                        'operations': worker_runtime.status(store, 'operations'),
                        'mandates': {row['mandate_id']: worker_runtime.status(
                            store, row['mandate_id']) for row in mandates}},
            'archive': {'limit': limit, 'offset': offset, 'total': {
                name: len(values) for name, values in keys.items()},
                'revision': revision, 'next_cursor': next_cursor}}, 200


def _periodic_plan(self: _Handler, params: dict[str, str], query: Any,
                   body: dict[str, Any]) -> tuple[Any, int]:
    fields = {'source_flow_id', 'rounds', 'apis', 'allowed_hosts',
              'max_units_each', 'max_requests_each', 'per_query'}
    _required_body(self, body, fields)
    project, store = _scheduler_context(self, params)
    if (not isinstance(body['source_flow_id'], str) or
            not isinstance(body['rounds'], list) or
            any(not isinstance(row, dict) for row in body['rounds'])):
        raise ControlError(422, 'VALIDATION', 'source flow and dated rounds are required')
    apis = _strings(body['apis'], 'apis')
    hosts = _strings(body['allowed_hosts'], 'allowed_hosts')
    try:
        result = periodic.plan(
            project, store, body['source_flow_id'], body['rounds'],
            apis=apis, allowed_hosts=hosts,
            max_units_each=_integer(body['max_units_each'], 'max_units_each'),
            max_requests_each=_integer(body['max_requests_each'], 'max_requests_each'),
            per_query=_integer(body['per_query'], 'per_query'))
    except operations.OperationError as exc:
        raise _scheduler_refusal(exc) from None
    return result, 201


def _schedule_read(self: _Handler, params: dict[str, str], query: Any,
                   body: dict[str, Any]) -> tuple[Any, int]:
    project, store = _scheduler_context(self, params)
    try:
        result = network_schedule.status(store, params['schedule_id'])
    except operations.OperationError as exc:
        if str(exc) == 'unknown schedule':
            raise portal_state.NotFound('no such schedule') from None
        raise _scheduler_refusal(exc) from None
    if result['plan']['project'] != project.name:
        raise portal_state.NotFound('no such schedule in this project')
    return result, 200


def _schedule_authorize(self: _Handler, params: dict[str, str], query: Any,
                        body: dict[str, Any]) -> tuple[Any, int]:
    _required_body(self, body, {'plan_sha256', 'max_total_requests'})
    shown, _ = _schedule_read(self, params, query, {})
    if (type(body['max_total_requests']) is not int or
            body['plan_sha256'] != shown['schedule_id'] or
            body['max_total_requests'] != shown['plan']['max_total_requests']):
        raise ControlError(409, 'PLAN_DIFFERS', 'schedule hash or request ceiling changed')
    _project, store = _scheduler_context(self, params)
    try:
        result = network_schedule.authorize(store, shown['schedule_id'],
                                            identity=_operator_identity(self))
    except operations.OperationError as exc:
        raise _scheduler_refusal(exc) from None
    return result, 201 if shown['state'] == 'PLANNED' else 200


def _schedule_revoke(self: _Handler, params: dict[str, str], query: Any,
                     body: dict[str, Any]) -> tuple[Any, int]:
    _required_body(self, body, {'plan_sha256'})
    shown, _ = _schedule_read(self, params, query, {})
    if body['plan_sha256'] != shown['schedule_id']:
        raise ControlError(409, 'PLAN_DIFFERS', 'schedule hash changed')
    _project, store = _scheduler_context(self, params)
    try:
        result = network_schedule.revoke(store, shown['schedule_id'],
                                         identity=_operator_identity(self))
    except operations.OperationError as exc:
        raise _scheduler_refusal(exc) from None
    return result, 200


def _periodic_export_create(self: _Handler, params: dict[str, str], query: Any,
                            body: dict[str, Any]) -> tuple[Any, int]:
    _required_body(self, body, {'dossier_id'})
    shown, _ = _schedule_read(self, params, query, {})
    if not EXPORT_ID.fullmatch(str(body['dossier_id'])):
        raise ControlError(422, 'VALIDATION', 'dossier_id must be a SHA-256 identity')
    project, store = _scheduler_context(self, params)
    try:
        directory, created = periodic_export.create(
            project, store, shown['schedule_id'], dossier_id=body['dossier_id'],
            actor=self._require_session().operator_id)
    except operations.OperationError as exc:
        raise _scheduler_refusal(exc) from None
    return {'export_id': directory.name, 'schedule_id': shown['schedule_id'],
            'dossier_id': body['dossier_id'], 'created_now': created,
            'download': f'/control/v1/p/{project.name}/periodic-exports/{directory.name}/download'}, (
                201 if created else 200)


def _periodic_export_record(self: _Handler, params: dict[str, str]) -> tuple[Any, Store,
                                                                             dict[str, Any]]:
    project, store = _scheduler_context(self, params)
    export_id = params['export_id']
    if not EXPORT_ID.fullmatch(export_id):
        raise portal_state.NotFound('no such periodic export')
    row = next((row for row in store.read(periodic_export.LEDGER)
                if row.get('export_id') == export_id), None)
    if row is None or not (store.root / 'periodic_exports' / export_id / 'manifest.json').is_file():
        raise portal_state.NotFound('no such periodic export')
    return project, store, row


def _periodic_export_read(self: _Handler, params: dict[str, str], query: Any,
                          body: dict[str, Any]) -> tuple[Any, int]:
    _project, store, row = _periodic_export_record(self, params)
    manifest = json.loads((store.root / 'periodic_exports' / row['export_id'] /
                           'manifest.json').read_text(encoding='utf-8'))
    return {'export': row, 'manifest': manifest}, 200


def _periodic_export_download(self: _Handler, params: dict[str, str], query: Any,
                              body: dict[str, Any]) -> None:
    project, store, row = _periodic_export_record(self, params)
    problems = periodic_export.verify(project, store, row['export_id'])
    if problems:
        raise ControlError(409, 'EXPORT_INVALID', ', '.join(problems))
    directory = store.root / 'periodic_exports' / row['export_id']
    self._respond(periodic_export.archive(directory), 200, 'application/zip',
                  download_name=f'claimstone-{row["export_id"]}.zip')


def _periodic_export_verify(self: _Handler, params: dict[str, str], query: Any,
                            body: dict[str, Any]) -> tuple[Any, int]:
    _required_body(self, body, set())
    project, store, row = _periodic_export_record(self, params)
    problems = periodic_export.verify(project, store, row['export_id'])
    return {'export_id': row['export_id'], 'holds': not problems,
            'problems': problems}, 200


def _copy_policy_plan(self: _Handler, params: dict[str, str], query: Any,
                      body: dict[str, Any]) -> tuple[Any, int]:
    fields = {'schedule_id', 'allowed_hosts', 'source_classes', 'max_candidates',
              'max_requests_each', 'not_before', 'expires_at'}
    _required_body(self, body, fields)
    project, store = _scheduler_context(self, params)
    if any(not isinstance(body[name], str) for name in
           ('schedule_id', 'not_before', 'expires_at')):
        raise ControlError(422, 'VALIDATION', 'schedule ID and UTC window are required')
    try:
        result = copy_policy.plan(
            project, store, body['schedule_id'],
            allowed_hosts=_strings(body['allowed_hosts'], 'allowed_hosts'),
            source_classes=_strings(body['source_classes'], 'source_classes'),
            max_candidates=_integer(body['max_candidates'], 'max_candidates'),
            max_requests_each=_integer(body['max_requests_each'], 'max_requests_each'),
            not_before=body['not_before'], expires_at=body['expires_at'])
    except operations.OperationError as exc:
        raise _scheduler_refusal(exc) from None
    return result, 201


def _copy_policy_read(self: _Handler, params: dict[str, str], query: Any,
                      body: dict[str, Any]) -> tuple[Any, int]:
    project, store = _scheduler_context(self, params)
    try:
        result = copy_policy.status(store, params['policy_id'])
    except operations.OperationError as exc:
        if str(exc) == 'unknown copy policy':
            raise portal_state.NotFound('no such copy policy') from None
        raise _scheduler_refusal(exc) from None
    if result['policy']['project'] != project.name:
        raise portal_state.NotFound('no such copy policy in this project')
    return result, 200


def _copy_policy_authorize(self: _Handler, params: dict[str, str], query: Any,
                           body: dict[str, Any]) -> tuple[Any, int]:
    fields = {'policy_sha256', 'max_candidates', 'max_requests_each',
              'max_total_requests'}
    _required_body(self, body, fields)
    shown, _ = _copy_policy_read(self, params, query, {})
    policy = shown['policy']
    if (body['policy_sha256'] != shown['policy_id'] or
            any(type(body[name]) is not int or body[name] != policy[name] for name in
                ('max_candidates', 'max_requests_each', 'max_total_requests'))):
        raise ControlError(409, 'PLAN_DIFFERS', 'copy policy hash or limits changed')
    _project, store = _scheduler_context(self, params)
    try:
        result = copy_policy.authorize(store, shown['policy_id'],
                                       identity=_operator_identity(self))
    except operations.OperationError as exc:
        raise _scheduler_refusal(exc) from None
    return result, 201 if shown['state'] == 'PLANNED' else 200


def _copy_policy_revoke(self: _Handler, params: dict[str, str], query: Any,
                        body: dict[str, Any]) -> tuple[Any, int]:
    _required_body(self, body, {'policy_sha256'})
    shown, _ = _copy_policy_read(self, params, query, {})
    if body['policy_sha256'] != shown['policy_id']:
        raise ControlError(409, 'PLAN_DIFFERS', 'copy policy hash changed')
    _project, store = _scheduler_context(self, params)
    try:
        result = copy_policy.revoke(store, shown['policy_id'],
                                    identity=_operator_identity(self))
    except operations.OperationError as exc:
        raise _scheduler_refusal(exc) from None
    return result, 200


def _local_mandate_read(self: _Handler, params: dict[str, str], query: Any,
                        body: dict[str, Any]) -> tuple[Any, int]:
    project, store = _scheduler_context(self, params)
    try:
        result = autopilot.status(store, params['mandate_id'])
    except operations.OperationError as exc:
        if str(exc) == 'unknown local mandate':
            raise portal_state.NotFound('no such local mandate') from None
        raise _scheduler_refusal(exc) from None
    if result['mandate']['project'] != project.name:
        raise portal_state.NotFound('no such local mandate in this project')
    return result, 200


def _local_mandate_series(self: _Handler, params: dict[str, str], query: Any,
                          body: dict[str, Any]) -> tuple[Any, int]:
    fields = {'schedule_id', 'flow_ids', 'extract_model', 'review_model',
              'max_total_local_calls'}
    _required_body(self, body, fields)
    project, store = _scheduler_context(self, params)
    if not isinstance(body['schedule_id'], str):
        raise ControlError(422, 'VALIDATION', 'schedule_id is required')
    try:
        shown = network_schedule.status(store, body['schedule_id'])
    except operations.OperationError as exc:
        if str(exc) == 'unknown schedule':
            raise portal_state.NotFound('no such schedule') from None
        raise _scheduler_refusal(exc) from None
    if (shown['plan']['project'] != project.name or
            body['flow_ids'] != [entry['flow_id'] for entry in shown['plan']['entries']]):
        raise ControlError(409, 'PLAN_DIFFERS', 'schedule child flows changed')
    if (not isinstance(body['extract_model'], str) or
            not isinstance(body['review_model'], str) or
            type(body['max_total_local_calls']) is not int):
        raise ControlError(422, 'VALIDATION', 'models and call cap are required')
    try:
        result = autopilot.enable_series(
            project, store, body['schedule_id'],
            extract_model=body['extract_model'],
            review_model=body['review_model'],
            max_total_local_calls=body['max_total_local_calls'],
            identity=_operator_identity(self))
    except operations.OperationError as exc:
        raise _scheduler_refusal(exc) from None
    return result, 201


def _local_mandate_single(self: _Handler, params: dict[str, str], query: Any,
                          body: dict[str, Any]) -> tuple[Any, int]:
    fields = {'flow_id', 'extract_model', 'review_model', 'max_total_local_calls'}
    _required_body(self, body, fields)
    project, store, flow, _selector = _flow_only(self, params)
    if body['flow_id'] != flow['flow_id']:
        raise ControlError(409, 'PLAN_DIFFERS', 'flow ID changed')
    if (not isinstance(body['extract_model'], str) or
            not isinstance(body['review_model'], str) or
            type(body['max_total_local_calls']) is not int):
        raise ControlError(422, 'VALIDATION', 'models and call cap are required')
    try:
        result = autopilot.enable(
            project, store, flow['flow_id'],
            extract_model=body['extract_model'],
            review_model=body['review_model'],
            max_total_local_calls=body['max_total_local_calls'],
            identity=_operator_identity(self))
    except operations.OperationError as exc:
        raise _scheduler_refusal(exc) from None
    return result, 201


def _local_mandate_disable(self: _Handler, params: dict[str, str], query: Any,
                           body: dict[str, Any]) -> tuple[Any, int]:
    _required_body(self, body, {'mandate_id'})
    shown, _ = _local_mandate_read(self, params, query, {})
    if body['mandate_id'] != shown['mandate_id']:
        raise ControlError(409, 'PLAN_DIFFERS', 'local mandate ID changed')
    _project, store = _scheduler_context(self, params)
    try:
        result = autopilot.disable(store, shown['mandate_id'],
                                   identity=_operator_identity(self))
    except operations.OperationError as exc:
        raise _scheduler_refusal(exc) from None
    return result, 200


for _name, _function in (("_operations_list", _operations_list),
                         ("_scheduler_index", _scheduler_index),
                         ("_periodic_plan", _periodic_plan),
                         ("_schedule_read", _schedule_read),
                         ("_schedule_authorize", _schedule_authorize),
                         ("_schedule_revoke", _schedule_revoke),
                         ("_periodic_export_create", _periodic_export_create),
                         ("_periodic_export_read", _periodic_export_read),
                         ("_periodic_export_download", _periodic_export_download),
                         ("_periodic_export_verify", _periodic_export_verify),
                         ("_copy_policy_plan", _copy_policy_plan),
                         ("_copy_policy_read", _copy_policy_read),
                         ("_copy_policy_authorize", _copy_policy_authorize),
                         ("_copy_policy_revoke", _copy_policy_revoke),
                         ("_local_mandate_read", _local_mandate_read),
                         ("_local_mandate_series", _local_mandate_series),
                         ("_local_mandate_single", _local_mandate_single),
                         ("_local_mandate_disable", _local_mandate_disable),
                         ("_batches_list", _batches_list),
                         ("_batch_authorize", _batch_authorize),
                         ("_acquire_hosts", _acquire_hosts),
                         ("_flow_start", _flow_start),
                         ("_batch_plan", _batch_plan),
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


# --- new project ----------------------------------------------------------------------------------


def _revision(body: dict[str, Any]) -> int:
    value = body.get("base_revision")
    if type(value) is not int or value < 1:
        raise ControlError(422, "VALIDATION", "base_revision must be the draft's current revision")
    return value


def _new_call(self: _Handler, function: Callable[..., Any], *args: Any) -> tuple[Any, int]:
    session = self._require_session()
    try:
        return function(self.projects_dir, self.store_dir, session.operator_id,
                        self.code_revision, *args)
    except new_project_service.ServiceError as exc:
        raise ControlError(exc.status, exc.code, exc.message, exc.details) from None


def _new_start(self: _Handler, params: dict[str, str], query: Any,
               body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset())
    return _new_call(self, new_project_service.start)


def _new_list(self: _Handler, params: dict[str, str], query: Any,
              body: dict[str, Any]) -> tuple[Any, int]:
    return _new_call(self, new_project_service.list_drafts)


def _new_templates(self: _Handler, params: dict[str, str], query: Any,
                   body: dict[str, Any]) -> tuple[Any, int]:
    return _new_call(self, new_project_service.templates)


def _new_template(self: _Handler, params: dict[str, str], query: Any,
                  body: dict[str, Any]) -> tuple[Any, int]:
    return _new_call(self, new_project_service.template, params["template_id"])


def _new_read(self: _Handler, params: dict[str, str], query: Any,
              body: dict[str, Any]) -> tuple[Any, int]:
    return _new_call(self, new_project_service.read, params["draft_id"])


def _new_step(self: _Handler, params: dict[str, str], query: Any,
              body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset({"base_revision", "data"}))
    if not re.fullmatch(r"[1-3]", params["step"]):
        raise ControlError(404, "NOT_FOUND", "no such step")
    return _new_call(self, new_project_service.save_step, params["draft_id"],
                     int(params["step"]), _revision(body), body.get("data"))


def _new_advanced(self: _Handler, params: dict[str, str], query: Any,
                  body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset({"base_revision", "files"}))
    files = body.get("files")
    if not isinstance(files, dict) or any(not isinstance(v, str) for v in files.values()):
        raise ControlError(422, "VALIDATION", "files must map a file name to its text")
    return _new_call(self, new_project_service.save_advanced, params["draft_id"],
                     _revision(body), files)


def _new_preview(self: _Handler, params: dict[str, str], query: Any,
                 body: dict[str, Any]) -> tuple[Any, int]:
    return _new_call(self, new_project_service.preview, params["draft_id"])


def _new_discard(self: _Handler, params: dict[str, str], query: Any,
                 body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset({"base_revision"}))
    return _new_call(self, new_project_service.discard, params["draft_id"], _revision(body))


def _new_create(self: _Handler, params: dict[str, str], query: Any,
                body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset({"confirm", "protocol_sha256"}))
    shown = body.get("protocol_sha256")
    if body.get("confirm") is True and (not isinstance(shown, str) or not PROFILE_SHA.match(shown)):
        raise ControlError(422, "VALIDATION", "protocol_sha256 must be the digest the review page showed")
    return _new_call(self, new_project_service.create, params["draft_id"], body.get("confirm"), shown)


for _name, _function in (("_new_start", _new_start), ("_new_list", _new_list),
                         ("_new_templates", _new_templates), ("_new_template", _new_template),
                         ("_new_read", _new_read), ("_new_step", _new_step),
                         ("_new_advanced", _new_advanced), ("_new_preview", _new_preview),
                         ("_new_discard", _new_discard), ("_new_create", _new_create)):
    setattr(_Handler, _name, _function)


# --- accounts and people (operator login) -------------------------------------------------------


def _require_admin(self: _Handler) -> Session:
    """An admin by the LEDGER at this request, not by the role the session was minted with: a
    demoted or disabled admin loses the power at once."""
    session = self._require_session()
    row = operators.load(self.state_dir).get(session.operator_id)
    if row is None or row["role"] != "admin":
        raise ControlError(403, "FORBIDDEN", "this needs an admin")
    return session


def _account_call(function: Callable[..., Any], *args: Any) -> Any:
    try:
        return function(*args)
    except account_service.AccountError as exc:
        raise ControlError(exc.status, exc.code, exc.message) from None


def _account_read(self: _Handler, params: dict[str, str], query: Any,
                  body: dict[str, Any]) -> tuple[Any, int]:
    session = self._require_session()
    person = operators.load(self.state_dir).get(session.operator_id)
    if person is None:
        raise ControlError(401, "UNAUTHORIZED", "no session")
    return {"operator": {**_operator_view(session), "role": person["role"],
                         "email": person["email"],
                         "google_linked": bool(person["google_sub"])}}, 200


def _account_password(self: _Handler, params: dict[str, str], query: Any,
                      body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset({"current", "new"}))
    session = self._require_session()
    token = self._session_token()
    _reauth(self, session, body.get("current"))
    if body.get("new") == body.get("current"):
        raise ControlError(422, "VALIDATION", "choose a different password")
    _account_call(account_service.change_own_password, self.state_dir, session.operator_id,
                  body.get("new"))
    self.sessions.end_others(session.operator_id, token)
    self.sessions.clear_must_change(token)
    self.sessions.set_stamp(token, operators.stamp(operators.load(self.state_dir)[session.operator_id]))
    return {"changed": True}, 200


def _account_sessions(self: _Handler, params: dict[str, str], query: Any,
                      body: dict[str, Any]) -> tuple[Any, int]:
    session = self._require_session()
    return {"sessions": self.sessions.list_for(session.operator_id, self._session_token())}, 200


def _account_end_others(self: _Handler, params: dict[str, str], query: Any,
                        body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset())
    session = self._require_session()
    n = self.sessions.end_others(session.operator_id, self._session_token())
    auth_events.record(self.state_dir, "sessions_revoked", id=session.operator_id, detail=f"{n}")
    return {"ended": n}, 200


def _people_list(self: _Handler, params: dict[str, str], query: Any,
                 body: dict[str, Any]) -> tuple[Any, int]:
    _require_admin(self)
    return {"people": [account_service.public(p)
                       for p in operators.people(self.state_dir).values()]}, 200


def _people_create(self: _Handler, params: dict[str, str], query: Any,
                   body: dict[str, Any]) -> tuple[Any, int]:
    self._only_keys(body, frozenset({"password", "id", "name", "email", "role",
                                     "temporary_password"}))
    session = _require_admin(self)  # before the re-authentication: a non-admin cannot burn the budget
    _reauth(self, session, body.get("password"))
    person = _account_call(account_service.create_person, self.state_dir, session.operator_id, body)
    return {"person": person}, 201


def _people_act(action: str, keys: frozenset[str]) -> Callable[..., tuple[Any, int]]:
    def handler(self: _Handler, params: dict[str, str], query: Any,
                body: dict[str, Any]) -> tuple[Any, int]:
        self._only_keys(body, frozenset({"password"}) | keys)
        session = _require_admin(self)
        _reauth(self, session, body.get("password"))
        person, ends = _account_call(account_service.apply_to_person, self.state_dir,
                                     session.operator_id, params["person_id"], action, body)
        if ends:
            self.sessions.end_operator(params["person_id"])
        return ({"changed": True} if action == "password" else {"person": person}), 200
    return handler


for _name, _function in (("_account_read", _account_read),
                         ("_account_password", _account_password),
                         ("_account_sessions", _account_sessions),
                         ("_account_end_others", _account_end_others),
                         ("_people_list", _people_list), ("_people_create", _people_create),
                         ("_people_password", _people_act("password", frozenset({"new_password"}))),
                         ("_people_disable", _people_act("disable", frozenset())),
                         ("_people_enable", _people_act("enable", frozenset())),
                         ("_people_email", _people_act("email", frozenset({"email"}))),
                         ("_people_role", _people_act("role", frozenset({"role"})))):
    setattr(_Handler, _name, _function)


# --- the server -----------------------------------------------------------------------------------


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class _Server(ThreadingHTTPServer):
    request_queue_size = 128   # the default of 5 resets a burst of logins before the budget can answer


def make_server(projects_dir: str | pathlib.Path = "projects",
                store_dir: str | pathlib.Path = "store", *,
                host: str = "127.0.0.1", port: int = 8790,
                allow_hosts: tuple[str, ...] = (),
                state_dir: str | pathlib.Path | None = None,
                resolver: Any = None, extract_text: Any = None, http_get: Any = None,
                env_file: str | pathlib.Path | None = None,
                trust_forwarded: bool = False) -> ThreadingHTTPServer:
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
        "address_budget": LoginBudget(limit=ADDRESS_FAILURE_LIMIT),
        "idempotency": Idempotency(),
        "resolver": staticmethod(resolver) if resolver is not None else None,
        "extract_text": staticmethod(extract_text) if extract_text is not None else None,
        "http_get": staticmethod(http_get) if http_get is not None else None,
        # `none` turns credential writes off: in a container `.env` belongs to the host, and the
        # deployment says so rather than writing a copy nobody reads.
        "env_file": (None if str(env_file) == "none" else pathlib.Path(env_file))
        if env_file is not None else pathlib.Path(projects_dir).resolve().parent / ".env",
        "started_at": _now_iso(),
        "trust_forwarded": bool(trust_forwarded),
        "verify_slots": threading.BoundedSemaphore(4),
    })
    httpd = _Server((host, port), handler)
    handler.bind_port = int(httpd.server_address[1])
    return httpd


def serve(projects_dir: str | pathlib.Path = "projects",
          store_dir: str | pathlib.Path = "store", *, host: str = "127.0.0.1",
          port: int = 8790, allow_hosts: tuple[str, ...] = (),
          state_dir: str | pathlib.Path | None = None,
          env_file: str | pathlib.Path | None = None, trust_forwarded: bool = False) -> None:
    """Block and serve the control API."""
    httpd = make_server(projects_dir, store_dir, host=host, port=port,
                        allow_hosts=allow_hosts, state_dir=state_dir, env_file=env_file,
                        trust_forwarded=trust_forwarded)
    print(f"claimstone control — http://{host}:{port}/control/v1/session  "
          "(authenticated writes; Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
