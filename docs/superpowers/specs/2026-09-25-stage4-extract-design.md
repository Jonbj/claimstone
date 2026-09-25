# Stage 4 — extract: design

Date: 2026-09-25 · Scope: stage 4 only · Status: approved, not implemented

Where invariant 1 lives. Chunks become records bound to verbatim quotes, verified in code, and
everything that fails verification is kept rather than softened.

It depends on the verdict contract (D16) rather than the reverse: what must be extracted follows
from what a verdict will do with it, and a claim bound to a quote is not the same artifact as a
study result with an estimand and a variance.

## 1. Four call shapes, one per kind

D16 gave each kind of question its own verdict rule, and the rules need different evidence. So a
chunk produces **one call per kind** — four, since `operational` questions generate none — and each
prompt lists only the questions of its kind and asks only for its schema, which `jsonshape`
validates strictly.

On the measured corpus: 86 chunks × 4 lanes ≈ **344 calls**, about $0.60 on a hosted open model.
D4 found harvest per call roughly constant regardless of window, so more focused calls yield more,
not less — and a prompt naming five effect questions is a better prompt than one naming
twenty-eight heterogeneous ones.

A useful side effect: **four stable prefixes instead of one.** Each lane's `system` — instructions
plus the questions of that kind — is identical across every chunk, so a backend that prices cached
input pays for it once per lane rather than once per call.

### `effect` — a study result

What the model returns — **as-written forms only**:

```json
{"result_id": "r1", "question_id": "H02", "stance": "SUPPORTS",
 "claim": "News sentiment predicts next-week abnormal returns.",
 "evidence_quote": "…net sentiment of 2.4% (0.008) over one week…",
 "estimate_as_written": "2.4%",
 "uncertainty_as_written": "(0.008)",
 "horizon_as_written": "one week",
 "sample": "US equities 1996-2008",
 "design": "panel regression with firm and time fixed effects",
 "dependence": "standard errors clustered by firm and week"}
```

**One record per result, not per question.** A chunk reporting three estimates that bear on H02
produces three records with distinct `result_id`s. A record per `(chunk, question)` would force the
second and third into the first or drop them, and the record is the unit of evidence.

The stored row is a **different shape**: the engine adds `estimate`, `scale` and `uncertainty` by
converting the as-written forms, and the model never sees those fields. That is the whole of §2.

### `heterogeneity` — a subgroup contrast

```json
{"result_id": "r1", "question_id": "H22", "stance": "SUPPORTS",
 "moderator": "firm size", "high_side": "small firms", "low_side": "large firms",
 "contrast_as_written": "0.31% versus 0.04%",
 "contrast_uncertainty_as_written": "(t = 3.4)",
 "prespecified": true,
 "claim": "…", "evidence_quote": "…"}
```

**Revised 2026-09-25.** An earlier version asked for `absent_case_reported` and a rule required it.
A review established that this is not a statement about moderation at all: **an effect can differ
materially between two subgroups that are both non-zero**, so a reported absent case is neither
necessary nor sufficient. What establishes moderation is the contrast and its uncertainty, and
whether the subgroup analysis was planned or found.

### `method` — an endorsement or a demonstrated failure

```json
{"result_id": "r1", "question_id": "H28", "stance": "SUPPORTS",
 "support_type": "ENDORSEMENT",
 "claim": "…", "evidence_quote": "…"}
```

`support_type` is `ENDORSEMENT` or `DEMONSTRATED_FAILURE` — the two ways the literature answers a
methodological requirement. The source's **declared `role`** comes from `sources.yaml` and is added
by the engine, not asked of the model: which classes are methodological is project data, and reading
it off the class id `MET` would be domain knowledge in the package.

### `premise` — a statement or a contradiction

`question_id`, `stance`, `claim`, `evidence_quote`. Nothing else.

## 2. Numbers exist twice, and the model does not convert

A paper writes `2.4%`; a numeric field wants `0.024`. As strings they do not match, so an exact
substring gate would reject a correct record — or be loosened until it verified nothing.

So **the model reports only the as-written form** and the engine converts, deterministically and in
code. The gate checks that the as-written string is in the quote; the value never came from the model
and so cannot be wrong in a way the quote cannot reveal.

**Revised 2026-09-25.** The first version had the model report both forms and added a sixth gate
check comparing them — the engine's conversion against the model's. A review pointed out the check is
redundant if the engine alone computes the value, and it is right: the check existed only because I
had asked for a field nobody needed. Removing the field removes the check and the design gets
smaller. What the check would have caught — a model that misread a table — is not addressed here at
all, and pretending it was is worse than the gap.

