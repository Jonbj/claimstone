"""One question's evidence profile. Pure: dictionaries in, one dictionary out, no store and no clock.

**Everything known, nothing concluded.** This module emits no verdict. Its one categorical output is
`NO_VERIFIED_CLAIM`, which says nothing survived to the profile and is deliberately *not*
`NEVER_ASKED` — that asserts nobody asked, which only screening establishes, and only a person may say
it (verdict contract §3).

It is separate from `synthesize.py` because it is the part with the arithmetic, and arithmetic that
decides what a reader is shown has to be testable without a corpus.

Three things here exist because a review caught their absence:

**Contrary results carry the same fields as agreeing ones.** A profile showing only the agreeing side
is a selection presented as a description, and the failure it hides is a verdict resting on vendor
research that refereed work disagrees with.

**Linkage is `unestablished`, always.** An earlier rule counted distinct `sample` strings as distinct
datasets. Two spellings of one dataset pass that; one broad label hides two. The labels are reported
verbatim and the unknown stays unknown.

**A direction count is labelled a count.** Three-to-one is not a strength, and `synthesize` prints the
label beside the number so that nothing downstream can quietly treat it as one.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

# The one categorical thing layer 1 may say. Not a verdict, and not `NEVER_ASKED`.
NO_VERIFIED_CLAIM = "NO_VERIFIED_CLAIM"

# An operational question receives no profile and no verdict, and is **not omitted**: omitting it would
# make the registry and the report disagree on how many questions exist, and "one verdict per question"
# is the project's contract. It is kept by answering every question, including with "this instrument
# cannot answer this one".
NOT_APPLICABLE = "LITERATURE_VERDICT_NOT_APPLICABLE"

# Only a claim a second reader passed reaches a profile. `OVERSTATED` and `AMBIGUOUS` rows are counted
# and shown, never used, and never deleted — an `OVERSTATED` row is the most informative row in the
# ledger, because it is a case the mechanical gate passed and a reader would not.
USABLE_REVIEW = "SUPPORTED"

# Which fields travel per kind, mirroring what stage 4 extracts. A profile carries the fields that were
# extracted rather than a subset of them, because a reader deciding a verdict needs the estimand.
FIELDS_BY_KIND: dict[str, tuple[str, ...]] = {
    "effect": ("estimate", "estimate_scale", "estimate_bound", "estimate_as_written",
               "uncertainty_as_written", "uncertainty", "uncertainty_bracketed",
               "horizon_as_written", "sample", "design", "dependence"),
    "heterogeneity": ("moderator", "high_side", "low_side", "contrast_as_written", "contrast_sides",
                      "contrast_scale", "contrast_uncertainty_as_written", "prespecified"),
    "method": ("support_type",),
    "premise": (),
}

# Which stance disagrees with the question, per kind. `QUALIFIES` is neither: it is a claim that the
# effect holds under conditions, and counting it on either side would be this module deciding something
# the adjudicator is there to decide.
AGAINST = "CONTRADICTS"


def _digest(payload: Mapping[str, Any]) -> str:
    """A profile's hash, over everything but the hash and the wall clock.

    An adjudication records the hash it was shown, so this has to change when the evidence changes and
    not when the same evidence is rebuilt. `built_at` is therefore excluded: a rebuild at a later minute
    is not different evidence, and treating it as such would make every adjudication stale overnight.
    """
    trimmed = {k: v for k, v in payload.items() if k not in ("profile_sha256", "built_at")}
    return hashlib.sha256(
        json.dumps(trimmed, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def result_of(claim: Mapping[str, Any], kind: str, *, role: str = "") -> dict[str, Any]:
    """One result row for a profile: who said it, what they said, and on what basis.

    A claim is an **evidence annotation attached to a result**, not an observation to be counted — the
    quote verifies the provenance of a text and does not establish that the right result was selected
    from the paper or that its standard error was read correctly. So this carries the record, and
    nothing here tallies claims as though each were a study.
    """
    row: dict[str, Any] = {
        "claim_id": claim.get("claim_id"),
        "source_id": claim.get("source_id"),
        "source_class": claim.get("source_class"),
        "stance": claim.get("stance"),
        "claim": claim.get("claim"),
        "evidence_quote": claim.get("evidence_quote"),
    }
    if role:
        # Declared in sources.yaml, never read off the class id: which classes are methodological is
        # project data, and inferring it from `MET` would be domain knowledge in the engine (invariant 4).
        row["role"] = role
    for field in FIELDS_BY_KIND.get(kind, ()):
        if field in claim:
            row[field] = claim[field]
    # Named rather than nulled, and stage 6 may not pool it (D37).
    if claim.get("unconverted"):
        row["unconverted"] = claim["unconverted"]
    return row


def profile(
    question: Any,
    *,
    claims: Iterable[Mapping[str, Any]],
    reviews: Mapping[str, Mapping[str, Any]],
    rejections: Iterable[Mapping[str, Any]] = (),
    examined: int = 0,
    roles: Mapping[str, str] | None = None,
    registry_version: int | None = None,
    registry_sha256: str = "",
    decision_contract_version: int = 1,
    provisional: bool = False,
    blocking: Sequence[str] = (),
) -> dict[str, Any]:
    """Everything known about one question. No verdict, and no threshold that could become one."""
    roles = dict(roles or {})
    kind = str(getattr(question, "kind", ""))

    mine = [c for c in claims if str(c.get("question_id")) == str(question.id)]
    reviewed = [c for c in mine if str(c.get("claim_id")) in reviews]
    verified = [c for c in reviewed
                if str(reviews[str(c["claim_id"])].get("verdict")) == USABLE_REVIEW]

    # Not zero verified claims: a claim nobody has read yet is not a claim a reader rejected, and
    # counting it either way would make a profile say something stage 5 has not established.
    awaiting_review = len(mine) - len(reviewed)
    not_usable: dict[str, int] = {}
    for claim in reviewed:
        verdict = str(reviews[str(claim["claim_id"])].get("verdict"))
        if verdict != USABLE_REVIEW:
            not_usable[verdict] = not_usable.get(verdict, 0) + 1

    results = [result_of(c, kind, role=roles.get(str(c.get("source_class")), ""))
               for c in verified]
    # Sorted so a rebuild produces the same bytes and therefore the same hash.
    results.sort(key=lambda r: (str(r.get("source_id")), str(r.get("claim_id"))))

    direction: dict[str, int] = {}
    for claim in verified:
        stance = str(claim.get("stance") or "")
        direction[stance] = direction.get(stance, 0) + 1

    for_classes: dict[str, int] = {}
    against_classes: dict[str, int] = {}
    for claim in verified:
        stance = str(claim.get("stance"))
        if stance == "QUALIFIES":
            continue
        bucket = against_classes if stance == AGAINST else for_classes
        klass = str(claim.get("source_class") or "")
        bucket[klass] = bucket.get(klass, 0) + 1

    rejected: dict[str, int] = {}
    for row in rejections:
        record = row.get("record") or {}
        if str(record.get("question_id") or row.get("question_id")) != str(question.id):
            continue
        reason = str(row.get("failure") or "?")
        rejected[reason] = rejected.get(reason, 0) + 1

    sources = sorted({str(c.get("source_id")) for c in verified if c.get("source_id")})

    built: dict[str, Any] = {
        "question_id": question.id,
        "kind": kind,
        # `null` for a profile with results, `NO_VERIFIED_CLAIM` for one without. Never a verdict.
        "state": None if results else NO_VERIFIED_CLAIM,
        "results": results,
        "direction_count": dict(sorted(direction.items())),
        # Never a count of datasets. No string comparison establishes one.
        "linkage": "unestablished",
        "sample_labels": sorted({str(c.get("sample")) for c in verified if c.get("sample")}),
        "coverage": {"sources": len(sources), "examined": examined},
        "sources": sources,
        "gate_rejected": dict(sorted(rejected.items(), key=lambda kv: (-kv[1], kv[0]))),
        "awaiting_review": awaiting_review,
        "reviewed_not_usable": dict(sorted(not_usable.items())),
        "by_class": {"for": dict(sorted(for_classes.items())),
                     "against": dict(sorted(against_classes.items()))},
        # A profile built from evidence that is still arriving can still change, so it is labelled and
        # may not be adjudicated.
        "provisional": bool(provisional) or awaiting_review > 0,
        "blocking": sorted(set(blocking) | ({"awaiting_review"} if awaiting_review else set())),
        "decision_contract_version": decision_contract_version,
        "registry_version": registry_version,
        "registry_sha256": registry_sha256,
    }
    built["profile_sha256"] = _digest(built)
    return built


def not_applicable(question: Any, *, see: Sequence[str] = ()) -> dict[str, Any]:
    """An operational question's row. It appears in the report and receives no verdict."""
    return {
        "question_id": question.id,
        "kind": str(getattr(question, "kind", "")),
        "state": NOT_APPLICABLE,
        "reason": "no paper can settle a choice belonging to the consuming system",
        "see": list(see),
    }
