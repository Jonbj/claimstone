"""`claimstone api`: the read-only JSON read model the portal frontend fetches (spec §3).

No HTML and no second opinion: every figure comes from `portal_state` over the live project
and ledgers, re-read on every request (F9). The wire rules — GET only, the security headers,
the Host/Origin defences with `--allow-host`, lookup-never-path parameters — are the shared
`transport.BaseHandler`. Every body, success or error, carries `api_version` (§3.1), and an
error is the §3.3 envelope, where a 500's message is the exception class name alone: a 500
never carries a body that could be read as data.
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from claimstone import flows, portal_state, round_state, scope
from claimstone.config import (ConfigError, RegistryDrift, check_registry_drift,
                               discover_projects, load_project)
from claimstone.store import LedgerCorrupt, Store
from claimstone.transport import LOOPBACK_HOSTS, BaseHandler

API_VERSION = 1

CSP = "default-src 'none'; frame-ancestors 'none'"

PREFIX = ("api", "v1")

MISDIRECTED_TEXT = "the Host header does not name this server"
CROSS_ORIGIN_TEXT = "the Origin header does not name this server"

DEFAULT_ACTIVITY_LIMIT = 50


def _one_query(query: dict[str, list[str]], name: str) -> str:
    """The single value of a required query parameter, or 400. A missing end of the diff
    is the caller's error, never a defaulted or empty comparison."""
    values = query.get(name)
    if not values or not values[0]:
        raise BadRequest(f"query parameter {name!r} is required")
    return values[0]


class BadRequest(ValueError):
    """A malformed query parameter: the caller's error, answered 400 BAD_REQUEST."""


