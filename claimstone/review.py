"""Stage 5 — review: an adversarial second read of every claim the gate accepted.

On the corpus that motivated this project a second read marked **54 of 292 claims OVERSTATED and 21
AMBIGUOUS — 25.7%** after they had already passed the quote check (D5). It is the control that pays best,
and the reason is structural: the gate verifies that a quote is present, and nothing mechanical can verify
that the claim the quote supports is the claim that was made.

**There is no gate here.** Nothing to check mechanically, which is exactly why the stage exists. The only
code-held rule is the different-reader refusal, and the only shape is the schema.

**The reviewer must not be the extractor**, and that is enforced rather than requested: a reader sharing the
extractor's blind spots is not adversarial, it is a second opinion from the same opinion. Matched on backend
and model and not on harness version — `claude-cli` at two CLI versions is the same model and the same blind
spots. Refused at build where the asked-for reader is known, and again at harvest, because only the results
say who answered.

`claims.jsonl` is never touched: it is append-only and belongs to stage 4. This stage owns `reviews.jsonl`.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from claimstone import model_call
from claimstone.store import Store

VERDICTS = ("SUPPORTED", "OVERSTATED", "AMBIGUOUS", "NOT_APPLICABLE")

# A verdict word and one sentence. Short on purpose: the expensive half of this call is the chunk going in.
MAX_OUTPUT_TOKENS = 400

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "reason"],
    "properties": {
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "reason": {"type": "string"},
    },
}

SYSTEM = f"""You are a second reader. Somebody else read a passage and made a claim from it, quoting a span
of the passage as evidence. The quote has already been checked, in code, to be an exact substring of the
passage. Your job is the part no code can do: decide whether the claim is what that quote supports, **in the
context of the whole passage**.

You are given the question, the claim, the quote, and the passage entire.

  SUPPORTED        the claim is what the quote supports, in the context it came from
  OVERSTATED       the quote is real and says less than the claim
  AMBIGUOUS        the quote will bear the claim and will also bear its opposite
  NOT_APPLICABLE   the quote does not speak to the question cited

Read the passage around the quote before deciding. A sentence reading "we find no effect", preceded by
"unlike prior work, we do not assume", means the opposite of how it reads alone — and that is the failure the
mechanical check cannot see, because the substring is exact.

`OVERSTATED` is the most useful thing you can say, and saying it is not a criticism of anybody. It is a case
where a mechanical check passed something a reader would not, which is the whole reason you are here. Do not
soften it, and do not reach for `SUPPORTED` because the claim sounds plausible: the question is whether
**this quote, in this passage**, carries it.

