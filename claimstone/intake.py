"""Operator-supplied material: a DOI, a link or a reference someone thinks belongs here (spec B7a).

`intake.jsonl` records what was proposed, where it was routed and why. A state change is a new row
with the same `intake_id`, never an edit. Nothing here counts toward any denominator, creates a
candidate, or runs a stage. Routing answers one question before anything is recorded as usable:
does this item add a work to the flow's population, or is it something the population already has?

The routing follows the engine's own notion of what is frozen (review F10). A round freezes its
population **predicate**, not its set: `discover` keeps adding candidates that match. Only the
curated manifest (`manifest_only`) has a fixed candidate set. So:

- an item matching a candidate already in the flow's scope by DOI or URL is a `DUPLICATE` of it;
- a match on folded title alone is a `POSSIBLE_VERSION` — the same work is likely, not established,
  and only a person decides identity (B8);
- an unmatched item in a manifest flow, or in a whole-store flow that names no round, cannot join:
  `NEEDS_NEW_ROUND`, listing the open flows it could go to;
- an unmatched item in an open round is `READY` for that round's next discover. Discover does not
  read `intake.jsonl` yet; until it does, `READY` means "recorded and routed", and the population
  predicate is applied by discover, never here.
"""

from __future__ import annotations

import datetime as _dt
import secrets
import urllib.parse
from typing import Any, Callable, Iterable

from claimstone import flows, ids, net, scope
from claimstone.store import Store

INTAKE_VERSION = 1

LEDGER = "intake.jsonl"

KINDS = ("doi", "url", "reference")

STATES = ("RECEIVED", "CHECKING", "DUPLICATE", "POSSIBLE_VERSION", "NEEDS_NEW_ROUND", "REJECTED",
          "READY", "COUNTED", "REPORTED_SEPARATELY")

MAX_VALUE_CHARS = 2_000
MAX_NOTE_CHARS = 2_000


class IntakeRefused(ValueError):
    """The item cannot be recorded at all: a malformed value or a forbidden destination."""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def normalize(kind: str, value: str, *, excluded_hosts: Iterable[str] = (),
              resolver: Callable[..., Any] | None = None) -> str:
    """The comparison form of one proposed value, or IntakeRefused with the reason.

    A URL is checked before anything is recorded: http(s) only, not an excluded host, and every
    address it resolves to global (F15). Nothing is fetched here — a resolution is not a request
    to the host."""
    if kind not in KINDS:
        raise IntakeRefused(f"kind must be one of {', '.join(KINDS)}")
    text = (value or "").strip()
    if not text:
        raise IntakeRefused("value must be non-empty")
    if len(text) > MAX_VALUE_CHARS:
        raise IntakeRefused(f"value is over {MAX_VALUE_CHARS} characters")
    if kind == "doi":
        doi = ids.normalize_doi(text)
        if doi is None:
            raise IntakeRefused("not a DOI")
        return doi
    if kind == "url":
        parts = urllib.parse.urlsplit(text)
        if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
            raise IntakeRefused("a link must be an http or https URL with a host")
        host = parts.hostname.lower()
        excluded = {h.lower() for h in excluded_hosts}
        if host in excluded or any(host.endswith("." + h) for h in excluded):
            raise IntakeRefused(f"{host} is an excluded host for this project")
        if net.global_addresses(host, resolver) is None:
            raise IntakeRefused(f"{host} does not resolve only to public addresses")
        return ids.normalize_url(text)
    return text  # a reference is kept as written; its folded title is used only to compare


