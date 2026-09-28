# `calls/<lane>/<batch>/` — the contract

Written by stage 4 (extract) and stage 5 (review); drained by `claimstone model-run`.

```
requests.jsonl   the work units, written by the stage
results.jsonl    append-only, written by a runner
raw/<sha256>.txt the response bytes, content-addressed
```

**A model call is not reproducible. It is auditable.** Sampling, model updates and a CLI's own
harness all break sameness of answer, and no amount of recording fixes that. What is promised and
checked in code is narrower and useful: this exact prompt was sent, this exact response came back,
and here are the hashes.

## The work unit

| field | meaning |
|---|---|
| `call_id` | `sha256(lane \| schema_version \| prompt_sha256 \| max_output_tokens \| schema_sha256)` |
| `lane` | `extract` or `review` |
| `schema_version`, `registry_version` | the row shape, and the question registry it was built against |
| `system` | the stable prefix: registry plus instructions, identical across the lane |
| `user` | the volatile part: one chunk, or one claim and its quote |
| `response_schema` | the shape the answer must satisfy, validated by `jsonshape` |
| `max_output_tokens` | the cap. Part of `call_id`: raising it makes a different call |
| `source_id`, `chunk_id` | where this unit's input came from |
| `asked_by` | **every** `{source_id, chunk_id}` that asked this call — see below |
| `prompt_sha256` | `sha256(rendered_prompt(system, user))` — the prompt and nothing else |
| `schema_sha256` | `sha256(canonical(response_schema))` |
| `created_at` | UTC, ISO 8601, seconds |

`system` and `user` are separate so a backend that prices cached input separately can charge the
registry once. A runner that concatenates them still works; it pays fifty times over.

### One call, several askers

Two chunks with identical text hash to one `call_id`, and the prompt is paid for once. `asked_by`
is what keeps that from costing provenance: writing a unit whose `call_id` is already queued appends
a row with the new asker merged in, rather than dropping the unit — which is what the first version
did, taking the second chunk's id with it, so a claim really present in that chunk could never be
recorded against it.

Read requests with `store.latest_by(requests_name, "call_id")`, never the raw rows: merging an asker
appends a row, and a drain over raw rows would pay for the same call once per chunk that asked.
`Queue.requests()` does the collapse; `Queue.request_rows()` is for auditing how a list grew.

## The result

| field | meaning |
|---|---|
| `call_id`, `result_key` | the unit this answers, and `call_id\|backend\|requested_model` |
| `attempt_no` | which try this was, for this backend |
| `ok` | true only when there is a validated output |
| `backend`, `model`, `harness_version` | who answered, and what sat between the prompt and the model |
| `prompt_sha256` | what the runner says it sent, hashed. `null` when it reports nothing |
| `prompt_verified` | whether that hash matched the request's. See the three states below |
| `output` | the parsed, validated answer, or `null` |
| `schema_errors` | why validation failed, by path |
| `raw_sha256`, `raw_path` | the bytes, always kept |
| `usage` | `input_tokens`, `cached_input_tokens`, `output_tokens` where reported |
| `cost_usd` | `null` means **not priced**, never free |
| `latency_s`, `started_at`, `finished_at` | observed, per call |
| `failure_class`, `detail` | what went wrong |

### The echo check has three outcomes, not two

A first version of this hashed the request's own `system` and `user` and compared the result to the
`prompt_sha256` computed from those same two fields: `hash(x) == hash(x)`, true by construction. A
guarantee that cannot fail is not a guarantee.

So a runner reports `prompt_sent`, and:

| `prompt_sent` | `prompt_verified` | `failure_class` |
|---|---|---|
| matches the request | `true` | none — the check ran and passed |
| differs | `false` | `PROMPT_MISMATCH`, which is the check working |
| not reported | `false` | none — **no check ran**, and the row says so |

`false` is therefore not a failure and not a pass. All three runners in this repository report
`prompt_sent`; `tests/test_runners_contract.py` requires it of every registered backend, because
remembering a shared obligation once per runner is how the fourth runner forgets it.

## Failure classes

Terminal — a retry changes nothing until the request or the backend does:
`NOT_JSON` · `SCHEMA_INVALID` · `REFUSED` · `PROMPT_MISMATCH` · `TRUNCATED`

