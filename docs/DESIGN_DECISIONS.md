# Design decisions, with the reason and the evidence

Recorded so they are not relitigated. Each carries what actually decided it.

## D1 — Extend, do not rewrite
A two-node literature pipeline already runs in the consuming project (protocol v4) with a
mechanical exact-substring evidence gate, a frozen question registry, an append-only
ledger and per-campaign retry budgets. Claimstone takes over the **acquisition front end**
and the **statistics back end**; it does not replace that pipeline and does not migrate it.
Contract between them is **files**, not imports.

## D2 — Topics in, questions out
Considered and rejected: a tool whose contract is "gather information on a set of topics".
It has no stopping condition and cannot express "we don't know", because not-knowing is
only definable against a question. Topics remain the discovery interface; the question
registry is the unit of result.

## D3 — Source class is mandatory on every item
A blog post and a refereed paper cannot share a pool without it being recorded which is
which; synthesis is ruined at the root otherwise. Classes are declared per project and
reported separately before anything is pooled.

## D4 — Local model: narrow window, many calls, short outputs
Measured on the target machine (i5-11400 / 61 GB / RTX 3050, Q8_0): **11.6 min per call**
on ~8K-token prompts, ~5 calls/hour, 1.43 tok/s generation against 121 tok/s prefill.
It reads far faster than it writes, so its regime is large input and short output.

A pre-registered probe (2026-09-14) tested Q8_0 with a 49K context and a 30,000-character
window against the production Q4/8K/9,000 configuration: **4 valid claims per source
against 12**, on both test sources, with no new question covered. The explanation is that
**harvest per call is roughly constant at ~2 claims regardless of window size** — widening
the window reduces the number of calls and therefore reduces the harvest. Consequence:
"one JSON per document" is the worst available call shape, and is not used.

**Perimeter (2026-09-22).** Everything above is the operating point of *that machine* at
that quantisation. It is not a general result about language models, and it does not govern
the pipeline — see D13. In particular, the constant-harvest-per-call finding was measured on
one local model; the optimal window for any other backend is unmeasured and must not be
inherited from here. D4 still governs whenever the local backend is the one serving a lane.

## D5 — The frontier model does selection and the decisive sources
Reading the whole corpus with a frontier model would cost on the order of tens of dollars;
the local path costs weeks and carries a measured error rate. On the existing corpus the
adversarial reader marked **54 of 292 claims OVERSTATED and 21 AMBIGUOUS — 25.7% — after
they had already passed the mechanical quote gate**. Self-reported confidence is therefore
not used for routing: mechanical gates first, adversarial reader second, and review
stratified by consequence rather than sampled at random.

**Revised by D13 (2026-09-22).** The routing conclusion stands — mechanical gates first,
adversarial reader second, review stratified by consequence. The *cost* premise does not: the
adversarial reader's input is compact by construction, which puts the whole corpus at ~$1.30
on a frontier model. "Reserved for the decisive sources" was a budget constraint that no
longer binds; the reader now runs over every claim, and D5's 25.7% figure is why.

## D6 — Statistics delegated to R across a file boundary
Meta-analysis tooling is overwhelmingly R (`metafor` is the reference implementation;
Python has only `PyMARE`). Writing random-effects pooling with publication-bias correction
from scratch is a research project, so it is not written. It is invoked as a batch step —
CSV of effect sizes in, JSON out — once per synthesis round, never per document. No
in-process R bridge.

For this domain the correction is the economics form (FAT-PET-PEESE, and MAIVE), not the
funnel-plus-p-curve stack from psychology and medicine: MAIVE exists precisely because
reported standard errors in observational research are not trustworthy.

## D7 — Dependencies must sit behind a process or file boundary
Adopted: **GROBID** (Docker, REST — PDF to TEI with references and tables is genuinely
hard and the boundary is HTTP), **SearXNG** (Docker), **metafor** (Rscript, file boundary).

