"""Stage 4 — extract: a chunk becomes claims, each bound to a verified quote.

Two commands around a file boundary, which is honest rather than awkward: `extract` builds work units,
`model-run` drains them on a named backend, `extract --harvest` gates the answers and writes the two
ledgers. Only this module touches a store; `claimgate` is where invariant 1 lives and is pure.

**One call per kind per chunk, not one per question.** The kind's system prompt — the instructions plus
the questions of that kind — is identical across every chunk, which is what a cached-input price applies
to. Four kinds: `effect`, `heterogeneity`, `method`, `premise`. The spec calls these lanes; they are
called kinds here because `model_call.LANES` already means the boundary's two queues, and one name for
two things in one codebase is the defect this project keeps finding. A question of kind `operational`
receives no verdict (invariant 2), so asking about it spends a call on an answer nothing will read.

**A failed call is not an absence of claims.** A call that returned no valid answer says nothing about
the chunk, and counting it as zero claims would be a finding it did not earn. `calls_without_an_answer`
is reported beside the ratios so the denominator is visible.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterable

from claimstone import claimgate, model_call, numbers
from claimstone.store import Store, sha256_text

# The registry's word, not "lane". `model_call.LANES` is ("extract", "review") — the boundary's two
# queues — and the spec's "four lanes" are the four question kinds. One name for two things in one
# codebase is the defect this project keeps finding, so here they are kinds.
KINDS = tuple(claimgate.STANCES_BY_KIND)

# Eight claims of a sentence and a quote each, with room to spare. There is no cap on the number of
# claims: `maxItems: 8` was measured failing 4 of 13 real records holding two thirds of the harvest, and
# a cap on item count is a cost bound dressed as a shape — `max_output_tokens` is that bound and is
# honest about itself, being part of `call_id`. See D22.
MAX_OUTPUT_TOKENS = 2500


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def system_prompt(kind: str, questions: Iterable[Any]) -> str:
    """The kind's stable prefix. Identical for every chunk of that kind, which is the point.

    The paragraph that earns its place is the last one. A model asked whether a passage supports a
    claim will find a way to say yes, and an empty answer has to be as easy to give as a full one —
    measured, 5 of 13 real calls returned `[]`, including three on a prospectus a keyword screen had
    ranked in its top ten. The project exists because "we found no evidence" and "there is no effect"
    are different sentences.
    """
    listed = "\n".join(f"  {q.id}: {q.text}" for q in questions)
    stances = ", ".join(claimgate.STANCES_BY_KIND[kind])
    # Named in the prompt as well as in the schema: a property the instructions do not mention is a field a
    # model fills by guessing what the name means.
    fields = EXTRA_FIELDS.get(kind, {})
    extra = "\n".join(f"  {name:<32} {FIELD_NOTES.get(name, '')}" for name in fields)
    if extra:
        extra = (extra + "\n\nEvery field after `stance` is optional: give it when the passage gives it and "
                 "leave it out otherwise.\nA field ending `_as_written` is copied from the passage exactly as "
                 "written — `2.4%`, not 0.024 —\nbecause the engine converts and a figure you converted "
                 "could be wrong in a way the quote cannot show.")
    return f"""You extract claims from one passage of one document. You judge nothing beyond what the
passage says.

The questions, verbatim from a frozen registry:

{listed}

Return a JSON array. Each element is one claim the passage makes that bears on one of those questions:

  result_id        a short id you choose, distinct per result within this answer. A passage
                   reporting two estimates for one question gives two records, not one
  question_id      one of the ids above, and only those
  claim            one sentence, in your words, stating what THIS passage asserts
  evidence_quote   a span copied EXACTLY from the passage, character for character, containing the
                   assertion. Do not normalise spacing, fix typography, join lines, or trim inside it.
  stance           one of: {stances}
{extra}

Three hard rules, each checked in code, each discarding a whole record when broken.

Every number, percentage, t-statistic and inequality in your `claim` must also appear inside your
`evidence_quote`. The quote must be a literal substring of the passage; a paraphrase is discarded.

And the claim must be what **this** passage establishes, not what it reports another work establishing.
"Smith (1990) found X" is a claim about Smith, which is a source nobody here has read. Contrasting this
passage's own finding with another work is fine.

