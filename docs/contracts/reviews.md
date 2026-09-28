# `reviews.jsonl` — the contract

Written by stage 5 (`claimstone review --harvest`). Append-only, keyed by `claim_id`, owned by this stage.
**`claims.jsonl` is never touched**: it is append-only and belongs to stage 4.

An adversarial second read of every claim the mechanical gate accepted. On the corpus that motivated this
project it marked **54 of 292 claims OVERSTATED and 21 AMBIGUOUS — 25.7%** after they had passed the quote
check. The gate verifies that a quote is present; nothing mechanical can verify that the claim the quote
supports is the claim that was made.

| field | meaning |
|---|---|
| `claim_id`, `question_id` | the claim this judges |
| `verdict` | `SUPPORTED`, `OVERSTATED`, `AMBIGUOUS`, `NOT_APPLICABLE` |
| `reason` | one sentence naming what the quote actually says where it differs from the claim |
| `reviewed_by` | `{backend, model, harness_version}` — who judged |
| `extracted_by` | `{backend, model, harness_version}` — who produced the claim |
| `call_id`, `batch`, `result_key`, `reviewed_at` | which call, originating batch and reader, and when |

## The verdicts

| | |
|---|---|
| `SUPPORTED` | the claim is what the quote supports, in the context it came from |
| `OVERSTATED` | the quote is real and says less than the claim |
| `AMBIGUOUS` | the quote will bear the claim and will also bear its opposite |
| `NOT_APPLICABLE` | the quote does not speak to the question cited |

An `OVERSTATED` row is not deleted and not hidden. It is the most informative row in the ledger, because it
is a case where a mechanical check passed something a reader would not.

## The reviewer may not be the extractor

Enforced in code, because it is exactly the rule inattention breaks: a reader sharing the extractor's blind
spots is not adversarial, it is a second opinion from the same opinion.

Matched on **backend and model**, not on harness version — `claude-cli` at two CLI versions is the same model
and the same blind spots. Refused twice: at build, where `--reviewer backend/model` names the reader that will
be asked and the claims it may not judge are excluded before a call is paid for; and at harvest, because only
a result says who actually answered.

`extracted_by` is copied onto the row rather than left to a join, so a row saying who produced it and who
judged it can be argued with on its own.

## The review unit is the whole chunk

Question, claim, quote, and **the passage entire**. The chunk is the expensive part and it is the point: a
sentence reading "we find no effect", preceded by "unlike prior work, we do not assume", means the opposite of
how it reads alone — and the mechanical gate cannot catch context-stripping, because the substring is exact.

There is no sampling. Every accepted claim is read.

## An unreviewed claim is not a supported claim

A claim with no review row is **awaiting review**, which stage 6 reports and may not use. Counting it as
supported would give the verdict rules an input nobody checked; counting it as unsupported would make a
verdict fall because stage 5 had not finished. It is the same shape as stage 3's `awaiting_normalize`.

## The report is the precision side, and says so

`review-report` groups by `extracted_by` and states the reviewers. It reports three of the four numbers a
comparison of extractors needs:

- verified useful results — proposed, passed the gate, and read as `SUPPORTED`
- gate rejections by reason — how much was proposed badly
- the `OVERSTATED` share — how much was proposed beyond its evidence

**It cannot report misses**, and names that rather than omitting it. Measuring results present in a chunk that
a backend did not propose needs a blind, human-adjudicated reference sample, and none exists. The reason this
matters is one sentence: **a backend emitting one bland, safe, well-quoted claim per chunk wins the
`OVERSTATED` rate while missing ten material results.** Precision without recall rewards timidity.

And one fixed reviewer controls reviewer *variation* while keeping reviewer *bias*: a reviewer that
systematically accepts a certain kind of overreach flatters every extractor equally. The fixed reviewer makes
the comparison internally consistent, not correct.

## Current reviews and replay (D47)

Use `review.current(store)`, not a raw latest-row lookup. The claim must still be accepted and the
current review answer must still contain the same verdict and reason. Invalidating an answer makes
its cached review unusable immediately. Harvest uses current results, including rejudgements, and
appends a changed review once. The historical review remains auditable. Legacy imports with no
model-call provenance retain their earlier interpretation.

Identical review prompts merge explicit targets; a valid answer fans out to all eligible annotations.
The reviewer is checked separately against each extractor. A changed annotation id never inherits
another annotation's review. This corrects identity and replay; the review prompt still needs R10's
full-result metadata repair before it can attest that metadata.