class _Handler(BaseHandler):
    """JSON routing on the shared transport base: every `/api/v1` route of §3.2."""

    csp = CSP
    started_at: str  # set by make_server; the meta route reports when the server began

    # --- payloads ---------------------------------------------------------------

    def _payload(self, payload: dict[str, Any], code: int = 200) -> None:
        body = json.dumps({"api_version": API_VERSION, **payload}, ensure_ascii=False,
                          indent=1, default=str).encode("utf-8")
        self._send(body, code, "application/json; charset=utf-8")

    def _error(self, code: int, name: str, message: str) -> None:
        self._payload({"error": {"code": name, "message": message}}, code=code)

    # --- routing ------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - http.server's naming
        try:
            route = urlparse(self.path)
            query = parse_qs(route.query)
            if not self._host_ok():
                self._error(421, "MISDIRECTED", MISDIRECTED_TEXT)
                return
            if not self._origin_ok():
                self._error(403, "CROSS_ORIGIN", CROSS_ORIGIN_TEXT)
                return
            segments = [unquote(part) for part in route.path.split("/") if part]
            self._route(segments, query)
        except BrokenPipeError:
            pass
        except RegistryDrift as exc:  # a ConfigError subclass: the named state first
            self._error(409, "REGISTRY_DRIFT", str(exc))
        except ConfigError as exc:
            # ConfigError is a named state, never a crash (F9).
            self._error(409, "CONFIG_ERROR", str(exc))
        except BadRequest as exc:
            self._error(400, "BAD_REQUEST", str(exc))
        except portal_state.NotFound as exc:
            self._error(404, "NOT_FOUND", str(exc))
        except LedgerCorrupt as exc:
            self._error(500, "LEDGER_CORRUPT", str(exc))
        except Exception as exc:  # noqa: BLE001 - the class name alone, never the payload
            self._error(500, "INTERNAL", type(exc).__name__)

    def _route(self, segments: list[str], query: dict[str, list[str]]) -> None:
        if len(segments) < 2 or tuple(segments[:2]) != PREFIX:
            raise portal_state.NotFound("no such api route")
        rest = segments[2:]
        if rest == ["meta"]:
            self._payload({
                "code": {"revision": self.code_revision, "dirty": self.code_dirty},
                "instruments": portal_state.instrument_versions(),
                "started_at": self.started_at,
            })
            return
        if rest == ["admin"]:
            self._payload(portal_state.admin_state(
                pathlib.Path(self.projects_dir).resolve().parent))
            return
        if rest == ["projects"]:
            self._payload(self._projects())
            return
        if len(rest) >= 3 and rest[0] == "projects":
            name, section = rest[1], rest[2]
            if len(rest) == 3 and section == "integrity":
                project, store, root = self._loaded(name)
                self._payload({"project": name, **portal_state.integrity(
                    root, store, code_revision=self.code_revision,
                    code_dirty=self.code_dirty)})
                return
            if len(rest) == 3 and section == "activity":
                _project, store, _root = self._loaded(name)
                self._payload({"project": name,
                               "activity": round_state.activity(store, self._limit(query))})
                return
            if len(rest) == 3 and section == "poll":
                # Parity with the portal's poll: a cheap liveness signature needs no registry
                # check — drift changes no mtime (spec §3.2, cost: cheap).
                root = self._project_root(name)
                self._payload({"project": name,
                               **round_state.cheap_state(Store(root.name, base=self.store_dir))})
                return
            if len(rest) >= 5 and section in ("flows", "unbound"):
                project, store, _root = self._loaded(name)
                selector, flow_row = self._selector(store, section, rest[3])
                tail = rest[4:]
                if tail == ["summary"]:
                    self._payload(self._summary(project, store, selector, flow_row))
                elif tail == ["overview"]:
                    self._payload(portal_state.flow_overview(project, store, selector,
                                                             flow_row))
                elif tail == ["inbox"]:
                    self._payload({"cards": [dataclasses.asdict(card) for card in
                                             portal_state.inbox_cards(project, store,
                                                                      selector, flow_row)]})
                elif len(tail) == 2 and tail[0] == "questions":
                    self._payload(portal_state.question_detail(project, store, selector,
                                                               tail[1]))
                elif len(tail) == 3 and tail[0] == "questions" and tail[2] == "profile-diff":
                    # Both hashes are required: a diff without either end is not a diff.
                    from_sha = _one_query(query, "from")
                    to_sha = _one_query(query, "to")
                    self._payload(portal_state.profile_diff(project, store, selector,
                                                            tail[1], from_sha, to_sha))
                elif len(tail) == 2 and tail[0] == "claims":
                    self._payload(portal_state.lineage(project, store, selector, tail[1]))
                elif len(tail) == 2 and tail[0] == "sources":
                    self._payload(portal_state.source_dossier(project, store, selector,
                                                              tail[1]))
                else:
                    raise portal_state.NotFound("no such api route")
                return
        raise portal_state.NotFound("no such api route")

    # --- the routes' own readings ---------------------------------------------------

    @staticmethod
    def _limit(query: dict[str, list[str]]) -> int:
        raw = (query.get("limit") or [str(DEFAULT_ACTIVITY_LIMIT)])[0]
        try:
            return int(raw)
        except ValueError:
            # A malformed parameter is reported, never defaulted — and it is the caller's
            # error (400), not a missing resource (404).
            raise BadRequest(f"limit must be an integer: {raw!r}") from None

    def _selector(self, store: Store, kind: str,
                  value: str) -> tuple[scope.Selector, dict[str, Any] | None]:
        """The selector a route names: a bound flow's, or an unbound slug looked up among the
        selectors that exist — an invented round is a 404, never an empty payload."""
        if kind == "flows":
            row = self._flow(store, value)
            return portal_state._selector_of(row, scope.Selector(None)), row
        return portal_state.selector_from_slug(store, flows.flows(store).values(), value), None

    def _projects(self) -> dict[str, Any]:
        """The cheap project list (§3.2): config, registry, flows, unbound selectors — no
        `compute()` anywhere (A4), which is what lets the index render before the expensive
        per-selector summaries arrive."""
        projects: list[dict[str, Any]] = []
        for root in discover_projects(self.projects_dir):
            card: dict[str, Any] = {"name": root.name, "config": "OK", "config_error": None}
            try:
                project = load_project(root)
            except ConfigError as exc:
                # The broken project stays in the list: its state is data here, not an error
                # for the whole route.
                card.update(config="ConfigError", config_error=str(exc))
                projects.append(card)
                continue
            store = Store(root.name, base=self.store_dir)
            drift = None
            try:
                check_registry_drift(project, store, record=False)
            except RegistryDrift as exc:
                drift = str(exc)
            card["registry_version"] = project.registry_version
            card["registry_sha256"] = project.registry_sha256[:12]
            card["registry_drift"] = drift
            card["integrity_error"] = None
            try:
                flow_rows = flows.flows(store)
                flows_out: list[dict[str, Any]] = []
                for flow_id, row in sorted(flow_rows.items()):
                    selector = portal_state._selector_of(row, scope.Selector(None))
                    flows_out.append({
                        "flow_id": flow_id,
                        "title": row.get("title"),
                        "selector": selector.as_dict(),
                        "selector_label": portal_state.selector_label(selector),
                        "binding_state": flows.binding_state(project, store, row)["state"],
                        "bound_after_data": bool(row.get("bound_after_data")),
                    })
                unbound = [{
                    "slug": portal_state.selector_slug(selector),
                    "label": portal_state.selector_label(selector),
                    "selector": selector.as_dict(),
                } for selector in portal_state.unbound_selectors(store, flow_rows.values())]
            except LedgerCorrupt as exc:
                # One damaged store is this project's named state, never a 500 that empties the
                # list of every other project (implementation review of S2).
                flows_out, unbound = [], []
                card["integrity_error"] = f"LEDGER_CORRUPT: {exc}"
            card["flows"] = flows_out
            card["unbound_selectors"] = unbound
            projects.append(card)
        return {"projects": projects}

    def _summary(self, project: Any, store: Store, selector: scope.Selector,
                 flow_row: dict[str, Any] | None) -> dict[str, Any]:
        """The index card's numbers for one selector: floor status, verdict counts, inbox
        counts by category — from exactly one `compute()` (§3.2, cost: expensive)."""
        computed = portal_state.compute(project, store, selector)
        counts: dict[str, int] = {}
        for card in portal_state.inbox_cards(project, store, selector, flow_row, computed):
            counts[card.category] = counts.get(card.category, 0) + 1
        verdicts = computed.verdicts
        return {
            "project": project.name,
            "flow_id": flow_row["flow_id"] if flow_row is not None else None,
            "selector": selector.as_dict(),
            "selector_label": portal_state.selector_label(selector),
            "floor_status": (computed.admitted or {}).get("status"),
            "verdicts": None if verdicts is None else {
                "adjudicated": verdicts["adjudicated"], "stale": verdicts["stale"],
                "awaiting_adjudication": verdicts["awaiting_adjudication"]},
            "inbox_counts": counts,
        }