Return `[]` if the passage bears on none of these questions. An empty array is a complete, correct and
expected answer, and most passages of most papers deserve one. It means "this passage does not address
these questions" — not "there is no effect", and nothing downstream will read it that way. Do not
stretch a passage about something else into a claim about one of these questions.

Output the JSON array and nothing else. No prose, no code fence, no explanation."""


# What each kind is asked for beyond the core five. Every one is **optional**: a chunk reporting an estimate
# and no standard error is ordinary, and requiring the field would reject a claim for something the passage
# does not have.
#
# `*_as_written` means exactly what the paper wrote — `2.4%`, `(0.008)` — and never a converted value. The
# gate checks the as-written string against the quote and `numbers.py` converts, so the value never came from
# the model and cannot be wrong in a way the quote could not reveal.
#
# Measured need: the first complete round produced 3,971 claims and **zero** carried a converted value,
# because this function asked only for the core five. A converter that works cannot improve a stage 6 input
# that does not exist.
EXTRA_FIELDS: dict[str, dict[str, Any]] = {
    "effect": {
        "estimate_as_written": {"type": "string"},
        "uncertainty_as_written": {"type": "string"},
        "horizon_as_written": {"type": "string"},
        "sample": {"type": "string"},
        "design": {"type": "string"},
        "dependence": {"type": "string"},
    },
    "heterogeneity": {
        "moderator": {"type": "string"},
        "high_side": {"type": "string"},
        "low_side": {"type": "string"},
        "contrast_as_written": {"type": "string"},
        "contrast_uncertainty_as_written": {"type": "string"},
        "prespecified": {"type": "boolean"},
    },
    "method": {
        # The two ways the literature answers a methodological requirement. The source's declared `role`
        # comes from sources.yaml and is added by the engine, not asked of the model: which classes are
        # methodological is project data, and reading it off the class id `MET` would be domain knowledge.
        "support_type": {"type": "string", "enum": ["ENDORSEMENT", "DEMONSTRATED_FAILURE"]},
    },
    # `premise`: question_id, stance, claim, evidence_quote. Nothing else.
    "premise": {},
}

# How each extra field is asked for, in the prompt. A schema property the instructions do not mention is a
# field a model fills by guessing what the name means.
FIELD_NOTES: dict[str, str] = {
    "estimate_as_written": "the effect size EXACTLY as the passage writes it: `2.4%`, `0.31`, `13 bps`",
    "uncertainty_as_written": "its standard error, t-statistic or interval, as written: `(0.008)`, `t = 3.4`",
    "horizon_as_written": "over what period, as written: `one week`, `T+63`",
    "sample": "what was studied: `US equities 1996-2008`",
    "design": "how: `panel regression with firm and time fixed effects`",
    "dependence": "how inference handled dependence: `standard errors clustered by firm and week`",
    "moderator": "what the effect varies by: `firm size`",
    "high_side": "the subgroup with the larger effect: `small firms`",
    "low_side": "the subgroup with the smaller one: `large firms`",
    "contrast_as_written": "the two sides as written: `0.31% versus 0.04%`",
    "contrast_uncertainty_as_written": "the contrast's uncertainty, as written: `(t = 3.4)`",
    "prespecified": "true only if the passage says the subgroup was chosen in advance",
    "support_type": "ENDORSEMENT if the passage endorses the requirement, DEMONSTRATED_FAILURE if it shows "
                    "what goes wrong without it",
}


def response_schema(kind: str, questions: Iterable[Any]) -> dict[str, Any]:
    """This kind's question ids, its stances, and the fields its shape asks for. No cap — see D22."""
    return {
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["result_id", "question_id", "claim", "evidence_quote", "stance"],
            "properties": {
                # One record per result, not per question: a chunk reporting three estimates that bear
                # on one question produces three records, and a table row quoted once can support
                # several. Without this, two of them citing the same sentence would collapse into one.
                "result_id": {"type": "string"},
                "question_id": {"type": "string", "enum": [q.id for q in questions]},
                "claim": {"type": "string"},
                "evidence_quote": {"type": "string"},
                "stance": {"type": "string",
                           "enum": list(claimgate.STANCES_BY_KIND[kind])},
                **EXTRA_FIELDS.get(kind, {}),
            },
        },
    }


def _confirmed_sources(store: Store) -> set[str]:
    return {
        str(row.get("source_id"))
        for row in store.latest_by("documents.jsonl", "source_id").values()
        if row.get("fulltext_confirmed")
    }