def _match(kind: str, normalized: str, candidates: dict[str, dict[str, Any]]
           ) -> tuple[str | None, str | None]:
    """(state, candidate_key) for an item against the scoped candidates, or (None, None)."""
    for key, row in candidates.items():
        if kind == "doi" and ids.normalize_doi(row.get("doi")) == normalized:
            return "DUPLICATE", key
        if kind == "url" and row.get("url") and ids.normalize_url(row.get("url")) == normalized:
            return "DUPLICATE", key
    if kind == "url":
        doi = ids.normalize_doi(normalized)  # a doi.org link names its DOI
        if doi:
            for key, row in candidates.items():
                if ids.normalize_doi(row.get("doi")) == doi:
                    return "DUPLICATE", key
    if kind == "reference":
        folded = ids.normalize_title(normalized)
        if folded:
            for key, row in candidates.items():
                title = ids.normalize_title(row.get("title"))
                if title and (title == folded or (len(title) > 20 and title in folded)):
                    return "POSSIBLE_VERSION", key
    return None, None


def latest(store: Store) -> dict[str, dict[str, Any]]:
    """intake_id -> the latest row for it, in first-recorded order."""
    out: dict[str, dict[str, Any]] = {}
    for row in store.read(LEDGER):
        out[str(row.get("intake_id"))] = dict(row)
    return out


def _open_flows(store: Store, project: Any, exclude: str) -> list[dict[str, Any]]:
    """Flows an unmatched item could start in: bound, current, and naming one round."""
    found = []
    for flow_id, row in flows.flows(store).items():
        if flow_id == exclude:
            continue
        selector = (row.get("binding") or {}).get("selector") or {}
        if selector.get("manifest_only") or not selector.get("round"):
            continue
        if flows.binding_state(project, store, row)["state"] != "CURRENT":
            continue
        found.append({"flow_id": flow_id, "round": selector.get("round"),
                      "title": row.get("title")})
    return found


def submit(store: Store, project: Any, flow_row: dict[str, Any], selector: scope.Selector, *,
           kind: str, value: str, note: str | None, actor: str, code_revision: str | None,
           resolver: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Route one proposed item and record it. Returns the row written."""
    if note is not None and len(note) > MAX_NOTE_CHARS:
        raise IntakeRefused(f"note is over {MAX_NOTE_CHARS} characters")
    normalized = normalize(kind, value, excluded_hosts=project.excluded_hosts, resolver=resolver)
    flow_id = str(flow_row["flow_id"])
    with store.writer_lock():
        held = [row for row in latest(store).values()
                if row.get("flow_id") == flow_id and row.get("kind") == kind
                and row.get("value") == normalized]
        state, key, reason, links = None, None, "", {}
        if held:
            state = "DUPLICATE"
            links = {"intake_id": held[0]["intake_id"]}
            reason = "the same item was already proposed for this flow; nothing added"
        else:
            state, key = _match(kind, normalized, scope.candidates(store, selector))
            if state == "DUPLICATE":
                links = {"candidate_key": key}
                reason = "already a candidate in this flow; it adds no new work"
            elif state == "POSSIBLE_VERSION":
                links = {"candidate_key": key}
                reason = ("the title matches a candidate in this flow; whether it is the same "
                          "work, a version of it or a different work is a person's decision")
            elif selector.manifest_only or not selector.round:
                state = "NEEDS_NEW_ROUND"
                links = {"open_flows": _open_flows(store, project, flow_id)}
                reason = ("this flow's candidate set is fixed: a new work cannot join it, and "
                          "can only start in an open round")
            else:
                state = "READY"
                reason = (f"routed to round {selector.round}'s next discover, which applies the "
                          "round's population predicate; nothing counts until then")
        row = {
            "intake_version": INTAKE_VERSION,
            "intake_id": secrets.token_hex(12),
            "flow_id": flow_id,
            "kind": kind,
            "value": normalized,
            "submitted": value.strip(),
            "note": note,
            "state": state,
            "stage": "routing",
            "reason": reason,
            "links": links,
            "actor": actor,
            "signer_auth": "portal-session",
            "code_revision": code_revision,
            "recorded_at": _now(),
        }
        store.append(LEDGER, row)
    return row


def for_flow(store: Store, flow_id: str) -> list[dict[str, Any]]:
    """Every item proposed for one flow with its latest state, newest first."""
    rows = [row for row in latest(store).values() if row.get("flow_id") == str(flow_id)]
    return list(reversed(rows))
