"""Today: what changed since an operator last looked, and what waits for them (spec B9).

The "seen up to" markers are installation state, like the operator accounts (D99). They live in
`seen.jsonl` under the state directory, one row per marker, with an optional project: a marker
without one covers every project. Time comes only from the rows' own timestamps; a file's mtime
belongs to whoever wrote the ledger last, so it is never used (review F17).
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
from typing import Any

from claimstone import (decisions, flows, intake, operations, operations_view, portal_state,
                        round_state, scope)
from claimstone.config import ConfigError, check_registry_drift, discover_projects, load_project
from claimstone.store import LedgerCorrupt, Store

SEEN_VERSION = 1

LEDGER = "seen.jsonl"

# Ledgers whose rows say something happened, with the stage a person would name.
CHANGE_LEDGERS: tuple[tuple[str, str], ...] = (
    ("candidates.jsonl", "discover"), ("acquisitions.jsonl", "acquire"),
    ("documents.jsonl", "normalize"), ("claims.jsonl", "extract"), ("reviews.jsonl", "review"),
    ("profiles.jsonl", "synthesize"), ("adjudications.jsonl", "adjudicate"),
    (intake.LEDGER, "intake"), (decisions.LEDGER, "decisions"), ("exports.jsonl", "export"),
)
_TIMES = round_state._ROW_TIMES + ("recorded_at", "created_at", "supplied_at")

# Inbox categories that need a person rather than a command: a question ready to sign, and a
# project whose integrity or protocol stops everything else.
REQUIRED_CATEGORIES = ("ADJUDICATION", "INTEGRITY", "PROTOCOL")

CHANGED_SAMPLE = 20


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _parse(value: Any) -> _dt.datetime | None:
    try:
        stamp = _dt.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return stamp if stamp.tzinfo else None  # an undated or naive time cannot be ordered safely


def _rows(directory: pathlib.Path) -> list[dict[str, Any]]:
    path = pathlib.Path(directory) / LEDGER
    if not path.exists():
        return []
    data = path.read_bytes()
    data = data[: data.rfind(b"\n") + 1] if not data.endswith(b"\n") else data  # torn tail
    return [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]


def mark_seen(directory: pathlib.Path, *, actor: str, project: str | None,
              until: str | None) -> dict[str, Any]:
    """Record that `actor` has seen everything up to `until` (default: now)."""
    moment = _parse(until) if until is not None else _dt.datetime.now(_dt.timezone.utc)
    if moment is None:
        raise ValueError("until must be an ISO date-time with a time zone")
    if moment > _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=5):
        raise ValueError("until cannot be in the future: nobody has seen what has not happened")
    row = {"seen_version": SEEN_VERSION, "actor": actor, "project": project,
           "until": moment.isoformat(timespec="seconds"), "recorded_at": _now()}
    directory = pathlib.Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / LEDGER
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return row


def seen_until(directory: pathlib.Path, *, actor: str, project: str) -> _dt.datetime | None:
    """The latest marker that covers `project` for `actor`, or None on a first visit."""
    best: _dt.datetime | None = None
    for row in _rows(directory):
        if row.get("actor") != actor or row.get("project") not in (None, project):
            continue
        moment = _parse(row.get("until"))
        if moment is not None and (best is None or moment > best):
            best = moment
    return best


def changes(store: Store, since: _dt.datetime | None) -> dict[str, Any]:
    """Rows written after `since`, counted per stage, with the newest few. Rows without their own
    timestamp are not counted and the count of them is reported, never guessed."""
    counts: dict[str, int] = {}
    newest: list[tuple[_dt.datetime, str, dict[str, Any]]] = []
    undated = 0
    for ledger, stage in CHANGE_LEDGERS:
        for row in store.read(ledger):
            moment = next((m for m in (_parse(row.get(k)) for k in _TIMES if row.get(k)) if m),
                          None)
            if moment is None:
                undated += 1
                continue
            if since is not None and moment <= since:
                continue
            counts[stage] = counts.get(stage, 0) + 1
            newest.append((moment, stage, row))
    newest.sort(key=lambda item: item[0], reverse=True)
    keep = ("source_id", "candidate_key", "question_id", "verdict", "state", "kind",
            "failure_class", "acquired", "provisional", "intake_id", "decision_id", "export_id")
    return {"counts": dict(sorted(counts.items())), "undated_rows": undated,
            "newest": [{"when": moment.isoformat(timespec="seconds"), "stage": stage,
                        "row": {k: row[k] for k in keep if k in row}}
                       for moment, stage, row in newest[:CHANGED_SAMPLE]]}


def _needs(project: Any, store: Store) -> dict[str, list[dict[str, Any]]]:
    required: list[dict[str, Any]] = []
    optional: list[dict[str, Any]] = []
    for flow_id, row in flows.flows(store).items():
        selector = portal_state._selector_of(row, scope.Selector(None))
        for card in portal_state.inbox_cards(project, store, selector, row):
            if card.category in REQUIRED_CATEGORIES:
                required.append({"flow_id": flow_id, "type": card.category.lower(),
                                 "subject": card.subject, "cause": card.cause})
        for item in decisions.open_items(store, selector, flow_id):
            entry = {"flow_id": flow_id, "type": item["type"], "subject": item["candidate_key"],
                     "id": item["id"]}
            (required if item["required"] else optional).append(entry)
    return {"required": required, "optional": optional}


def today(projects_dir: pathlib.Path, store_dir: pathlib.Path, state_dir: pathlib.Path, *,
          actor: str) -> dict[str, Any]:
    """Per project: since when, what changed, what needs this operator. A project that cannot be
    read is listed with its error rather than left out: absent is not the same as quiet."""
    projects: list[dict[str, Any]] = []
    for root in discover_projects(projects_dir):
        entry: dict[str, Any] = {"project": root.name}
        try:
            project = load_project(root)
            store = Store(project.name, base=store_dir)
            check_registry_drift(project, store, record=False)
            since = seen_until(state_dir, actor=actor, project=project.name)
            entry.update({"since": since.isoformat(timespec="seconds") if since else None,
                          "first_visit": since is None,
                          "changed": changes(store, since),
                          "needs_you": _needs(project, store),
                          "continues_without_you": operations_view.continuing(store)})
        except (ConfigError, LedgerCorrupt, operations.OperationError) as exc:
            entry.update({"error": f"{type(exc).__name__}: {exc}"})
        projects.append(entry)
    return {"operator": actor, "projects": projects}
