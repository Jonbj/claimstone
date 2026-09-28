# Handoff

Written 2026-09-28, after the first end-to-end round; completeness corrected by D45. It holds what the
repository does not: live state, pending decisions, and the things that were established in conversation
and would otherwise be lost.

`CLAUDE.md` is the contract and overrides this file wherever they differ. `AGENTS.md` says what to read in
what order.

## Where the work stands

One round has run all six stages: `pmc-screen-time`, 37 of 40 confirmed against a floor of 0.80,
1,721 accepted annotations and 271 current rejections, **0 verdicts**. There are eight historical
profiles and eight newly built v5 profiles. **Q04 is formally complete and awaiting human reading;
the other seven remain provisional.** Its current hash is
`9340389c9aac29b77e901c20e27434d211fe9e7825a68d99995d8c6fa5b20fdd`.

D49 applied the offline replay while preserving original bytes. D51/D52 subsequently harvest 53 new
PMC annotations and 12 new rejections from model responses. Repeat extraction harvest appends zero
of either; repeat review harvest reports zero reviewed and 42 already held. These are annotations,
not independent studies. All current scoped annotations satisfy gate v4; harvest/regate backlog is zero.
The historical narrow-task reviews remain in the append-only ledgers; 42 Q04 annotations now also
have usable complete-annotation v2 reviews. No historical profile hash is relabelled or signed.

PMC has 24 unanswered readings: effect 0, heterogeneity 4, method 15, premise 5. The measured
remaining full-review workload is 1,679 unique calls, all outside Q04. The completed effect readings
cover all 734 active chunks. Q04 has 42 current annotations, all independently reviewed by
`ollama-cloud/mistral-large-3:675b`: 4 SUPPORTED, 31 OVERSTATED and 7 NOT_APPLICABLE. SUPPORTED
is the single-annotation review label, not a verdict on the question. The profile retains four results
from four of 37 examined sources, with sample linkage unestablished.

The operator delegated the bounded Q04 run. Seven primary extraction answers and three targeted
`gemma4:31b` answers complete its ten missing readings; original invalid responses remain invalid.
Mistral differs from both extractors. No publisher, parser, registry, floor or population was changed.
The USD 1 plan records USD 0.0556299 at conservative rates, plus USD 0.339 reserved for the old
unknown-cost DNS failure: USD 0.3946299 accounted. This is not a provider invoice. Agent inspection
matches the saved audit/profile hash; no additional model call or profile rebuild was made by the agent.

The human-reading packet is local and gitignored:
`store/pmc-screen-time/audits/reading/6b11da9f50a22c8fbeb4a1cd3b43a132c7034f88e0c75ca9e19a60647781254e.md`.
It flags the relevance/stance of each of the four retained results, especially PMC009's GRADE rating
labelled CONTRADICTS without testing preregistration or correction for multiple comparisons. These
are inspection notes, not new ledger decisions or a scientific verdict. Throughput and valid-output
rate are measured; scientific agreement with an independent v2 reference is not established.

Read the live profile without requests:

```bash
.venv/bin/claimstone verdicts projects/pmc-screen-time --question Q04
```

The completed host audit is
`store/pmc-screen-time/audits/question-round/1943dcbe8082fa76370d8b9fd0b013a55c59e74c04a6a2e24b3b9afa19442e4b.json`.
See D52 and [the completed round report](replays/2026-09-28-q04-ready.md). The cumulative local v2
plan is retained for audit/resume; it is not an instruction to start the other seven questions.

Alembic's curated manifest still has 28 unanswered readings and 6,183 prospective review calls covering
6,188 annotations. It is 14/25 confirmed (0.56), below its floor. Its 27 missing raw responses remain
unresolved; the whole-store count must not replace the selected population.

The earlier queue measurement was offline and used only temporary copies. See
[the production replay report](replays/2026-09-28-production-replay.md) and local content-addressed
audits under `store/<project>/audits/offline-replay/`.

Two other instances exist and both stand below their floor and produce nothing: `alembic-s4` at 0.56 with a
measured ceiling of 0.72, and `pilot-screen-time` at 0.45. That is the correct behaviour, not a backlog.

## Running, or left running

- **GROBID** is up (`docker compose up -d grobid`), healthy, ~3.6 GB. Only `normalize` needs it. Stop it
  with `docker compose down` when idle; it is `restart: unless-stopped`, so it will come back on reboot.
