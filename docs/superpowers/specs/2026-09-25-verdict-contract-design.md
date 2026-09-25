# The verdict contract — design

Date: 2026-09-25 · Scope: what a verdict is, per kind of question · Status: approved, not implemented

Required by D15, which refused to specify stage 6 until this existed. It turns out to block stages
4 and 5 as well: what stage 4 must extract depends on what a verdict will do with it, and a claim
bound to a quote is not the same artifact as a study result with an estimand and a variance.

Everything below was derived by reading the 28 questions of `alembic-s4` one at a time.

## 1. What the registry actually contains

| kind | count | questions |
|---|---|---|
| `effect` | 5 | H02, H03, H19, H23, H25 |
| `heterogeneity` | 5 | H06, H20, H21, H22, H27 |
| `method` | 11 | H05, H07, H08, H09, **H10**, **H13**, H15, H18, H24, H26, H28 |
| `premise` | 1 | H01 |
| `operational` | 6 | H04, H11, H12, H14, H16, H17 |

**H10 and H13 are the two that had to be argued about.** Both are worded operationally — "must
determine accountability and anchoring", "requires a trial ledger" — and both are methodological
requirements underneath: a point-in-time observable timestamp and multiplicity control over a trial
ledger are practices the literature endorses and can be shown failing. An earlier draft of this
document left them unassigned, and its counts added to 26 of 28. Assigning every question in the
registry is what exposed that.

**Five of twenty-eight are poolable effects.** Eleven are requirements about how one must measure.
Six are assertions about the consuming system's own architecture — versioned lanes, a frozen
counterfactual policy, an exclusive first loss cause — which no paper can confirm. One is a
definition.

This is why a single multiplicity correction across 28 was meaningless: twenty-three of them are
not statistical hypotheses, and a correction applies to a family.

It is also why a random-effects pool as the default operation was the wrong shape. It would apply
to five questions, and to those five only where the extracted estimates share an estimand.

## 2. `kind` is a property of the question, not a verdict

Each entry in `questions.yaml` declares its kind. The verdict rule follows from it, and a question
whose kind is `operational` receives **no verdict at all** — the report names the kind and says
why, rather than filing it under `UNANSWERED_IN_LITERATURE`, which would assert that the
literature is silent on a question it was never asked.

**Adding `kind` is a dated registry bump**, and `kind` is part of the registry digest. It has to
be: a question silently reclassified from `method` to `effect` changes the rule that judges it and
therefore its answer, which is exactly what invariant 5 exists to prevent. `alembic-s4` goes to
`registry_version: 3`; the shipped example declares kinds from the start.

## 3. Two layers, and only one of them is automatic

**Revised 2026-09-25**, after a review asked the question this document had invited: is a
count-based rule meaningfully different from vote counting, or the same error at one remove?

It is the same error. The rule as first written declared `SUPPORTED` on three agreeing sources from
two distinct samples, and gave contrary evidence no weight unless it independently cleared the same
bar. **Three small, imprecise, biased positive results and one large, precise negative result would
have been labelled `SUPPORTED`** — which is precisely what the README says vote counting gets wrong,
rebuilt under a better name.

The tell was internal: stage 4 extracts `standard_error`, `design` and `dependence`, and the rule
used none of them. A verdict that ignores precision has no business asking for it.

So the work splits in two, and the split is the design.

### Layer 1 — the evidence profile. Automatic, and descriptive only.

Deterministic code produces, per question, everything known and nothing concluded:

- every verified result with its estimate, its uncertainty as reported, horizon, sample, design and
  dependence
- the **direction count**, labelled as a count and never as strength
- coverage: sources speaking to the question over sources examined
- what was rejected by the gate, by reason
- what is awaiting review
- the source classes on both sides, not only the agreeing one

Layer 1 emits **no verdict**. Its one categorical output is `NO_VERIFIED_CLAIM` when nothing
survived to the profile — descriptive, and deliberately not `NEVER_ASKED`, which asserts that
nobody asked and can only be established by screening the corpus for the question rather than by
finding no claim.

### Layer 2 — adjudication. Recorded, attributable, not automatic.

A verdict is a judgement made by a person reading the profile, written to `adjudications.jsonl`:

```json
{"question_id": "H02", "verdict": "SUPPORTED",
 "rationale": "Four independent samples, the two largest agreeing; the one negative is a
               subsample of ACA002 and is not independent evidence.",
 "profile_sha256": "…", "adjudicated_by": "…", "adjudicated_at": "…"}
```

`profile_sha256` is what makes it auditable: if the evidence changes after the judgement, the
adjudication is stale and the report says so rather than continuing to display it. An adjudication
whose profile no longer matches is not a verdict; it is a verdict about something else.

This is slower and it is the honest shape. The alternative was an automatic threshold that would
have had to be defended, and the defence did not exist.

### What each kind contributes to a profile

| kind | the profile carries |
|---|---|
| `effect` | estimates with uncertainty, design, dependence, sample labels; the direction count; counter-evidence with the same fields |
| `heterogeneity` | the **contrast** between subgroups with its uncertainty, and whether the subgroup analysis was prespecified |
| `method` | endorsements and demonstrated failures separately, each with the **declared role** of its source |
| `premise` | statements and contradictions |
| `operational` | nothing. No profile and no verdict — see §6 |

### The heterogeneity rule had the same class of error

The first version required a reported case where the effect is **absent**, and called that the
strictest rule here. It is not a rule about moderation at all: **an effect can differ materially
between two subgroups that are both non-zero**, so an absent case is neither necessary nor
sufficient. What establishes moderation is a contrast and its uncertainty, which is what stage 4
must extract and what the profile must show.

### Independence is not inferred from a string

`min_distinct_data_sources` counted distinct `sample` strings. Two spellings of one dataset pass it;
one broad label can hide two datasets. It is removed rather than weakened.

The profile instead reports the sample labels **verbatim** and states that linkage is
**unestablished**. Unknown stays unknown, and the adjudicator sees the labels and decides. A
canonical dataset identity and a dependency graph are what would make this countable, and neither
can be built against records that do not exist yet.

## 4. The verdict vocabulary belongs to layer 2

Five states, and all five are outcomes an **adjudicator** records. None is produced by a threshold.

| verdict | means |
|---|---|
| `SUPPORTED` | the profile persuades on the evidence, and the rationale says why |
| `CONTRADICTED` | the profile persuades the other way |
| `CONTESTED_IN_LITERATURE` | the literature speaks and disagrees irreducibly |
| `UNANSWERED_IN_LITERATURE` | the corpus was read and does not settle it |
| `NEVER_ASKED` | nobody asked, established by screening rather than inferred from silence |

`CONTESTED_IN_LITERATURE` was added because a live disagreement reported as
`UNANSWERED_IN_LITERATURE` is invariant 2's error one category over: absence of evidence stated as
evidence of absence, with "we found nothing" standing in for "they disagree".

`NEVER_ASKED` is the state most easily got wrong, and layer 1 must not reach for it. Its automatic
neighbour is `NO_VERIFIED_CLAIM`, which says only that nothing survived to the profile — and an
extraction miss, an all-rejected question and a genuinely unasked question all look identical from
there. Only screening tells them apart, so only an adjudicator may say `NEVER_ASKED`.

No sixth state for `operational` questions: they get no profile and no verdict, and §6 says how the
report shows that without silently omitting a row.

## 5. Multiplicity

**No correction is performed, and none is claimed.** Reconciled with D17 on 2026-09-25; an earlier
version of this section promised a computed family and a correction, which contradicted D17 in the
same repository.

A Bonferroni or Benjamini-Hochberg adjustment needs test statistics, and layer 1 produces none. But
the reason not to correct is stronger than that: **layer 1 makes no inferential claim at all.** A
direction count is a description. There is nothing to control the error rate of.

What must be stated, every time, is that **the five effect questions carry no controlled
family-wise error rate**. A review supplied the arithmetic that makes this necessary rather than
pedantic: under independent random signs with three studies per question, a three-positive rule
fires on a null question with probability 1/8, and across five null questions the chance of at least
one is about 0.49. That is an illustration and not a measurement here — the real questions are
dependent and selected — but it is the order of magnitude of what a threshold would have been
hiding, and it is why the threshold is gone.

