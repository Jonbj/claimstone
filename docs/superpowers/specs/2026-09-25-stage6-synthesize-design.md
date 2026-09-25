# Stage 6 — synthesize: design

Date: 2026-09-25 · Scope: stage 6 only · Status: approved, not implemented

Claims become a verdict per question. **Deterministic Python. No model, no network, and — in this
version — no statistics.**

That last part is the design. D15 refused to specify this stage until a verdict was defined; D16
defined one, and defining it removed most of what this stage was going to do.

## 1. Two things this stage does not do, and why

### It does not pool

Read what D16's rules actually require. `min_studies: 3`. `min_distinct_data_sources: 2`. Contrary
evidence counted. An absent case reported. An endorsement **and** a demonstrated failure.

**None of them needs an aggregated estimate.** They are counting and coverage rules. A
random-effects pool would produce *additional information* — a magnitude — and not the basis of any
verdict the contract defines.

So this version needs no R, no `metafor`, no PET-PEESE and no MAIVE. **D6 is deferred rather than
implemented**, and the reasoning that chose `metafor` over writing pooling from scratch still holds
for whenever pooling is wanted; it simply is not wanted yet.

Pooling stays a separate deliverable, available for the five `effect` questions under D15's
conditions: compatible estimands, verified sampling variances, within-study dependence handled. The
project's contract is "a verdict per question", not "an effect size per question", and conflating the
two is how a verdict acquires a false precision.

### It does not correct for multiplicity

This contradicts a concern the original registry carried, so it is worth being exact.

Multiplicity control was wanted because the design assumed **significance testing**. D16's rules test
no significance: there is no p-value anywhere in them and therefore no family-wise error rate to
control. A Bonferroni or Benjamini-Hochberg adjustment applied to count-based rules would adjust
nothing — it would be rigour-shaped output with no object, which is the specific kind of thing this
project exists to refuse.

What remains is **disclosure**, and it is mandatory: the report states how many questions were asked,
how many are of each kind, how many reached each verdict, and how many sources each rests on. That is
a multiple-comparisons disclosure. It is not a correction and must never be labelled one.

`H24` — "the effect survives correction for multiple testing at the declared significance bar" —
survives this unchanged. It is a `method` question about what the literature did, not a calculation
this stage performs.

## 2. What it does

Reads `claims.jsonl` joined to `reviews.jsonl`, keeps the claims whose review is `SUPPORTED`, applies
the rule for each question's `kind`, and writes one verdict per question plus the evidence it rests
on.

**It refuses to produce any verdict when `admissibility.admit` reports
`INSUFFICIENT_ACQUISITION`.** That is invariant 3, and this is the first place in the project where
it has something to gate. The refusal is the whole output: the report says the round is inadmissible,
gives the rate and the floor, and stops. There is no flag.

## 3. The verdict rules, as code

From D16, with the thresholds declared in `sources.yaml` under `verdict_rules`:

| kind | `SUPPORTED` when |
|---|---|
| `effect` | ≥ `min_studies` distinct `source_id` with stance `SUPPORTS`, spanning ≥ `min_distinct_data_sources` distinct `sample` values, **after** contrary claims are counted |
| `heterogeneity` | ≥ `min_studies` distinct sources with a consistent `moderator` direction **and** ≥ 1 with `absent_case_reported: true` |
| `method` | ≥ 1 source of a methodological class with `support_type: ENDORSEMENT` **and** ≥ 1 with `DEMONSTRATED_FAILURE` |
| `premise` | ≥ 1 source stating it and none contradicting |
| `operational` | never. No verdict is produced |

`CONTRADICTED` is the same bar met by `CONTRADICTS` stances. `CONTESTED_IN_LITERATURE` is both bars
met. `UNANSWERED_IN_LITERATURE` is supported claims existing and no bar met. `NEVER_ASKED` is no
claim citing the question.

**Studies are counted by distinct `source_id`**, per stage 4 §5: a paper discussing an effect in five
sections is one study. And `min_distinct_data_sources` counts distinct `sample` strings, which is a
weak proxy and declared as one — two papers writing "US equities 1996-2008" differently will count as
two, and the remedy is the independence rule stage 4 left open, not a cleverer string comparison
here.

## 4. The evidence table

