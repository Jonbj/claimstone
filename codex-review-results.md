# Claimstone — adversarial review for the spec author

Date: 2026-09-24. Scope: current code, `store/alembic-s4/`, and the three unexecuted plans named in `codex-review-prompt.md`. Commit messages were not used as evidence. This is a review, not an implementation.

## Decision requested

Do not implement stage 6 as currently described. First define what each question asks, what evidence could answer it, and when evidence is insufficient or conflicting. Random-effects pooling, PET-PEESE and MAIVE should be optional analyses for a pre-specified subset of genuinely comparable, verified effect estimates, not the default operation on LLM-extracted claims.

Before building any verdict pipeline, fix the acquisition denominator. As written, the gate can approve a round in which only one of 25 found candidates was attempted.

## Findings ranked by consequence

### 1. The acquisition floor can pass a nearly unread corpus

`claimstone/admissibility.py:61-67,92-106` computes `attempted = len(collapse(acquisitions))` and divides by that value. The declared rule in `projects/alembic-s4/sources.yaml:33-45` is a share of *found* sources. I reproduced this with 25 candidate rows and one successful acquisition row: `rate()` returned 1.0. Thus an incomplete run, `acquire --limit`, or newly discovered but unattempted candidates could pass the 0.80 floor. The real 25-source round happens to have attempted every candidate, so its current 0.60 is not inflated by this particular bug.

**Change:** define a frozen candidate set per round; report found, classified, attempted, obtained and confirmed separately; gate on confirmed/found only after the round is complete. Decide and document how unclassified candidates affect that denominator. The stage 1 plan deliberately writes `source_class: null` (`docs/superpowers/plans/2026-09-24-stage1-discover.md:1047-1055`), while `claimstone/acquire.py:54-58` refuses to acquire them. They must not disappear silently from coverage accounting.

### 2. Stage 3's own implementation contradicts its advertised 14/25

The local ledger has 15 obtained sources: 14 PDFs and one HTML full text (`IND001`). The plan's `normalize.run()` records every non-PDF as `fulltext_confirmed: False`, `failure_class: NOT_PDF` (`docs/superpowers/plans/2026-09-24-stage3-normalize.md:1369-1380`). Once `IND008` is correctly rejected as a fact sheet, the plan would report **13/25**, not the spec's **14/25** (`docs/superpowers/specs/2026-09-24-stage3-normalize-design.md:210-219`). It also increments `confirmed` for sources with no document row yet (`docs/superpowers/plans/2026-09-24-stage3-normalize.md:1683-1713`), so the metric called “confirmed” can include unexamined bytes.

**Change:** implement an HTML normalization/confirmation path before switching the report to a confirmed basis. Keep pending normalization separate and prevent a final confirmed rate or verdict while it remains pending. Add a real 14-PDF + 1-HTML fixture to the plan's accounting tests.

### 3. `model_call` does not implement the backend comparison that justifies it

`Queue.pending()` treats a successful `call_id` as done regardless of backend (`docs/superpowers/plans/2026-09-24-model-call.md:595-608`). Draining the same batch with backend B after backend A produces no B results. `model_report.summarise()` then collapses all results by `call_id` (`docs/superpowers/plans/2026-09-24-model-call.md:1860-1865`), losing retry cost, retry latency and any earlier backend's result. The planned report cannot answer “which backend is better?” or “what did the batch cost?”

There are two concrete plan execution failures:

- `test_a_runner_that_mangled_the_prompt_is_caught` expects `PROMPT_MISMATCH` (`docs/superpowers/plans/2026-09-24-model-call.md:817-825`), but `drain()` gives the runner a copy (`docs/superpowers/plans/2026-09-24-model-call.md:981`) and `build_result()` rehashes the original request (`docs/superpowers/plans/2026-09-24-model-call.md:929-936`). The mutation cannot be observed; the test cannot pass as written.
- CLI `--model` is optional (`docs/superpowers/plans/2026-09-24-model-call.md:2065-2070`), but `CliRunner` requires `model` (`docs/superpowers/plans/2026-09-24-model-call.md:1223-1227`). `_model_run` constructs it without that argument when omitted and catches only `ValueError`, not the resulting `TypeError` (`docs/superpowers/plans/2026-09-24-model-call.md:1994-1999`).

**Change:** identify attempts by `(call_id, backend, model, harness_version, attempt_no)`; keep every attempt for cost accounting and a separate selected result per backend. Have the runner return or record the actual prompt it sent, if prompt-echo verification is a requirement. Require `--model` for backends needing it, or give each runner an explicit default.

### 4. The second discovery channel is useful but does not estimate completeness here