## 3. The gate

Six checks, in order, all code and no judgement:

| | check | failure |
|---|---|---|
| 1 | `question_id` exists **and its kind matches the lane of the call** | `UNKNOWN_QUESTION_ID`, `WRONG_KIND` |
| 2 | `evidence_quote` is an exact substring of the chunk's text | `QUOTE_NOT_FOUND` |
| 3 | every `*_as_written` field is an exact substring of the quote | `VALUE_NOT_IN_QUOTE` |
| 4 | every numeral in `claim` appears in the quote | `NUMBER_NOT_IN_QUOTE` |
| 5 | every comparative **class** in `claim` is present in the quote | `COMPARATIVE_NOT_IN_QUOTE` |
| 6 | `stance` is admissible for the question's kind | `WRONG_STANCE` |
| 7 | every as-written form the engine cannot convert | `UNPARSEABLE_VALUE` |

Check 2 compares against `chunks.jsonl`'s stored `text`, which stage 3 guarantees is byte-for-byte
what the model was shown. Rendering the chunk a second time here would turn any difference between
the two renderings into the rejection of a true claim.

**What no check here establishes.** The gate verifies that a quote is present in the chunk and that
the claim's numbers and comparisons are in the quote. It does not establish that the model read the
right row of the table, that `(0.008)` is a standard error rather than a t-statistic, or that the
uncertainty is on the same scale as the estimate. Those are estimand questions and nothing mechanical
reaches them. The project's prose has been implying otherwise, and stage 5 exists because of the gap
— but stage 5 is a model reading, not a verification.

### What counts as a numeral and a comparative

Checks 4 and 5 need definitions, or an implementer invents them.

A **numeral** is a run matching `[-−]?\d[\d,.]*(?:[eE][-−+]?\d+)?%?` — digits, optional thousands
separators and decimal point, optional scientific exponent, optional percent, and a leading ASCII
hyphen **or Unicode minus**, which typeset papers use and an earlier draft of this rule did not
match. Written-out numbers (`two-thirds`) are not numerals and are not checked: the rule exists to
stop a fabricated figure, and a fabricated figure is written in digits.

A **comparative** is matched by **class, not by phrase**, and this is a correction. Comparing phrases
literally rejects a correct record whose claim says `exceeds` where the quote says `is greater than`
— a false rejection for a synonym. So `extraction.comparatives` in `sources.yaml` declares a mapping
from phrase to class, and the check asks whether the class is present:

```yaml
extraction:
  comparatives:
    ">":  [more than, higher than, greater than, exceeds, outperforms, above]
    "<":  [less than, lower than, below, underperforms]
    ">=": [at least, no less than]
    "<=": [at most, no more than]
```

The symbols `>`, `<`, `≥`, `≤` map to their own classes. A claim introducing a class the quote does
not contain is rejected; a claim using a different word for a class the quote does contain is not.
The mapping is English by default and declared per project, for the reason the content gate already
established.

The same section declares which stances a kind may use, because they are not the same:

| kind | admissible `stance` |
|---|---|
| `effect` | `SUPPORTS`, `CONTRADICTS`, `QUALIFIES` |
| `heterogeneity` | `SUPPORTS`, `CONTRADICTS`, `QUALIFIES` |
| `method` | `SUPPORTS`, `CONTRADICTS` |
| `premise` | `SUPPORTS`, `CONTRADICTS` |

`METHOD_ONLY`, which the original stance vocabulary carried, is retired: it said "this source bears
on method rather than on the effect", and that is now what `kind: method` says. A stance outside its
kind's list is `WRONG_STANCE`, rejected like any other check.

### Nothing is ever partially accepted

A record that fails any check goes to the rejection ledger **whole**, with the check that failed
and the record as it was. Not partially accepted, not with the offending field nulled.

The reason is arithmetic rather than moral. An `effect` record that lost its `standard_error`
because check 3 failed on that field would still carry an estimate — and stage 6 would count it as
a study it cannot weight. **A mutilated record is worse than an absent one**, because it enters the
numerator without carrying what the denominator needs.

A conversion the engine cannot perform is likewise a recorded rejection and never a `null`:
`"about 2.4"` or `"2.4 (t=3.1)"` produce `UNPARSEABLE_VALUE` naming the form that was not
understood, so the list of notations grows from real cases.

**The first round must audit its rejections before the rate is quoted**, in the shape `gate-audit`
already established for stage 2. A gate rejecting a quarter of what it is offered might be catching
a sloppy model or throwing away correct records over a notation nobody anticipated, and only reading
them tells you which. `extract-report --show-rejected` lists every rejection with its failed check
and the record intact, and the cost of the whole-record rule is not established until that has been
read once.