def _source_classes(store: Store) -> dict[str, str]:
    return {
        str(row.get("source_id")): str(row.get("source_class") or "")
        for row in store.latest_by("documents.jsonl", "source_id").values()
    }


def build(
    project: Any,
    store: Store,
    *,
    batch: str,
    limit: int | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    """One work unit per kind per chunk of every confirmed document.

    `kind` builds one alone, so a lane can be measured on its own budget — without it, testing the gate
    on a kind it has never seen means building all four and draining in request order, which is the
    first document's chunks four times over. `limit` counts **within** each kind, because a limit that
    stopped after the first would measure one lane and call it a sample of four.
    """
    wanted = KINDS if kind is None else (kind,)
    if kind is not None and kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}: {', '.join(KINDS)}")
    confirmed = _confirmed_sources(store)
    chunks = [
        row for row in store.latest_by("chunks.jsonl", "chunk_id").values()
        if str(row.get("source_id")) in confirmed
    ]
    by_kind: dict[str, int] = {}
    units: list[dict[str, Any]] = []

    for kind in wanted:
        questions = [q for q in project.questions if q.kind == kind]
        if not questions:
            continue
        system = system_prompt(kind, questions)
        schema = response_schema(kind, questions)
        for chunk in chunks[:limit] if limit is not None else chunks:
            unit = model_call.work_unit(
                lane="extract",
                system=system,
                user=str(chunk["text"]),
                response_schema=schema,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                registry_version=getattr(project, "registry_version", 0),
                source_id=str(chunk.get("source_id") or ""),
                chunk_id=str(chunk.get("chunk_id") or ""),
            )
            # Which kind this unit belongs to, so harvest knows which rules judge the answer without
            # re-deriving it from the question ids the model chose to use.
            unit["kind"] = kind
            units.append(unit)
            by_kind[kind] = by_kind.get(kind, 0) + 1

    queue = model_call.Queue(store, lane="extract", batch=batch)
    written = queue.write(units)
    return {
        "batch": batch,
        "units": written,
        "chunks": len(chunks),
        "sources": len(confirmed),
        "by_kind": by_kind if written else {},
        "prompt_chars": sum(len(u["system"]) + len(u["user"]) for u in units),
    }


def claim_id(chunk_id: str, question_id: str, quote: str, result_id: str = "") -> str:
    """Stable across a re-harvest, so gating the same answer twice does not double a claim.

    `result_id` joins the hash only when the record supplies one. A batch built before the field existed
    cannot, and re-deriving every stored claim's id would write the already-harvested ones a second time
    for nothing — the same reasoning as `kind_verified`. Two records sharing a quote and supplying no
    result_id therefore still collapse, which is a known limit of those batches and not of this one.
    """
    parts = [chunk_id, question_id, quote] if not result_id else [
        chunk_id, question_id, result_id, quote]
    return sha256_text("|".join(parts))[:16]


