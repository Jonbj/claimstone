# Stage 6 — synthesize: design

Date: 2026-09-25 · Scope: stage 6 only · Status: **implemented 2026-09-27** — `evidence.py`, `synthesize.py`, 28 tests

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

## 2. What it does, and what it refuses to decide

**Revised 2026-09-25.** The first version applied a verdict rule automatically. A review established
that the rule was vote counting with a threshold, and the verdict contract now splits the work in
two (that spec, §3). This stage implements **layer 1 only.**

It reads `claims.jsonl` joined to `reviews.jsonl`, keeps the results whose review is `SUPPORTED`, and
writes an **evidence profile** per question: everything known, nothing concluded. It reads
`adjudications.jsonl` if it exists and displays the verdicts recorded there, marking any whose
profile hash no longer matches as **stale**.

It produces no verdict of its own. The one categorical thing it may say is `NO_VERIFIED_CLAIM`.

### Two gates, both refusals

**It refuses to write profiles at all when the round is not admissible.** `admissibility.admit`
reporting `INSUFFICIENT_ACQUISITION` stops the stage: invariant 3, and this is the first place in the
project with something to gate.

**It marks every profile provisional when the round is not final.** `admit()` returns `final: False`
while anything is awaiting normalization, an acquisition has no candidate, or a ledger had to be
repaired — and a profile from an incomplete corpus is a profile that can still change. Claims
awaiting review count the same way: one later `SUPPORTED` review can move a question out of
`NO_VERIFIED_CLAIM`, so a profile with unreviewed claims is not settled.

A provisional profile is written, labelled, and **may not be adjudicated**. `synthesize` refuses to
accept an adjudication whose profile was provisional, because a verdict recorded against evidence
that was still arriving is a verdict about something that no longer exists.

## 3. What a profile contains

Per question, and the fields are the ones stage 4 extracted rather than a subset of them:

- every verified result: estimate, scale, uncertainty as reported, horizon, sample label, design,
  dependence, source, source class
- **the same fields for every contrary result**, because a profile showing only the agreeing side is
  a selection rather than a description
- the **direction count**, labelled a count
- coverage: sources speaking to the question over sources examined
- gate rejections attributed to this question, by reason
- claims awaiting review
- `by_class` for both sides separately
- **sample labels verbatim, with linkage declared unestablished** — no independence count, because
  no string comparison establishes one

For `heterogeneity`, the contrast and its uncertainty and whether the analysis was prespecified. For
`method`, endorsements and demonstrated failures separately, each with its source's declared `role`.

## 4. The profile as printed

```
H02  effect                       provisional — 2 claims awaiting review
  results
    ACA001  +2.4%  (0.008)  1w   panel, clustered by firm and week   sample: US equities 1996-2008
    ACA002  +1.1%  (0.005)  1w   panel, clustered by firm            sample: US equities 1996-2008
    ACA003  +0.9%  [0.1,1.7] 4w  portfolio sort                      sample: CRSP 1993-2010
    ACA004  -0.3%  (0.004)  1w   panel, clustered by firm            sample: US equities 1996-2008
  direction count       3 positive, 1 negative   (a count, not a strength)
  linkage               unestablished: three results share a sample label
  coverage              4 of 14 examined sources
  gate rejected         6   QUOTE_NOT_FOUND 4   VALUE_DISAGREES 2
  by class              for ACA 3   against ACA 1
  no controlled family-wise error rate across the 5 effect questions

H11  operational                  LITERATURE_VERDICT_NOT_APPLICABLE
  reason   no paper can confirm an architectural choice of the consuming system
  see      H26, which asks the literature question underneath
```

Three things in that output exist because of a review.

**`linkage unestablished`** replaces a count of distinct datasets. Three of those four results carry
the same sample label, which may mean one dataset or three overlapping extracts of it, and the
earlier rule would have called two spellings two datasets.

**The negative result is shown with the same fields as the positives.** The earlier `by_class`
counted supporting sources only, which would have hidden a verdict resting on vendor research
disagreeing with refereed work.

**The error-rate line is mandatory.** It is not a correction and must never be printed as one.

## 5. What the two rows carry

A **profile row**, written by this stage:

```json
{"question_id": "H02", "kind": "effect",
 "state": null,
 "results": [{"result_id": "ACA001#c2|r1", "source_id": "ACA001", "source_class": "ACA",
              "stance": "SUPPORTS", "estimate": 0.024, "scale": "percent",
              "uncertainty_as_written": "(0.008)", "horizon_as_written": "one week",
              "sample": "US equities 1996-2008", "design": "panel regression",
              "dependence": "clustered by firm and week"}],
 "direction_count": {"SUPPORTS": 3, "CONTRADICTS": 1, "QUALIFIES": 0},
 "linkage": "unestablished",
 "coverage": {"sources": 4, "examined": 14},
 "gate_rejected": {"QUOTE_NOT_FOUND": 4, "VALUE_DISAGREES": 2},
 "awaiting_review": 2,
 "by_class": {"for": {"ACA": 3}, "against": {"ACA": 1}},
 "provisional": true, "blocking": ["awaiting_review"],
 "profile_sha256": "…",
 "decision_contract_version": 1,
 "registry_version": 3, "registry_sha256": "…",
 "built_at": "…"}
```

`state` is `null` for a profile that has results and `"NO_VERIFIED_CLAIM"` for one that has none. It
is never a verdict.

An **adjudication row**, written by a person and only read here:

```json
{"question_id": "H02", "verdict": "SUPPORTED",
 "rationale": "…", "profile_sha256": "…",
 "adjudicated_by": "…", "adjudicated_at": "…"}
```

`verdicts` displays an adjudication only when its `profile_sha256` matches the current profile. When
it does not, the row is shown as **stale** with both hashes, because a judgement made against
different evidence is a judgement about a different question and quietly keeping it on screen is how
a verdict outlives its reason.

Three identities ride on the profile: `decision_contract_version`, `registry_version` and
`registry_sha256`. A profile is a statement about a question at a registry version under a decision
contract, and two profiles are comparable only when all three agree.

## 6. Module boundaries and CLI

```
synthesize.py     join, apply the rule per kind, write verdicts.jsonl
evidence.py       build the evidence table for one question. Pure.
```

`evidence.py` is separate because it is the part with the arithmetic — counting distinct sources,
distinct samples, absent cases, rejections per question — and it must be testable without a store.
`synthesize.py` reads, gates on admissibility, and writes.

```
claimstone synthesize <project> [--batch B]                 profiles.jsonl, or the refusal
claimstone verdicts <project> [--question H02] [--json]     profiles with any adjudication
claimstone adjudicate <project> H02 --verdict SUPPORTED --rationale-file r.md
```

No `model-run` step: there is no model here.

`adjudicate` refuses a provisional profile, refuses a rationale shorter than a declared minimum, and
records the profile hash it was shown. It is the only command in the project that writes a human
judgement, and it is the only place a verdict can come from.

## 7. Testing

| file | covers |
|---|---|
| `test_evidence.py` | one record per result carried through with all its fields; contrary results present with the same fields; direction counts; coverage; rejections attributed to the right question; `by_class` split for and against; sample labels verbatim and linkage always `unestablished` |
| `test_synthesize.py` | `INSUFFICIENT_ACQUISITION` producing **no profiles at all**; a non-final round producing profiles marked provisional; unreviewed claims making a profile provisional; `NO_VERIFIED_CLAIM` where nothing survived; an `operational` question producing a `LITERATURE_VERDICT_NOT_APPLICABLE` row rather than no row; all three identities on every profile |
| `test_adjudicate.py` | a provisional profile refused; a stale adjudication displayed as stale with both hashes; a matching one displayed; a too-short rationale refused |

And one test asserting the module contains **no threshold that decides a verdict**, in the shape
`discover_report` already uses for the population estimate: reintroducing an automatic `SUPPORTED`
should mean arguing with the verdict contract's §3 rather than quietly shipping it.

## 8. Out of scope, deliberately

**Pooling, publication-bias correction, and the R boundary** (§1). Available under D15's conditions
for the five `effect` questions when someone wants a magnitude; not needed for a verdict.

**Any multiplicity correction** (§1). Disclosure is mandatory; correction has no object.

**Round-over-round comparison of verdicts.** The rows carry everything needed for it — rule version,
registry version and digest — and the comparison itself is a separate report, written when there are
two rounds to compare.

**A confidence or strength score per verdict.** The five states plus the profile say what is known. A
number on top of them would be a summary of a summary, and the first thing anyone would do is
average it.

**Any automatic verdict** (§2, and the verdict contract §3). Layer 1 describes; a person judges and
signs. Reintroducing a threshold means showing it does not do what the first one did.

**A material-effect threshold.** What magnitude matters is per question and belongs to whoever asked
it. Until it is declared, an adjudication reasoning about magnitude is reasoning without a bar, and
its rationale has to say so.