def make_server(projects_dir: str | pathlib.Path = "projects",
                store_dir: str | pathlib.Path = "store", *, host: str = "127.0.0.1",
                port: int = 8788, allow_hosts: tuple[str, ...] = ()) -> ThreadingHTTPServer:
    revision, dirty = flows._code_identity(pathlib.Path(projects_dir))
    # Inside a container git is absent; the image may carry the revision it was built from.
    if revision is None and os.environ.get("CLAIMSTONE_CODE_REVISION"):
        revision = os.environ["CLAIMSTONE_CODE_REVISION"]
    names = set(LOOPBACK_HOSTS)
    if host not in ("0.0.0.0", "::"):
        # A wildcard bind is not a name anyone should send as Host; it widens nothing.
        names.add(host)
    handler = type("ApiHandler", (_Handler,), {
        "projects_dir": pathlib.Path(projects_dir),
        "store_dir": pathlib.Path(store_dir),
        "allowed_hosts": frozenset(n.lower() for n in names),
        "allowed_authorities": frozenset(a.lower() for a in allow_hosts),
        "bind_port": int(port),
        "code_revision": revision,
        "code_dirty": dirty,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    httpd = ThreadingHTTPServer((host, port), handler)
    # With port 0 the real port exists only after the bind; the Host allowlist must know it.
    handler.bind_port = int(httpd.server_address[1])
    return httpd


def serve(projects_dir: str | pathlib.Path = "projects", store_dir: str | pathlib.Path = "store",
          *, host: str = "127.0.0.1", port: int = 8788,
          allow_hosts: tuple[str, ...] = ()) -> None:
    """Block and serve the JSON API, read-only."""
    print(f"claimstone api — http://{host}:{port}/api/v1/meta  (read-only JSON; Ctrl-C to stop)")
    httpd = make_server(projects_dir, store_dir, host=host, port=port, allow_hosts=allow_hosts)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
