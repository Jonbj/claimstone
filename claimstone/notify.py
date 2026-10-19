"""Derive notification events from the ledgers, and hand them to `notifications`.

The stages do not write to the outbox. This module reads what the stages already recorded, so a
stage that crashed before notifying loses nothing: the next drain sees the same rows. An event
is either a **state** (an operation waiting for authorization, a question waiting for a
signature, an open integrity problem, a round below its floor) or an **occurrence** (a retry
that succeeded, a candidate given up, a batch completed, a failure, a breaker opened).

States are derived on every drain and deduplicated by identity. Occurrences are filtered against
the outbox's start row (`notifications.start`), because an operator who enables notifications
should be told what needs them now, not every historical success; `--since` is the deliberate
replay.

"Needs a person" is read from `portal_state.inbox_cards`, the portal's one computation of open
items, and filtered to `today.REQUIRED_CATEGORIES`. A new integrity check therefore reaches
notifications by existing, not by being remembered here.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from typing import Any, Iterable

from claimstone import (acquire, admissibility, flows, intake, net, notifications, operations,
                        portal_state, retry_policy, scope, today)
from claimstone.config import Project
from claimstone.store import Store


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _parse(value: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(value)


def _occurrence(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _event(*, event: str, reason: str, project: str, subject: str, ids: Iterable[str],
           occurrence: str, occurred_at: str, code: str | None = None,
           count: int = 1) -> dict[str, Any]:
    return {"event": event, "reason": reason, "project": project, "subject": subject,
            "ids": list(ids), "count": count, "occurrence": occurrence,
            "occurred_at": occurred_at, "code": code}


def card_event(project: str, card: portal_state.Card, *, now: str | None = None) -> dict | None:
    """A required inbox card as a `needs_person` event, or None for a command-only card."""
    if card.category == "ADJUDICATION":
        reason, code = "signature_required", "ADJUDICATION"
    elif card.category in ("INTEGRITY", "PROTOCOL"):
        # A protocol binding or registry that moved under the round stops everything, exactly
        # as a damaged ledger does. `code` says which without putting prose in the message.
        reason, code = "integrity_error", card.category
    else:
        return None
    return _event(
        event="needs_person", reason=reason, project=project, subject=card.subject,
        ids=[card.subject], code=code, occurred_at=now or _now(),
        # The card's own text identifies the occurrence: it carries the counts, the stale
        # reason and the profile hash. It is hashed, never stored.
        occurrence=_occurrence(card.category, card.scope, card.subject, card.cause,
                               card.command or ""))


def floor_event(project: str, round_name: str | None, manifest_only: bool,
                admitted: dict[str, Any], *, now: str | None = None) -> dict | None:
    """A round below its acquisition floor, once per round and floor version.

    No candidate is not a rate below a floor: an empty round is not notified. A round that
    declared partial reading (D146) still gets this event; its profiles say partial, and the
    person should know why."""
    if admitted.get("status") != admissibility.INSUFFICIENT:
        return None
    found = int(admitted.get("found") or 0)
    if found <= 0:
        return None
    subject = (round_name or "-") + ("~manifest" if manifest_only else "")
    return _event(
        event="finished", reason="round_below_floor", project=project, subject=subject,
        ids=[subject], count=found, code=str(admitted["status"]), occurred_at=now or _now(),
        occurrence=_occurrence(subject, str(admitted.get("floor_version") or "")))


def _needs_person(project: Project | None, store: Store, moment: str) -> list[dict[str, Any]]:
    if project is None:
        return []
    found: list[dict[str, Any]] = []
    rows = flows.flows(store)
    selectors = [(row, portal_state._selector_of(row, scope.Selector(None)))
                 for row in rows.values()]
    selectors += [(None, selector)
                  for selector in portal_state.unbound_selectors(store, rows.values())]
    for flow_row, selector in selectors:
        computed = portal_state.compute(project, store, selector)
        for card in portal_state.inbox_cards(project, store, selector, flow_row,
                                             computed=computed):
            if card.category not in today.REQUIRED_CATEGORIES:
                continue
            event = card_event(project.name, card, now=moment)
            if event is not None:
                found.append(event)
        if computed.admitted is not None:
            event = floor_event(project.name, selector.round, selector.manifest_only,
                                computed.admitted, now=moment)
            if event is not None:
                found.append(event)
    return found


def _operation_events(store: Store, since: str, project_name: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for operation_id, rows in operations._events(store).items():
        last = rows[-1]
        if last["event"] == "planned":
            found.append(_event(
                event="needs_person", reason="plan_awaiting_authorization",
                project=project_name,
                subject=f"operation:{operation_id}", ids=[operation_id],
                occurrence=operation_id, occurred_at=last["at"]))
        elif last["event"] == "failed" and _parse(last["at"]) >= _parse(since):
            found.append(_event(
                event="failure", reason="operation_failed",
                project=project_name,
                subject=f"operation:{operation_id}", ids=[operation_id],
                code=str(last.get("failure_class") or "FAILED"),
                occurrence=str(last["event_id"]), occurred_at=last["at"]))
    return found


def _batch_events(store: Store, since: str, project_name: str) -> list[dict[str, Any]]:
    grouped = operations._events(store)
    found: list[dict[str, Any]] = []
    for batch in store.read(operations.BATCH_LEDGER):
        batch_id = str(batch.get("batch_id") or "")
        operation_ids = list(batch.get("operation_ids") or [])
        if not batch_id or not operation_ids:
            continue
        histories = [grouped.get(str(operation_id)) or [] for operation_id in operation_ids]
        if any(not rows for rows in histories):
            continue
        if not all(rows[-1]["event"] == "completed" for rows in histories):
            continue
        completed_at = max((rows[-1]["at"] for rows in histories), key=_parse)
        if _parse(completed_at) < _parse(since):
            continue
        found.append(_event(
            event="finished", reason="batch_completed", project=project_name,
            subject=f"batch:{batch_id}", ids=[batch_id], count=len(operation_ids),
            occurrence=batch_id, occurred_at=completed_at))
    return found


def _retry_is_a_fetch(row: dict[str, Any]) -> bool:
    """A store reuse and an operator intake are not requests, so neither is a retry."""
    return (row.get("provenance") != "store-reuse"
            and row.get("campaign") != intake.CAMPAIGN)


def _acquisition_events(store: Store, since: str, project_name: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for candidate_key, row in store.latest_by("acquisitions.jsonl", "candidate_key").items():
        fetched = str(row.get("fetched_at") or "")
        if not fetched or _parse(fetched) < _parse(since):
            continue
        attempt = int(row.get("attempt_no") or len(row.get("attempts") or []) or 1)
        if row.get("acquired") and attempt > 1 and _retry_is_a_fetch(row):
            found.append(_event(
                event="retry", reason="copy_obtained_after_retry", project=project_name,
                subject=str(candidate_key), ids=[str(candidate_key)],
                occurrence=f"{candidate_key}|{attempt}", occurred_at=fetched))
        elif not row.get("acquired") and net.is_terminal(row.get("failure_class")):
            found.append(_event(
                event="retry", reason="candidate_given_up", project=project_name,
                subject=str(candidate_key), ids=[str(candidate_key)],
                code=str(row.get("failure_class") or "UNKNOWN"),
                occurrence=f"{candidate_key}|{attempt}", occurred_at=fetched))
    return found


def _reservation_authorisations(store: Store, policy_id: str) -> list[str]:
    return [rows[1]["at"] for rows in operations._events(store).values()
            if len(rows) > 1 and rows[1]["event"] == "authorized"
            and (rows[1].get("identity") or {}).get("retry_policy_id") == policy_id]


def _retry_policy_events(store: Store, since: str, moment: str, project_name: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    now = _parse(moment)
    for policy_id, history in retry_policy._read(store).items():
        if len(history) < 2 or history[-1]["event"] != "authorized":
            continue
        spec = history[0]["policy"]
        expires_at = str(spec.get("expires_at") or "")
        if expires_at and _parse(expires_at) >= _parse(since) and _parse(expires_at) <= now:
            found.append(_event(
                event="retry", reason="retry_window_expired", project=project_name,
                subject=f"retry-policy:{policy_id}", ids=[policy_id],
                code="RETRY_WINDOW", occurrence=f"{policy_id}|{expires_at}",
                occurred_at=expires_at))
        state = retry_policy.status(store, policy_id)
        if state["remaining_retries"] == 0:
            used_at = max(_reservation_authorisations(store, policy_id) or [history[-1]["at"]],
                          key=_parse)
            if _parse(used_at) >= _parse(since):
                found.append(_event(
                    event="retry", reason="retry_ceiling_used", project=project_name,
                    subject=f"retry-policy:{policy_id}", ids=[policy_id],
                    code="RETRY_CEILING", occurrence=f"{policy_id}|{used_at}",
                    occurred_at=used_at))
    return found


def _breaker_events(store: Store, since: str, project_name: str) -> list[dict[str, Any]]:
    episodes: dict[str, list[str]] = {}
    for row in store.read("requests.jsonl"):
        if row.get("event") != "blocked" or row.get("failure_class") != net.BUDGET:
            continue
        recorded_at = str(row.get("recorded_at") or "")
        host = net.host_of(str(row.get("url") or row.get("request_url") or ""))
        if recorded_at and _parse(recorded_at) >= _parse(since) and host:
            episodes.setdefault(host, []).append(recorded_at)
    return [
        _event(event="retry", reason="host_breaker_open", project=project_name, subject=host,
               ids=[host], count=len(times), code="DOMAIN_BUDGET_EXHAUSTED",
               occurrence=f"{host}|{min(times, key=_parse)}", occurred_at=min(times, key=_parse))
        for host, times in sorted(episodes.items())]


def derive(project: Project | None, store: Store, *, project_name: str | None = None,
           since: str | None = None, now: str | None = None) -> list[dict[str, Any]]:
    """Every event the current ledgers support, newest last, one per identity.

    `since` filters occurrences only. It defaults to the outbox's start row; before that row
    exists, it defaults to now, so a first drain sends what needs a person and no history."""
    moment = now or _now()
    name = project_name or (project.name if project is not None else None)
    if not name:
        raise ValueError("derive needs a project name for the outbox")
    boundary = notifications._timestamp(since or notifications.watermark(store) or moment)
    found = (_needs_person(project, store, moment)
             + _operation_events(store, boundary, name)
             + _batch_events(store, boundary, name)
             + _acquisition_events(store, boundary, name)
             + _retry_policy_events(store, boundary, moment, name)
             + _breaker_events(store, boundary, name))
    unique: dict[str, dict[str, Any]] = {}
    for event in found:
        unique.setdefault(notifications.key(event), event)
    return sorted(unique.values(), key=lambda row: (_parse(row["occurred_at"]),
                                                    row["subject"]))
