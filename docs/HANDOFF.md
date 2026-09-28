# Handoff

Written 2026-09-28, after the first end-to-end round; completeness corrected by D45. It holds what the
repository does not: live state, pending decisions, and the things that were established in conversation
and would otherwise be lost.

`CLAUDE.md` is the contract and overrides this file wherever they differ. `AGENTS.md` says what to read in
what order.

## Where the work stands

One round has run all six stages: `pmc-screen-time`, 37 of 40 confirmed against a floor of 0.80, 1,668
claims, 8 historical profiles, **0 verdicts**. **None is adjudicable under the completeness check in D45.**
D49 applies the complete offline replay to the real PMC and Alembic stores. Every original byte is
preserved; derived ledgers only receive additional rows and each whole repeat appends zero rows.
PMC retains all 1,668 claim ids and has 259 current rejections. Alembic retains 6,991 original claim
ids, gains 203 distinct ids and has 7,194 accepted annotations / 1,166 rejections across the whole
store. These are annotations, not independent studies. No model or publisher was called.

**All current scoped annotations now satisfy gate v4; `unregated` and `unharvested` are zero.**
The original 83 review ids remain historical, plus 33 additional Alembic reviews harvested from stored
responses: 116 historical ids and zero usable complete-annotation v2 reviews. A replay cannot supply
the new independent reading. Profile instrument 5 requires rebuilding and reading; no historical hash
is signable, and profiles were not rebuilt in this operation.

PMC still has 34 unanswered readings: effect 10, heterogeneity 4, method 15, premise 5. Its measured
full-review workload is 1,668 unique calls. Q04 needs 42 current annotations reviewed and shares the
10 missing effect readings. Completing extraction can add review work. All PMC annotations were
extracted by `ollama-cloud/deepseek-v4.1-flash`, which cannot review them.

Alembic's curated manifest has 28 unanswered readings and 6,183 prospective review calls covering
6,188 annotations. That population is 14/25 confirmed (0.56), below its floor; the whole-store
annotation count must not replace it. Its 27 results without raw response bytes remain unresolved.

On 2026-09-28 the operator delegated reader selection and authorised continuing Q04. The selected
extractor is `ollama-cloud/deepseek-v4.1-flash`; the independent reviewer is
`ollama-cloud/mistral-large-3:675b`. The bounded run plan has a USD 1 ceiling. Ten current effect
requests are prepared with an output cap of 7,500, and 42 full v2 reviews are queued. The first
extraction attempt failed resolving `ollama.com` in the agent environment; no response arrived,
no new annotation was harvested and no profile was rebuilt. Reviewer quality remains unmeasured.

Continue on the host with network access:

```bash
.venv/bin/python tools/complete_question_round.py --plan store/pmc-screen-time/audits/q04-run-plan.json --execute
```

Without `--execute` the command only inspects. It reads the two required values from `.env`,
resumes prepared calls, harvests extraction, adds reviews for new annotations, reviews with the
independent reader and rebuilds profiles only after Q04 is complete. It never adjudicates.
Every physical attempt counts against the cumulative budget; an unpriced failure reserves the
full declared context and output cap rather than being treated as free. The current unknown-cost
DNS attempt reserves USD 0.339. Execution stops at the first failed response or budget boundary.
See D50 and [the bounded continuation report](replays/2026-09-28-q04-continuation.md).

The earlier queue measurement was offline and used only temporary copies. See
[the production replay report](replays/2026-09-28-production-replay.md) and local content-addressed
audits under `store/<project>/audits/offline-replay/`.

Two other instances exist and both stand below their floor and produce nothing: `alembic-s4` at 0.56 with a
measured ceiling of 0.72, and `pilot-screen-time` at 0.45. That is the correct behaviour, not a backlog.

## Running, or left running

- **GROBID** is up (`docker compose up -d grobid`), healthy, ~3.6 GB. Only `normalize` needs it. Stop it
  with `docker compose down` when idle; it is `restart: unless-stopped`, so it will come back on reboot.
- **Nothing else is in flight.** Drained means no routine retry is pending, not that every reading
  succeeded. Historical batches are drained; D50's new Q04 extraction and review batches are pending.
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
Q04, need a v2 review. D49 measures 1,668 PMC calls, including 42 for Q04, before any new extraction
results. Q04 reader selection was delegated and bounded in D50; extending paid review to the
other questions remains the operator's decision, based on this measured queue.

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
