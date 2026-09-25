# Stage 5 — review: design

Date: 2026-09-25 · Scope: stage 5 only · Status: approved, not implemented

An adversarial second read of every claim that passed the mechanical gate. On the corpus that
motivated this project it marked **54 of 292 claims OVERSTATED and 21 AMBIGUOUS — 25.7%** after they
had already passed the quote check (D5). It is the control that pays best, and the reason is
structural: the gate verifies that a quote is present, and nothing mechanical can verify that the
claim the quote supports is the claim that was made.

## 1. The one rule that makes it a control

**The reviewer must run on a different model from the one that produced the claim, and this is
enforced rather than requested.** A reader sharing the extractor's blind spots is not adversarial;
it is a second opinion from the same opinion.

For that to be enforceable, a `claims.jsonl` row carries
`extracted_by: {backend, model, harness_version}` — stage 4 writes it from the `model_call` result —
and `review` **refuses** a reviewer whose backend and model match. It is exactly the kind of rule
violated by inattention, so code holds it.

Matching on backend and model, not on harness version: `claude-cli` at two CLI versions is the same
model and the same blind spots.

## 2. The review unit

Question text, the claim, its quote, and **the whole chunk the quote came from**.

The chunk is the expensive part and it is the point. The most valuable thing an adversarial reader
can do is notice that the quote is true and the claim it supports is not — and a sentence reading
"we find no effect" preceded by "unlike prior work, we do not assume" means the opposite of how it
reads alone. **The mechanical gate cannot catch context-stripping, because the substring is exact.**

Cost, measured against the corpus: roughly 309 claims × ~3,000 tokens of input ≈ **$5** on a
frontier model. D5 prescribed compact input because the local model made reading everything
prohibitive; at five dollars that constraint no longer exists, and **there is no sampling**. Every
claim is read.

Output is short: one of four verdicts and one sentence of reason.

| verdict | meaning |
|---|---|
| `SUPPORTED` | the claim is what the quote supports, in the context it came from |
| `OVERSTATED` | the quote is real and says less than the claim |
| `AMBIGUOUS` | the quote will bear the claim and also bear its opposite |
| `NOT_APPLICABLE` | the quote does not speak to the question cited |

## 3. The ledger

`reviews.jsonl`, keyed by `claim_id`, owned by this stage. **`claims.jsonl` is not touched** — it is
append-only and belongs to stage 4.

```json
{"claim_id": "ACA001#c2|H02|1", "question_id": "H02",
 "verdict": "OVERSTATED",
 "reason": "The quote reports a 2.4% mean, not predictive power out of sample.",
 "reviewed_by": {"backend": "claude-cli", "model": "claude-opus-5",
                 "harness_version": "claude 2.1.280"},
 "extracted_by": {"backend": "ollama-cloud", "model": "deepseek-v4.1-flash"},
 "reviewed_at": "…"}
```

`extracted_by` is copied onto the review row rather than left to a join. It is what makes §5's
measurement a single read, and a row that carries who produced it and who judged it can be argued
with on its own.

**Stage 6 uses only claims whose review is `SUPPORTED`**, and counts the rest in its denominator.
An `OVERSTATED` claim is not deleted and not hidden: it is the most informative row in the ledger,
because it is a case where the mechanical gate passed something a reader would not.

## 4. Unreviewed claims are not supported claims

A claim with no review row is **not** treated as reviewed. Stage 6 reports it as awaiting review and
may not use it, in the same shape as stage 3's `awaiting_normalize`: counting an unexamined claim as
supported would give the verdict rules an input nobody checked, and counting it as unsupported would
make a verdict fall because stage 5 had not finished.

## 5. The review rate is the yardstick D13 was waiting for

D13 deferred lane assignment to a measurement and did not say which. This is it.

**The `OVERSTATED` rate per extraction backend answers "which backend extracts better."** Two
backends drain the same `requests.jsonl` (the `model_call` boundary guarantees their results line up
per call), their claims pass the same mechanical gate, and the same reviewer judges both. The
backend whose claims survive an adversarial read more often is better at this lane, and the
difference is a number rather than a preference.

For that to hold, the reviewer must be **held fixed** while the extractor varies — the comparison is
between extractors, and a reviewer that changed with them would measure nothing. `review-report`
therefore groups by `extracted_by` and states the single `reviewed_by` used.

## 6. Module boundaries and CLI

```
review.py  build review units from claims, harvest verdicts, write the ledger.
```

One module. The judgement is the model's; the mechanical part is the different-model refusal and the
schema, and both are small. There is no gate here — nothing to verify mechanically, which is exactly
why this stage exists.

```
claimstone review <project> --batch B                          build the review units
claimstone model-run <project> review --batch B --backend X    drain them
claimstone review <project> --batch B --harvest                write reviews.jsonl
claimstone review-report <project> --batch B                   rates per extraction backend
```

`--harvest` refuses to run when a result's `reviewed_by` matches the `extracted_by` of the claim it
judges, naming both. Refusing at harvest as well as at build is deliberate: the build knows which
backend was *asked*, and only the results know which answered.

## 7. Testing

| file | covers |
|---|---|
| `test_review.py` | units built from claims with the chunk attached; the same-model refusal at build and at harvest; the four verdicts round-tripped; an unreviewed claim reported as awaiting and never as supported; `review-report` grouping by `extracted_by` with one `reviewed_by` |

No test reaches a model. Review units are built and inspected; harvest is fed prepared
`results.jsonl` rows.

## 8. Out of scope, deliberately

**Sampling and stratification.** D5 proposed stratifying by consequence because the local model
could not read everything. At five dollars for the corpus, every claim is read, and a stratification
rule would be a complication bought with nothing.

**Any verdict on a question.** Stage 6. This stage judges claims, one at a time, and never
aggregates.

**Re-review after a claim changes.** A claim cannot change: `claims.jsonl` is append-only and a
re-extraction writes a new claim with a new id, which arrives here unreviewed like any other.