**The GROBID build is part of the instrument, recorded 2026-09-25.** Every corpus figure — body
characters, sections, references, tables — was measured with `lfoppiano/grobid:0.8.1`, and the two
images on hand are not interchangeable: on the same PDF `latest-crf` produced 508 KB of TEI against
0.8.1's 91 KB, and it uses *more* memory rather than less. Switching would change every count
without touching a version number, so `tools/check_instrument_versions.py` holds the declared image
to this entry.

On this machine the container needs `-e JAVA_TOOL_OPTIONS=-XX:-UseContainerSupport`: the image's JVM
cannot read cgroup v2 under Docker 29 and dies at startup. Measured footprint, 2.4 GB idle and
3.6 GB under load, which makes GROBID — not the language model — the binding constraint on where
this runs.

Rejected, with reasons:
- **PaperQA2** — a framework that wants to own the data model, and it lacks the two things
  most needed here: it does not acquire PDFs and it does not verify quotes mechanically.
  Kept as a reference implementation for the metadata fan-out, which is ~200 lines of
  direct API calls.
- **ASReview** — active-learning screening pays off at thousands of records; the candidate
  set here is in the hundreds. Revisit above ~1000.
- **ASySD / synthesisr / statcheck** — would add an R runtime for roughly a hundred lines
  of deduplication and numeric checking.
- **prismAId** — a complete competing pipeline, not a component; adopting it means
  abandoning the quote gate and the protocol.

## D8 — Full-text acquisition is the part nobody solved
In the curated survey of the evidence-synthesis ecosystem, PDF retrieval has essentially
one entry. The OA fallback chains that exist are single scripts, and at least one routes
through Sci-Hub, which is excluded here. This is why acquisition is stage 2 and the first
milestone: it is the binding constraint on the science, not extraction quality.

### Measured, 2026-09-23

On the 25-source manifest, with the content gate at `gate_version: 2`:

```
ACA            6/10  0.60
IND            1/9   0.11
MET            5/6   0.83
total         12/25  0.48   floor 0.80 (v1)   INSUFFICIENT_ACQUISITION
failures      PAYWALL_403 7   ABSTRACT_ONLY 6
by host       ravenpack 4 · sciencedirect 2 · wiley 1 · ssrn 1 · doi.org 1 ·
              sec.gov 1 · lseg 1 · marketpsych 1 · spglobal 1
```

**0.42 → 0.48.** The round recorded 0.72 before a gate existed; re-judging the bytes it had
already stored dropped six artifacts that were vendor abstract or product pages, not documents.
No source was re-fetched to establish this — the bytes were on disk and the gate does no I/O.

**The thresholds are not deciding it.** All four swept flat: `min_text_chars`, `min_pdf_bytes`
and `paywall_doubt_chars` at spread 0.00, `fulltext_chars` at 0.04 and only downward from
15000, where a 9243-character product page would slip through. The rate is set by the structural
signal — a reference list present or absent — not by any constant chosen at a desk.

**Every rejection was checked by hand: 6 of 6 correct, no false positive.** Four RavenPack
research abstracts, one LSEG product page, one MarketPsych overview.

### The named campaign, 2026-09-24

The seven 403s were terminal, so a routine run left them alone. But the cascade had changed
since they were refused — the known wall now sorts last instead of being re-promoted by format
ranking, a DOI is resolved from the title when the URL carries only a publisher's internal id,
and a source with no DOI falls back to an archived snapshot. A changed capability is what a
named campaign is for, so `--campaign cascade-v2-walls --retry-class PAYWALL_403` re-knocked on
those seven and no others.

**Three of seven recovered. 0.48 → 0.60.**

