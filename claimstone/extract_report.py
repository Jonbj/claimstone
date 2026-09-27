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


def summarise(
    store: Store, *, batch: str | None = None, project: Any = None
) -> dict[str, Any]:
    """Both ratios, per question and per class, plus what was rejected and why.

    The second ratio needs a denominator and the registry is where it lives, so `project` is required to
    compute coverage. Without it the coverage is `None` rather than a number: a ratio printed without its
    denominator would be one this module invented.
    """
    # Computed once. Calling `_batch_calls` inside the comprehension re-read all 1,888 request rows for
    # every one of 4,358 claims, and the report took minutes on a ledger it should read in a second.
    wanted = _batch_calls(store, batch) if batch is not None else None
    claims = [
        row for row in store.latest_by("claims.jsonl", "claim_id").values()
        if wanted is None or str(row.get("call_id")) in wanted
    ]
    accepted_ids = {str(row.get("claim_id")) for row in claims}
    rejections = [
        row for row in store.latest_by("rejections.jsonl", "claim_id").values()
        if (wanted is None or str(row.get("call_id")) in wanted)
        # A claim in claims.jsonl is accepted now, whatever an older rejection row says. Correcting the
        # numeral rule moved 77 from rejected to accepted, and the rejection rows stay — append-only, and
        # they record what the old rule did — but counting both inflated `proposed`.
        and str(row.get("claim_id")) not in accepted_ids
    ]
    superseded = len([
        row for row in store.latest_by("rejections.jsonl", "claim_id").values()
        if (wanted is None or str(row.get("call_id")) in wanted)
        and str(row.get("claim_id")) in accepted_ids
    ])

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

    # Only the kinds that receive a verdict. An `operational` question gets none (invariant 2), and
    # counting it in the denominator would make full coverage unreachable by construction.
    asked: list[str] = []
    if project is not None:
        from claimstone.claimgate import STANCES_BY_KIND

        asked = sorted(q.id for q in project.questions if q.kind in STANCES_BY_KIND)

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
        "questions_asked": len(asked) if project is not None else None,
        "coverage": (len(by_question) / len(asked)) if asked else None,
        # Named, because a question with no claim after a complete round is UNANSWERED_IN_LITERATURE and
        # one whose calls never ran is NEVER_ASKED, and only somebody who can see which is which can tell.
        "questions_without_a_claim": [q for q in asked if q not in by_question],
        "by_question": dict(sorted(by_question.items())),
        "failures": dict(sorted(failures.items(), key=lambda kv: -kv[1])),
        # Rejections a later, corrected reading turned into claims. Kept visible: the count is how much a
        # gate rule change was worth.
        "superseded_rejections": superseded,
    }


def _batch_calls(store: Store, batch: str) -> set[str]:
    return {
        str(row.get("call_id"))
        for row in store.read(f"calls/extract/{batch}/requests.jsonl")
    }
