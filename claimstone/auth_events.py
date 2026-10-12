"""auth_events.jsonl — who tried to sign in, how, and what came of it (design 2026-10-12).

Append-only, owner-only, in the same state directory as `operators.jsonl`. It never holds a
password, a token or a Google claim beyond the subject: `detail` is a short fixed code. A failed
attempt records the *id typed*, because that is what an investigation needs; it is cut to 200
characters and stripped of control characters so a hostile id cannot forge a second line.
"""

from __future__ import annotations

import json
import os
import pathlib
from datetime import datetime, timezone

LEDGER = "auth_events.jsonl"
EVENTS = frozenset({
    "login_ok", "login_failed", "login_blocked", "logout", "google_ok", "google_denied",
    "google_linked", "google_unlinked", "password_changed", "password_set_by_admin",
    "sessions_revoked", "person_created", "person_disabled", "person_enabled",
    "person_email_set", "person_role_set", "reauth_failed"})


def _clean(value: object, limit: int = 200) -> str | None:
    if value is None:
        return None
    text = "".join(ch for ch in str(value) if ch.isprintable())
    return text[:limit]


def record(directory: str | pathlib.Path, event: str, *, id: object = None,
           method: str | None = None, remote: object = None, detail: str | None = None,
           by: object = None, now: str | None = None) -> None:
    """Append one event. An unknown event name is a programming error, not a row."""
    if event not in EVENTS:
        raise ValueError(f"unknown auth event: {event}")
    row = {"at": now or datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "event": event, "id": _clean(id), "method": _clean(method, 20),
           "remote": _clean(remote, 64), "detail": _clean(detail, 60), "by": _clean(by)}
    path = pathlib.Path(directory) / LEDGER
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    os.chmod(path, 0o600)  # a file created earlier under a looser umask is tightened too
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