def harvest(project: Any, store: Store, *, batch: str) -> dict[str, Any]:
    """Gate every drained answer into `claims.jsonl` or `rejections.jsonl`. Opens no socket.

    Re-runnable at no cost after a gate change — the arrangement `gate-audit`,
    `normalize --confirm-audit` and `model-run --rejudge` already use, for the same reason: the answers
    are on disk and re-reading them costs nothing.
    """
    queue = model_call.Queue(store, lane="extract", batch=batch)
    requests = {str(u["call_id"]): u for u in queue.requests()}
    chunks = store.latest_by("chunks.jsonl", "chunk_id")
    classes = _source_classes(store)
    seen = set(store.latest_by("claims.jsonl", "claim_id"))
    seen_rejections = set(store.latest_by("rejections.jsonl", "claim_id"))

    thresholds = dict(getattr(project, "extraction", {}) or {})
    comparatives = thresholds.pop("comparatives", None)

    proposed = accepted = rejected = unanswered = kind_unverified = already = 0
    failures: dict[str, int] = {}

    for row in queue.attempts():
        if row.get("rejudged_from"):
            continue
        request = requests.get(str(row.get("call_id")))
        if request is None:
            continue
        if not row.get("ok") or row.get("output") is None:
            unanswered += 1
            continue

        # Every chunk that asked for this call, not only the one whose id the request happens to
        # carry: identical chunks are one call and every one of them is a place the answer came from.
        askers = request.get("asked_by") or [
            {"source_id": request.get("source_id"), "chunk_id": request.get("chunk_id")}
        ]
        for record in row["output"]:
            for asker in askers:
                chunk_id = str(asker.get("chunk_id") or "")
                chunk = chunks.get(chunk_id)
                if chunk is None:
                    continue
                proposed += 1
                identifier = claim_id(chunk_id, str(record.get("question_id")),
                                      str(record.get("evidence_quote")),
                                      str(record.get("result_id") or ""))
                # WRONG_KIND catches a model answering about a question outside the kind it was asked
                # about. A request that never recorded which kind was asked cannot support that check,
                # so the question's own kind is used and the claim says the check did not run — the
                # same honest third state as `prompt_verified`, rather than inventing a lane or
                # rejecting a whole batch that predates the field and was already paid for.
                asked_kind = str(request.get("kind") or "")
                kind_verified = bool(asked_kind)
                if not kind_verified:
                    question = next(
                        (q for q in project.questions if q.id == record.get("question_id")), None)
                    asked_kind = getattr(question, "kind", "") or ""
                    kind_unverified += 1
                verdict = claimgate.check(
                    record, chunk=str(chunk["text"]), questions=project.questions,
                    lane=asked_kind,
                    comparatives=comparatives, thresholds=thresholds or None,
                )
                common = {
                    "claim_id": identifier,
                    "call_id": row.get("call_id"),
                    "backend": row.get("backend"),
                    "model": row.get("model"),
                    "harness_version": row.get("harness_version"),
                    "source_id": str(asker.get("source_id") or ""),
                    "chunk_id": chunk_id,
                    "source_class": classes.get(str(asker.get("source_id") or ""), ""),
                    "lane": asked_kind,
                    # False means the request did not record which kind was asked, so no kind check
                    # ran. It is not a pass and it is not a failure.
                    "kind_verified": kind_verified,
                    "registry_version": request.get("registry_version"),
                    "claim_gate_version": claimgate.CLAIM_GATE_VERSION,
                    "harvested_at": _now(),
                }
                converted, unreadable = numbers.convert(record) if verdict.ok else (record, [])
                if unreadable:
                    # A conversion the engine cannot perform is never a null: a null would read as "no
                    # estimate reported", which is a claim about the paper that a parser failure has not
                    # earned. Which of the two honest answers it gets depends on the field.
                    fields = [name for name in numbers.NUMERIC_FIELDS + numbers.COMPOSITE_FIELDS
                              if any(problem.startswith(f"{name}:") for problem in unreadable)]
                    blocking = [name for name in fields
                                if name in numbers.FIELDS_REQUIRED_TO_CONVERT]
                    if blocking:
                        # The claim's own figure could not be read, so there is nothing to weigh.
                        verdict = claimgate.Verdict(
                            False, "UNPARSEABLE_VALUE", "; ".join(unreadable), record)
                    else:
                        # An auxiliary field in a notation the engine does not read. The claim keeps its
                        # verified quote and its as-written form, the absent machine value is named
                        # rather than nulled, and stage 6 may not pool what is named here.
                        converted["unconverted"] = fields
                        converted["unconverted_why"] = "; ".join(unreadable)

                if verdict.ok:
                    if identifier in seen:
                        already += 1
                        continue
                    seen.add(identifier)
                    store.append("claims.jsonl", common | converted)
                    accepted += 1
                else:
                    failures[verdict.failure or "?"] = failures.get(verdict.failure or "?", 0) + 1
                    if identifier in seen_rejections:
                        already += 1
                        continue
                    seen_rejections.add(identifier)
                    # The record whole, so a rejection is examinable rather than merely counted.
                    store.append("rejections.jsonl", common | {
                        "failure": verdict.failure,
                        "detail": verdict.detail,
                        "record": record,
                    })
                    rejected += 1

    return {
        "batch": batch,
        "proposed": proposed,
        # What was newly written. `already_held` is the rest of `proposed`, so "0 accepted" beside
        # "SECONDHAND_CLAIM 2" stops reading as a contradiction on a re-harvest.
        "accepted": accepted,
        "rejected": rejected,
        "already_held": already,
        # Not zero claims: a call with no valid answer says nothing about its chunk.
        "calls_without_an_answer": unanswered,
        "kind_unverified": kind_unverified,
        "failures": dict(sorted(failures.items(), key=lambda kv: -kv[1])),
    }