## 4. Two ledgers, two ratios, never fused

`claims.jsonl` holds accepted records. `rejections.jsonl` holds everything rejected, with the
failed check and the intact record — which is what makes a rejection examinable rather than merely
counted.

```
extraction — the instrument's quality
  proposed     412    accepted 309  0.75    rejected 103
    QUOTE_NOT_FOUND 61   NUMBER_NOT_IN_QUOTE 28   VALUE_DISAGREES 9   WRONG_KIND 5

coverage — what the corpus says
  H02  effect          9 of 14 examined sources speak to it
  H19  effect          2 of 14
  H25  effect          0 of 14      → NEVER_ASKED
  H28  method          6 of 14      (4 endorsements, 2 demonstrated failures)
```

The first decides **whether to believe the instrument**; the second says **what the corpus
contains**. A 25% rejection rate with high coverage is a noisy instrument on a rich corpus; the
same rate with no coverage is a broken instrument. One fraction could not tell those apart, and the
project's standing phrase — "that ledger is the denominator" — had never said which denominator it
meant.

**Examined** carries stage 3's definition: a source all of whose chunks have been through all four
lanes. A half-processed source is not in the denominator, or a question its chunks have not reached
yet would read as a question they failed to answer.

## 5. Records are per question; studies are per source

A record exists **per (chunk, question)**: the quote and the reasoning differ between questions, so
one study result yields distinct records for H02 and H23.

But **`min_studies` counts distinct `source_id`, not records.** A paper discussing an effect across
five sections produces five records and remains one study. Without that rule a verbose paper would
clear a three-study bar by itself, which is the shape vote counting takes when nobody is looking.

Left open, deliberately: two papers by the same authors on the same dataset are not two studies
either, and the rule for that case can only be written against records that exist. D16 recorded the
same gap; stage 4's output is what closes it.

**What stage 6 receives**: records grouped by question, each carrying `source_id` and
`source_class`, the coverage denominators, and for the five `effect` questions the normalised values
with their scales. No verdicts and no pooling — that is stage 6's work, and D15 governs whether it
may pool at all.

## 6. Module boundaries

```
extract.py    orchestration: build work units per chunk per lane, harvest results, write ledgers.
claimgate.py  the six checks. Pure: a record and a chunk text in, a verdict out.
numbers.py    an as-written form into a value and a scale. Pure.
```

Only `extract.py` touches a store. The gate is where invariant 1 becomes executable and must be
testable without one; `numbers.py` is separate because the gate compares strings while conversion
produces the values stage 6 consumes, and because notations are what will grow.

Prompt templates live in the engine with the questions injected. "Report the estimate and its
standard error" is research methodology, not domain knowledge, so invariant 4 is satisfied by the
questions being data — which they are.

## 7. CLI

The stage is **two commands around a file boundary**, which is honest rather than awkward:

```
claimstone extract <project> --batch B                          build the work units, 4 lanes
claimstone model-run <project> extract --batch B --backend X    drain them
claimstone extract <project> --batch B --harvest                gate the results, write the ledgers
claimstone extract-report <project> --batch B                   the two ratios
```

`--harvest` opens no socket: it reads `results.jsonl` and writes ledgers, so re-running it after a
gate change costs nothing — the arrangement `gate-audit` and `normalize --confirm-audit` already
use.

## 8. Testing

| file | covers |
|---|---|
| `test_claimgate.py` | all seven checks; a record failing one is rejected **whole**; a `question_id` whose kind does not match the lane; a stance outside its kind's list; a synonym for a comparative class **accepted** and a class the quote lacks **rejected**; a declared mapping replacing the English default |
| `test_numbers.py` | percentages, basis points, parenthesised standard errors, scientific notation; and a notation not understood producing `UNPARSEABLE_VALUE` rather than `null` |
| `test_extract.py` | four lanes built and `operational` producing none; both ledgers; both ratios; studies counted by `source_id` and not by record |

No test reaches a model: work units are built and inspected, and harvest is fed prepared
`results.jsonl` rows.

## 9. Out of scope, deliberately

**Which backend serves the lane.** That is `model-run --backend`, and D13 makes it a measurement
rather than a design decision.

**The adversarial review.** Stage 5, with its own spec, and D5's requirement that it run on a
different model from the extractor.

**Any pooling or verdict.** Stage 6, governed by D15 and D16.

**The definition of independent studies** (§5). It waits for real records.
