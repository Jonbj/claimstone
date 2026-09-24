# Adversarial review of Claimstone

You are reviewing a research-tooling project to find what is **wrong** with it. I am the author
of nearly everything you are about to read, and I want disconfirmation, not validation. A review
that concludes "this looks solid" has told me nothing I can act on.

## What the project claims to be

Claimstone takes a set of topics and a frozen list of numbered questions, obtains the literature
legally, extracts what each source claims with every claim bound to a verbatim quote verified in
code, and returns a verdict per question from four states: `SUPPORTED`, `CONTRADICTED`,
`UNANSWERED_IN_LITERATURE`, `NEVER_ASKED`.

It exists because a real corpus in a consuming project was read at 42% and its pipeline reported
itself saturated. The project's whole value proposition is refusing to overstate what it knows.

Read in this order: `README.md`, `CLAUDE.md`, `docs/DESIGN_DECISIONS.md` (13 numbered decisions,
each claiming to carry the measurement that decided it).

## Current state

- ~2,300 lines across 12 modules, 105 tests passing, 3 skipped (network, off by default)
- **Stage 2 (acquire) is implemented and measured.** Stages 1, 3-6 are not.
- 5 design specs and 4 implementation plans under `docs/superpowers/`, none executed except
  stage 2's
- One real corpus: `store/alembic-s4/`, 25 sources from a hand-curated manifest

The headline measurement, in `docs/DESIGN_DECISIONS.md` under D8: acquisition went from 0.42 to
0.60, sits below a declared floor of 0.80, and is annotated as an **upper bound** because one
acquired PDF was later found to be a vendor fact sheet.

## What I want you to attack, in priority order

### 1. Do the invariants hold in the code, or only in the prose?

`CLAUDE.md` lists seven non-negotiable invariants. For each, find where the code enforces it or
show that nothing does. I am most suspicious of invariant 1 (no claim without a verified quote),
because the stage that would enforce it does not exist yet, and invariant 4 (the engine holds no
domain knowledge), because I kept finding domain-shaped things and moving them into YAML — check
whether I actually succeeded or merely relocated the problem.

### 2. Are the measured claims honest?

Several numbers are load-bearing: 0.60 acquisition, 12 of 25 full texts, 818,678 characters of
body text, 711 distinct references, an overlap of 6 between two discovery channels. Re-derive
what you can from `store/alembic-s4/` and the code. Tell me where a number is stated more
confidently than its derivation supports. Pay attention to denominators — several bugs in this
project were exactly that.

### 3. Are the three unexecuted plans actually implementable as written?

`docs/superpowers/plans/2026-09-24-{model-call,stage3-normalize,stage1-discover}.md`. They
contain complete code for every step and will be executed by a model with no context beyond the
file. Find: type signatures that disagree between tasks, tests that cannot pass against the code
in the same plan, arithmetic errors in expected values, steps that assume state an earlier task
did not create. I found five such errors in my own self-reviews and expect I missed more.

### 4. Is the architecture right, or is it elaborate?

Specifically challenge these, which are my decisions and may be over-built:

- `model_call` (spec + plan): a file boundary with interchangeable backends, justified by "which
  backend is better is a measurement, not a decision". Is that worth its complexity for a project
  that may only ever use one backend?
- The dashboard spec, deferred to last and possibly never worth building.
- Six stages with strict data ownership. Would four do?
- Append-only JSONL as the source of truth, with several "collapse" rules layered on top
  (`admissibility.collapse`, `gate_audit._artifacts`). The rules got subtle — is the storage
  model paying for itself?

### 5. Is meta-analysis the right frame for stage 6 at all?

This is the part where I have **no measurements and no domain expertise**, so treat it as the
least defended part of the design. It is specified only in `README.md` and D6; there is no spec
document yet, and I would rather find out now that the plan is wrong than write one.

The intent: pool effect sizes across sources with random-effects meta-analysis, delegated to an R
script using `metafor` across a file boundary, with publication-bias correction in the economics
form (FAT-PET-PEESE, and MAIVE because reported standard errors in observational research are not
trustworthy). Then a verdict per question, with a multiplicity correction across ~28 questions.

Challenge the premise, not the implementation:

- The inputs are **claims extracted by a language model from heterogeneous papers**, each bound
  to a quote — not a curated set of comparable effect estimates with known standard errors. Can
  anything be pooled from that? Is expecting an effect size and its precision to survive that
  extraction realistic, or is this a category error dressed as statistics?
- The corpus mixes event studies, textual-analysis papers and methodology references across
  different outcome variables, horizons and samples. What would a pooled estimate across them
  even denote?
- If pooling is not defensible, what *should* a "verdict per question" rest on instead — and
  would that still be better than the vote counting the project explicitly rejects?
- Is PET-PEESE plus MAIVE the right correction here, or is it cargo-culted from a literature that
  does not match this use?
- What should `SUPPORTED` mean operationally? No threshold is defined anywhere, and I suspect
  that absence is hiding a hard problem rather than deferring an easy one.

A well-argued "do not build stage 6 as described" is the most valuable answer you could give.

### 6. Will this reach its stated deliverable?

The floor is 0.80 and the measured rate is 0.60, with 4 hard publisher 403s and 6 sources that
are not documents. Is the goal reachable on this corpus, or is the project structurally committed
to reporting `INSUFFICIENT_ACQUISITION` forever? If the latter, say so plainly.

## What I am already uncertain about

Do not spend effort confirming these; extend or refute them.

- The citation channel admits references cited by 2+ corpus documents, which biases toward
  canonical works — and I use that bias while also relying on unequal catchability being a
  problem for capture-recapture. That may be incoherent.
- Building stages 1-3 thoroughly before 4-6 exist may be front-loading the wrong end.
- Several thresholds (gate character counts, confirmation counts) were chosen by looking at one
  corpus of 14-25 documents. Sweeps show them flat, but flat on n=14.

## How to answer

- Cite `path/to/file.py:line` for every claim about the code.
- Rank findings by consequence, not by count. Three real defects beat twenty nits.
- Where you think something is wrong, say what you would do instead.
- If you conclude a whole subsystem should not exist, say that — it is more valuable than a bug.
- Run `.venv/bin/pytest -q` and `.venv/bin/claimstone validate --all-projects`, and tell me if
  anything you see contradicts what the docs claim.
- **Ignore commit messages as evidence.** They are written by the same author as the code and are
  the least trustworthy artifact in the repository. Where a message and the code disagree, the
  message is what is lying.