Transient — the next drain tries again:
`TIMEOUT` · `RATE_LIMITED` · `BACKEND_ERROR` · `EMPTY`

`TRUNCATED` is terminal because raising the cap changes `call_id`: a retry under a bigger cap is a
different call, not a second attempt at this one. An unrecognised class counts as terminal, so a
typo costs a retry rather than a loop.

Truncation is judged **before** emptiness. An answer cut off before it produced a byte would
otherwise be `EMPTY`, which is transient, and it would be retried on every drain for ever — each
retry cut off in the same place.

**None of these ever becomes an empty output.** `EMPTY` is not "the chunk contained no claims" and
`TRUNCATED` is not "the answer was short": both would be assertions about the literature that a
failed call has not earned. Stage 4's rejection ledger is the denominator, and it can only be that
if a failure stays a failure.

## Re-judging what was already paid for

`claimstone model-run --rejudge` re-reads every stored answer under the current rules. It opens
nothing and calls nobody: the bytes are on disk under their hash, so asking what the current
classifier makes of them costs nothing. This is stage 2's `regate`, one module over, and it exists for
the same reason — the first classifier fix here would otherwise have left two answers already paid for
permanently mis-recorded.

D14 governs the row it writes. A re-judgement is **not** an attempt: it carries `rejudged_from`, no
cost and no latency, and `model-report` leaves it out of what the queue cost and how fast it went. It
*is* authoritative about that answer, so latest-wins is right — a tightened schema turns a success
into a failure and the queue says so. A row whose bytes are gone is skipped rather than given an
invented verdict.

The echo check cannot run on stored bytes, because the runner is not there to say what it sent. The
earlier row's `prompt_verified` stands rather than being downgraded by a re-reading that was never in
a position to ask.

## Cost and throughput

`claimstone model-report` sums `results.jsonl`. Two rules, both about not producing a figure that
describes nothing.

**`null` is unpriced, never zero.** A subscription-backed CLI has no per-call price. Such calls are
counted under `unpriced` and excluded from the total, and a backend with both reports the total it
can compute and how many rows it left out.

**Every number is per backend, and the parts add up.** Each bucket reports `attempts` — what was
paid for and waited on — and `calls`, how many distinct calls it answered; a retry is what separates
them. `summary["attempts"]` and `summary["calls"]` are the sums of their parts by construction,
because a report whose parts disagree with its totals is a report nobody can use.
Each bucket's `ok` follows `calls` — distinct calls whose current answer stands valid, so it sums to
`summary["ok"]` — and `attempt_failures_by_class` follows `attempts`, holding every failure that
happened, including ones a retry or a re-judgement later fixed. `attempts_per_hour` counts attempts,
since a timed-out attempt is time the queue spent, and it is the figure that answers how long the rest
will take. The local server runs at about five an hour
where a hosted endpoint finishes the same queue in an afternoon, so there is no aggregate.

## Resuming, and the comparison

`pending(backend=...)` returns units that backend has no result for, plus those whose last result
was transient. So a drain interrupted after two hours resumes rather than restarts.

Identity is the call **and** the backend. Collapsing results on `call_id` alone was the first
version, and it destroyed the one property this boundary exists for: after backend A answered a
batch, draining it with backend B produced nothing, because every call already looked done. Pointing
a second backend at the same `requests.jsonl` now produces a second set of rows whose answers line up
per `call_id` — which is what makes "is backend A better than B at this lane" a question with an
answer, and why D13 refuses to assign a lane to a vendor in advance.

## Authoritative replay (D47)

`result_judge_version 2` records `answer_failure_class`, `answer_refused`, `answer_truncated` and
`judged_schema` on results. Replay preserves transport, refusal, truncation and prompt-mismatch facts
from the original physical attempt, even if a historical rejudgement accidentally cleared them.
Only parsing/schema failures can be repaired by parsing again. A recorded raw hash mismatch becomes
`RAW_HASH_MISMATCH`, never a successful answer. Missing raw bytes remain explicitly skipped.
A schema override is recorded and retained on repeat replay; identical repeat judgements append nothing.
The original requested-reader `result_key` is preserved even when the backend reports a model name.

Review requests additionally carry `review_targets`: each `{claim_id, question_id, extracted_by}`
judged by an identical prompt. Queue merging retains every target. Harvest checks reader independence
for each target, reports excluded own-reader targets and refuses a call with no eligible target.
