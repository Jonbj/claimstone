# `claims.jsonl` and `rejections.jsonl` — the contract

Written by stage 4 (`claimstone extract --harvest`). Append-only. Stage 4 owns both; no other stage
writes them. Stage 6 reads `claims.jsonl`; **`rejections.jsonl` is the denominator** and reading it is
not optional before a rate is quoted.

Both are keyed by an immutable annotation id. Under D47 (`annotation_version 2`), new ids are
`sha256(canonical([2, chunk_id, result_key, harness_version, raw_record]))[:32]`. The complete
model record participates, including optional metadata. Two readers quoting the same passage keep
separate annotations; changing metadata creates a new annotation and does not inherit its review.
These are annotations, not independent studies: source coverage still counts sources.

An existing legacy id is retained only when call, reader and the complete original record match.
A changed record or another reader receives a new id even for an old answer without `result_id`.
Re-gating the identical annotation preserves identity. Separate gate ledgers are logs, not a partition.

## Current decisions and replay (D46)

Use `claim_records.current(store)` for the current accepted and rejected maps. A new gate decision
appends a higher `gate_revision` to whichever ledger its outcome belongs to: a rejection can retire an
old acceptance, and an acceptance can recover an old rejection. An identical decision at the same
instrument version appends nothing. A changed instrument version is recorded once even if its outcome
stays the same. `latest_by` on just one file is a historical view, not the current accepted set.

Legacy rows have revision zero; where both logs contain such a row, the accepted-wins interpretation is
preserved because those logs do not establish cross-file chronology. Higher revisions supersede them.
Every consumer uses the current decision, including profiles, review queues, reports and discovery.

D47 also checks the authoritative extraction answer when reading either ledger. A latest failure,
valid empty answer or changed record makes the old annotation unusable immediately, before harvest.
Its row remains in the historical ledger. `answer_batches` records the batches attesting the identical
annotation; any current matching success in those batches suffices. Imported legacy rows without
model-call history retain their legacy interpretation. Harvest selects current results per reader,
including rejudgements, rather than the first successful physical attempt.

Version 4 verifies whole numeric tokens. `2` cannot come from `-2`, `.2`, `2.7`, `2,000` or `2e3`.
Single-figure fields require both their verbatim form and complete tokens; composite and prose fields
check their asserted figures. Range separators, `reversals-3.7`, spaced leading decimals and implicit
percent retain the measured policies in D25, D38 and D46.

## `claims.jsonl`

| field | meaning |
|---|---|
| `claim_id` | identity, stable across a re-harvest |
| `annotation_version`, `raw_record` | identity instrument and the complete original model record |
| `result_key`, `answer_batches` | reader identity and batches attesting this annotation |
| `result_id` | the model's own id for this result within its answer |
| `question_id`, `stance` | which question, and which way. The stance is admissible for the question's kind |
| `claim` | one sentence, the model's words, about what **this** source establishes |
| `evidence_quote` | an exact substring of the chunk, verified in code |
| `*_as_written` | what the paper wrote: `2.4%`, `(0.008)`, `one week`. The model reports only these |
| `estimate`, `estimate_scale` | the engine's conversion. The model never sees these fields |
| `*_bracketed` | the figure was in parentheses. Whether that is a standard error or a t-statistic is **not** recorded, because nothing here knows |
| `*_bound` | `lower`, `upper` or `approximate`, when the paper hedged: `over 300%`, `all below 65%`, `nearly 6%`. Absent means exact, and it is never inferred from the magnitude |
| `contrast_sides`, `contrast_scale` | the two sides of a contrast in the order written, on one shared scale. No difference is taken: which side is the treatment is not something the string says |
| `unconverted`, `unconverted_why` | auxiliary fields in a notation the engine does not read. The claim stands and the absent value is **named**. Stage 6 may not pool a field listed here |
| `gate_revision` | increasing revision for this annotation across both gate ledgers; absent means zero |
| `claim_gate_version` | which rule set admitted it. Absent means rule set 1, written before the constant existed |
| `chunk_text_sha256` | complete passage identity; obsolete generations and changed legacy context are unusable |
| `source_id`, `chunk_id`, `source_class` | where it came from, and which class weighs it |
| `lane`, `kind_verified` | the question kind the call asked about, and whether that could be checked |
| `call_id`, `backend`, `model`, `harness_version` | which call produced it, and what sat between the prompt and the model |
| `registry_version` | which frozen registry the question came from |
| `harvested_at` | UTC, ISO 8601, seconds |

### The value never came from the model

A paper writes `2.4%` and a numeric field wants `0.024`. As strings they do not match, so a gate checking
the value against the quote would reject a correct record or be loosened until it verified nothing. So
the model reports the as-written form **only**, the gate checks that string against the quote, and
`numbers.py` converts. The value therefore cannot be wrong in a way the quote could not reveal.

A scale is recorded and never assumed. `0.024` may be a fraction, a coefficient or a t-statistic and
nothing here knows which, so its scale is `as_reported`. `2.4 pp` is a difference of percentages and says
so. A notation the engine cannot read is never a `null`: a null would read as "no estimate reported",
which is a claim about the paper that a parser failure has not earned.

