"""The two ratios stage 4 produces, and why they are never one.

`accepted / proposed` is the **gate's** ratio: how much of what a model offered survived invariant 1.
`questions with a claim / questions asked` is the **corpus's**: how much of the registry the literature
addresses. Fusing them would let a clean gate on a silent corpus read like a well-covered one.

A rejection rate is not a quality score either way round. A gate rejecting a quarter of what it is
offered might be catching a quarter of fabrications or discarding a quarter of good evidence, and only
reading the rejections tells you which — which is why they are kept whole.
"""

from __future__ import annotations

from typing import Any

from claimstone.store import Store


def summarise(store: Store, *, batch: str | None = None) -> dict[str, Any]:
    """Both ratios, per question and per class, plus what was rejected and why."""
    claims = [
        row for row in store.latest_by("claims.jsonl", "claim_id").values()
        if batch is None or str(row.get("call_id")) in _batch_calls(store, batch)
    ]
    rejections = [
        row for row in store.latest_by("rejections.jsonl", "claim_id").values()
        if batch is None or str(row.get("call_id")) in _batch_calls(store, batch)
    ]

    by_question: dict[str, dict[str, Any]] = {}
    for row in claims:
        bucket = by_question.setdefault(str(row.get("question_id")), {
            "claims": 0, "sources": set(), "stances": {}, "by_class": {},
        })
        bucket["claims"] += 1
        bucket["sources"].add(str(row.get("source_id")))
        stance = str(row.get("stance"))
        bucket["stances"][stance] = bucket["stances"].get(stance, 0) + 1
        klass = str(row.get("source_class") or "UNCLASSIFIED")
        bucket["by_class"][klass] = bucket["by_class"].get(klass, 0) + 1

    for bucket in by_question.values():
        # Counted by source, not by record: ten claims from one paper are one study, and calling them
        # ten is the vote counting invariant 7 forbids.
        bucket["studies"] = len(bucket.pop("sources"))
        bucket["stances"] = dict(sorted(bucket["stances"].items(), key=lambda kv: -kv[1]))
        bucket["by_class"] = dict(sorted(bucket["by_class"].items()))

    failures: dict[str, int] = {}
    for row in rejections:
        name = str(row.get("failure"))
        failures[name] = failures.get(name, 0) + 1

    proposed = len(claims) + len(rejections)
    return {
        "batch": batch,
        "proposed": proposed,
        "accepted": len(claims),
        "rejected": len(rejections),
        # The gate's ratio. `None` rather than 1.00 when nothing was offered: a gate that judged
        # nothing has no pass rate, and printing one would describe a measurement never taken.
        "gate_rate": (len(claims) / proposed) if proposed else None,
        "questions_with_a_claim": len(by_question),
        "by_question": dict(sorted(by_question.items())),
        "failures": dict(sorted(failures.items(), key=lambda kv: -kv[1])),
    }


def _batch_calls(store: Store, batch: str) -> set[str]:
    return {
        str(row.get("call_id"))
        for row in store.read(f"calls/extract/{batch}/requests.jsonl")
    }
