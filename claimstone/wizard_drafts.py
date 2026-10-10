"""The new-project wizard's drafts — append-only, private to the operator who started them.

A draft is what someone typed before a project existed. `wizard_drafts.jsonl` lives in
`store/_new-projects/` (there is no project yet to hold it), and like every ledger it is only ever
appended to: the state of a draft is replayed from its rows. No stage, profile, verdict or export
reads it. A save names the revision it was based on, so two tabs cannot silently overwrite each other.
"""

from __future__ import annotations

import datetime as _dt
import pathlib
import secrets
from typing import Any

from claimstone.store import Store

WIZARD_VERSION = 1
LEDGER = "wizard_drafts.jsonl"
STORE_NAME = "_new-projects"


class DraftRefused(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def open_store(store_base: str | pathlib.Path) -> Store:
    return Store(STORE_NAME, base=store_base)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _row(draft_id: str, event: str, revision: int, actor: str, code_revision: str | None, *,
         step: int | None = None, data: Any = None, project: str | None = None,
         note: str | None = None) -> dict[str, Any]:
    return {"wizard_version": WIZARD_VERSION, "event": event, "draft_id": draft_id,
            "revision": revision, "step": step, "data": data, "project": project, "note": note,
            "actor": str(actor), "signer_auth": "portal-session", "code_revision": code_revision,
            "recorded_at": _now()}


def _rows(store: Store, draft_id: str) -> list[dict[str, Any]]:
    return [r for r in store.read(LEDGER) if r.get("draft_id") == draft_id]


def start(store: Store, *, actor: str, code_revision: str | None) -> dict[str, Any]:
    row = _row(secrets.token_hex(16), "started", 1, actor, code_revision)
    store.append(LEDGER, row)
    return row


def state(store: Store, draft_id: str, actor: str) -> dict[str, Any]:
    """Replay one draft. Another operator's draft, and an unknown id, are the same 404."""
    rows = _rows(store, str(draft_id))
    if not rows or rows[0].get("actor") != str(actor):
        raise DraftRefused(404, "NOT_FOUND", "no such draft")
    steps: dict[int, dict[str, Any]] = {}
    advanced: dict[str, str] = {}
    status, project, failure = "open", None, None
    for row in rows:
        event = row["event"]
        if event == "step_saved":
            steps[int(row["step"])] = {"data": row["data"], "revision": row["revision"]}
        elif event == "advanced_saved":
            advanced = dict(row["data"] or {})
        elif event == "discarded":
            status = "discarded"
        elif event == "created":
            status, project, failure = "created", row["project"], None
        elif event == "create_failed":
            failure = row["note"]
    return {"draft_id": str(draft_id), "revision": rows[-1]["revision"], "status": status,
            "steps": steps, "advanced": advanced, "project": project, "last_failure": failure,
            "started_at": rows[0]["recorded_at"], "updated_at": rows[-1]["recorded_at"]}


def _append(store: Store, draft_id: str, actor: str, event: str, code_revision: str | None, *,
            base_revision: int | None, **fields: Any) -> dict[str, Any]:
    with store.writer_lock():
        current = state(store, draft_id, actor)
        if current["status"] != "open":
            raise DraftRefused(409, "DRAFT_CLOSED", f"this draft is {current['status']}")
        if base_revision is not None and base_revision != current["revision"]:
            raise DraftRefused(409, "STALE_REVISION",
                               f"saved from revision {base_revision}; the draft is at "
                               f"revision {current['revision']}")
        row = _row(draft_id, event, current["revision"] + 1, actor, code_revision, **fields)
        store.append(LEDGER, row)
        return row


def save_step(store: Store, *, actor: str, draft_id: str, step: int, base_revision: int,
              data: dict[str, Any], code_revision: str | None) -> dict[str, Any]:
    return _append(store, draft_id, actor, "step_saved", code_revision,
                   base_revision=base_revision, step=step, data=data)


def save_advanced(store: Store, *, actor: str, draft_id: str, base_revision: int,
                  files: dict[str, str], code_revision: str | None) -> dict[str, Any]:
    return _append(store, draft_id, actor, "advanced_saved", code_revision,
                   base_revision=base_revision, data=files)


def discard(store: Store, *, actor: str, draft_id: str, base_revision: int,
            code_revision: str | None) -> dict[str, Any]:
    return _append(store, draft_id, actor, "discarded", code_revision, base_revision=base_revision)


def mark_created(store: Store, *, actor: str, draft_id: str, project: str, files: dict[str, str],
                 code_revision: str | None) -> dict[str, Any]:
    return _append(store, draft_id, actor, "created", code_revision, base_revision=None,
                   project=project, data=files)


def mark_failed(store: Store, *, actor: str, draft_id: str, reason: str,
                code_revision: str | None) -> dict[str, Any]:
    return _append(store, draft_id, actor, "create_failed", code_revision, base_revision=None,
                   note=str(reason)[:500])


def list_drafts(store: Store, actor: str) -> list[dict[str, Any]]:
    """This operator's drafts, most recently updated first."""
    mine = sorted({r["draft_id"] for r in store.read(LEDGER)
                   if r["event"] == "started" and r.get("actor") == str(actor)})
    out = []
    for draft_id in mine:
        current = state(store, draft_id, actor)
        first = (current["steps"].get(1) or {}).get("data") or {}
        out.append({"draft_id": draft_id, "status": current["status"],
                    "revision": current["revision"], "steps_saved": sorted(current["steps"]),
                    "project_name": first.get("name"), "project": current["project"],
                    "updated_at": current["updated_at"]})
    return sorted(out, key=lambda d: (d["updated_at"], d["revision"]), reverse=True)