Return a JSON object with `verdict` and one sentence of `reason`. The reason names what the quote actually
says where it differs from the claim. Nothing else — no prose, no code fence."""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def reader_of(row: dict[str, Any]) -> tuple[str, str]:
    """Who read this. A reader is a backend and a model; the harness version is not part of it."""
    return str(row.get("backend") or ""), str(row.get("model") or "")


def _identity(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "backend": str(row.get("backend") or ""),
        "model": str(row.get("model") or ""),
        "harness_version": str(row.get("harness_version") or ""),
    }


class SameReader(RuntimeError):
    """The reviewer is the extractor. A second opinion from the same opinion is not a control."""


def review_unit(question: Any, claim: dict[str, Any], chunk_text: str) -> str:
    """Question, claim, quote, and the **whole chunk** — which is the expensive part and the point."""
    return (
        f"QUESTION {question.id}: {question.text}\n\n"
        f"CLAIM: {claim.get('claim')}\n\n"
        f"QUOTE: {claim.get('evidence_quote')}\n\n"
        f"THE PASSAGE ENTIRE:\n{chunk_text}"
    )


def build(
    project: Any,
    store: Store,
    *,
    batch: str,
    reviewer: tuple[str, str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """One review unit per accepted claim that has no review yet.

    `reviewer` names the reader that will be asked, so the claims it may not judge are excluded here rather
    than discovered after the calls are paid for.
    """
    reviewed = set(store.latest_by("reviews.jsonl", "claim_id"))
    chunks = store.latest_by("chunks.jsonl", "chunk_id")
    questions = {q.id: q for q in project.questions}

    units: list[dict[str, Any]] = []
    same_reader = missing_chunk = unknown_question = 0

    for claim in store.latest_by("claims.jsonl", "claim_id").values():
        if str(claim.get("claim_id")) in reviewed:
            continue
        if reviewer is not None and reader_of(claim) == reviewer:
            same_reader += 1
            continue
        question = questions.get(str(claim.get("question_id")))
        if question is None:
            unknown_question += 1
            continue
        chunk = chunks.get(str(claim.get("chunk_id")))
        if chunk is None:
            # The chunk is the unit. Reviewing a claim without the passage it came from would be asking the
            # reader to judge the quote alone, which is the thing the gate already did.
            missing_chunk += 1
            continue

        unit = model_call.work_unit(
            lane="review",
            system=SYSTEM,
            user=review_unit(question, claim, str(chunk["text"])),
            response_schema=SCHEMA,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            registry_version=getattr(project, "registry_version", 0),
            source_id=str(claim.get("source_id") or ""),
            chunk_id=str(claim.get("chunk_id") or ""),
        )
        # Which claim this judges, and who made it. Carried on the request so harvest needs no join and the
        # different-reader refusal can be made against the row that arrives.
        unit["claim_id"] = str(claim.get("claim_id"))
        unit["question_id"] = str(claim.get("question_id"))
        unit["extracted_by"] = _identity(claim)
        units.append(unit)
        if limit is not None and len(units) >= limit:
            break

    written = model_call.Queue(store, lane="review", batch=batch).write(units)
    return {
        "batch": batch,
        "units": written,
        "already_reviewed": len(reviewed),
        # Named separately because the remedies differ: a different reviewer, a normalize run, a registry bump.
        "same_reader": same_reader,
        "missing_chunk": missing_chunk,
        "unknown_question": unknown_question,
        "prompt_chars": sum(len(u["system"]) + len(u["user"]) for u in units),
    }


def harvest(project: Any, store: Store, *, batch: str) -> dict[str, Any]:
    """Write `reviews.jsonl` from the drained verdicts. Opens no socket; touches no other ledger."""
    queue = model_call.Queue(store, lane="review", batch=batch)
    requests = {str(u["call_id"]): u for u in queue.requests()}
    held = set(store.latest_by("reviews.jsonl", "claim_id"))

    reviewed = already = unanswered = 0
    verdicts: dict[str, int] = {}

    for row in queue.attempts():
        if row.get("rejudged_from"):
            continue
        request = requests.get(str(row.get("call_id")))
        if request is None:
            continue
        if not row.get("ok") or not isinstance(row.get("output"), dict):
            # Not a verdict. An unreviewed claim is neither supported nor unsupported: counting it either way
            # would give the verdict rules an input nobody checked, or make a verdict fall because this stage
            # had not finished.
            unanswered += 1
            continue

        extracted = request.get("extracted_by") or {}
        if (str(extracted.get("backend")), str(extracted.get("model"))) == reader_of(row):
            raise SameReader(
                f"claim {request.get('claim_id')!r} was extracted by "
                f"{extracted.get('backend')}/{extracted.get('model')} and reviewed by the same reader. "
                f"A second opinion from the same opinion is not a control."
            )

        claim_id = str(request.get("claim_id"))
        if claim_id in held:
            already += 1
            continue
        held.add(claim_id)
        verdict = str(row["output"].get("verdict"))
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
        store.append("reviews.jsonl", {
            "claim_id": claim_id,
            "question_id": request.get("question_id"),
            "verdict": verdict,
            "reason": row["output"].get("reason"),
            "reviewed_by": _identity(row),
            # Copied rather than left to a join: a row saying who produced it and who judged it can be
            # argued with on its own.
            "extracted_by": extracted,
            "call_id": row.get("call_id"),
            "reviewed_at": _now(),
        })
        reviewed += 1

    return {
        "batch": batch,
        "reviewed": reviewed,
        "already_held": already,
        "calls_without_an_answer": unanswered,
        "verdicts": dict(sorted(verdicts.items(), key=lambda kv: -kv[1])),
    }
