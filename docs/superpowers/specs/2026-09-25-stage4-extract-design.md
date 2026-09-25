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

```json
{"question_id": "H02", "stance": "SUPPORTS",
 "claim": "News sentiment predicts next-week abnormal returns.",
 "evidence_quote": "…net sentiment of 2.4% (0.008) over one week…",
 "estimate_as_written": "2.4%",  "estimate": 0.024, "scale": "percent",
 "standard_error_as_written": "(0.008)", "standard_error": 0.008,
 "horizon_as_written": "one week",
 "sample": "US equities 1996-2008",
 "design": "panel regression with firm and time fixed effects",
 "dependence": "standard errors clustered by firm and week"}
```

### `heterogeneity` — a subgroup contrast

```json
{"question_id": "H22", "stance": "SUPPORTS",
 "moderator": "firm size", "high_side": "small firms", "low_side": "large firms",
 "absent_case_reported": true,
 "contrast_as_written": "0.31% versus 0.04%",
 "claim": "…", "evidence_quote": "…"}
```

`absent_case_reported` exists because D16's rule needs it: a moderation supported only by the
high side is a main effect wearing a moderation's clothes.

### `method` — an endorsement or a demonstrated failure

```json
{"question_id": "H28", "stance": "SUPPORTS",
 "support_type": "ENDORSEMENT",
 "claim": "…", "evidence_quote": "…"}
```

`support_type` is `ENDORSEMENT` or `DEMONSTRATED_FAILURE`, which are the two ways the literature
answers a methodological requirement and which D16's rule requires both of.

### `premise` — a statement or a contradiction

`question_id`, `stance`, `claim`, `evidence_quote`. Nothing else.

## 2. Numbers exist twice, and the model does not convert

A paper writes `2.4%`; a numeric field wants `0.024`. As strings they do not match, so an exact
substring gate would reject a correct record — or be loosened until it verified nothing.

So every numeric field appears twice: `*_as_written`, exactly as the source has it, and the
normalised value with its `scale`. **The gate checks the as-written form. The engine does the
conversion**, deterministically and in code. A model asked to convert is a model handed a way to be
wrong that no quote check could catch.

## 3. The gate

Six checks, in order, all code and no judgement:

| | check | failure |
|---|---|---|
| 1 | `question_id` exists **and its kind matches the lane of the call** | `UNKNOWN_QUESTION_ID`, `WRONG_KIND` |
| 2 | `evidence_quote` is an exact substring of the chunk's text | `QUOTE_NOT_FOUND` |
| 3 | every `*_as_written` field is an exact substring of the quote | `VALUE_NOT_IN_QUOTE` |
| 4 | every numeral in `claim` appears in the quote | `NUMBER_NOT_IN_QUOTE` |
| 5 | every comparative in `claim` appears in the quote | `COMPARATIVE_NOT_IN_QUOTE` |
| 6 | the engine's normalisation of each as-written form **agrees with the value the model wrote** | `VALUE_DISAGREES` |

Check 2 compares against `chunks.jsonl`'s stored `text`, which stage 3 guarantees is byte-for-byte
what the model was shown. Rendering the chunk a second time here would turn any difference between
the two renderings into the rejection of a true claim.

**Check 6 is the one the project did not have.** Carrying both forms lets the engine verify the
model's own arithmetic: a record saying `"2.4%"` and `0.03` is caught, and no check on the quote
alone could catch it, because `"2.4%"` is in the quote and `0.03` is not a number the paper
contains. The other five say the model quoted badly; this one says it **computed badly on a number
it was looking at**, which is a different and worse failure.

### What counts as a numeral and a comparative

Checks 4 and 5 need definitions, or an implementer invents them.

A **numeral** is a run matching `-?\d[\d,.]*%?` — digits, optional thousands separators and
decimal point, optional percent. Written-out numbers (`two-thirds`) are not numerals and are not
checked: the rule exists to stop a fabricated figure, and a fabricated figure is written in digits.

A **comparative** is a symbol from `>`, `<`, `≥`, `≤`, `=` or a phrase from a declared list —
`more than`, `less than`, `higher than`, `lower than`, `at least`, `at most`, `greater than`,
`exceeds`, `outperforms`, `underperforms`. That list is English, and by the lesson the content gate
already taught, it belongs in `sources.yaml` under `extraction:` rather than in the package. The
engine ships these as defaults; a project in another language declares its own, and the list in
force rides on every ledger row.

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
| `test_claimgate.py` | all six checks; a record failing one is rejected **whole**; `VALUE_DISAGREES` on a wrong conversion; a `question_id` whose kind does not match the lane; a stance outside its kind's list; a declared comparative list replacing the English default |
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