The stage 1 spec itself says the curated manifest is not a random sample, exact-title matching misses known overlaps, and the citation threshold creates unequal catchability (`docs/superpowers/specs/2026-09-24-stage1-discover-design.md:153-170`). The implementation plan correctly forbids a Lincoln-Petersen estimate (`docs/superpowers/plans/2026-09-24-stage1-discover.md:1324-1338`). This removes the stated justification in `docs/DESIGN_DECISIONS.md` D10: two channels do not, by themselves, make completeness estimable. The citation channel is valuable for finding omissions; its raw overlap is not a population estimate.

**Change:** present keyword and citation yields and their overlap as descriptive diagnostics. Treat “705 references not in the manifest” as a manifest coverage finding, not as a population coverage percentage. If completeness is an intended claim, design a separate sampling/validation study.

### 5. The storage semantics are more subtle than the claimed crash recovery

`claimstone/admissibility.py:21-50` chooses between latest row, latest success and latest re-gate; `claimstone/gate_audit.py:23-70` recovers artifact pointers from the entire log. These are necessary business rules, not incidental views. `Store.append()` writes a line without transaction or recovery handling and `Store.read()` parses every nonempty line directly (`claimstone/store.py:34-54`). A truncated last line after a crash makes the ledger unreadable, contrary to the unqualified “resumable after a crash” claim in `README.md`.

**Change:** document one authoritative event schema and collapse rule, and implement last-line recovery or atomic journal writes. Test an interrupted append and replay. SQLite as a derived read model remains reasonable; the JSONL decision needs a real recovery guarantee.

## Audit of the seven invariants in `CLAUDE.md`

| # | Finding | Evidence |
|---|---|---|
| 1 — verified quote | **Not implemented.** No extraction gate or rejection ledger exists yet. | `claimstone/cli.py:14,267-269` |
| 2 — four verdicts | Constants exist, but no code assigns or validates final verdicts. | `claimstone/config.py:18-20`; `claimstone/cli.py:267-269` |
| 3 — floor gates verdicts | `admit()` produces a status, but its denominator is wrong; synthesis does not exist. | `claimstone/admissibility.py:61-106`; `claimstone/cli.py:267-269` |
| 4 — no domain knowledge | Topics and source classes are YAML, but short HTML admission assumes English bibliography headings or author-year citations. This can reject legitimate documentation or non-English research. | `claimstone/fulltext.py:61-68,124-128,155-167` |
| 5 — dated registry bump | Loader validates a positive version, date and unique IDs, but cannot detect changed question text under the same version. | `claimstone/config.py:181-217` |
| 6 — source class per item | Acquire refuses a missing class. The current API discovery row does not include one; the stage 1 plan still allows null classes into its ledger. | `claimstone/acquire.py:54-58`; `claimstone/discover.py:28-60`; stage 1 plan `:767-773` |
| 7 — no vote counting | No synthesis exists, so this is currently a design commitment only. | `claimstone/cli.py:267-269` |

For invariant 4, moving class names to YAML solves one kind of domain coupling but not the admission rule. A project involving regulations, technical standards, non-English sources or primary records needs to be expressible without editing `claimstone/fulltext.py`. Make content-gate policy depend on declared source type and language, with an explicit “needs review” outcome for uncertain cases. Do not silently weaken the gate globally.

## What the measured numbers support

- Replayed from `store/alembic-s4/acquisitions.jsonl` using the current collapse rule: **12/25 = 0.48** after the re-gate and **15/25 = 0.60** after the named campaign. Current `claimstone report projects/alembic-s4 --json` gives ACA 7/10, IND 3/9, MET 5/6; failures are six `ABSTRACT_ONLY` and four `PAYWALL_403`; status is `INSUFFICIENT_ACQUISITION`.
- The 15 current obtained artifacts are 14 PDFs and one HTML full text. `IND008` is a known false positive, so **14/25 = 0.56** is the documented adjusted count (`docs/DESIGN_DECISIONS.md:139-155`). The CLI still exposes 0.60 as `rate` without this qualification (`claimstone/cli.py:122-149`).
- The baseline **0.42** is not reproducible from this repository; D11 already acknowledges that (`docs/DESIGN_DECISIONS.md`, D11). The **818,678 body characters**, **711 distinct references** and **overlap of 6** occur in the specs (`docs/superpowers/specs/2026-09-24-stage3-normalize-design.md:10-19`; `docs/superpowers/specs/2026-09-24-stage1-discover-design.md:24-40`), but the generated TEI and `references.jsonl` are not present in the current store. The raw PDFs are present; reproducing those figures needs the specified GROBID version/configuration and a saved derivation. Do not call these three numbers independently audited by the current code.
- The first stage 3 run should persist its TEI, counts, parser version and a reproducible report of the derivation. A synthetic fixture cannot validate corpus-level counts.