```
ACA009   PDF_FULLTEXT   unpaywall  1062 KB   accepted version in an institutional repository
IND001   HTML_FULLTEXT  wayback     504 KB   a SEC EDGAR filing, 247,993 characters
IND007   PDF_FULLTEXT   wayback     934 KB   an S&P Global PDF
total   15/25  0.60   floor 0.80 (v1)   INSUFFICIENT_ACQUISITION
failures  ABSTRACT_ONLY 6   PAYWALL_403 4   (sciencedirect 2, wiley 1, doi.org 1)
```

Against the 0.42 the project started from: **0.42 → 0.60**, with every source's OA status,
licence and failure reason recorded, and with the six that look obtained but are not now named
as what they are. Two of the three recoveries came from the archive, which is the fallback that
did not exist before — for the classes with no open-access infrastructure it is the whole
cascade.

### The denominator was wrong, 2026-09-24

An adversarial review found, and running it confirmed, that `rate()` divided by the number of
acquisition rows rather than by the candidates found. With 25 candidates discovered and one
attempted and obtained it returned **1.00** and `admit()` returned **OK** against an 0.80 floor: a
corpus read at 4% certifying itself complete, which is the failure D11 exists to prevent, in the
module that exists to prevent it.

`sources.yaml` has always declared the floor a share of what was *found*. The code did not
implement that. Fixed in `7490f6d`, with the chain of states — found, classified, attempted,
obtained, confirmed — reported separately, because each has a different remedy.

**The figures below are unaffected.** That round attempted all 25 candidates, so its denominator
happened to be right. That was luck, not protection, and it is why the defect survived a
measurement that looked correct.

### 0.60 is an upper bound, 2026-09-24

Running GROBID over the fourteen acquired PDFs found one that is not a document: `IND008` is
`lseg-machine-readable-news-fact-sheet.pdf` — 4,618 characters of body, **zero references**, and
sections titled "Key use cases" and "Find out more". Marketing, and the PDF twin of the six HTML
abstract pages, caught by the same signal: no bibliography, short body, commercial prose.

It passed stage 2 because **the PDF gate there is structural** — magic bytes, `%%EOF`, size — and
says so: no PDF parser exists before stage 3, and a half-working heuristic would be the softening
the invariants forbid. `IND008` has 299,781 bytes against 4,618 characters of text, a ratio of
65:1 where a paper runs 15-20:1, but reaching the character count needs the parser that is
missing.

So **the honest count is 14 of 25 = 0.56**, and 0.60 is an upper bound with one known false
positive already named. This is the `fulltext_confirmed` signal the stage 2 spec promised stage 3
would write back; it paid for itself on the first document it saw. Nobody should quote 0.60 as a
confirmed figure, and the record is corrected here rather than after stage 3 lands, because a
number left optimistic is how a corpus certifies itself better than it is.

**Why the floor is out of reach here, and what that is evidence of.** Five sources separate
0.60 from 0.80. Four are publisher 403s that survived a named campaign with an improved cascade.
Six are pages for which no open full text exists to obtain — and three of those are *product pages*, which are not research in any form
and would fail this gate at any threshold. `IND 3/9` is therefore a finding about the manifest's
composition as much as about acquisition: entries were admitted as industry research that are
vendor marketing. That is the shape of argument the pre-registered rule asks for before a floor
may move (see the floor-versioning rule in the stage 2 spec) — but the argument belongs to
whoever owns the manifest, and the floor stays at 0.80 (v1) until they make it. The published
result for this round is `INSUFFICIENT_ACQUISITION`.

## D9 — Append-only JSONL is the source of truth
Hashable, diffable, and auditable with grep.

**What resumability means, added 2026-09-24** after a review pointed out the claim was
unqualified while `Store.read` would raise on a truncated last line. A crash mid-append leaves a
final line with no trailing newline; readers skip exactly that line and record it, and
`Store.repair` truncates it. Incompleteness is judged by the missing newline and never by
parseability, since a row cut at `{"k": 2}` is valid JSON and still half-written. Damage anywhere
other than the end raises: it is not a crash artefact, and skipping it would remove a row from a
denominator silently. SQLite is a derived
read model, rebuildable from the JSONL. No Postgres (single writer, megabytes of data),
no vector database (a few hundred documents: similarity is one matrix multiplication), no
graph database (a citation graph is a table of edges).

