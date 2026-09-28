# Handoff

Written 2026-09-28, after the first end-to-end round; completeness corrected by D45. It holds what the
repository does not: live state, pending decisions, and the things that were established in conversation
and would otherwise be lost.

`CLAUDE.md` is the contract and overrides this file wherever they differ. `AGENTS.md` says what to read in
what order.

## Where the work stands

One round has run all six stages: `pmc-screen-time`, 37 of 40 confirmed against a floor of 0.80, 1,668
claims, 8 historical profiles, **0 verdicts**. **None is adjudicable under the completeness check in D45.**
There are 34 unanswered extraction readings: effect 10, heterogeneity 4, method 15, premise 5.
D46 additionally requires gate v4: the real ledger has not been re-harvested, so every profile reports
`awaiting_regate` too. D47 repaired authoritative replay and immutable reader annotations; D48 closes
all fifteen software review findings, including active chunk generations and complete result review.
The full D48 temporary replay preserves all 1,668 PMC claim ids; alembic-s4 retains 6,991 old ids and
creates 203 new ids, with 7,194 accepted annotations and 1,166 rejections afterwards. These are
annotation counts, not independent studies or ground truth. Every repeat appends zero rows and hashes
confirm the real ledgers are unchanged.

**The original 83 reviews remain historical, and zero attest the new v2 full-annotation task.** Q04
therefore needs an independent complete review as well as its 10 missing effect readings. Its prior
review counts describe the narrower old task and cannot certify its metadata. Profile instrument 5
requires rebuilding and reading; no historical hash is signable. No paid review or acquisition ran.

The next operational step is production offline replay of stored answers, followed by completing
unanswered extraction and independent v2 review under an operator-approved budget/backend. The
software checks and copy-based replay are complete; new scientific readings are not.

Two other instances exist and both stand below their floor and produce nothing: `alembic-s4` at 0.56 with a
measured ceiling of 0.72, and `pilot-screen-time` at 0.45. That is the correct behaviour, not a backlog.

## Running, or left running

- **GROBID** is up (`docker compose up -d grobid`), healthy, ~3.6 GB. Only `normalize` needs it. Stop it
  with `docker compose down` when idle; it is `restart: unless-stopped`, so it will come back on reboot.
- **Nothing else is in flight.** Drained means no routine retry is pending, not that every reading
  succeeded. Every batch in `store/*/calls/` is drained. A batch is resumable by
  `call_id`, so re-running `model-run` on any of them costs nothing for work already done.

## The decisions to read first

`DESIGN_DECISIONS.md` is 2,000 lines. For what happens next, these are the ones that bind:

| | why it binds |
|---|---|
| **D36** | the per-class floor exists and `alembic-s4` deliberately does not use it, because fitting a bar to a rate already seen is what the invariant prevents. Its closing clause was **corrected** on 2026-09-27: it claimed `sources.yaml` pre-authorised declaring `IND` a pointer, and it does not. |
| **D38** | a reviewer table that was **retracted the same day**. Its numbers measure the tool's filter, not the readers. The consequence matters: hosted reviewers are **unmeasured**, not bad. |
| **D39** | 0.64 on literature that declares itself free, and why the gap does not close by retrying. This is the only evidence a floor revision could rest on. |
| **D40 + D44** | a second reader marks 23 of 41 and 36 of 42 gate-passed claims `NOT_APPLICABLE`. Over-attachment is the dominant cost of the current call shape, and it is not a property of one question kind. |
| **D41** | why the closed round is legitimate: the selector is deposits, not outcomes, and it excludes 159 of 199 candidates. |
| **D48** | all review repairs; full-result reviews are a new task, legacy revisions are retained but cannot certify it. |
| **D47** | authoritative replay and immutable reader annotations; measured across all stored batches without changing real ledgers. |
| **D46** | whole numeric tokens, revision-aware gate outcomes and `awaiting_regate`; measurements used temporary ledgers. |
| **D45** | completeness, scope and live signature validation; corrects D44’s claim that Q04 was ready to sign. |
| **D43** | the notation vocabulary was domain knowledge in the engine and a corpus in another field proved it. The `extraction` config section that fixes it had never been loaded at all. |

