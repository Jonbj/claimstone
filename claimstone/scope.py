"""One selector, one predicate: which rows belong to a round.

Every reader that shows a figure "for a round" must use these functions, so a portal page and
`report` can never count two different populations under one name (review F1, F3). Before this
module existed, three modules carried three slightly different ideas of the same selector —
`_stage_discover` matched `round or "routine"` while admission matched `round` — and a figure
shown "for r1" could silently include r2's rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from claimstone.store import Store

SCOPE_VERSION = 1

# Which ledger is filtered by which identity. The nine ledgers a round's figures come from;
# anything not listed here has no round meaning and is never in a scoped read.
CANDIDATE_LEDGERS = ("candidates.jsonl", "acquisitions.jsonl")
SOURCE_LEDGERS = ("documents.jsonl", "chunks.jsonl", "claims.jsonl", "rejections.jsonl")
CLAIM_LEDGERS = ("reviews.jsonl",)
ROUND_LEDGERS = ("profiles.jsonl", "adjudications.jsonl")
SCOPED_LEDGERS = CANDIDATE_LEDGERS + SOURCE_LEDGERS + CLAIM_LEDGERS + ROUND_LEDGERS


@dataclass(frozen=True)
class Selector:
    """The round selector every reader shares. `round=None` with `manifest_only=False` is the
    whole store; `manifest_only=True` alone is the curated manifest population across rounds."""

    round: str | None
    manifest_only: bool = False

    @property
    def whole_store(self) -> bool:
        return self.round is None and not self.manifest_only

    def as_dict(self) -> dict[str, Any]:
        return {"round": self.round, "manifest_only": self.manifest_only}


def candidate_in_scope(row: Mapping[str, Any], selector: Selector) -> bool:
    """The one predicate. Mirrors `admissibility.rate`'s population exactly (F3)."""
    return (
        selector.round is None or row.get("round") == selector.round
    ) and (not selector.manifest_only or row.get("source_id"))


def candidates(store: Store, selector: Selector) -> dict[str, dict[str, Any]]:
    """Latest candidate row per key, filtered to the selector."""
    return {
        key: row
        for key, row in store.latest_by("candidates.jsonl", "candidate_key").items()
        if candidate_in_scope(row, selector)
    }


def source_ids(store: Store, selector: Selector) -> set[str]:
    """The downstream identity of every scoped candidate: `source_id` or the key (F1)."""
    return {
        str(row.get("source_id") or key) for key, row in candidates(store, selector).items()
    }


def row_in_scope(
    ledger: str,
    row: Mapping[str, Any],
    *,
    selector: Selector,
    keys: set[str],
    sources: set[str],
    claim_sources: Mapping[str, str],
) -> bool:
    """Whether one ledger row belongs to the selector. Whole store: every row of the nine.

    `keys` are the scoped candidate keys, `sources` the scoped source ids, and `claim_sources`
    maps claim_id → source_id for the claims in scope (a review is scoped through its claim).
    """
    if selector.whole_store:
        return ledger in SCOPED_LEDGERS
    if ledger in CANDIDATE_LEDGERS:
        key = row.get("candidate_key")
        return key is not None and str(key) in keys
    if ledger in SOURCE_LEDGERS:
        return str(row.get("source_id")) in sources
    if ledger in CLAIM_LEDGERS:
        return claim_sources.get(str(row.get("claim_id"))) in sources
    if ledger in ROUND_LEDGERS:
        return row.get("round") == selector.round and bool(row.get("manifest_only")) == (
            selector.manifest_only
        )
    return False