## D10 — Two independent discovery channels, by construction
Keyword search over metadata APIs, and backward citations extracted by GROBID.

The reason is **not** that two channels give a completeness estimate. It is that a
round-over-round delta cannot be trusted on its own: that delta is confounded with acquisition
failure, because a blocked downloader produces "0% new" and reads as saturation. A second channel
that does not depend on the first breaks that confound — if the citation channel keeps producing
sources the keyword channel never found, the corpus is not saturated regardless of what the delta
says.

**Revised 2026-09-24**, after a review pointed out the original wording claimed capture-recapture
made completeness *estimable*, and the stage 1 spec had already established that it does not here.
Measured: the manifest and the reference set overlap on 6 works, which yields about 2,962 and a
coverage of 0.8% — and all three assumptions fail. Exact-title matching understates the overlap by
an unknown amount, since GROBID took an NBER cover banner as a title in 15 cases. The manifest was
curated by hand and is not a sample of anything. And catchability is unequal by construction, which
the citation channel's own `min_citations_in_corpus` threshold depends on, so our filter breaks the
assumption the estimate requires.

What survives is the whole operational point: **705 of 711 references were not in the manifest**,
which says the first channel missed hundreds of sources and needs no population estimate to say it.
The number the report must not print is the percentage.

## D11 — Admissibility gates verdicts
Acquisition rate is computed every round and reported. Below the declared floor the round
is `INSUFFICIENT_ACQUISITION` and produces no verdicts. The corpus that motivated this
project stands at 0.42 with most of its sources lost to 403 and connection failures, and the
criterion it was using would have declared it saturated.

**Provenance check (2026-09-23).** The manifest this refers to is
`SOURCE_MANIFEST.tsv` in the consuming project and holds **25 sources**, not the 26 stated
in earlier drafts here and in the README. An earlier "20 sources lost" cannot be reconciled
with 25 sources at 0.42, and the original measurement is not in this repository, so the count
is left as "most" rather than restated with a number that cannot be checked. What is
checkable is recorded instead: the round in `630ca52` attempted 25 and obtained 12 full
texts (0.48) once abstract pages were recognised.

## D12 — "Never asked" is a distinct state
`SUPPORTED` / `CONTRADICTED` / `UNANSWERED_IN_LITERATURE` / `NEVER_ASKED` are four states,
not three. Two questions in the existing registry sit at zero claims and the existing
system cannot say which of the last two they are in.

## D13 — One model boundary, several interchangeable backends
Adopted 2026-09-22, replacing the assumption that the local `llama.cpp` server was the model.

The stages that need a model write **work units to JSONL and read results from JSONL**. A
backend is whatever consumes that queue: the local server, a CLI already installed on the
machine (`claude -p --output-format json`, `codex exec`, `opencode`), a subscription endpoint
with an API key (Ollama Cloud), or a metered API. Every result row records `backend`,
`model`, `harness_version` and `prompt_sha256`.

**What decided it.** The local operating point (D4) implied weeks of wall-clock for a corpus
of a few hundred documents, which forced a corpus ceiling — a limit on the science imposed by
one machine. Measured against real rates instead: extraction of the 25-source manifest is
~86 chunks, and since stage 4 asks one call per chunk per question kind, **~344 calls** (the ~130
figure in an earlier version of this entry predated the four-lane design); a 300-source corpus is
roughly 4,000. Stage 5 adds one review call per claim, about $5 for this corpus. On Ollama Cloud's hosted open models at
$0.30/$1.20 per MTok that is **$0.23 and $2.63** respectively, inside the $60 of monthly
credit a $20 plan includes; the adversarial reader of stage 5, whose input is compact by
construction, is **~$1.30 for the whole corpus** on a frontier model. The ceiling was never
a property of the problem.