## What is a person's decision and not an engine's

**The adjudication.** Q04 must first complete its 10 missing effect readings, harvest and review any new
claims, and be rebuilt and read again. Its historical hash
`8e93cbde7a5a11a2e6d84933dd48539194d22ace3b149f7f2b10003e440c0bf0` is not signable under
`profile_version 5`. The current read-only preview marks it provisional. Nothing in the historical profile supports the
question; five results bear on it, and one of the five is not a result at all (D44). Whether that reads
`CONTRADICTED` on two independent papers or `UNANSWERED_IN_LITERATURE` on a coverage of 3 sources of 37 is
a judgement, and an agent must not make it. The rationale has to state the round's scope, its coverage, and
that bad row.

**Whether the floor moves.** D39 is the first evidence that 0.80 may be unreachable for openly-obtainable
literature by legal routes. That is a real basis for a dated, versioned, motivated revision — and it is the
operator's call. An agent proposing it must cite the measurement and must not fold it into other work.

**Whether to spend on independent full-result review.** D48 changes the task: the historical estimate
of about 1,100 calls covered only the remaining seven questions. Now all eligible annotations, including
Q04, need a v2 review. Rebuild the proposed queue and measure its size before choosing a backend/budget.

## Open problems, with what is known about each

**The reviewer does not scale, measured twice.** `claude-opus-5` discriminates — its verdicts on 83 real
claims are checkable and correct on inspection — but it runs on an interactive subscription plan and
`claude-cli` returned `BACKEND_ERROR: exit 1` on 8 of 43 H15 calls and **36 of 42** Q04 calls before the
limit reset. CLAUDE.md's standing constraint ("interactive subscription plans are not batch
infrastructure") is therefore measured, not precautionary. The calls retry cleanly afterwards.

*The honest path to a reviewer that scales*: measure a hosted reader's **agreement with `claude-opus-5`**
over the 83 claims already reviewed **using the same old task**. Full-annotation v2 reviews require a
new comparison; agreement with an old verdict cannot measure agreement on fields it never saw.
That is inter-rater agreement and not ground truth, and it must be reported as such — but it is a real measurement, unlike D38's retracted attempt, and it costs a few hundred
Ollama Cloud calls. `SameReader` forbids `deepseek-v4.1-flash`, which did the extracting.

**Europe PMC is the highest-value acquisition improvement left, and was deliberately not done.** Its REST
API serves full-text JATS XML by design and would plausibly beat the 0.93 the HTML route reaches. It was
skipped because `normalize` handles GROBID's TEI and not JATS, so adding it is a new parser path and a chain
of new assumptions — which was the wrong thing to start while closing a round. It is the right thing to
start next.

**Over-attachment in stage 4.** Every chunk is asked about every question of its kind and the model answers
rather than declining. 23 of 41 and 36 of 42 claims do not speak to the question they cite. Nothing
mechanical can catch it — the gate's `WRONG_KIND` check passed all of them correctly — so the fix is the
prompt or the unit shape, and it should be measured against the 83 reviewed claims that now exist as a
reference.

**The 586 rows that explain the largest rejection class.** In 586 of 593 `NUMBER_NOT_IN_QUOTE` cases the
asserted figure *is* in the chunk and not in the quoted span: the model quotes one sentence and cites a
figure from the table two lines below. It is a property of the call shape, and it is why the gate's standard
and the reviewer's must differ (D38).

## A discipline this session had to adopt, from four failures

Four times in one day a fix's effect was predicted from counting a signature in a small sample, and four
times the prediction was far too high — 45 predicted and 1 delivered, 166 and 18, 6 and 1, and one
hypothesis falsified outright. **Quote what `regate` or a re-harvest returns, never what a sample suggests.**
The rule is recorded in D37 and D39 and it applies to any figure an agent puts in front of the operator.

The related failure, three times: a test that greps source text matches the comments *explaining* the thing
it forbids. Walk the AST, or strip comment lines first.