Which of the two honest answers it gets depends on the field (D37). An unreadable `estimate_as_written` is
a **rejection** — a claim whose own figure cannot be read has nothing to weigh. An unreadable *auxiliary*
field leaves the claim standing and is **named in `unconverted`**: `t = 5.73` says nothing against the
claim it qualifies, and dropping the claim would also drop it from the coverage denominator that makes
`UNANSWERED_IN_LITERATURE` sayable. 132 claims in the first full round.

A label is stripped, not interpreted. `t = 5.73` and `standard error of 1.90` both convert to a bare
figure at scale `as_reported`, and the label stays in the as-written form for a reader — because whether a
figure is a standard error or a t-statistic is the estimand question this engine has always declined.

A hedge is part of the notation and its bound is recorded. `over 300%` is 3.0 with `bound: lower`, not an
exact 3.0: flattening it would drop an inequality the paper wrote, which is what
`COMPARATIVE_NOT_IN_QUOTE` exists to catch one field over.

### `kind_verified`, the honest third state

`WRONG_KIND` catches a model answering about a question outside the kind the call asked about. A request
that did not record which kind was asked cannot support that check, so the question's own kind is used and
this field is `false` — not a pass and not a failure, exactly as `prompt_verified` works for the echo
check in `docs/contracts/model_calls.md`.

## `rejections.jsonl`

The same fields, plus:

| field | meaning |
|---|---|
| `failure` | which check failed |
| `detail` | the sentence saying why, so the verdict can be argued with |
| `record` | **the model's record, whole and unaltered** |

Nothing is ever partially accepted. A record failing any check goes here entire, because a rejection
nobody can read is not a denominator. `extract-report --show-rejected` prints every one with its claim and
its quote.

### The failure classes

| | |
|---|---|
| `UNKNOWN_QUESTION_ID` | not in the registry |
| `WRONG_KIND` | the question's kind is not the one the call asked about, or receives no verdict at all |
| `QUOTE_NOT_FOUND` | the quote is not an exact substring of the chunk's stored text |
| `VALUE_NOT_IN_QUOTE` | an `*_as_written` form is not in the quote |
| `NUMBER_NOT_IN_QUOTE` | a figure the claim asserts is not in the quote |
| `COMPARATIVE_NOT_IN_QUOTE` | a comparative **class** in the claim is absent from the quote |
| `WRONG_STANCE` | the stance is not admissible for the question's kind |
| `SECONDHAND_CLAIM` | the claim reports what another work found, not what this source establishes |
| `QUOTE_TOO_THIN` | the quote is too short for its claim. **Off by default** — see below |
| `UNPARSEABLE_VALUE` | the engine could not convert an as-written form |

`QUOTE_TOO_THIN` ships disabled. Swept on 66 real claims the ratio rejects nothing from 0 to 34 and one
*true* claim at 35, and the case it was written for is caught by `SECONDHAND_CLAIM` instead. Length is the
wrong instrument for adequacy; the check is declarable per project and defaults to zero. See D25.

### A rejection can be a discovery signal

A `SECONDHAND_CLAIM` names a work the corpus is relying on. `discover --promote-contested` reads these
rejections and admits the named work whatever the citation threshold says, because a work cited once for a
contradiction is worth more than a textbook cited three times. It invents nothing: a name with no
reference is reported, and a name whose surname is in the bibliography while the year is not is reported
as ambiguous. See D26.

## The two ratios

`extract-report` prints them separately and never fused.

**The gate's ratio** is `accepted / proposed`: how much of what a model offered survived invariant 1.
**The corpus's coverage** is `questions with a claim / questions that can receive a verdict` — the
denominator is the registry, so the report needs the project, and without one the coverage is `None` rather
than a number a module invented. An `operational` question is not in the denominator: it receives no
verdict (invariant 2), and counting it would make full coverage unreachable by construction.

Questions with no claim are **named**, because `UNANSWERED_IN_LITERATURE` and `NEVER_ASKED` are different
states and only somebody who can see which questions were asked can tell them apart.

## What no check here establishes

That a quote is in the chunk, and that the claim's figures and comparisons are in the quote. **Not** that
the model read the right row of a table, that `(0.008)` is a standard error rather than a t-statistic, or
that an uncertainty is on the estimate's scale. Those are estimand questions and nothing mechanical
reaches them. Stage 5 is a model reading them, which is not a verification.

## Measured, 2026-09-26

The first harvest, on one question.

```
proposed         66
accepted         63   0.95      SECONDHAND 2 · COMPARATIVE_NOT_IN_QUOTE 1
H02              63 claims from 4 studies   QUALIFIES 38 · SUPPORTS 25 · CONTRADICTS 0
```

**63 claims from four studies, and four is the number that matters.** Ten claims from one paper are one
study; counting them as ten is the vote counting invariant 7 forbids, so `extract-report` counts by
`source_id`.

**0.95 is a floor on the gate's pass rate and not an estimate of it.** One question, one prompt, one
corpus, and rules corrected against these same claims (D25). And `CONTRADICTS 0` is the finding, not the
95%: the gate correctly removed the only contradicting claim because it was secondhand, so the accepted
set holds no evidence against H02 at all while the corpus cites some. See D26.