**Why a file boundary rather than an SDK.** It is D7's shape, it keeps the engine free of a
vendor dependency, and it is the only arrangement under which "does backend A extract better
than backend B" is answerable **by measurement** rather than by preference: the same work
units can be served by two backends and the results compared. Lane assignment is therefore
deliberately deferred — it is a finding, not a design decision.

**Consequence.** A CLI's harness (its own system prompt, tools and context management) sits
between the prompt and the model and changes with its version, which is why
`harness_version` is recorded and why the metered API is preferred wherever a result must be
exactly reproducible. High-volume lanes go where throughput is priced per token; interactive
subscription plans are not batch infrastructure and are not used as though they were.

## D14 — A retry and a re-judgement collapse differently
Adopted 2026-09-24, discovered while correcting a round that had been measured before the content
gate existed.

Two rules about the append-only ledger both sound right and pull in opposite directions, and the
order between them is the whole content of `admissibility.collapse`.

A **retry** that fails must not erase a recorded success. Its failure is a fact about the world —
the host refused us this time — and says nothing about bytes already on disk. Plain latest-wins
would drop the rate while the corpus was unchanged.

A **re-gate** that fails must erase one. It is not a new attempt at anything; it is a corrected
reading of the very artifact the earlier row claimed, and it says that artifact was never a
document. A row carrying `regated_from` is therefore authoritative, and a genuine acquisition
afterwards supersedes it in turn.

The same reasoning gives `gate_audit._artifacts` its shape: it reads the **whole** log rather than
the latest row per candidate, because the store is content-addressed and append-only, so a pointer
to bytes never goes stale. A later row that happens not to mention an artifact — which a rejection
does, since row-level `stored_path` means "what we accepted" — must not hide bytes that are still
on disk.

## D16 — A verdict's rule follows the kind of question, and one kind gets no verdict
Adopted 2026-09-25, by reading all 28 questions of `alembic-s4` one at a time. This is D15's first
step, done.

| kind | count | judged by |
|---|---|---|
| `effect` | 5 | studies in the stated direction, from more than one dataset, with contrary evidence counted |
| `heterogeneity` | 5 | a consistent moderation **and a reported case where the effect is absent** |
| `method` | 11 | a methodological endorsement **and** a demonstrated failure mode |
| `premise` | 1 | stated explicitly by at least one source, contradicted by none |
| `operational` | 6 | **nothing. No verdict is produced** |

**Five of twenty-eight are poolable effects.** Six are assertions about the consuming system's own
architecture — versioned lanes, a frozen counterfactual policy, an exclusive first loss cause — and
no paper can confirm them. Filing those under `UNANSWERED_IN_LITERATURE` would assert that the
literature is silent on a question it was never asked, so they receive no verdict and the report
says which kind they are.

Two consequences follow, and both were already suspected by the review that prompted this.

**The multiplicity family is the effect questions, not the registry.** Five, rising to at most ten
if a heterogeneity verdict comes to rest on a pooled estimate. A correction applies to a family of
statistical hypotheses and a methodological requirement is not one, so the declared number of tests
is computed from the verdicts produced and stated beside the correction.

**A fifth verdict state exists**: `CONTESTED_IN_LITERATURE`. Under the effect rule, a question where
the bar is cleared in both directions is none of the other four, and calling it `UNANSWERED` reports
silence while the literature is speaking and disagreeing — invariant 2's error, one category over.

**And stage 4's extraction target now depends on the kind it extracts for.** A study-result record
with an estimand and a variance is a different artifact from a claim bound to a quote; for a
`method` question the target is an endorsement or a demonstrated failure instead. This is why the
contract had to come before stages 4, 5 and 6 rather than after them. Full rules, thresholds and
the argument for each in `docs/superpowers/specs/2026-09-25-verdict-contract-design.md`.