One per question, and it is the actual deliverable: a verdict without it is an assertion.

```
H02  effect                                          SUPPORTED
  for       4 sources   ACA001 ACA002 ACA003 ACA009   (3 distinct samples)
  against   1 source    ACA004
  qualified 1 source    ACA007
  awaiting review       2 claims
  gate rejected         6 claims   QUOTE_NOT_FOUND 4  VALUE_DISAGREES 2
  rests on  9 of 14 examined sources

H25  effect                                UNANSWERED_IN_LITERATURE
  for       1 source    ACA002
  rests on  1 of 14 examined sources
  reason    min_studies 3 not met

H11  operational                                    no verdict
  reason    no paper can confirm an architectural choice of the consuming system
```

**The gate-rejected line is there on purpose.** A question whose claims were all discarded by the
mechanical gate is not in the same state as one nobody wrote about, and a verdict that showed only
what survived would hide the difference. The rejection ledger being "the denominator" means this:
it appears beside the verdict it could have changed.

`awaiting review` likewise blocks nothing from being reported but is stated, because an unreviewed
claim is not a supported claim (stage 5 §4) and a reader deciding how much to trust a verdict needs
to know the review was incomplete.

## 5. What a verdict row carries

```json
{"question_id": "H02", "kind": "effect", "verdict": "SUPPORTED",
 "for": ["ACA001", "ACA002", "ACA003", "ACA009"],
 "against": ["ACA004"], "qualified": ["ACA007"],
 "distinct_samples": 3,
 "awaiting_review": 2,
 "gate_rejected": {"QUOTE_NOT_FOUND": 4, "VALUE_DISAGREES": 2},
 "examined_sources": 14,
 "by_class": {"ACA": 4, "MET": 0, "IND": 0},
 "rule": {"min_studies": 3, "min_distinct_data_sources": 2},
 "verdict_rules_version": 1,
 "registry_version": 3, "registry_sha256": "…",
 "decided_at": "…"}
```

The rule that decided it rides on the row, with its version, and so does the registry digest. A
verdict is a statement about a question at a version under a rule, and without all three it cannot
be compared to another verdict or defended against one.

`by_class` is on every row because D3 requires classes reported before anything is pooled — and it is
the line that would show a verdict resting entirely on vendor research.

## 6. Module boundaries and CLI

```
synthesize.py     join, apply the rule per kind, write verdicts.jsonl
evidence.py       build the evidence table for one question. Pure.
```

`evidence.py` is separate because it is the part with the arithmetic — counting distinct sources,
distinct samples, absent cases, rejections per question — and it must be testable without a store.
`synthesize.py` reads, gates on admissibility, and writes.

```
claimstone synthesize <project> [--batch B]     verdicts.jsonl, or the refusal
claimstone verdicts <project> [--question H02] [--json]    the evidence tables
```

No `model-run` step: there is no model here.

## 7. Testing

| file | covers |
|---|---|
| `test_evidence.py` | counting by `source_id` and not by record; distinct samples; an absent case present and missing; endorsement without demonstration and both; rejections attributed to the right question |
| `test_synthesize.py` | each kind's rule at, below and above its bar; `CONTESTED_IN_LITERATURE` when both bars are met; `NEVER_ASKED` distinguished from `UNANSWERED_IN_LITERATURE`; an `operational` question producing no verdict; **`INSUFFICIENT_ACQUISITION` producing no verdicts at all**; unreviewed claims excluded but reported; the rule and both registry fields on every row |

And one test that asserts the module contains no pooling and no multiplicity correction, in the shape
`discover_report` already uses: adding either later should mean arguing with §1 rather than quietly
shipping it.

## 8. Out of scope, deliberately

**Pooling, publication-bias correction, and the R boundary** (§1). Available under D15's conditions
for the five `effect` questions when someone wants a magnitude; not needed for a verdict.

**Any multiplicity correction** (§1). Disclosure is mandatory; correction has no object.

**Round-over-round comparison of verdicts.** The rows carry everything needed for it — rule version,
registry version and digest — and the comparison itself is a separate report, written when there are
two rounds to compare.

**A confidence or strength score per verdict.** The five states plus the evidence table say what is
known. A number on top of them would be a summary of a summary, and the first thing anyone would do
is average it.
