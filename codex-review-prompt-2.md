# Second adversarial review of Claimstone — the verdict path

You reviewed this project once already, on 2026-09-24. Your findings are in
`codex-review-results.md`, and every one of them was acted on. This review has two jobs: check
whether I acted on them **correctly**, and attack four new specifications that together define how a
verdict is reached.

I am the author of all of it. A review concluding "this looks solid" has told me nothing.

## What to read

Start with `docs/DESIGN_DECISIONS.md`, which now has 17 entries. D14 through D17 are new and all
four came out of your review or out of work it prompted.

Then, in this order:

1. `docs/superpowers/specs/2026-09-25-verdict-contract-design.md` — what a verdict is, per kind of
   question. This is D15's first step, done.
2. `docs/superpowers/specs/2026-09-25-stage4-extract-design.md` — where invariant 1 lives.
3. `docs/superpowers/specs/2026-09-25-stage5-review-design.md` — the adversarial reader.
4. `docs/superpowers/specs/2026-09-25-stage6-synthesize-design.md` — and D17, which says defining the
   verdict removed the statistics.

## Part one: did I act on your findings correctly?

Each of these is now claimed fixed. Verify or refute, and say where I over-corrected.

| your finding | what I did | where |
|---|---|---|
| the floor could pass a 4%-read corpus | denominator is now the candidate set; five states reported separately; orphan acquisitions counted | `claimstone/admissibility.py`, `tests/test_admissibility.py` |
| stage 3 would report 13/25, not 14 | added an HTML path so a SEC filing is a document; `NOT_PDF` deleted | stage 3 plan Task 4 |
| `model_call` could not compare backends | identity is `(call_id, backend)`; every attempt kept; the echo check now hashes what the runner says it sent | `model-call` plan §"Three defects" |
| storage crash recovery was unqualified | torn final line skipped and recorded, `repair()` truncates, damage elsewhere raises | `claimstone/store.py`, `tests/test_store.py` |
| invariant 4: the gate assumed English | paywall phrases, reference headings and the structural signal are declarable per project | `claimstone/fulltext.py`, `claimstone/config.py` |
| invariant 5: text could change under a version | registry digest over ids, texts **and kinds**; every command that opens a store refuses on drift | `claimstone/config.py`, `tests/test_registry_drift.py` |
| the corpus figures were not reproducible | `tools/derive_corpus_figures.py`; running it corrected 818,678 to 775,266 | `tools/`, stage 3 spec §1 |
| "confirmed" could include unexamined bytes | the confirmed basis is used only when nothing is awaiting normalize | `claimstone/admissibility.py` |

Two I want you to be especially sceptical about:

- **The gate policy.** I made the English lists declarable rather than changing the rule. Is that
  enough for invariant 4, or did I move the coupling into YAML and call it solved?
- **The registry digest.** It now covers `kind`, which made assigning kinds a dated bump (v3 for
  `alembic-s4`). Is there still a way to change what a verdict means without the digest moving?

## Part two: the thing I am least sure of

**D17 claims that defining the verdict removed the need for meta-analysis and for multiplicity
correction.** This is the single load-bearing claim in the new work and the place where I have no
competence.

The argument: D16's rules are count-and-coverage rules — three studies, two distinct datasets,
contrary evidence counted, an absent case reported, an endorsement plus a demonstrated failure. None
requires a pooled estimate, so a pool would be additional information rather than the basis of a
verdict. And because no rule tests significance, there is no p-value and no family-wise error rate,
so a correction would adjust nothing.

Attack both halves:

- Is a count-based verdict rule **defensible at all**, or have I replaced vote counting with a
  threshold on the same counts and given it a nicer name? Your first review said counting significant
  results is not synthesis. Is "three sources agreeing, from two datasets, with disagreement counted"
  meaningfully different, or the same error at one remove?
- If it is not defensible, what should a verdict rest on that does not require the pooled estimate I
  have just argued the inputs cannot support?
- Is it true that no correction applies? A rule with a threshold applied across five questions still
  has a false-positive rate across those five. Does declaring the count discharge that, or am I
  discarding a real control because it is inconvenient?
- `min_distinct_data_sources` counts distinct `sample` strings, which I declared to be a weak proxy.
  Is it too weak to be worth having — does a proxy that fails silently do more harm than no check?

## Part three: the new specifications

**The verdict contract.** I classified all 28 questions of `alembic-s4` by what could answer them:
five effects, five heterogeneity claims, eleven methodological requirements, one premise, six about
the consuming system's own architecture that get no verdict. H10 and H13 were the two I had to argue
about and could have got wrong. Read the registry (`projects/alembic-s4/questions.yaml`) and tell me
which assignments you disagree with, and whether `operational` receiving no verdict is right or is a
way of not answering questions someone wanted answered.

**Stage 4.** Four call shapes, one per kind, and a six-check gate. Check 6 — the engine's
normalisation must agree with the value the model wrote — is the one the project did not have, and I
think it is the sharpest thing in the design. Tell me if it is instead redundant or unimplementable.
Also: is "nothing is ever partially accepted" right, or will it reject so much that the rejection
ledger becomes the output?

**Stage 5.** The reviewer sees the whole chunk, costs about $5 for the corpus, and must run on a
different model from the extractor — enforced in code. §5 claims the `OVERSTATED` rate per extraction
backend is the measurement D13 deferred lane assignment to. Does that comparison actually work, or
does holding one reviewer fixed just move the bias rather than remove it?

**Stage 6.** Deterministic, no model, no R. Refuses all verdicts when the round is
`INSUFFICIENT_ACQUISITION`. Is the evidence table sufficient as the deliverable, or is a verdict
without a magnitude going to be useless to whoever has to act on it?

## Part four: is any of this still the wrong shape?

Four stages are now specified and three have implementation plans. Stage 2 is the only one built.

- Is specifying stages 4, 5 and 6 before executing any of the three ready plans front-loading the
  wrong end again? Your first review said a thin vertical slice beats a complete front end.
- The project now has 17 design decisions, 8 specs, 4 plans and about 2,400 lines of code. Is the
  ratio of writing to working software itself a finding?
- With the floor at 0.80 and the rate at 0.60 — 14 of 25 once the fact sheet is excluded — stage 6
  will refuse to produce verdicts on this corpus. Is building the whole verdict path before that is
  resolved defensible, or should the acquisition problem be closed first?

## How to answer

- Cite `path:line` for every claim about code or spec text.
- Rank by consequence. Three real defects beat twenty nits.
- Where something is wrong, say what you would do instead.
- If a subsystem should not exist, say so — you did that once and it was the most useful finding.
- Run `.venv/bin/pytest -q`, `.venv/bin/claimstone validate --all-projects`,
  `.venv/bin/python tools/derive_corpus_figures.py alembic-s4` and
  `.venv/bin/python tools/check_instrument_versions.py`. Tell me where output contradicts documents.
- **Ignore commit messages as evidence.** Same author as the code, least trustworthy artifact in the
  repository. Where a message and the code disagree, the message is lying.