## D17 — Defining the verdict removed the statistics
Adopted 2026-09-25, on writing the stage 6 spec. D15 refused to specify the stage until a verdict
was defined. D16 defined one, and most of what this stage was going to do turned out to be
unnecessary.

**No pooling in this version.** D16's rules require counts and coverage — three studies, two
distinct datasets, contrary evidence counted, an absent case reported, an endorsement and a
demonstrated failure. Not one of them needs an aggregated estimate. A random-effects pool would
produce a magnitude, which is additional information and not the basis of any verdict the contract
defines. **D6 is therefore deferred, not implemented**: its reasoning for `metafor` over hand-written
pooling still holds for whenever a magnitude is wanted, and the contract is "a verdict per question",
not "an effect size per question".

**No multiplicity correction, and this contradicts the original registry's concern.** That control
was wanted because the design assumed significance testing. D16's rules test no significance, so
there is no p-value and no family-wise error rate to control, and a correction applied to
count-based rules adjusts nothing. It would be rigour-shaped output with no object. What is mandatory
instead is **disclosure**: how many questions were asked, of each kind, reaching each verdict, on how
many sources each rests. That is not a correction and must never be labelled one. `H24` — whether
the effect survives multiplicity correction in the literature — is unaffected: it is a `method`
question about what the field did.

So stage 6 is a deterministic aggregator with no model, no network and no R. What it gains instead is
the first place in the project where **invariant 3 has something to gate**: it refuses to produce any
verdict at all when the round is `INSUFFICIENT_ACQUISITION`, and the refusal is the entire output.

## D15 — Stage 6 is not specified until a verdict is defined
Adopted 2026-09-24, on the recommendation of an adversarial review, which asked to be allowed to
conclude that a subsystem should not exist and then did.

The plan was random-effects pooling with PET-PEESE and MAIVE, delegated to `metafor` across a file
boundary (D6). The review's objection is not about the statistics; it is that the inputs cannot
support them. An exact-substring quote verifies the **provenance of a text**. It does not establish
that the model selected the right result from the paper, extracted its estimand and uncertainty
correctly, or weighed study quality — and the project's rhetoric has been treating the quote gate
as if it did.

Worse, the registry mixes kinds. Of 28 questions in `alembic-s4`, several are methodological
requirements or operational judgements rather than empirical effects. Pooling across event studies,
textual-analysis papers and methods references would lack a common estimand, and random effects
explain variation among comparable estimates — they do not confer meaning on incomparable ones.

So, in order, before any statistics:

1. Per question, predefine the eligible designs, the outcome, the direction, the horizon, the
   population, what magnitude would matter, and what would count as a counterexample. Identify the
   questions that are not effect-estimation questions at all.
2. Extract a structured **study-result** record — estimate, scale, standard error or interval,
   sample, horizon, design, dependence — with claims as evidence annotations rather than as
   independent observations.
3. Build a structured evidence table per question: pertinent studies, findings in each direction,
   risk of bias, missing acquisition, missing precision, live disagreements. Not a count of
   significant results; the distinction is the one Cochrane draws between structured synthesis and
   vote counting.
4. Allow meta-analysis only for a pre-specified subset with compatible estimands and verified
   sampling variances, and omit a pooled estimate when observational studies are not similar
   enough.
5. Treat PET-PEESE and MAIVE as sensitivity analyses where their inputs fit. MAIVE needs enough
   estimates and a real relationship between inverse sample size and reported variance; it repairs
   neither missing nor incomparable effects.

And `SUPPORTED` needs an operational definition before any code: evidence sufficiency, coverage,
design quality, replication, and a rule for material counter-evidence. That no threshold was
written anywhere was not a deferral of something easy.