An adjudication may reason about multiplicity in its rationale. It may not be presented as having
corrected for it.

## 6. Operational questions appear in the report

They receive no profile and no verdict, and they are **not omitted**. The report gives each one a
row saying `LITERATURE_VERDICT_NOT_APPLICABLE` and why, and points at the literature question
underneath where there is one — H12 rests on H26, H04 on a horizon the literature can judge even
though the S4 mandate is not its business.

Omitting them would make the registry and the report disagree on how many questions exist, and
"one verdict per question" is the project's stated contract. The contract is kept by answering
every question, including with "this instrument cannot answer this one".

## 7. What this forces on stage 4

This is why the contract comes first.

The extraction target **depends on the kind of the question being extracted for**:

| for a question of kind | stage 4 must extract |
|---|---|
| `effect` | a study-result record: estimate, scale, uncertainty as reported, sample, horizon, design, dependence — plus the quote. **One record per result**, not per question |
| `heterogeneity` | the **contrast** between subgroups with its uncertainty, and whether the subgroup analysis was prespecified |
| `method` | whether the source **endorses** the practice or **demonstrates the failure**, plus its declared `role` |
| `premise` | the explicit statement, or a contradiction of it |
| `operational` | nothing. No work unit is built |

A claim bound to a quote is not a study result. The quote verifies **the provenance of a text** —
it does not establish that the model selected the right result from the paper, read its estimand
correctly, or noticed its standard error was clustered. The gate is narrower than this project's
own prose has been implying, and the record is the place to say so.

So a claim remains an **evidence annotation** attached to a study-result record, not an
independent observation to be counted. Counting claims would be vote counting with extra steps —
and §3 records that counting *sources* was the same thing, arrived at more slowly.

**One record per result, not per question.** A chunk reporting three estimates for one question
must produce three records with distinct result ids, or the third is either crammed into the second
or silently dropped. The record is the unit of evidence; the question is what it bears on.

## 8. The declared decision contract

There are no verdict thresholds any more, because no threshold decides a verdict. What must be
declared and versioned instead is everything an adjudication depended on, so two verdicts can be
compared only when they were reached under the same instrument:

```yaml
decision_contract_version: 1
gate_policy: { … }            # what counted as a document (stage 2)
extraction:                   # what counted as a verified record (stage 4)
  comparatives: [ … ]
classes:
  - id: MET
    role: methodological      # declared, never inferred from the class id
```

**`role` closes an invariant 4 violation this document had inside it.** The method rule said "a
source of a methodological class", and the only way to know which class that is was to read `MET`
and understand what it stands for — domain knowledge in the engine, exactly what invariant 4
forbids. A class now declares its role and the rule reads the declaration.

A verdict row carries `decision_contract_version` alongside `registry_version` and
`registry_sha256`. Three identities, because a verdict is a judgement about a question at a
registry version under a decision contract, and without all three it cannot be compared with
another or defended against one.

The registry digest stays **question identity only**: ids, texts and kinds. Widening it to cover
thresholds and prompts would make every tuning change look like a registry bump, and the check
would stop being believed.

## 9. Out of scope

**No stage 6 statistics here.** This says which questions could be pooled and under what
conditions; whether `metafor`, PET-PEESE and MAIVE are the right tools for those five is a
separate decision, and D15's steps 4 and 5 still stand unaddressed.

**No reclassification of the six operational questions.** They keep their wording and receive no
verdict. Rewriting them into the literature questions underneath would be a different registry,
and the consuming project asked what it asked.

**No automatic verdict** (§3). Layer 1 describes; layer 2 judges and is attributable.

**No independence count.** Two papers by the same authors on one dataset are not two studies, and no
string comparison establishes that. The profile reports sample labels verbatim and says linkage is
unestablished. A canonical dataset identity and a dependency graph are what would make replication
countable, and they can only be built against records that exist.

**No magnitude assessment rule.** The profile carries estimates and uncertainty; what counts as a
material effect is per-question and has to be predefined by whoever asks the question. That
predefinition is the first thing to write once real records exist, and until it does exist an
adjudication is reasoning about magnitude without a declared bar — which the rationale must say.
