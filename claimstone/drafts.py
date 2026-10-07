"""Operator reasoning drafts — what a person was writing before they signed (spec B5).

`drafts.jsonl` is append-only like every ledger, and it is deliberately inert: no stage reads
it, no profile or verdict depends on it, and `export.snapshot` leaves it out. A draft is the
operator's unfinished text; a signature is the only judgement the project records. Keeping the
draft lets the reading desk survive a changed profile (the design's "profile changed while you
read" variant): the text is kept, the hash it was written against is kept, and the page says
whether that hash is still the current one.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from claimstone.store import Store

DRAFT_VERSION = 1

LEDGER = "drafts.jsonl"

MAX_DRAFT_CHARS = 20_000  # far beyond any rationale; the control body limit is the outer bound


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def append(store: Store, *, actor: str, flow_id: str, question_id: str, rationale: str,
           profile_sha256: str, code_revision: str | None) -> dict[str, Any]:
    """Record one draft. The text is kept as typed: a draft is not yet a rationale, so it is
    neither trimmed nor held to the 120-character minimum a signature needs."""
    if len(rationale) > MAX_DRAFT_CHARS:
        raise ValueError(f"a draft of {len(rationale)} characters is over {MAX_DRAFT_CHARS}")
    row = {
        "draft_version": DRAFT_VERSION,
        "flow_id": str(flow_id),
        "question_id": str(question_id),
        "rationale": rationale,
        "profile_sha256": str(profile_sha256),
        "actor": str(actor),
        "signer_auth": "portal-session",
        "code_revision": code_revision,
        "recorded_at": _now(),
    }
    store.append(LEDGER, row)
    return row


def latest(store: Store, *, actor: str, flow_id: str, question_id: str) -> dict[str, Any] | None:
    """This operator's last draft for one question of one flow. Another operator's drafts are
    never returned: a draft is private working text, not a shared record."""
    found: dict[str, Any] | None = None
    for row in store.read(LEDGER):
        if (str(row.get("actor")) == str(actor) and str(row.get("flow_id")) == str(flow_id)
                and str(row.get("question_id")) == str(question_id)):
            found = dict(row)
    return found