**A fifth outcome is likely needed.** The four states do not express "relevant literature exists
and conflicts", and forcing that into `UNANSWERED_IN_LITERATURE` would be the same collapse
invariant 2 forbids, one category over. Invariant 2 forbids reporting absence as absence of effect;
it does not forbid a fifth state, and an explicit abstention is the honest place for irreducible
disagreement.

## D18 — Stop specifying. The next artifact is a working vertical slice
Adopted 2026-09-25, on the recommendation of a second adversarial review, which was asked whether
the ratio of writing to working software was itself a finding and answered that it is.

The state: 17 decisions before this one, 8 specifications, 4 implementation plans, ~2,400 lines of
code, and **one stage of six actually built.** Stages 4, 5 and 6 were specified in a single day, and
every threshold, independence assumption and false-rejection rate in them was chosen by reading
documents rather than records.

Two reviews found, between them, that the effect verdict was vote counting with a threshold, that
the heterogeneity rule established nothing about moderation, that an independence count could be
passed by two spellings of one dataset, that a gate check existed only because of a field nobody
needed, and that the acquisition floor could pass a corpus read at 4%. **All five were errors of
reasoning in a document, and all five would have been caught faster by one real record than by
another specification.**

So the next artifact is not a spec. It is **one complete effect question carried end to end** —
normalize, extract, review, evidence profile — with at least one negative result and one duplicated
dataset in it, because those are the two cases the removed rules got wrong. What that produces is
what the rules get rewritten against.

Three things stay blocked until it exists: what counts as an independent study, what magnitude is
material per question, and whether the gate's whole-record rejection is affordable. None is
answerable from a document, and answering them in one anyway is what this decision exists to stop.

And in parallel, acquisition. The floor is 0.80; the corpus stands at 15 of 25 obtained, 14 once the
fact sheet is excluded, and 20 confirmed documents are needed. Recovering the four remaining walls
reaches 18 at best, so the gap is not closable by retrying publishers. A public pilot corpus that
actually clears its own preregistered floor is what would let the vertical slice be validated while
this one stays gated — and lowering the floor to make the path look usable is the one move that
remains off the table.

## D19 — The chunker is an instrument, at `chunk_version 1`
A chunk is the unit stage 4 prompts with and the unit the quote gate checks a quote against. So
the boundaries and the rendering are not formatting: change either and a claim that was
extractable stops being extractable, or a true quote starts failing the gate. Rendered once,
stored with its hash, never rendered a second time for the check.

### Measured, 2026-09-25

The same 14 TEI, chunked by `claimstone/chunk.py` at `chunk_version 1`. Every figure below is
reproduced by `.venv/bin/python tools/derive_corpus_figures.py alembic-s4`, which calls the module
rather than reading the TEI a second time:

```
chunks                352      prose 224 · table 117 · note 11
characters        928,473      largest single chunk 8,983 (budget 9,000)
merged forward/back    77
dropped as bare heads  28
over budget after split 0
```

**117 tables in, 117 tables out, and nothing else dropped.** The 28 dropped divs are exactly the
28 bare heads the TEI measurement found; the 117 table chunks are exactly its 117 tables. The
chunker discards nothing it was not asked to.

**Conservation is tested, not asserted.** Every paragraph of 40 characters or more appears in the
chunks exactly as many times as in the document. A lost paragraph is a claim that can never be
made, and a doubled one is a claim counted twice — neither is visible in a total.

**One count, two instruments, 48 phantom duplicates.** Counting exact paragraph equality in the
source against substring occurrence in the chunks reported 48 duplicates. All were artefacts: the
repeated text is JSTOR's per-page watermark, already repeated in the source, and a one-character
paragraph `'.'` was "found" 1,086 times. Counting both sides the same way gives zero. This is the
same error as calling all 95 short divs captions on length alone — the corpus is small enough to
look at, and looking is what corrected both.

**What decides a short div is what it is, not how long it is.** The 95 short divs are 28 bare
heads, 2 figure notes and 65 genuine short sections. Length alone would have thrown away 65
sections of real prose.