## Stage 6: replace the default synthesis design

An exact-substring quote verifies provenance of text. It does not establish that the LLM chose the right study result, extracted its estimand and uncertainty correctly, or handled study quality. The 28 questions mix empirical effects with methodological requirements and operational judgments: for example H04, H15 and H23 (`projects/alembic-s4/questions.yaml:16-17,39-40,54-56`). Pooling claims across event studies, text analyses and methods references would generally lack a common estimand. Random effects account for variation among comparable effects; they do not give an interpretable mean to incomparable outcomes.

Recommended sequence:

1. For each question, predefine eligible study designs, outcome, direction, horizon, population, meaningful effect and what would count as a counterexample. Identify which questions are not effect-estimation questions at all.
2. Extract a structured *study-result* record, including estimate, scale, standard error or interval, sample, horizon, design, dependencies and source quote. Keep claims as evidence annotations, not independent observations. Verify decisive numerical records against the source, including tables and footnotes.
3. Produce a structured evidence table per question: pertinent studies, findings in each direction, risk of bias, missing acquisition, missing precision and important disagreements. This is not an informal count of significant results. Cochrane's guidance explicitly distinguishes structured synthesis from vote counting by significance: https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-12 . SWiM provides reporting guidance: https://www.bmj.com/content/368/bmj.l6890 .
4. Allow meta-analysis only for a pre-specified subset with compatible estimands and verified sampling variances, with within-study dependence handled explicitly. Cochrane recommends omitting a pooled estimate when observational studies are insufficiently similar: https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-24 .
5. Treat PET-PEESE/MAIVE as sensitivity analyses where their inputs and assumptions fit. MAIVE needs a sufficiently strong relationship between inverse sample size and reported variance, enough estimates, and an assumption about sample-size selection; it cannot repair missing or incomparable effect estimates: https://www.nature.com/articles/s41467-025-63261-0 .

Define `SUPPORTED` operationally before coding. The definition needs question-specific evidence sufficiency, coverage, design quality, replication and rules for material counterevidence. The current four verdicts do not clearly express “relevant literature exists but conflicts”; provide an explicit abstention/indeterminate outcome or a documented no-verdict status rather than forcing it into `UNANSWERED_IN_LITERATURE`.

The multiplicity correction across approximately 28 questions also needs a defined family of statistical hypotheses. Many registry entries are methodological statements, so applying one adjusted significance threshold to all 28 is not meaningful.

## Architecture and delivery

- **Model boundary:** keep the work-unit/result file contract for audit and replay, but start with one functioning backend and one measured comparison sample before implementing five adapters and a full cost dashboard. Fix the comparison identity first.
- **Dashboard:** keep it deferred. `docs/superpowers/specs/2026-09-22-dashboard-design.md:18-34` already places it after real rows; it may not be needed if the CLI report answers progress and coverage questions.
- **Six stages:** the number of stage names is not the main cost. Protect the transitions between “found”, “attempted”, “obtained”, “confirmed” and “usable for a verdict”. A thinner vertical slice through those states is more valuable than a complete discovery front end before any verdict logic exists.
- **This manifest and the 0.80 floor:** 15 provisionally obtained + all four remaining 403s = 19/25, below the required 20. With the known false positive excluded, 14 + 4 = 18. Recovering only the four walls cannot reach the floor (`docs/DESIGN_DECISIONS.md:152-165`). Some of the six abstract/product pages might have separate full texts, so impossibility for all future acquisition methods is not proven. With the current cascade and evidence, the deliverable remains `INSUFFICIENT_ACQUISITION`. Any manifest eligibility change should be motivated and versioned; lowering the floor because this round failed would invalidate the intended control.

## Commands and result

```text
.venv/bin/pytest -q
105 passed, 3 skipped in 0.31s

.venv/bin/claimstone validate --all-projects
OK alembic-s4: 16 topics, 28 questions, 6 classes, floor 0.80, 25 manifest rows
OK example-news-and-returns: 16 topics, 20 questions, 6 classes, floor 0.80
```

These checks establish that the existing tests and input validation pass. They do not exercise the unimplemented stages or the end-to-end scientific claims.

## Suggested order for revising the specs and plans

1. Fix round identity and the found-source denominator; specify partial-run behavior.
2. Correct stage 3's HTML path, pending state and 14/25 accounting; add a corpus-level reproducibility artifact.
3. Define question-level eligibility, study-result extraction and an abstention rule before designing stage 6 statistics.
4. Repair `model_call` comparison identity, attempt accounting, impossible prompt-mismatch test and optional-model CLI failure.
5. Rephrase D10 as discovery gain rather than completeness estimation; preserve raw channel counts and caveats.