- **Nothing else is in flight.** Drained means no routine retry is pending, not that every reading
  succeeded. The bounded Q04 driver now has no eligible extraction/review work remaining.
  A batch is resumable by `call_id`; answered calls are skipped, while transient failures may retry.

## The decisions to read first

`DESIGN_DECISIONS.md` is 2,000 lines. For what happens next, these are the ones that bind:

| | why it binds |
|---|---|
| **D36** | the per-class floor exists and `alembic-s4` deliberately does not use it, because fitting a bar to a rate already seen is what the invariant prevents. Its closing clause was **corrected** on 2026-09-27: it claimed `sources.yaml` pre-authorised declaring `IND` a pointer, and it does not. |
| **D38** | a reviewer table that was **retracted the same day**. Its numbers measure the tool's filter, not the readers. The consequence matters: hosted reviewers are **unmeasured**, not bad. |
| **D39** | 0.64 on literature that declares itself free, and why the gap does not close by retrying. This is the only evidence a floor revision could rest on. |
| **D40 + D44** | a second reader marks 23 of 41 and 36 of 42 gate-passed claims `NOT_APPLICABLE`. Over-attachment is the dominant cost of the current call shape, and it is not a property of one question kind. |
| **D41** | why the closed round is legitimate: the selector is deposits, not outcomes, and it excludes 159 of 199 candidates. |
| **D49** | production replay completed, with preserved bytes; actual scoped remaining readings and full-review workload. |
| **D50** | delegated Q04 readers, bounded continuation and the first recorded DNS failure; no reading or review was completed. |
| **D51** | five host readings harvested, strict prose rejection, targeted alternate extractor and shared budget. |
| **D52** | Q04 formally complete; four retained results need human relevance/stance assessment before adjudication. |
| **D48** | all review repairs; full-result reviews are a new task, legacy revisions are retained but cannot certify it. |
| **D47** | authoritative replay and immutable reader annotations; measured across all stored batches without changing real ledgers. |
| **D46** | whole numeric tokens, revision-aware gate outcomes and `awaiting_regate`; measurements used temporary ledgers. |
| **D45** | completeness, scope and live signature validation; corrects D44’s claim that Q04 was ready to sign. |
| **D43** | the notation vocabulary was domain knowledge in the engine and a corpus in another field proved it. The `extraction` config section that fixes it had never been loaded at all. |

## What is a person's decision and not an engine's

**The adjudication.** Q04 is now formally complete under profile v5, with the current hash above;
the historical D44 hash is not signable. A person must read the four retained annotations and their
passages, assess their relevance to both preregistration and multiple-comparison correction, and
state the PMC-deposit scope and coverage in the rationale. D52's reading packet identifies specific
stance/attribution ambiguities. An agent does not choose or sign the verdict, and no verdict exists.

**Whether the floor moves.** D39 is the first evidence that 0.80 may be unreachable for openly-obtainable
literature by legal routes. That is a real basis for a dated, versioned, motivated revision — and it is the
operator's call. An agent proposing it must cite the measurement and must not fold it into other work.

**Whether to spend on independent full-result review.** D48 changes the task: the historical estimate
of about 1,100 calls covered only the remaining seven questions. Now all eligible annotations, including
Q04, need a v2 review. D49 measures 1,668 PMC calls, including 42 for Q04, before any new extraction
results. Q04 is completed in D52. The remaining queue is 1,679 calls and extending paid review to
the other questions remains the operator's decision, based on the current measured queue.

## Open problems, with what is known about each

**The reviewer does not scale, measured twice.** `claude-opus-5` discriminates — its verdicts on 83 real
claims are checkable and correct on inspection — but it runs on an interactive subscription plan and
`claude-cli` returned `BACKEND_ERROR: exit 1` on 8 of 43 H15 calls and **36 of 42** Q04 calls before the
limit reset. CLAUDE.md's standing constraint ("interactive subscription plans are not batch
infrastructure") is therefore measured, not precautionary. The calls retry cleanly afterwards.

*The hosted reviewer measurement*: D52 records 42/42 valid full-v2 Mistral responses on Q04.
The four retained cases carry relevance/stance flags for human reading. This measures valid output
and execution, not scientific accuracy. Agreement with `claude-opus-5` over the original 83 reviews
would require using the same old task; it cannot certify metadata those reviews never saw. Full-v2
agreement requires a new independent reading or human reference. Inter-rater agreement is not ground
truth, and no such full-v2 comparison has yet been measured. `SameReader` still forbids the extractor
from reviewing its own annotations.

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
