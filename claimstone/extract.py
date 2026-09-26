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
    return f"""You extract claims from one passage of one document. You judge nothing beyond what the
passage says.

The questions, verbatim from a frozen registry:

{listed}

Return a JSON array. Each element is one claim the passage makes that bears on one of those questions:

  question_id      one of the ids above, and only those
  claim            one sentence, in your words, stating what THIS passage asserts
  evidence_quote   a span copied EXACTLY from the passage, character for character, containing the
                   assertion. Do not normalise spacing, fix typography, join lines, or trim inside it.
  stance           one of: {stances}

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


def response_schema(kind: str, questions: Iterable[Any]) -> dict[str, Any]:
    """Only this kind's question ids and only its stances. No cap on the claim count — see D22."""
    return {
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["question_id", "claim", "evidence_quote", "stance"],
            "properties": {
                "question_id": {"type": "string", "enum": [q.id for q in questions]},
                "claim": {"type": "string"},
                "evidence_quote": {"type": "string"},
                "stance": {"type": "string",
                           "enum": list(claimgate.STANCES_BY_KIND[kind])},
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


def build(project: Any, store: Store, *, batch: str, limit: int | None = None) -> dict[str, Any]:
    """One work unit per lane per chunk of every confirmed document."""
    confirmed = _confirmed_sources(store)
    chunks = [
        row for row in store.latest_by("chunks.jsonl", "chunk_id").values()
        if str(row.get("source_id")) in confirmed
    ]
    by_kind: dict[str, int] = {}
    units: list[dict[str, Any]] = []

    for kind in KINDS:
        questions = [q for q in project.questions if q.kind == kind]
        if not questions:
            continue
        system = system_prompt(kind, questions)
        schema = response_schema(kind, questions)
        for chunk in chunks:
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
            if limit is not None and len(units) >= limit:
                break

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


def claim_id(chunk_id: str, question_id: str, quote: str) -> str:
    """Stable across a re-harvest, so gating the same answer twice does not double a claim."""
    return sha256_text(f"{chunk_id}|{question_id}|{quote}")[:16]


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
                                      str(record.get("evidence_quote")))
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
                    "harvested_at": _now(),
                }
                converted, unreadable = numbers.convert(record) if verdict.ok else (record, [])
                if unreadable:
                    # A conversion the engine cannot perform is a recorded rejection and never a null:
                    # a null would read as "no estimate reported", which is a claim about the paper
                    # that a parser failure has not earned.
                    verdict = claimgate.Verdict(
                        False, "UNPARSEABLE_VALUE", "; ".join(unreadable), record)

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
