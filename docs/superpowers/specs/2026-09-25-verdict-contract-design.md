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

## 3. The verdict rules

### `effect`

What answers it: study-result records carrying an estimate, a direction and a precision.

`SUPPORTED` requires three things together:

1. at least `min_studies` independent sources reporting the effect in the stated direction;
2. those sources spanning at least `min_distinct_data_sources` — **a finding replicated on its own
   dataset is one finding**, and counting it twice is the inflation this project exists to refuse,
   arriving through the numerator instead of the denominator;
3. contrary evidence **counted rather than absent**: every claim in the opposite direction
   appears in the verdict's evidence, and the agreeing side clears the bar *after* they are
   counted. The failure mode this prevents is a verdict pooled from the sources that agreed, with
   the disagreement never reaching the page — which is not a judgement, it is a selection.

`CONTRADICTED` is the same bar in the opposite direction. `CONTESTED_IN_LITERATURE` (§4) is both
directions clearing it. `UNANSWERED_IN_LITERATURE` is claims that exist and do not reach the bar.
`NEVER_ASKED` is no claim citing the question at all.

### `heterogeneity`

What answers it: studies reporting a difference between subgroups, or an interaction.

`SUPPORTED` requires `min_studies` in a consistent direction **and at least one source reporting
the case where the effect is absent.**

That second condition is the strictest rule here and it earns its place. "Attention moderates
underreaction", supported only by the high-attention side, **is a main effect wearing a
moderation's clothes**: without the low-attention case nobody has observed moderation, only an
effect inside a subset. The rule will reject claims that currently read as well supported, and
that is the point of having it.

### `method`

What answers it: the literature either adopts the practice, or demonstrates what goes wrong
without it.

`SUPPORTED` requires **both**: an endorsement in a source of a methodological class, and at least
one demonstration of the failure mode. Endorsement alone is convention; a single demonstration
alone is one paper's result. Eleven of twenty-eight questions are judged by this rule — the largest
group — and it is the one rule that consumes the source classes directly, which is what D3 declared
them for.

`CONTRADICTED` is a methodological source arguing against the practice.

**No pooling, ever, for this kind.** There is no estimand.

### `premise`

A consistency check. `SUPPORTED` when at least one source states it explicitly and none
contradicts it. H01 — that a future return is neither semantic ground truth nor causal proof — is
true by construction, and what the instrument can report is whether the corpus agrees.

### `operational`

No verdict. The report names the kind, and where a literature question sits underneath it, points
at that question: H12 rests on H26, and H04 on a horizon the literature can judge even though the
S4 mandate is not its business.

## 4. A fifth verdict state

`CONTESTED_IN_LITERATURE`.

With the `effect` rule above, a question where three studies clear the bar in one direction and
three clear it in the other is none of the existing four. It is not `SUPPORTED`, not
`CONTRADICTED`, and emphatically not `UNANSWERED_IN_LITERATURE` — which would report silence while
the literature is speaking and disagreeing.

Invariant 2 forbids reporting absence of evidence as absence of effect. It does not forbid a fifth
state, and forcing irreducible disagreement into `UNANSWERED` would be that same collapse one
category over. The name parallels `UNANSWERED_IN_LITERATURE` so the two cannot be confused in a
report.

A sixth state for "not a literature question" is **not** added: that is `kind: operational`, and a
property of the question is the right home for it. Inventing verdict states for things that are
not verdicts is how a four-state vocabulary becomes a nine-state one nobody reads.

## 5. Multiplicity

The family is the `effect` questions: **five**. A `heterogeneity` question joins it only when its
own verdict rests on a pooled estimate rather than on the presence of an absent case, so the family
size is between five and ten and is **computed from the verdicts actually produced**, never assumed.

A correction applies to a family of statistical hypotheses, and a methodological requirement is not
one. So the declared number of tests falls from 28 to that computed number, which is also the only
number that could be defended — and it is stated beside the correction, never implied by it. A
report that gives an adjusted threshold without saying how many tests it adjusted for has not said
anything.

## 6. What this forces on stage 4

This is why the contract comes first.

The extraction target **depends on the kind of the question being extracted for**:

| for a question of kind | stage 4 must extract |
|---|---|
| `effect` | a study-result record: estimate, scale, standard error or interval, sample, horizon, design, dependence — plus the quote |
| `heterogeneity` | the subgroup contrast, including which side is the absent case |
| `method` | whether the source **endorses** the practice or **demonstrates the failure**, and its class |
| `premise` | the explicit statement, or a contradiction of it |
| `operational` | nothing. No work unit is built |

A claim bound to a quote is not a study result. The quote verifies **the provenance of a text** —
it does not establish that the model selected the right result from the paper, read its estimand
correctly, or noticed its standard error was clustered. The gate is narrower than this project's
own prose has been implying, and the record is the place to say so.

So a claim remains an **evidence annotation** attached to a study-result record, not an
independent observation to be counted. Counting claims would be vote counting with extra steps.

## 7. Declared thresholds

```yaml
verdict_rules:
  effect:
    min_studies: 3
    min_distinct_data_sources: 2
    counter_evidence: addressed
  heterogeneity:
    min_studies: 2
    require_absent_case: true
  method:
    require_methodological_endorsement: true
    require_demonstrated_failure: true
  premise:
    require_explicit_statement: true
```

**These are not measured.** They are a defensible starting point, and the project's own standard
applies: they ride on every verdict alongside a `verdict_rules_version`, and a sweep must be able
to ask what a verdict owes to `min_studies: 3` rather than to the evidence. "Three studies" should
be an interrogable choice, not an inherited number — the content gate's thresholds were flat when
swept and that was worth knowing; these may not be.

## 8. Out of scope

**No stage 6 statistics here.** This says which questions could be pooled and under what
conditions; whether `metafor`, PET-PEESE and MAIVE are the right tools for those five is a
separate decision, and D15's steps 4 and 5 still stand unaddressed.

**No reclassification of the six operational questions.** They keep their wording and receive no
verdict. Rewriting them into the literature questions underneath would be a different registry,
and the consuming project asked what it asked.

**No definition of "independent" for `min_studies`.** Two papers by the same authors on the same
dataset are not two studies, and a rule for that needs the study-result records to exist before it
can be written against anything real. Recorded here as the first thing to settle once stage 4 runs.
