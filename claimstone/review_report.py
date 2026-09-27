"""What the second reader found, per extraction reader — and what this is not a measurement of.

**This is a precision-side comparison.** It reports how much each extractor proposed that survived both the
gate and the reader. It cannot report **misses**: results present in a chunk that a backend did not propose.
Measuring those needs a reference — a blind, human-adjudicated sample where somebody reads the chunk and
lists what a correct extraction would find — and no such sample exists. So the recall side is named here as
missing rather than left for a reader to assume was covered.

Why that matters, in one sentence from the spec: **a backend emitting one bland, safe, well-quoted claim per
chunk wins on the OVERSTATED rate while missing ten material results.** Precision without recall rewards
timidity, and the extractor whose claims survive best could be the one that claimed least.

And one fixed reviewer controls reviewer *variation* while keeping reviewer *bias*. A reviewer that
systematically accepts a certain kind of overreach flatters every extractor equally. The fixed reviewer makes
the comparison internally consistent, not correct.
"""

from __future__ import annotations

from typing import Any

from claimstone.store import Store

CAVEAT = (
    "A precision-side comparison. Misses — results in a chunk that a backend did not propose — are not "
    "measured and cannot be without a blind, human-adjudicated reference sample. A backend proposing one "
    "safe claim per chunk wins this table while missing ten results."
)


def _reader(identity: Any) -> str:
    if not isinstance(identity, dict):
        return "unknown"
    backend, model = identity.get("backend") or "", identity.get("model") or ""
    return f"{backend}/{model}" if model else (backend or "unknown")


def summarise(store: Store) -> dict[str, Any]:
    """Verdict counts per extraction reader, the reviewers that judged, and what is still unreviewed."""
    claims = store.latest_by("claims.jsonl", "claim_id")
    reviews = store.latest_by("reviews.jsonl", "claim_id")
    rejections = store.latest_by("rejections.jsonl", "claim_id")

    by_extractor: dict[str, dict[str, Any]] = {}
    reviewers: dict[str, int] = {}

    for claim_id, claim in claims.items():
        key = _reader({"backend": claim.get("backend"), "model": claim.get("model")})
        bucket = by_extractor.setdefault(key, {
            "claims": 0, "reviewed": 0, "awaiting_review": 0, "verdicts": {},
            "gate_rejections": 0, "gate_rejections_by_reason": {},
        })
        bucket["claims"] += 1
        held = reviews.get(claim_id)
        if held is None:
            # Not supported and not unsupported. Stage 6 may not use it and must report it.
            bucket["awaiting_review"] += 1
            continue
        bucket["reviewed"] += 1
        verdict = str(held.get("verdict"))
        bucket["verdicts"][verdict] = bucket["verdicts"].get(verdict, 0) + 1
        who = _reader(held.get("reviewed_by"))
        reviewers[who] = reviewers.get(who, 0) + 1

    # The gate's own rejections, per reader: "how much it proposed badly", which is the third of the spec's
    # four numbers and is knowable without a reference.
    for row in rejections.values():
        key = _reader({"backend": row.get("backend"), "model": row.get("model")})
        bucket = by_extractor.setdefault(key, {
            "claims": 0, "reviewed": 0, "awaiting_review": 0, "verdicts": {},
            "gate_rejections": 0, "gate_rejections_by_reason": {},
        })
        bucket["gate_rejections"] += 1
        reason = str(row.get("failure"))
        bucket["gate_rejections_by_reason"][reason] = (
            bucket["gate_rejections_by_reason"].get(reason, 0) + 1)

    for bucket in by_extractor.values():
        bucket["verdicts"] = dict(sorted(bucket["verdicts"].items(), key=lambda kv: -kv[1]))
        bucket["gate_rejections_by_reason"] = dict(
            sorted(bucket["gate_rejections_by_reason"].items(), key=lambda kv: -kv[1]))
        supported = bucket["verdicts"].get("SUPPORTED", 0)
        # Conditional on having passed the gate, which is why it is not extraction quality.
        bucket["supported_share"] = (supported / bucket["reviewed"]) if bucket["reviewed"] else None
        bucket["verified_useful"] = supported

    return {
        "claims": len(claims),
        "reviewed": len(reviews),
        "awaiting_review": len(claims) - len([c for c in claims if c in reviews]),
        "by_extractor": dict(sorted(by_extractor.items())),
        "reviewed_by": dict(sorted(reviewers.items(), key=lambda kv: -kv[1])),
        # Named, not omitted.
        "misses": None,
        "caveat": CAVEAT,
    }
