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
IND001   HTML_FULLTEXT  wayback     504 KB   a 424B2 prospectus supplement, 247,993 chars
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
`lseg-machine-readable-news-fact-sheet.pdf` — around 4,600 characters of body, **1 reference**, and
sections titled "Key use cases" and "Find out more". (Both figures were sharpened when stage 3
ran for real; see "stage 3, end to end" below. 4,618 counts
section heads; `Document.body_chars`, which the confirmation rule uses, counts div prose and gives
4,377. Neither is wrong and the difference is 241 characters of headings.) Marketing, and the PDF twin of the six HTML
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

## D20 — The HTML path extracts tables, because not extracting them does not remove them
The stage 3 plan decided `html_doc` would skip tables: a filing has no bibliography, and its tables
need the work TEI tables already received. That reasoning was written before anyone opened the file.

### Measured, 2026-09-25

`IND001` is the corpus's only HTML full text, and it is not the SEC 10-K three documents called it.
It is a **Credit Suisse 424B2 prospectus supplement** filed on EDGAR, describing an index built on
RavenPack event scores. It has **no `h1`, `h2` or `h3` anywhere** — EDGAR renders headings with font
weight — so it is one unnamed section, and 140 `<table>` elements.

```
found                 140 tables      44,248 chars of cells, 18% of the document
                      1,256 prose paragraphs, median 30 chars, 549 under 20
a table (>=2 rows,     30 tables      222 rows, 14,112 chars of cells
 >=2 columns)
a layout box          110 tables      104 of them 1x3, text returned to prose
after the rule          57 chunks     prose 27 · table 30, largest 8,995
                        751 prose paragraphs, median 161 chars, 206 under 20
```

**Skipping tables does not skip them.** `td` is a block element, so every cell arrived as its own
prose paragraph: a bare `4.2` packed next to unrelated prose, which a model attributes to whichever
sentence precedes it. The median prose paragraph was 30 characters and 549 of 1,256 were under 20.
The choice was never "tables or no tables"; it was "tables, or tables silently flattened into
prose".

**Two rows and two columns.** Below that it is a publisher's spacing box, and its text returns to
the prose at the position it occupied. Keeping the boxes as tables would be 110 extra chunks on one
document — at the measured local operating point of ~5 calls an hour, 22 hours of model time for
spacing elements. The 30 that survive are real: a 54-row event-category scoring table, a 40-row
one, the S&P sector tickers, worked headline-scoring examples.

**Nothing leaves the document.** A demoted box's cells are asserted present in some chunk, and the
cell that holds a nested table keeps its own words — the first implementation dropped them, because
opening the inner table cleared the buffer mid-cell.

**Two instruments, two counts, and no reconciliation offered.** The content gate recorded 247,993
characters; this parser finds 232,084 of prose and 14,112 in cells. The gate strips tags without
regard to block boundaries and this one does not. Neither number is wrong and they are not
comparable, which is the same reason `chunk_version` and `gate_version` exist.

## D21 — Stage 3, end to end: 14 of 25, and neither confirmation constant decides it
The first run of stage 3 over the real corpus. GROBID was never called — the TEI is on disk under
each PDF's hash, so the stage needed no network and no container.

### Measured, 2026-09-25

```
normalized            15 sources        14 confirmed · 1 NOT_A_DOCUMENT · 0 awaiting
rate                  14/25 = 0.56      lower bound and ceiling both 0.56, final
floor                 0.80 (v1)         INSUFFICIENT_ACQUISITION
by class              ACA 7/10 0.70 · IND 3/9 0.33 · MET 5/6 0.83
chunks                406              prose 249 · table 146 · note 11
references            710              distinct, deduplicated across the corpus
```

**The headline figure is 0.56, and it is now `final`.** Nothing is awaiting normalization, there are
no orphan acquisitions, and the lower bound equals the ceiling — so the round is a settled
measurement rather than a partial one, and it is 24 points under its own floor. That is the
deliverable: a sentence with a number in it, and the number is not good enough.

**`IND008` is the one rejection.** 1 reference and 4,377 characters of div prose, against the
next-lowest legitimate document at 9 references and 20,844 characters. Sections titled "Key use
cases" and "Find out more".

**Both confirmation constants are flat.** Swept on the 15 documents:

```
min_references    0 -> 15 confirmed     confirm_chars    1,000 -> 15
                  1 -> 15                                4,377 -> 15
                  2 -> 14                                4,378 -> 14
                  5 -> 14  (the default)                 15,000 -> 14  (the default)
                 60 -> 14                              100,000 -> 14
                                                       240,000 -> 13
```

`min_references: 5` could be anything from 2 to 60 without changing a single verdict, and
`confirm_chars: 15000` anything from 4,378 to 100,000. Neither constant is doing the work; the gap
in the corpus is. This is the same result the gate thresholds gave, and it means the same thing:
the rule is structural, and a reviewer arguing about the numbers is arguing about the wrong thing.

**One negative is one negative.** A flat sweep over a corpus with a single non-document says the
rule is insensitive *here*, not that it is right. The next corpus with two marketing PDFs in it is
the test, and until then this is evidence about robustness and not about accuracy.

## D22 — The first real extraction records, and what they cost
D18 blocked three questions on records that did not exist: what counts as an independent study, what
magnitude is material per question, and whether the gate's whole-record rejection is affordable. Two
calls answered the third and nothing else, which is what two calls are worth.

### Measured, 2026-09-26

One hand-built `extract` batch for **H02** (kind `effect`), twelve calls queued by
`tools/handbuilt_h02_batch.py`, two drained on `claude-cli` with `claude-opus-5`.

```
answered                   2      54.3s and 110.8s
recorded valid             0      both NOT_JSON
prompt_verified         true      on both
evidence quotes        16/16      exact substrings of their chunk
after unfencing        1 of 2      the other: 9 claims against a maxItems of 8
```

**16 of 16 quotes were exact.** Every one a literal substring of the chunk it came from, checked in
code, with numbers and t-statistics inside the span. Invariant 1's gate passed on the first real
output it ever saw. That is one prompt against two passages of one paper and is not a rate, but the
failure mode it was built to catch did not occur.

**Both answers were recorded `NOT_JSON`, and both were valid.** The model wrapped the array in a
```json fence, which the prompt forbade in as many words. `model_call` now unwraps a body that is
*exactly* one fenced block — the fence is the harness's presentation habit, one envelope outside the
answer, and the schema still judges what is inside. Prose *beside* a fence stays `NOT_JSON`: a model
saying something the schema cannot see must not have that something pass unread.

**A classifier fix must not orphan answers already paid for.** Stage 2 has `regate` for exactly this;
`model_call` had nothing, so the fence fix would have left two paid answers permanently mis-recorded.
`model-run --rejudge` re-reads the stored bytes under the current rules, opens nothing, and writes a
row carrying `rejudged_from` that D14 keeps out of what the queue cost and how fast it went while
letting it stand as the verdict. Run on those two: **1 recovered, for nothing.**

**Whole-record rejection is not affordable, and the cap was mine.** The record that still fails holds
nine claims with nine exact quotes, discarded entire because I wrote `maxItems: 8` at a desk. A cap on
item count is a cost bound dressed as a shape, and the cost bound already exists and is honest about
itself — `max_output_tokens` is inside `call_id`, so raising it is a different call. The builder no
longer caps item count. What stops a model padding the array is the quote gate, which is the defence
that actually reads what was written.

That does not settle the unit of rejection for stage 4. It settles that a shape constraint nobody
measured will throw away good evidence, and that the first one did.

**What two calls did not answer.** Nothing about independence, nothing about material magnitude, and
nothing about the harvest rate: two passages of one paper, chosen by a screen that counts the word
"sentiment". The `QUALIFIES` stance was used seven times in sixteen, which is either the prompt
working or a model hedging, and two calls cannot tell those apart.

## D23 — Thirteen calls, sixty-six claims, and the one that would decide the verdict is the weakest
The second drain of the hand-built H02 batch, with the item cap removed and a negative control added.
This is the harvest D18 was waiting for, and it is one prompt against one question on one corpus.

### Measured, 2026-09-26

```
calls                    13      all valid, 0 NOT_JSON, prompt_verified true on all
claims                   66      8 productive chunks, 5 answering []
exact quotes          66/66      100%, checked in code against the chunk
quote length         median 132 chars, min 48, max 348
stances          SUPPORTS 25 · QUALIFIES 40 · CONTRADICTS 1
throughput            132 attempts/hour, unpriced (subscription)
```

**Every quote was exact, 66 for 66.** Invariant 1's gate has now passed on sixty-six real claims with
no failure. That is a corpus of one question and one prompt, and it is the failure the whole design
feared not occurring.

**The empty answer works, and it caught a mistake the screen made.** The negative control —
`MET005#c5`, "II. New Delisting Data", a methods passage with a screen score of zero — answered `[]`.
So did the three `IND001` chunks the keyword screen had ranked *in the top ten*, scoring 54 to 59.
`IND001` is the Credit Suisse prospectus: it says "news" and "sentiment" on every page and makes no
empirical claim about whether either predicts returns, and the model declined to manufacture one. The
screen is a bad selector and the prompt is a good gate, which is the opposite of the risk anyone
worries about.

**The item cap would have destroyed a third of the batch.** `maxItems: 8` — chosen at a desk — fails 4
of 13 records, and those four hold 41 of the 66 claims. Two thirds of the harvest, for a number nobody
measured. It is gone; see D22.

**The fence is intermittent, at 2 of 13.** The prompt forbids a code fence in as many words and the
model obeyed eleven times. An instruction honoured 85% of the time is not a guarantee, which is why
the tolerance belongs in the classifier and not in the prompt.

### The finding that matters: exact is necessary and not sufficient

The single `CONTRADICTS` in sixty-six claims is this:

```
claim  Roll (1988) found little discernible difference in return variation between days with and
       without financial-press news stories, implying news added little explanatory power for firm
       returns.                                                                        (190 chars)
quote  Roll (1988) finds little discernible difference.                                 (48 chars)
```

The quote is exact. It is also the shortest in the batch, it carries almost none of what the claim
asserts, and the finding is **not this paper's** — `ACA002` is citing Roll (1988), which is not in the
corpus. So the one piece of evidence that could make H02 anything other than `SUPPORTED` is the
weakest claim present and belongs to a source nobody read.

Two rules stage 4 needs, both now with an instance rather than an argument:

1. **A claim must be about what this source establishes**, not about what it reports another source
   establishing. 4 of 66 claims (6%) name another work in the claim text. Without this rule a citation
   network is double-counted and an unread paper votes — and invariant 7 says vote counting is not
   synthesis, which is exactly what that would be.
2. **A quote must carry its claim**, not merely appear in the chunk. 2 of 66 (3%) are under sixty
   characters against claims three times as long. The numeric rule already in invariant 1 does not
   reach this: neither of those claims contains a figure.

Neither rule is written here. What is settled is that quote-exactness at 100% is not the same as
evidence adequacy at 100%, and a review that read only the first number would have concluded otherwise.

**And what thirteen calls still do not answer.** `QUALIFIES` took 40 of 66, which is either the
literature hedging or the model hedging, and one prompt cannot separate those. Nothing about
independence between sources. Nothing about material magnitude. And no reason yet to believe any
backend other than this one behaves the same way — the queue exists so that is measurable, and it has
not been measured.

## D24 — A round is the unit the floor is judged on, and a candidate's identity is an instrument
Resolving the citation channel's references exposed two things about accounting that nothing had
tested, and both were found by running the real commands rather than by reading them.

### The floor is per round, 2026-09-26

Running `discover --channel citation` against `alembic-s4` took the settled figure from **14/25 = 0.56
to 14/75 = 0.19**. Both are true. Only the first means anything:

```
report --round manifest       25 found · 15 obtained · 14 confirmed · 0.56   final
report --round stage1-first    50 found ·  0 obtained ·  0 confirmed · 0.00
report (every candidate)       75 found · 15 obtained · 14 confirmed · 0.19
```

The second round is 39 references admitted by a rule that deliberately favours works the corpus
cites most, and the stage 1 spec already said why that sinks a rate for a reason that says nothing
about the cascade: a canonical textbook has no open copy. Judging one floor across both populations
compares a curated manifest with a bibliography sweep and calls the result a corpus.

So `report` takes `--round`, and `admissibility.rate` already did. **`round` is the round that first
found a candidate**, not the one that last mentioned it: a re-import under a new name would otherwise
move a candidate out of the round that found it, and latest-wins would empty the earlier round's
population without a word. `import-manifest` defaults to `manifest` for the same reason — a round
nobody named is a round nobody can isolate.

A named round matching nothing prints that it matched nothing. Without a named round, zero candidates
against existing acquisition rows is a broken ledger and still reaches the gate — the two look
identical in a count and are not the same fact.

### `candidate_key_version 2`, 2026-09-26

The citation channel now keys on the reference stage 3 gave it rather than on a derived key.
Preferring a DOI is right for a search result and wrong for a reference, because **resolution adds a
DOI**: a derived key would move the moment a candidate was resolved, and the same work would become
two candidates with nothing superseding either.

Measured when the rule changed under an existing store: **13 ghost rows** for 39 references, a `found`
count of 50, and each ghost correctly carrying `possible_duplicate_of` pointing at its twin. The
design noticed; nothing silently double-counted. But a denominator that grows by a third because an
identity rule changed is the same hazard `gate_version` and `chunk_version` exist for, so the
derivation now carries a version and `tools/check_instrument_versions.py` refuses a bump this record
does not name.

What supersedes what: any candidate count for `alembic-s4`'s citation channel taken before this is not
comparable to one taken after. The manifest round is untouched, because a manifest row's key was
derived from a DOI or title that resolution never changes.

## D25 — Invariant 1 is executable, and the gate's first audit found six of its own faults
`claimgate.py` makes invariant 1 code: a record and a chunk's text in, a verdict out, no store and no
model. Seven checks, the first failure is the verdict, and a failing record goes to the rejection ledger
whole. D23 named two checks the spec did not have; the other five are spec §3.

### Measured on 66 real claims, 2026-09-26

The H02 harvest, run through the gate. The spec says the first round must audit its rejections before
the rate is quoted, so every rejection below was read by hand.

```
first run     58 accepted  88%   8 rejected
              NUMBER_NOT_IN_QUOTE 3 · SECONDHAND 2 · COMPARATIVE 2 · QUOTE_TOO_THIN 1
by hand       2 of 8 were true rejections. Six were the gate's fault.
after         63 accepted  95%   SECONDHAND 2 · COMPARATIVE 1
```

**Six false rejections, four distinct causes, none of them visible without real claims.**

`day-0` and `reversals-3.7`. The numeral rule read the hyphen in a compound word as a minus sign, so a
claim about "the day-0 market reaction" asserted a figure of `-0` that no quote had reason to contain.
Three rejections from this. A digit hanging off a word is a name, not a figure — and on the other side,
extracting the *quote's* numerals found neither figure in `return reversals-3.7 bps versus 16.7`, which
is how the paper typesets it. The quote is now searched as a string, bounded by digits so a claim of
`1.5` does not pass on a quote of `11.5`.

`exceeds` against `exceeding`. The comparative list held exact words, and the spec had already corrected
phrase-matching to class-matching for precisely this reason without going far enough. Stems, not words.

`Tetlock (2007)`. A citation's year is a numeral, and every one of the 4 claims naming another work
would have been rejected for a year its quote had no reason to carry. A rule whose purpose is to catch a
*fabricated* figure was rejecting bibliography.

**And one fault I introduced while fixing another.** Adding `over` to the `>` class rescued "over 90% of
stocks … exceeding one" and broke "over a much longer horizon than", where `over` is a preposition. It is
out. A stem that is sometimes a preposition manufactures a comparison the claim never made.

### The thinness check earns nothing, so it ships off

D23 asked for a check that a quote carries its claim and not merely appears in the chunk. Length ratio
was the obvious instrument and the sweep says it is the wrong one:

```
min_quote_ratio     0-34  →  0 rejected
                      35  →  1 rejected, and it is a TRUE claim
                      60  →  2
                      80  →  13
quote/claim ratio   min 25%, median 104%, max 204%
```

At 35 — the value I chose at a desk — it rejects a claim whose 57-character quote carries both the figure
(15.9%) and the direction (much lower). The one case the check was written for, Roll (1988) at 25%, is
caught by `SECONDHAND_CLAIM`, which is about attribution rather than length. So the check stays,
declarable per project, and **defaults to zero**. Shipping a constant that earns nothing and costs a true
claim is the desk-chosen threshold this project keeps finding and removing.

### The two rejections that stand, and the one that is a real cost

Both `SECONDHAND_CLAIM` rejections are correct: `ACA001` reporting Tetlock and Loughran, and `ACA002`
reporting Roll (1988). Without this check an unread paper votes, which invariant 7 calls vote counting.

The remaining `COMPARATIVE_NOT_IN_QUOTE` is a **true claim rejected for a defensible reason**: the claim
says one kind of news "moves prices more than" another, and the quote states only "a substantial
difference" with medians of 1.5 and 2.2. The claim is right, and establishing it means comparing two
numbers — which §3 of the spec says this gate does not do. One in 66 is what that costs. It is recorded
rather than fixed, because fixing it means the gate reasoning about magnitudes, and a gate that reasons
is not a gate.

**What 95% is not.** It is one prompt, one question, one corpus, and a gate whose rules were corrected
*against these same claims* — so it is a floor on the false-rejection rate and no kind of estimate of
the true one. The next question's harvest is the test.

## D26 — Stage 4 closes the vertical slice, and a rejected claim is a discovery signal
`extract build` → `model-run` → `extract --harvest` → `extract-report`. Two commands around the file
boundary, which is honest rather than awkward. Only `extract.py` touches a store; `claimgate` stays pure.

**One call per kind per chunk, not one per question.** The kind's system prompt is identical across every
chunk, which is what a cached-input price applies to: four calls a chunk instead of twenty-three. The
spec calls these lanes; they are `kind` in the code, because `model_call.LANES` already means the
boundary's two queues and one name for two things is the defect this project keeps finding — three times
in `model_report` alone.

### Measured, 2026-09-26

The H02 batch harvested into the ledgers. These are the first claims this project has ever stored.

```
proposed         66
accepted         63   0.95      claims.jsonl
rejected          3             rejections.jsonl, each with its failed check and the record whole
H02              63 claims from 4 studies    QUALIFIES 38 · SUPPORTS 25 · CONTRADICTS 0
```

**Sixty-three claims from four studies, and the count that matters is four.** Ten claims from one paper
are one study; calling them ten is the vote counting invariant 7 forbids, so `extract-report` counts by
`source_id`. The gate's ratio and the corpus's coverage are printed as separate numbers and never fused:
a clean gate on a silent corpus would otherwise read like a well-covered one.

### `CONTRADICTS 0`, and why that is the finding

Before the gate, H02 had exactly one contradicting claim in 66. The gate rejected it, correctly — it was
`ACA002` reporting Roll (1988), a source nobody here has read. So the accepted set contains **no
contradicting evidence at all**, and a verdict machinery fed it would see four studies that support or
qualify and nothing against.

Then: is Roll (1988) reachable? It is in the bibliography as **`R-squared`**, cited **once**, which is the
title of his 1988 *Journal of Finance* paper as GROBID recovered it. Nine folded characters. So it fails
two of the citation channel's three conditions — `min_citations_in_corpus: 2` and
`require_title_chars: 25` — and would fail `TITLE_TOO_SHORT` in resolution too. Every rule behaved as
declared, and the effect is that H02's only contradiction is invisible and nothing points at it.

**A rejected `SECONDHAND_CLAIM` is therefore a discovery signal, not only a rejection.** It names a work
the corpus is relying on for a claim, and the rejection ledger already holds the claim text with the
citation inside it. Feeding those names to the citation channel *regardless of citation count* is the
remedy, because a work cited once for a contradiction is worth more to this project than a textbook cited
three times. Not built; recorded with its instance, which is the standard D18 set.

**And one honest third state, the second in this codebase.** `WRONG_KIND` catches a model answering about
a question outside the kind it was asked about, and a request built before that field existed cannot
support the check. So the question's own kind is used and the claim carries `kind_verified: false` — not a
pass, not a failure — exactly as `prompt_verified` does for the echo check. Rejecting a whole batch that
predates a field, and was already paid for, would be the alternative.

**What 0.95 is not.** One question, one prompt, one corpus, and a gate whose rules were corrected against
these same claims (D25). It is a floor on the false-rejection rate. `numbers.py` is not built, so no
as-written value has been converted and nothing yet feeds stage 6.

## D27 — The citation channel obtains almost nothing, and that was predicted
The bibliography channel run end to end for the first time: 710 references, 39 admitted, 34 with a class
and an address, acquired. Three defects surfaced on the way and all three killed a whole sweep or a whole
budget; each is fixed and each is recorded here because the fix changes what a figure means.

### Measured, 2026-09-27

```
round stage1-first     51 found · 34 classified · 51 attempted · 2 obtained · 0.04
failures               PAYWALL_403 25 · UNCLASSIFIED 17 · ABSTRACT_ONLY 6
obtained               an NYU working paper and an LSE eprint, both PDF_FULLTEXT
```

**Two of thirty-four, and the stage 1 spec said so before the run.** The citation channel admits works the
corpus cites most, and a canonical paper's open copy is the exception: 25 of 34 are publisher paywalls and
6 are abstract pages. This sinks an acquisition rate for a reason that says nothing about the cascade,
which is why the floor is judged per round (D24) and why the manifest round's 0.56 is untouched.

The 17 `UNCLASSIFIED` are the ghosts of the key-rule change (D24) plus the four references OpenAlex could
not resolve. They carry no class, `acquire` refuses them, and that refusal is invariant 6 working.

### Three sweeps that died, and one budget spent on the wrong host

**One unclassified candidate ended the acquisition sweep.** `acquire_one` raises `MissingSourceClass`,
correctly — a caller handing it an unclassified candidate has made a mistake — and the raise reached the
top, so the run died on the first of the 17 having acquired none of the other 34. The same defect shape as
an unreadable artifact ending a normalize sweep, one module over. The sweep now records an `UNCLASSIFIED`
row, which is terminal because a host budget has nothing to do with it, and moves on.

**The failure budget was charged to a redirector, and it cost 17 candidates.** Every citation candidate's
only address is a `doi.org` URL and the fetcher follows redirects, so a doi.org request landing on Wiley
and taking a 403 charged the failure to **doi.org** — one budget shared by every publisher the resolver
points at, spending itself on 403s from journals the next candidate had nothing to do with. First run: 18
of 34 came back `DOMAIN_BUDGET_EXHAUSTED`, 17 on doi.org.

Charged now to the host of the response's final URL. A timeout reaches no final URL, so the requested host
keeps that charge. Re-run under a named campaign — the mechanism for re-requesting, and the reason was a
fixed defect rather than impatience — those 18 became **13 real paywalls and 3 abstract pages**. Every
candidate reached its publisher and got an answer. The number did not improve and the *meaning* did: 0.04
is now what the publishers said, not what our own bookkeeping said.

**And a rule change could not be re-applied.** 35 references resolved to a venue while `alembic-s4`
declared no `assign_when` at all, so every one was written with a null class; adding the rules changed
nothing, because a resolved candidate is skipped rather than re-requested. `discover --reclassify` exists
for that, and **its first run was destructive**: it re-judged the manifest candidates too, overwriting 9
`IND` and 4 `MET` rows with null and demoting 6 `ACA` to `WP`, because a manifest row has no venue type and
the host rule matched some URLs. A manifest states its class. An inferred class must not replace a given
one, and the guard, the test and the repair are in the history.

That is the third re-judge path this project has needed — `regate`, `model-run --rejudge`,
`discover --reclassify` — and a fourth in `extract --harvest`. The pattern is not a coincidence: every
judgement the engine makes over rules a project declares needs a way back that costs no request, or
editing a line of YAML costs a round of fetching.

### The corpus grew, and the figures above are the fourteen-document measurement

Normalizing the two obtained references takes `alembic-s4` to **16 confirmed documents**. Re-derived with
`tools/derive_corpus_figures.py alembic-s4`:

```
                 14 documents        16 documents
body characters     775,266             905,189
sections                318                 363
tables                  117                 144
footnotes               103                 124
raw references          817                 909
distinct                711                 789
chunks                  352                 472
```

Every figure in D19, D21 and D25 is the fourteen-document measurement and stays that, which is the whole
reason they carry dates and a command. The corpus-totals test **skipped** rather than failed —
`if len(CORPUS) != 14: pytest.skip(...)` — which is the guard doing its job: a number measured on one
corpus is not a number about another, and an assertion that quietly re-fit itself would have hidden that.

A full extraction over the 16 documents is **1,888 calls**: 472 chunks × 4 kinds, 2.4M tokens in and 4.7M
capped out. On `claude-cli` at the observed 30 seconds a call that is about sixteen hours; on the local
server at D4's measured 11.6 minutes a call it is fifteen days. The arithmetic is why `model_call` exists
and why D13 refuses to assign a lane to a backend in advance.

## D28 — The gate holds on a kind it was never tuned against
D25 said 0.95 was a floor on the false-rejection rate and not an estimate, because the gate's rules had
been corrected against the very claims they were measured on. This is the test that was missing.

### Measured, 2026-09-27

Thirteen chunks of one document through the `heterogeneity` lane — five questions the gate had never seen,
a stance vocabulary it had never exercised, and no rule changed afterwards.

```
hetero-probe    50 proposed · 49 accepted · 0.98 · 1 rejected
                all five heterogeneity questions produced claims: H06 H20 H21 H22 H27
both batches   116 proposed · 112 accepted · 0.97 · 4 rejected
               SECONDHAND_CLAIM 2 · COMPARATIVE_NOT_IN_QUOTE 2
coverage         6 of 22 questions that can receive a verdict, 0.27
```

**0.98 on unseen claims, against 0.95 on the tuned ones.** The false-rejection rate is not an artefact of
having fitted the rules to one question's harvest. That is what the number was uncertain about and it is
now measured — on one document and one kind, which is a second data point and not a population.

**Both `COMPARATIVE_NOT_IN_QUOTE` rejections are the same case, and one of them explains where it lives.**
A claim says one thing is *larger* than another and the quote is a table row: `| 0 | 3.37% | 41.08 | 4.22%
| 24.46 |`. The comparison is true and established by comparing two figures the quote contains, which §3 of
the stage 4 spec says this gate does not do. 5 of 112 accepted claims came from table chunks, so this is
where that rejection will keep happening, and it is the cost of a gate that does not reason about
magnitudes. Recorded rather than fixed, for the reason D25 gave: a gate that reasons is not a gate.

**One claim I doubted and was wrong about.** The surviving `CONTRADICTS` for H22 rests on a quote I first
read as describing a procedure rather than a result. Read whole, it carries the result — "The results show
that size and momentum not subsume the return predictability of news", typo and all, from the paper. The
claim is supported. Reading a truncated quote is how a reviewer invents a defect, and it is the same
mistake as counting a one-character paragraph's occurrences.

**What the coverage says.** 6 of 22 verdict-bearing questions have a claim, from 26 chunks of 472 — so
`no claim yet` on sixteen questions means nothing yet about the literature. That distinction is the whole
of invariant 2: `UNANSWERED_IN_LITERATURE` requires a complete round, and this is not one.

## D29 — The production host is a container set, and two compose idioms are refused
Claimstone moves to a node that is not the development machine. The correct shape for that is
`docker compose`, and it is not a concession: D7 says a dependency must sit behind a process or file
boundary, and a container is the strongest such boundary available. GROBID was already one.

**What runs.** `grobid`, long-running and stateless, and `claimstone`, which is a **batch job** — it runs,
appends to a ledger, exits. The job sits behind a `profiles: [cli]` so `compose up` does not start it, and
carries no restart policy: giving a job one is how a finished run becomes an infinite one.

**The image is pinned by digest, and that is correctness rather than hygiene.**

```
lfoppiano/grobid:0.8.1@sha256:820a623a0234cda235d5eb83e924934162c5f0554a843cf665c339da8b51f900
```

Measured: `latest-crf` produced **508 KB** of TEI against 0.8.1's **91 KB** on the same PDF. Every corpus
figure in D19, D21 and D27 — 905,189 body characters, 472 chunks, 789 references — was measured with this
build. A tag can be re-pushed under the same name; a digest cannot. `tests/test_compose.py` holds the
compose file, `grobid.IMAGE` and this record together, the same way `cli.BACKENDS` is held against
`runners.available()`.

### Two compose idioms refused, with the reason

**No named volume for the store.** A named volume is the portable choice and the wrong one here. The entire
argument for append-only JSONL is that it is hashable, diffable and **auditable with `grep`**; a volume
makes that require entering a container. `./store` and `./projects` are bind mounts, and the job runs as
the host's UID so a ledger does not come back root-owned.

**No service per stage, and no broker.** The six stages communicate through append-only files (D7, D9). An
HTTP boundary where a file boundary is the recorded decision would invent a distributed system for a
single-writer workload of a few dozen megabytes — the same argument CLAUDE.md uses to refuse Postgres and a
vector database. And the work queue is already `calls/<lane>/<batch>/requests.jsonl`, resumable by
`call_id`: a broker would hold a second copy and be the authority on neither.

### And R is not in it

An earlier answer of mine said R needed installing on the production node. That was wrong. **D17 removed
the statistics**: stage 6 is a deterministic aggregator with no model, no network and no R, and D6 is
deferred rather than implemented. There is nothing to containerise.

### The production node, measured

Both nodes of `llm-cluster-admin` are i7-1355U laptops with 12 threads and 14 GB of RAM, running 24/7.
**node2** (`192.168.178.164`) is the host: node1 is the cluster coordinator and its `llama-server` holds a
16.8 GB dense model, leaving no room beside GROBID's measured 3.6 GB, while node2's RPC service has been
stopped and disabled since 24/08 because the llama.cpp RPC backend is serial by construction. The memory
limit in compose is 6 GB for that reason — on this pipeline GROBID, not a model, is the ceiling.

The workload suits a laptop: the 1,888 extraction calls are HTTP against a cloud endpoint, and acquisition
is deliberately slow — per-domain budgets, throttling, explicit timeouts. The store is 28 MB for 16
documents against 278 GB of ext4.

### What the container found that the host had hidden

**The suite did not pass on the minimum supported Python.** `pyproject.toml` says `>=3.11` and the image
pins 3.13, where two test files failed to import: `NameError: name 'Any' is not defined`. `tests/test_
searchers.py` held a dead copy of `_row`'s implementation — a plan snippet appended by mistake — and Python
3.14 on the development machine evaluates annotations lazily, so it never looked. 39 lines of dead code,
invisible for as long as one interpreter was the only one that ran it.

**A project instance was not self-contained, and said `OK` about it.** `projects/alembic-s4/manifest.tsv` is
a symlink into another repository. A bind mount carries the link and not its target, so inside the container
it dangled — and `Path.exists()` follows a link, so a broken one is indistinguishable from no link at all.
`validate` printed `OK ... 6 source classes` with the manifest's 25 rows simply absent. **A project that
declares no manifest and a project whose manifest points nowhere are different facts**, and the second
silently removes 25 sources from a round's denominator. `load_manifest` now refuses it with the path, the
target and what to do.

Neither defect was reachable on the development machine. That is the argument for the container set that no
paradigm supplies: a second interpreter and a second filesystem view are two instruments, and this project's
whole method is that a figure measured by one instrument is not a figure measured by another.

## D30 — Two backends read the same corpus and find mostly different evidence
The first use of the thing `model_call` was built for: the same thirteen work units drained on two backends
and compared per `call_id`. D13 called backend choice a measurement. It turns out to be a **coverage**
variable and not only a quality one, which is a larger claim than D13 made.

### Measured, 2026-09-27

Thirteen `heterogeneity` units, `claude-opus-5` through `claude-cli` against `deepseek-v4.1-flash` on Ollama
Cloud. Same prompts, same schema, same chunks.

```
                  claims   pass the gate   []   rejected by            attempts/hour
claude-cli            50        49  98%     5   COMPARATIVE 1                    125
ollama-cloud          40        38  95%     4   QUOTE_NOT_FOUND 2                530
```

**Both cover all five questions.** H06, H20, H21, H22, H27 — neither backend misses one.

**And two thirds of each one's evidence is invisible to the other.** Counting a quote as shared when either
span contains the other, 16 of claude's 49 accepted claims overlap something ollama found (33%) and 17 of
ollama's 38 overlap something claude found (45%). Per question the depth differs sharply: 18 claims against
10 for H21, 4 against 9 for H27.

So the interesting question is not which backend is better. It is **whether one is enough**, and the answer
looks like no. That bears directly on invariant 2: if the evidence a round finds depends on which model read
the corpus, then `UNANSWERED_IN_LITERATURE` is in part a statement about the reader, and a round that used
one backend cannot claim otherwise. Nothing here settles what to do about it — two backends double the cost
and the union is not obviously the right pool — but the figure has to be in the record before a verdict
rests on a single reading.

**Where the cheap model is measurably worse, it is worse at the thing that matters.** Its two rejections are
`QUOTE_NOT_FOUND`: plausible sentences that are not in the passage. `claude-opus-5` produced none in 116
claims. That is 5% of ollama's output paraphrasing, caught by the gate every time — which is invariant 1
earning its place rather than a reason to reject the backend.

### Reasoning is budget taken from the answer

The first drain returned **4 of 13 valid and 9 `TRUNCATED`**, and the truncated rows show 2,500 output tokens
against **zero characters of body**: `deepseek-v4.1-flash` reasons, Ollama returns the reasoning separately,
and the whole cap went to it before the JSON array began. With `--no-think`, **9 of 9**.

Two things this vindicated. Judging `TRUNCATED` before `EMPTY` — `EMPTY` is transient, so reading an
exhausted budget as empty would retry it on every drain and pay 2,500 output tokens each time. And
`harness_version` existing at all: it records what sat between the prompt and the model, and a reasoning pass
that consumes the output budget is exactly that, so two results differing only in it are not comparable.

`model-run --retry-class TRUNCATED` was needed and missing. Acquire has had the named-campaign rule since
stage 2 — a class a retry cannot change is left alone on a routine run, and re-opening it is deliberate and
for a stated reason. The boundary now has it for the same reason.

### The schema was already in the request

Ollama's `format` takes a JSON schema and **enforces** it, and the work unit has carried `response_schema`
since the boundary was built — travelling to a backend able to honour it while being asked for in prose
instead. Measured: `claude-opus-5` wrapped 2 of 13 answers in a ```json fence the prompt forbids in as many
words, so `NOT_JSON` is a failure class that stops being reachable when the shape is imposed. Off by default,
because a backend that does not accept `format` would refuse the request and this runner does not guess which
does.

**And it cannot touch the failure that is actually occurring.** A third probe — 13 `method` units on
`deepseek-v4.1-flash` with reasoning off and the schema enforced — returned 13 of 13 valid answers at 0.7
seconds a call, 42 claims, and **3 more `QUOTE_NOT_FOUND`**. The schema constrains shape; fidelity is not a
shape. Across both probes the cheap model stands at **38 accepted of 42 (0.90)** against `claude-opus-5`'s
**112 of 116 (0.97)**, and every one of its four rejections is a paraphrase or a figure the quote does not
carry, where all four of claude's are attribution or a comparison implied by numbers.

Coverage is now **16 of 22** verdict-bearing questions, from 39 chunks of 472 and one document for two of the
three kinds. Nine of the eleven `method` questions produced claims from thirteen chunks, which says more about
how much a single paper addresses than about the corpus.

## D31 — Six readers on thirteen units, and my own prediction was wrong
The bake-off D30 asked for. Same thirteen `heterogeneity` work units, same prompts, same schema, six
readers, scored by the gate rather than by a benchmark. `--no-think --enforce-schema` throughout.

### Measured, 2026-09-28

```
reader                          answered  ok  claims  pass  rate   []  s/call  out tokens
claude-cli/claude-opus-5              13  13      50    49  0.98    5    18.5           —
ollama-cloud/deepseek-v4.1-flash      13  13      40    38  0.95    4     1.7       9,029
ollama-cloud/mistral-large-3:675b     13  13      35    16  0.46    2     4.8       5,274
ollama-cloud/gpt-oss:120b             13  10      11     8  0.73    5     4.1      19,322
ollama-cloud/gpt-oss:20b              13   6       2     1  0.50    4    23.9      23,734
ollama-cloud/glm-5.3-flash            13   0       0     0     —    0    10.3      29,158
```

**The decision: `deepseek-v4.1-flash`, reasoning off, schema enforced.** It is the only hosted model within
reach of `claude-opus-5`'s fidelity — 38 accepted claims against 49 — at 1.7 seconds a call and the smallest
output of any of them. `gpt-oss:120b` produces a quarter of the claims at twice the latency; `gpt-oss:20b`
and `glm-5.3-flash` spend the budget before answering.

**My prediction was wrong, and the way it was wrong is the finding.** I expected `mistral-large-3` to do well
because it is the one model the catalogue does not mark as *thinking*, and a lane whose operating point is
short structured output should favour a non-reasoning model. It answered 13 of 13, produced 35 claims, and
**17 of them quote sentences that are not in the passage** — 0.46 through the gate. Not reasoning made it
fast and fluent and not faithful. Fluency is not fidelity, and no capability tag on a catalogue page
distinguishes them; the gate does.

**A cap fitted to one model is not a fair test of another.** `max_output_tokens: 2500` was set against
`claude-opus-5` and `deepseek`. Three readers truncated at it — `glm-5.3-flash` eleven times out of thirteen
— so this table ranks these models **at this cap** and not in general. Raising it is honestly a different
call, which is why the cap is inside `call_id`, and chasing it was not worth the spend when one reader
already clears the bar.

**And a catalogue name is not an endpoint name.** `mistral-large-3` returned `404 model not found` thirteen
times; `/api/tags` calls it `mistral-large-3:675b`. The display name on the search page is not the tag, and
13 calls were spent learning that.

### One reader finds about half the evidence

Counting a quote as shared when either span contains the other:

```
                claude-opus-5  deepseek  gpt-oss:120b  gpt-oss:20b  mistral
claude-opus-5              49       33%            6%           0%      14%
deepseek                  45%        38           11%           0%      13%
gpt-oss:120b              38%       38%             8           0%      25%
mistral-large-3           44%       31%           12%           0%       16
union: 93 distinct pieces of evidence; the best single reader finds 49
```

Six readers on the same thirteen chunks found **93 distinct pieces of evidence and the best one found 49**.
Between the two strongest, the overlap is 33% and 45%, so their union is about 61 — a quarter more than
either alone. D30 asked whether one reader is enough and the answer is no, in the sense that matters:
`UNANSWERED_IN_LITERATURE` after one reading is partly a statement about the reader.

**What follows, and what does not.** The full extraction runs on one reader — `deepseek-v4.1-flash`, 1,888
calls, about fifty minutes and two dollars — because the manifest round stands at 0.56 against a floor of
0.80 and **will produce no verdicts regardless** (invariant 3). Spending sixteen hours of the expensive
reader before the corpus clears its own floor would be spending the scarce resource first. The round's
coverage is therefore one reader's coverage, and it is recorded as such: a second reading is a known,
priced addition of roughly a quarter more evidence, not a discovery waiting to be made.

## D32 — The pilot's acquisition measured the wrong twenty-eight
Recorded because the run happened and the figure does not mean what it looks like.

### Measured, 2026-09-28

`acquire` on `pilot-screen-time` reported **28 attempted, 10 obtained**. That is not the pilot's acquisition
rate, and `report --manifest` is what showed why: of the 28 manifest sources, **1 was attempted**.

`acquire` has no selector. `report` takes `--round` and now `--manifest`; `acquire` takes neither, so
`--limit 28` attempted the first twenty-eight unattempted candidates of the **199** the discovery sweep
found, and only one of them happened to be on the curated list. The 10 obtained are a sample of the sweep.

**So `acquire` needs the same selector as `report`,** and until it has one a curated corpus cannot be
acquired as a corpus. That is the next step and it is small; what is recorded here is that a figure was
produced, looked plausible, and was about a different population — which is exactly the failure `report
--round` was added for two days ago, one command over.

**And a second finding that does stand.** Of the 21 sources attempted before the run finished, 5 returned
`PAYWALL_403` and 4 gave abstract-only pages — and every one of them was selected *because OpenAlex reports
it open access*. `is_oa` is a claim about a version existing somewhere, not about this URL serving it. A
selection rule built on that flag is weaker than it looks, which matters for the pilot's whole premise that
curating for open access can clear an 0.80 floor.

**A reporting bug of mine, fixed.** `manifest_only` filters the candidate population, and the orphan check
compared acquisition rows against the *filtered* set — so 27 perfectly ordinary rows were reported as
"acquisition rows with no candidate — the ledger is inconsistent". An acquisition outside a filtered
population belongs to a candidate the filter excluded. The check now runs only over the whole store.

## D33 — The first complete round, and the gate rule that was wrong at scale
1,888 calls over 472 chunks and 16 documents, four kinds each, on `deepseek-v4.1-flash` with reasoning off
and the schema enforced. About fifty minutes.

### Measured, 2026-09-28

```
calls            1,888      1,869 valid (0.99)   2,484 attempts/hour
                            NOT_JSON 10 · SCHEMA_INVALID 8 · TRUNCATED 1
claims           4,400 proposed · 3,859 accepted · 0.88 · 541 rejected
ledger           3,971 claims   SUPPORTS 3,031 · QUALIFIES 547 · CONTRADICTS 393
by kind          heterogeneity 1,332 · method 1,039 · effect 914 · premise 686
coverage         22 of 22 verdict-bearing questions   1.00
rejected         NUMBER_NOT_IN_QUOTE 393 · QUOTE_NOT_FOUND 80 · COMPARATIVE 44 · SECONDHAND 24
```

**Coverage is 1.00, which makes a state sayable that was not.** Every verdict-bearing question now has claims
from twelve to sixteen sources, so `UNANSWERED_IN_LITERATURE` can be distinguished from "we did not look" —
which is the whole of invariant 2 and had been unavailable in every previous round.

**393 CONTRADICTS.** D26 recorded that H02 read as uncontested because the gate correctly removed its one
secondhand contradiction. On the full round contrary evidence is everywhere: 163 against H01, 20 against H26,
21 against H28. A verdict machinery now has something to be contested about.

### A gate rule that looked fine on 116 claims and was wrong on 4,358

The first harvest rejected 614 and **470 of them were `NUMBER_NOT_IN_QUOTE` — 76% of all rejections**, where
116 earlier claims had produced one. Reading them, as the spec requires before a rate is quoted, found two
families and the worse one is embarrassing:

**`1964-1997` was read as 1964 and minus 1997.** The claim said "Across NYSE stocks during 1964-1997" and the
quote said *the same words*. The sign was taken off a range separator, and the presence test then refused to
find `-1997` in a quote where the hyphen follows a digit — so the rule rejected the very text it had read. A
sign preceded by a digit is not a sign.

**`3-factor` was read as the figure 3.** The `day-0` fix caught a digit hanging off a word and missed one in
front of it. `3-factor` names a model the way `day-0` names a day.

Corrected and re-harvested, which cost nothing because the answers are on disk: **77 rejections became
claims**, 470 down to 393. Two of the recovered 79 failed a different check instead.

Not every flagged figure was a false positive, and the entry says which: a claim citing `days [-15,-6]`
against a quote that is a table of alphas asserts a window the quote does not carry, and that stays refused.
The remaining 393 have not been read one by one and the 0.88 is therefore a floor.

### Two defects the scale exposed

**A re-harvest put 77 claims in both ledgers.** The rejection rows stay — append-only, and they record what
the old rule did — but a claim in `claims.jsonl` is accepted *now*, and counting both rows inflated
`proposed` and understated the gate rate. `extract-report` prefers the claims ledger and reports
`superseded_rejections` separately, because that count is what a gate rule change was worth.

**And the report was quadratic.** It re-read all 1,888 request rows once per claim, so a ledger it should read
in a second took minutes. Computed once now.

### Nothing feeds stage 6 yet, and `numbers.py` being built does not change that

**Zero of the 3,971 claims carry a converted value.** `numbers.py` exists and harvest calls it, but the
schema stage 4 builds asks only for `result_id`, `question_id`, `claim`, `evidence_quote` and `stance` — not
the `*_as_written` fields the stage 4 spec's four call shapes specify. So there is nothing to convert, and
saying "numbers.py is built" would imply values exist. They do not. That is the next step and it means a new
batch: the schema is inside `call_id`, so asking for more fields is honestly a different call.

## D34 — The pilot obtained 0.32, and it is the cascade rather than the literature
The pilot corpus was curated **for** open access: every one of its 28 sources carries a DOI that OpenAlex
reports open. Acquired as a corpus — with the selector `acquire` had been missing — it obtained **9 of 28 =
0.32**, against the same 0.80 floor, and worse than `alembic-s4`'s 0.56.

That looks like evidence the floor is structurally unreachable, which is the one ground its own rationale
names for lowering it. **It is not, and reading the attempt records is what showed it.**

### Measured, 2026-09-28

```
attempted            27 of 28 · obtained 9 · 0.32       ACA 5/14 · WP 4/14
failures             PAYWALL_403 10 · ABSTRACT_ONLY 9
of the 18 failures   9 tried exactly one location
                     3 declined an open copy because robots.txt disallows it
by host and cause    doi.org ABSTRACT_ONLY 13 · doi.org PAYWALL_403 9
                     link.springer.com UNEXPECTED_CONTENT_TYPE 4
                     www.ncbi.nlm.nih.gov ROBOTS_DISALLOWED 3
```

One record tells the story. `ACA008`, reported `green` open access, tried three locations: Springer's
`content/pdf/…` returned `UNEXPECTED_CONTENT_TYPE`, **PubMed Central was declined for `robots.txt`**, and
`doi.org` served an abstract page. The open copy existed, the cascade found it, and we did not take it —
correctly, because honouring `robots.txt` is not negotiable.

**So 0.32 is a statement about this cascade.** Three fixable gaps, none of which is the literature being
closed:

**PubMed Central is not crawlable and has a sanctioned route.** `ROBOTS_DISALLOWED` on
`ncbi.nlm.nih.gov/pmc/articles/…` is correct conduct and a dead end; PMC publishes an OA Web Service and an
FTP service precisely so nobody crawls it. A biomedical corpus without that route loses its best source of
full text, which for this field is most of it.

**Springer's PDF endpoint is not returning a PDF to us.** Four `UNEXPECTED_CONTENT_TYPE` on
`link.springer.com/content/pdf/…`, a URL that usually serves one. Worth one look at the bytes before
concluding anything: it may be an interstitial, and it may be the gate's `expect` being too narrow.

**Half the failures tried one location.** Nine of eighteen had a single attempt, so Unpaywall offered one
address or none. Whether that is Unpaywall's coverage or how `resolve.plan` reads it is not yet measured.

### What this means for the floor, stated carefully

**Nothing here justifies moving it.** The floor is lowered only on evidence that a class of sources is
structurally unobtainable, and what has been established is that three routes are missing from the
downloader. That is the opposite finding: the number is low because of work not done, and lowering the bar to
meet it would be exactly the move the invariant forbids.

And the earlier reading in D32 — that `is_oa` is a weak predictor of obtainability — survives but shifts. It
is not that the flag is wrong; the open copy really was open. It is that **`is_oa` predicts a copy exists and
says nothing about whether the route to it is one we may take**.

## D35 — Two cascade fixes, and the two corpora fail for different reasons
D34 named three gaps in the downloader and refused the conclusion that the floor is unreachable until they
were closed. Two are now closed and the third turned out not to be a gap.

### Measured, 2026-09-28

**PubMed Central had a sanctioned route we were not using.** `www.ncbi.nlm.nih.gov/robots.txt` disallows
`/pmc/articles/` for `*`, so every open copy Unpaywall offered there was correctly refused.
`pmc.ncbi.nlm.nih.gov` is a **different host** whose robots says `Allow: /articles/` in as many words, and it
serves the article as 211 KB of HTML — which the content gate judges and `html_doc` normalises, the same path
`IND001` took. `resolve.pmc_route` rewrites the address and drops the forbidden one rather than demoting it,
because asking a host that says no spends a request on a certain refusal. Honouring robots.txt is not
negotiable; reading which host it belongs to is our job.

Worth **one** source of 28, not the several I implied in D34: only one of the retried set had a PMC copy at
all. The field I chose has less PMC presence than I assumed.

**One useless location was suppressing a second source.** Nine of eighteen failures had tried exactly one
address, and for every one of them Unpaywall's single offered location was `doi.org` — the resolver, not a
file. Five were `green`, so a repository copy existed. `openalex_locations` was reachable only `if not upw`,
so one useless answer hid the source that might have had a real address. Both APIs are now consulted, the
results deduped by normalised URL, and a location that is only the DOI resolver is dropped: it adds nothing
over the candidate URL, which is already the DOI, and counting it as an attempt is how nine failures looked as
though something had been tried.

**Springer was not a gap.** Its `content/pdf/…` endpoint returned HTTP 200 with **3,038 bytes of
`text/html`** — an interstitial, not an article. `UNEXPECTED_CONTENT_TYPE` was the correct verdict. A wall, not
a defect.

```
pilot-screen-time    0.32 → 0.36 (PMC) → 0.46 (both)    ACA 0.43 → 0.64 · WP stuck at 0.29
alembic-s4           0.56 → 0.56                        0 of 10 retried walls gained anything
```

### The finding: one floor over a mixed manifest measures the mixture

The same two fixes moved the pilot by fourteen points and `alembic-s4` by nothing, and the reason is in the
failure hosts. The pilot's misses were repository copies we could not reach. `alembic-s4`'s ten are four
RavenPack research pages, ScienceDirect, Wiley, LSEG and MarketPsych — **commercial vendor research with no
open copy in existence**. There is no second address to find, and no cascade will find one.

Per class, on `alembic-s4`: **MET 0.83, ACA 0.70, IND 0.33**. Obtainability is a property of the genre, and a
single floor across a manifest that mixes refereed papers with vendor product research is measuring the
proportions of the manifest as much as the diligence of the downloader.

**This still does not justify moving the floor**, and the reason is worth stating precisely. The floor is
lowered only on evidence that a class of sources is structurally unobtainable — and that evidence now exists
for `IND`. What does *not* follow is lowering the number: a project whose corpus is one third vendor research
should either declare a **per-class** floor, or accept that its rounds are `INSUFFICIENT_ACQUISITION` and read
the per-class rates instead. Both are honest. Dropping 0.80 to 0.56 so the round passes is neither, and it is
the move the invariant names.

## D36 — A per-class floor, and why declaring one now cannot certify this round
D35 left two honest options and one dishonest one. This takes the first, in the form that cannot be used as
the third.

**A source class may declare its own `acquisition_floor`, and it is an additional constraint.** The project
floor still judges the whole. So a declared class floor can make admission harder or leave it unchanged, and
**can never let a round pass that the project floor refused** — there is a test for exactly that, where every
class clears a generous bar of its own and the round stays `INSUFFICIENT_ACQUISITION`.

A class floor requires a `floor_rationale`, refused without one, on the same terms as the project floor: a bar
without a reason is a bar somebody moved.

`report` now judges each class against its own bar and names the ones below it. On `alembic-s4`:

```
ACA   7/10  0.70   floor 0.80  <- below its floor
IND   3/9   0.33   floor 0.80  <- below its floor
MET   5/6   0.83   floor 0.80
```

Which is more useful than one number, because the remedies differ: `MET` clears it, `ACA`'s three misses are
publisher walls worth a campaign, and `IND`'s six are vendor pages with no open copy in existence.

### The part that matters: this cannot certify `alembic-s4`

The floor's own rationale allows lowering it on evidence that a class of sources is structurally unobtainable,
and D35 established that evidence for `IND`. So declaring `IND: 0.33` is *permitted* by the letter of the
rule. It would also be **fitting a bar to a rate already seen**, and that is the thing the invariant exists to
prevent — the distance between "this genre cannot be obtained" and "this number is inconvenient" is entirely
in whether the declaration came before the measurement.

So: the mechanism exists and `alembic-s4` does not use it. A round declared per-class **in advance** is clean
and this one is not, and no amount of correct reasoning after the fact converts one into the other. What a
future round may legitimately do is declare, before acquiring, that `IND` is admitted as a pointer to primary
sources rather than as readable evidence — ~~which is what that class's own note in `sources.yaml` already says
it is.~~

**Corrected 2026-09-27.** That last clause was false, and it is the dangerous kind of false: it asserts a
pre-authorisation that would make a later declaration look principled rather than fitted. `IND`'s note reads
in full *"vendor and sell-side research; disclose the commercial interest"*. It says nothing about the class
being a pointer instead of readable evidence. So a round declaring that has to argue it on its own grounds,
and the argument cannot cite this entry as having already made it.

And `ACA` at 0.70 is below 0.80 regardless, so even the fitted declaration would not have passed this round.
That is worth stating plainly: the corpus that motivated this project is short of its floor on its *best*
class, and no accounting change reaches that.

---

## D37 — The claim gate was unversioned, and three of its rules were about my code rather than the papers

Date: 2026-09-27 · `claim_gate_version 2` · Supersedes every claim and rejection figure quoted for the
`full-shapes-2026-09-28` batch before this entry.

The first batch that used all four call shapes returned 1,849 valid answers of 1,888 and proposed 3,749
records. 882 were rejected — 0.235, against 0.12 on the earlier round with the narrow shapes. A rejection
rate that doubles when the *question shape* changes is a claim about the gate, not about the literature, so
the rejections were read before the rate was quoted.

### What the 882 were

| class | v1 | v2 | what changed |
|---|---|---|---|
| `VALUE_NOT_IN_QUOTE` | 326 | 167 | verbatim rule narrowed to single-figure fields |
| `UNPARSEABLE_VALUE` | 183 | 48 | labels, hedges and periods read; auxiliary fields no longer fatal |
| `NUMBER_NOT_IN_QUOTE` | 242 | 277 | unchanged rule; +35 records now reach it |
| `QUOTE_NOT_FOUND` | 70 | 70 | unchanged |
| `COMPARATIVE_NOT_IN_QUOTE` | 37 | 38 | unchanged |
| `SECONDHAND_CLAIM` | 24 | 24 | unchanged |
| **total** | **882** | **624** | acceptance 0.765 → **0.834** |

258 records were admitted that v1 rejected. The +35 on `NUMBER_NOT_IN_QUOTE` are **not** a regression: they
are records that previously died at an earlier check and now reach a later one. Reclassified, not recovered.

### The three defects, and which of them was mine

**1. The verbatim rule applied to prose.** 295 of the 326 `VALUE_NOT_IN_QUOTE` were `horizon_as_written`
(182) and `contrast_as_written` (113) — and stage 4's own prompt asks for `weekly` and for
`0.31% versus 0.04%`. Demanding that a quote contain the composite string verbatim rejects a true claim
whenever the paper joined the two sides with `compared with`. The invariant is about *numbers and
inequalities*, so the fields the engine converts are checked verbatim and every other `_as_written` field is
checked numeral by numeral.

**2. `contrast_as_written` was in `NUMERIC_FIELDS`**, where `parse` correctly refused it: it holds two
numbers by construction. 60 of the 183 `UNPARSEABLE_VALUE` were this module rejecting the shape this project
asked the model for. It now has a two-sided reading, and both sides must share a scale — `2.00% versus 0.14`
is a per-cent against a bare number, and a difference taken across that pair is off by a hundred with nothing
looking wrong.

**3. An unreadable auxiliary field destroyed the whole claim.** `t = 5.73`, `(se = 1.20)`,
`standard error of 1.90`, `nearly 6%`, `40 bps`, `0.55% per month` — 135 claims with verified quotes, lost to
notations this engine did not read. The notation is now read, the hedge is recorded as the bound it states
(`lower`, `upper`, `approximate`) rather than flattened to an exact value, and the label is stripped without
being interpreted: **whether a bracketed figure is a standard error or a t-statistic remains the estimand
question `numbers.py` has always declined**, so `t = 5.73` converts to 5.73 `as_reported` and the label stays
in the as-written form for a reader.

Where a field still cannot be read, the claim is kept and the field is named in `unconverted` — 132 claims.
Nothing is nulled: a null would read as "no uncertainty reported", which a parser failure has not earned.
Only `estimate_as_written` is fatal, because a claim whose own figure cannot be read has nothing to weigh.
**Stage 6 may not pool a field named in `unconverted`.**

### Two predictions, both falsified by the measurement

Worth recording because the pattern is the point of D25.

**`[2,5]` is an event window, not twenty-five.** `NUMERAL` allowed `[\d,.]*`, so the interval `[2,5]` read as
one thousands-separated figure and the quote was asked for a number nobody wrote — the same error as reading
`1964-1997` as minus 1997. 45 rejections carried that signature and the fix was predicted to recover them.
**It recovered one.** The quotes contain neither `2` nor `5`: the model took the window from a table header,
not from the span it quoted. The fix stays, because reading `2,5` as twenty-five is wrong whatever it
recovers; the recovery was zero.

**The negative window offsets were predicted to be the same defect.** `days [-15,-6]`, `days (-∞,-16]` — 26
rejections. Measured: the bare figure is absent from the quote in 20 of them. Genuine rejections, and the
gate was right. **No change made.**

The finding behind both: `horizon` is the field where the model most often reaches past its own quote. That
is a property of the call shape, not of the gate, and it belongs to whoever next edits the prompt.

### The gate had no version, and that is the more serious half

`claimgate.py` — the executable form of invariant 1, the most load-bearing instrument here — carried **no
version constant**, and claims written under two different rule sets were indistinguishable in the ledger.
`CLAIM_GATE_VERSION` now exists, is stamped on every claim and rejection, and is registered in
`tools/check_instrument_versions.py`, which refused to pass until this entry existed. Rows written before it
carry no `claim_gate_version` and are rule set 1.

One limit stated plainly: `extract --harvest` recomputes the failure breakdown it prints, so no *published*
figure is stale — but the stored rejection rows for records re-judged and still rejected keep their v1 label.
Anyone reading `rejections.jsonl` with `grep` rather than through `extract-report` sees rule set 1 labels on
624 rows. There is no re-judge path for the claim gate over stored rejections; `regate` is the acquisition
gate.

### What actually reaches stage 6, which is smaller than the claim count

3,033 claims for this batch, 22 of 22 questions covered. But pooling needs an estimate, and:

```
effect-lane claims                   593
  with a converted estimate          190
  with an as-written estimate that failed to convert   0
  with no estimate_as_written at all 403
```

**190 poolable estimates**, not 3,033 claims. The 403 are effect claims the model made without reporting a
figure — which is a finding about the call shape and the honest denominator for anything stage 6 says.

---

## D38 — Stage 6 is built and refuses every corpus here, which is the invariant working

Date: 2026-09-27 · `decision_contract_version 1`

`evidence.py` and `synthesize.py`, 28 tests, no model and no network. The stage that was going to be the
hardest turned out to be the smallest, because D16 defined a verdict and defining it removed most of the
work: the rules are counting and coverage rules, so there is no pool, no R, no publication-bias
correction and no multiplicity adjustment — a Benjamini-Hochberg over count-based rules would be
rigour-shaped output with no object. The disclosure that no error rate is controlled is printed instead,
and is never labelled a correction.

**It produces no verdict.** Layer 1 writes a profile; `adjudicate` is the only command in the project
that writes a judgement, and it refuses a provisional profile, refuses a rationale under 120 characters,
and records the profile hash it was shown. A judgement against a hash that has since moved is displayed
as **stale** with both hashes, because a verdict that outlives its reason is worse than no verdict.

Two tests exist to make a regression here argue rather than ship: one walks both modules' syntax trees
and asserts no name resembling a verdict threshold, and one asserts that the four states beyond
`SUPPORTED` appear nowhere except the declared vocabulary. They walk the AST rather than grepping the
text, because the docstrings discuss thresholds at length and a test that fails over a comment explaining
why there is no threshold is a test that gets deleted rather than fixed.

### What it says about the real corpora, which is nothing

```
synthesize projects/alembic-s4                 INSUFFICIENT_ACQUISITION: 0.21 against floor 0.80
synthesize projects/alembic-s4 --manifest-only  INSUFFICIENT_ACQUISITION: 0.56 against floor 0.80
```

No profiles written, exit 3. This is **the first place in the project where invariant 3 has had something
to gate**, and it gates. The happy path is covered by tests and has never run on a real corpus, because
no corpus here clears its floor — and the one response that is off the table is lowering the floor to see
it, which is what makes the refusal worth anything.

### The reviewer is the binding constraint now, and it is measured

Stage 5 is implemented and cannot be run on this corpus, because `SameReader` forbids the extractor —
`deepseek-v4.1-flash` — from judging its own claims, and no other available reader discriminates.

`tools/measure_reviewer_sensitivity.py` scores a candidate against a ground truth the store holds. A
record rejected for `NUMBER_NOT_IN_QUOTE` asserted a figure its quote lacks — but that alone is not clean,
because the gate checks the quote while stage 5's prompt asks the reviewer to judge **in the context of
the whole passage**, so a reviewer finding the figure two sentences later and saying `SUPPORTED` answered
the question it was asked. The first run of this tool made exactly that error and reported 0.15 for a
reviewer that may only have been reading. The set is therefore narrowed to figures absent from the **whole
chunk**: unambiguous under either standard.

Beside it, the claims the gate accepted. Sensitivity alone is worthless — a reviewer answering
`OVERSTATED` to everything scores 1.00 on the first set — so the quantity is the **gap**.

```
reader                              answered   sensitivity   flagged anyway   discrimination
claude-cli/claude-opus-5               6/6           1.00             1.00           +0.00   (n=3)
ollama-cloud/mistral-large-3:675b     70/70          0.77             0.77           +0.00
ollama-cloud/gpt-oss:120b             69/70          0.09             0.17           -0.08
ollama-cloud/gpt-oss:20b              62/70          0.06             0.23           -0.16
ollama-cloud/glm-5.3-flash             0/70             —                —               —
```

**RETRACTED the same day. The table above is invalid and the paragraph below it was wrong.** See
"The ground truth was contaminated" at the end of this entry. The rows are kept because a superseded
figure is recorded here rather than erased, and because the way it was wrong is the finding.

~~**Not one of them carries information, and two are negative.**~~ `mistral-large-3:675b` is the cleanest
demonstration: 0.77 on both sets, an identical rate on two sets that differ by ground truth. `gpt-oss:120b`
is worse than a coin — it flags a good claim more often than a fabricated figure — and its reasons show
the mechanism: it *asserts* the figure is in the quote when the figure is nowhere in the passage, which is
the fluency-without-fidelity failure D31 found in a different model on a different task.

**Second cap error of the project, mine.** A first pass at gpt-oss:120b lost 34% of calls to `NO_BODY` and
`TRUNCATED` at stage 5's shipped 400-token cap, and I read that as a property of the model. At 1,200 it
answered 69 of 70. D31 had already recorded that a cap fitted to one model is not a fair test of another,
and the tool now takes the cap as an argument.

**`claude-opus-5` is not cleared by this table.** n=3 is nothing, and a perfect score on both sets is what
a reviewer flagging everything also produces. What it does show is a different *kind* of answer: its
reasons name the exact figures in the quote and it reaches `NOT_APPLICABLE` — the quote does not speak to
the question cited — where the hosted readers reach for `SUPPORTED` or `OVERSTATED` wholesale. That is a
lead, not a result.

And the standing constraint still holds: 3,033 claims on an interactive subscription plan is not a batch
lane. Measuring a reviewer on 40 calls is not that, and buying one on 3,033 would be.

### The honest ceiling on the second rate

The second column is **not** a false-positive rate. Stage 5 exists because a gate-passed claim can still
overstate its quote, and the spec's reference corpus had 25.7% of them doing so. So the ceiling on the gap
is about 0.74, not 1.00, and the tool says so where the number is printed.

### The ground truth was contaminated, and the table above measures nothing

Written after the table, on the same day, from the same tool.

`claude-opus-5` was then measured at 0.60 sensitivity and 0.83 flagged-anyway — and its *reasons* did not
read like a lenient reviewer. They read like a careful one: "the quoted row sits under Panel A: Positive
Signals with the header ordering Group, N, Initial Reaction…", naming the table structure the figure came
from. A reviewer that specific, scoring badly, is a reason to doubt the scorer.

The ground truth was rebuilt by putting every candidate row **back through `check` as the gate is now**,
rather than trusting the `failure` and `detail` the ledger was written with:

```
rows labelled NUMBER_NOT_IN_QUOTE                                   713
  still rejected that way under claim_gate_version 3                593
  and asserting a figure absent from the whole chunk                  7
```

**Seven.** The set the table was drawn from held 125 rows under the stored labels and holds 7 under the
current gate. Two things had leaked in: rows whose figures the gate no longer considers asserted at all
(`89-91%` read as minus 91, fixed before the table was written — the ledger keeps the old label), and the
per-cent defect below, fixed after it. A reviewer calling those `SUPPORTED` was **right**, and the tool
counted it wrong. Every sensitivity figure above is therefore a measurement of my filter.

Seven rows cannot measure a reviewer. **The reviewer question is open**, and the stage 5 spec had already
said how it closes: §5 of that spec states that a reference "needs a blind, human-adjudicated sample of
chunks", and that inventing a mechanical one is the honest difficulty rather than an oversight. This entry
is what trying to invent one anyway looks like.

### What the 586 are, which is the real finding

The gap between 593 and 7 is not noise. In **586 of 593 cases the asserted figure is somewhere in the
chunk and not in the quoted span** — the model quotes one sentence and cites a figure from the table two
lines below it.

That is the dominant rejection mode of this project, it is a property of the **call shape** rather than of
the gate or the literature, and it is actionable: the quote span stage 4 asks for is too narrow for a
claim whose figure lives in a table. It also explains why `horizon` and `contrast` overreach the way D37
measured — same cause, different field.

And it is exactly why the reviewer's standard and the gate's standard must differ. The gate is right to
insist the figure be in the quote; the reviewer is right to judge in context. Two correct rules, and the
distance between them is 586 rows.

### `claim_gate_version 3` — a per-cent sign the quote leaves implicit

A table cell reads `1.99` under a header declaring percent; the claim writes `1.99%`. `_figure_present`
asked the quote for the sign and refused a figure that was plainly there.

The sign may now be dropped — but only when the quote attaches no **different** unit to those digits, so
`2.4%` against `2.4 basis points` stays a rejection, because that is a real disagreement about magnitude
and two orders of it. The unit vocabulary is `numbers._UNITS` rather than a second copy: two lists of
what a unit is would drift, and the drift would look like a rejection.

**Predicted from a sample of five, and wrong again.** Three of five sampled rejections were this defect,
which implied around 166 of 277. Measured: **18**. `NUMBER_NOT_IN_QUOTE` fell 277 → 259 and 17 claims were
admitted. Third falsified prediction of the day, and the only one where the sample was mine and I treated
five rows as representative of two hundred. The pattern is now well enough attested to state as a rule:
**on this corpus, a defect's signature in a five-row sample predicts nothing about its mass.**

---

## D39 — 0.64 on literature that is declared free, and a bot check recorded as a fact about the corpus

Date: 2026-09-27 · `gate_version 3` · Campaigns `oa-cascade-2026-09-27`, `bot-challenge-v3-2026-09-27`

D38 left the floor as the binding constraint and the question open: is 0.46 on the pilot a fact about the
literature or about our cascade? The discovery ledger already held the population that answers it —
`is_oa`, recorded by OpenAlex **at discovery time**, so selecting on it is a scope restriction and not an
outcome filter. 69 candidates carried it; 10 had been attempted; **59 had not**.

### Measured, 2026-09-27

```
the 59 untried open-access candidates      39 obtained   0.66
the whole is_oa population (69)            44 obtained   0.64
the pilot overall                          62 of 199     0.31  (was 0.12)
```

**Where the 39 came from is the finding.** `unpaywall+pmc` 25, `unpaywall` 12, `candidate` 2. Thirty-seven
of thirty-nine came from a location the resolver found rather than from the DOI the candidate carried, and
the PMC route alone carried two thirds. The cascade is not the problem: it made up to **seven** attempts
per candidate across Unpaywall, OpenAlex and PMC before giving up.

So the 36% that remains is not "we did not try". Of the 25 misses:

| | what it is |
|---|---|
| `ABSTRACT_ONLY` 14 | Unpaywall lists a repository record page as a free location. Measured: 777 KB of HTML yielding 2,746 characters — a DSpace or Pure page is megabytes of JavaScript around an abstract, and the gate is right to refuse it |
| `PAYWALL_403` 7 | hosts refusing the crawler, **including BMC and MDPI**, which publish nothing but open access. A 403 on a gold article is a bot block, not a paywall |
| `ROBOTS_DISALLOWED` 2 | honoured. Not recoverable, by our own rules, and that is the point of having them |
| `UNCLASSIFIED` 1 | ours: a host `assign_when` does not place |
| `BOT_CHALLENGE` 1 | see below |

**The conclusion, stated carefully.** On literature where a free copy is *declared to exist*, legal routes
obtain 0.64. The gap is hosts refusing automation and metadata that overstates what is reachable — neither
of which more retries fix. That is evidence about the floor that did not exist this morning, and it is the
only legitimate basis on which 0.80 could ever be revised: a dated, motivated, versioned event resting on
a measurement across two corpora and a pre-specified open-access population, rather than on one corpus's
rate having come out awkward. **It remains the project owner's decision and this entry does not make it.**

### `gate_version 3` — a bot challenge is not an abstract

The defect that found itself. A PMC fetch returned **HTTP 200, 21,312 bytes, 165 characters of text**, and
the gate called it `ABSTRACT_ONLY`. The bytes read *"Checking your browser before accessing
pmc.ncbi.nlm.nih.gov"*.

`ABSTRACT_ONLY` asserts that only a summary of this paper is freely available. That is a claim about the
literature, and a reCAPTCHA interstitial has not earned it — on the route carrying 25 of our 39 successes.
It is the same defect shape as `NOT_A_DOCUMENT` on an unreadable artifact, which stage 3 already had to
split out: **infrastructure failure recorded as an established negative.**

`BOT_CHALLENGE` is now its own kind, checked before every rule that describes the source, and bounded by
the same doubt threshold the paywall phrases use so a paper discussing CAPTCHAs is not caught by its own
prose.

**Terminal, on conduct grounds rather than because a retry could not work.** The host asked us to prove we
are not a robot; knocking again without answering that is ignoring the request, so it needs a named
campaign like any other terminal class. The class exists to keep the *denominator* honest, and that job is
done by the name and not by the retry policy.

**Fourth overestimate of the day, same shape.** Nine attempts across six unobtained candidates carried the
challenge signature, and the expectation was six reclassifications. `regate` produced **one**: it judges
the final artifact per candidate, and for five of the six the challenge sat in an intermediate attempt
while the cascade ended on a genuine 403 or abstract. The eight other attempts are now correctly labelled
inside their cascades, which is worth having for diagnosis and worth nothing for the rate.

That is the fourth time today a signature count has overshot its effect — 45 predicted and 1 delivered,
166 predicted and 18 delivered, the negative offsets predicted as a defect and genuine, and now 6 and 1.
D37 recorded this as a rule after the second. Four is enough to stop predicting from signatures at all and
quote only what `regate` or a re-harvest returns.

### Two selectors added, both needed rather than convenient

`acquire --only-oa`, because the population that measures a cascade rather than a literature is the one
where a free copy exists by definition, and because scoping a round to legally readable literature is the
honest alternative to lowering a floor a closed corpus cannot reach. Absent metadata is **unknown, not
closed**: a candidate whose channel recorded nothing stays outside this population and inside `report`'s.

`review --question`, because a verdict is per question and a profile needs only its own claims reviewed.
Measured on `alembic-s4`: 7,021 claims over 22 questions, median 250, smallest 43. One adjudicable profile
costs 43 review calls rather than seven thousand — which is what takes stage 5 from "needs batch
infrastructure" to "runs now".

---

## D40 — Stage 5 ran, the reviewer discriminates, and coverage is inflated

Date: 2026-09-27 · Batch `h15-opus-2026-09-27` · Reviewer `claude-cli/claude-opus-5`

The first real execution of stage 5 in this project. 43 review units for `H15` — one question, chosen
because it is the smallest at 43 claims of 7,021, which is what `review --question` exists for. 43
answered, 41 valid, 2 `NOT_JSON`.

```
NOT_APPLICABLE  23   (56%)
SUPPORTED       12   (29%)
OVERSTATED       6   (15%)
```

### The reviewer question is closed for this reader

D38's retracted table could not measure discrimination because the mechanical ground truth held seven
usable rows. Forty-one real claims settle it a different way: by whether the reasons are checkable.

`H15` is a `method` question — *"Semantic accuracy requires representative, blind human annotation,
distinct from the diagnostic cohort."* The `NOT_APPLICABLE` claims are about earnings-announcement timing,
the magnitude of return reversals after stale news, and whether headlines reveal good from bad. None of
them is about annotation. The `SUPPORTED` claims are a 3,000-article triple-annotated training sample with
randomised annotation order, and an anonymisation pass over 100,401 of 129,431 stories. Those are about
blind human annotation, exactly.

It neither passes everything nor flags everything, and every verdict sampled is right on inspection. That
is the control stage 5 was specified to be, and it is not the reviewer that is the constraint.

### Coverage after one reading was a statement about the extractor, and it was too high

**23 of 41 claims that passed the mechanical gate do not speak to the question they cite.** Every one of
them was extracted in the `method` lane with `kind_verified: true`, so the gate's `WRONG_KIND` check passed
them correctly: it verifies that the question is of the lane's kind, never that the claim bears on *that*
question. The stage 5 spec drew this boundary in one sentence — "nothing mechanical can verify that the
claim the quote supports is the claim that was made" — and this is the first measurement of how wide it is.

The mechanism is visible in the sources. `IND001` is vendor documentation that genuinely discusses
annotation and splits 6 supported to 10 not-applicable, which is a reasonable mix. But three
`NOT_APPLICABLE` claims come from a paper on AI and online job vacancies and two from one on illiquidity
and the cross-section of returns. Those sources say nothing about annotation methodology, and the extract
lane asked them anyway — every chunk is asked about every question of its kind, and the model answers
rather than declining.

**So `coverage: 22 of 22` is inflated**, and that figure is the one that made `UNANSWERED_IN_LITERATURE`
sayable (D33). A question whose claims all turn out to be `NOT_APPLICABLE` is not covered; it is unread.
The honest coverage figure is post-review, and it does not exist yet for 21 of the 22 questions.

**One question, and the rate elsewhere is unmeasured.** This is `method`, which asks whether the
literature endorses a practice, and a chunk about anything can be made to gesture at a methodological
requirement more easily than at an effect size. The same measurement on an `effect` question could come out
very differently, and the fourth overestimate of the day is four reasons not to guess which way. The next
step is a second question of a different kind, and the cost is now known: 43 to 250 calls.

### What this does not change

It does not change the floor. `alembic-s4` is `INSUFFICIENT_ACQUISITION` at 0.56 on its manifest, so
`synthesize` still writes no profile for `H15` and there is still nothing to adjudicate. The reviews sit in
the ledger waiting for a corpus that clears its bar, which is the correct order: invariant 3 gates
verdicts, and a profile built from a corpus read at 0.56 would invite one.

---

## D41 — The first admissible round: 38 of 40, and what it cost to get one

Date: 2026-09-27 · `pmc-screen-time`, round `pmc-oa-v1`, campaign `pmc-round-2026-09-27`

```
pmc-screen-time — round all
  ACA            38/40  0.95   floor 0.80
  obtained       38/40  0.95
  floor          0.80 (v1, 2026-09-27)   OK
  failures       BOT_CHALLENGE 2   by host: pmc.ncbi.nlm.nih.gov 2
```

**The first round in this project's history that clears its floor.** Invariant 3 has gated every corpus
here since the floor was written, and this is the first one it lets through. Both misses are the class
added the same day (D39), on live traffic, from PMC itself.

### Why a new round rather than a floor change

The arithmetic left nothing else. `alembic-s4` is 14 of 25 with a ceiling of 18, because six of its eleven
misses are vendor product pages with no open copy in existence. `pilot-screen-time` reached 0.45 over 199
candidates after three cascade fixes and 14 of 28 on its declared manifest. Its open-access subset —
`is_oa` from OpenAlex, a property recorded at discovery — obtains **0.64**, and the gap there is hosts
refusing a crawler and metadata naming repository record pages as free copies. None of that is closable by
retrying, and lowering 0.80 to meet it would have been the bar-fitting the invariant exists to stop.

What was left was to change the **population** rather than the bar. PMC is a public archive built for
automated full-text access, and across every attempt this project had made to it, 29 of 34 succeeded.

### The two properties that make the restriction legitimate

**The selector is deposits, not outcomes.** Membership is whether a PMC copy exists, which Unpaywall and
OpenAlex report; the same 40 sources were identifiable before any document was fetched. Selecting instead
the 90 candidates the pilot had *obtained* would have been outcome selection and would have produced a
meaningless 1.00. The distinction is the whole of it, and it is why the round is declared by a metadata
predicate and not by a success list.

**The restriction is declared with its size.** It excludes **159 of the 199** candidates discovered on
these topics, and that sentence is in the round's own `sources.yaml` rather than in a footnote here. A
verdict from this corpus is a verdict about PMC-deposited literature on screen time and adolescent mental
health — **not about the literature** — and an adjudication has to say so in its rationale.

The floor stays 0.80, declared before acquiring and deliberately not tuned to this round. Had it come out
at 0.7 the finding would have been `INSUFFICIENT_ACQUISITION`, as for the other two.

Questions and topics are `pilot-screen-time`'s, unchanged at registry v1. A scope restriction is not a
registry change, and bumping the registry would have made two rounds incomparable for no reason.

### What was obtained

32 HTML and 6 PDF, 25 KB to 1,388 KB, median 236. Seven carry a declared licence — `cc-by-nc` 4, `cc-by`
2, `public-domain` 1 — and thirty do not, which is recorded as unknown rather than as permission.

### The honest limitation, stated before any verdict exists

A corpus restricted to what a public archive holds is restricted by deposit policy, and deposit policy is
not random: funder mandates put publicly-funded work in PMC and leave privately-funded work out. If the
closed literature on this topic differs systematically from the deposited literature, this corpus is
biased in a direction nothing in it can measure. That is a limitation of the round and not a defect of the
engine, it cannot be fixed by reading harder, and it belongs in every sentence this round produces.

---

## D42 — `html_parser_version 2`: the HTML parser had no bibliography and no version

Date: 2026-09-27 · `pmc-screen-time`

`normalize` reported `0 refs` for 32 of 38 documents in the PMC round while all 6 of its PDFs, parsed by
GROBID, reported theirs. `html_doc.py`'s docstring said why, and said it as a decision: *"It extracts no
references and no footnotes: a filing has no bibliography, and the confirmation rule's second clause — long
enough to stand without a reference list — is what admits these documents honestly."*

That reasoning was measured against **one** HTML document, an SEC prospectus supplement. A PMC article in
HTML has a bibliography, and the consequence was not cosmetic: `PMC040` carries a `ref-list`, a
`References` heading and 38 entries, and was refused as `NOT_A_DOCUMENT` for *"0 references and body_chars
12334: below both min_references"*. **A limitation of this parser was recorded as a property of the
source** — the same defect shape as `ARTIFACT_UNREADABLE` (stage 3) and `BOT_CHALLENGE` (D39), now found a
third time in a third place.

### Measured, 2026-09-27

```
                          before   after
documents with references    6/38   37/38
distinct reference keys       354   2,594
confirmed                   36/40   37/40      0.90 -> 0.93
```

Read loosely and on purpose: a container the markup itself declares (`ref-list`, `references`,
`bibliography` in a class or id — never a heading's text, which would catch a prose section discussing
references), each `li` over 30 characters, a DOI where the entry carries one, and a year **only when the
entry names exactly one candidate** — two is a page range or a volume that looks like a year, and choosing
between them would be a coin toss recorded as a fact. Where nothing better exists the entry's text is the
title, because a reference that can be *counted* is what the confirmation rule needs and one that can be
*resolved* needs a title or a DOI; this says which it got rather than inventing the rest.

### The parser is an instrument and was unversioned

Same gap as the claim gate had this morning (D37). What a parser extracts decides `body_chars` and
`references`, and those decide `fulltext_confirmed` — so two documents confirmed under different versions
of it are not the same kind of row. The PDF parser has been pinned by digest in `compose.yaml` since D29
precisely because it is an instrument; the HTML parser is code in this repository and had no version at
all. `HTML_PARSER_VERSION` is now stamped on every `documents.jsonl` row and registered with
`tools/check_instrument_versions.py`, which refused to pass until this entry existed. Rows written before
it carry none and are version 1.

### And the operational defect underneath, which wasted a measurement

The first re-normalize changed nothing, and the reason was not in the code. `claimstone.sh` runs
`docker compose run`, `compose.yaml` bind-mounts `store/` and `projects/` **and nothing else**, so the code
comes from the image — and the image predated the fix. The run re-appended its previous output and the
figure it printed was the old one, which I read as "the fix does not work".

No data was lost: 1,460 chunk rows held 730 distinct ids, because the ledger is append-only and `latest_by`
takes the last. That is the resumability property D9 is for, working without being asked.

`claimstone.sh` now builds before it runs. The build is cached and costs a second when nothing changed,
which is the right price for never reasoning about a stale image again.

---

## D43 — The notation vocabulary was domain knowledge in the engine, and a corpus in another field proved it

Date: 2026-09-27 · `pmc-screen-time`, batch `pmc-round-2026-09-27`

2,936 work units over 734 chunks of 37 sources; 2,902 answered, 1,927 records proposed. The first harvest
accepted 1,605 and rejected 322, and `UNPARSEABLE_VALUE` was the largest class at **172**. Since D37 that
class only fires on `estimate_as_written` — the claim's own figure — so 172 of them was a claim about this
engine and not about the papers.

It was. The refusals read `AOR=1.66`, `AOR = 2.74`, `ß = −.22`, `ß = .19`, `p < .01`, `95% CI=1.14–2.42`.

**CLAUDE.md states the test this failed**: *"a project in an unrelated field must be expressible without
touching the package."* `numbers.py`'s label list contained `sharpe|sharpe ratios?` and did not contain
`OR`. The finance corpus parsed and the epidemiology corpus did not, and the reason was a discipline's
vocabulary sitting in `claimstone/`.

### Three gaps, and only one of them was vocabulary

**Typography, which belongs in the engine unconditionally.** A bare leading decimal — `.22`, `-.18`,
`−.22` — is how psychology and epidemiology write a coefficient, and `_NUMBER` required a digit before the
point. And `<`, `>`, `≤`, `≥` are the symbols an inequality is written with, where `_BOUNDS` had only the
words. Both are how figures are typeset, in any field.

**Vocabulary, which is project data.** `DEFAULT_VALUE_LABELS` now holds what any quantitative field writes
— `t`, `se`, `sd`, `p`, `z`, `n`, `mean`, `median` — and `sharpe` is gone from it. A discipline's labels are
declared in `extraction.value_labels`: 38 of them in the two screen-time projects (`AOR`, `aHR`, `IRR`,
`ß`, `β`, `Cohen's d`, `η2`, `95% CI`), 6 in `alembic-s4` (`Sharpe`, `alpha`, `IR`). The engine merges its
generic set with the project's at use, so neither module holds the other's business — `config` validates a
declaration and `numbers` owns its default.

**And the plumbing did not exist.** `extract.harvest` read `getattr(project, "extraction", {})`, and
`config.py` loaded no `extraction` section at all — so the `comparatives` override that the gate has
supported since D22 had never once come from a project. The getattr's default made a missing feature look
like an absent configuration. `load_extraction` exists now, refuses a misspelt key, and `Project` carries it.

### Measured, 2026-09-27

```
                       first harvest   with the declared vocabulary
UNPARSEABLE_VALUE                172                            109
total rejections                 322                            259
claims                         1,605                          1,668
```

The 109 that remain are overwhelmingly `holds more than one number` — a confidence interval or a range put
in the estimate field, which is a badly shaped record and a correct refusal.

**1,668 claims, 8 of 8 questions covered, 36 distinct sources, 120 carrying a converted estimate.**

### One defect I introduced and caught in the same minute

Making the label's connector optional — needed because `p < .01` puts an inequality where `=` goes — let
the one-character labels eat the start of a word: `n` took the `n` of `nearly 6%` and left `early 6%`,
breaking a hedge that had been parsing correctly since this morning. A label may not be followed by a
letter. The test suite caught it on the run after the change, which is the argument for the suite.

---

## D44 — The first complete round, and the first evidence profile

Date: 2026-09-28 · `pmc-screen-time`, decision contract v1, registry v1 `82007de2b5`

All six stages ran end to end on an admissible corpus, for the first time since the project began.

```
discover    40 candidates, round pmc-oa-v1, scope declared before acquiring
acquire     38/40 obtained
normalize   37/40 = 0.93 confirmed          floor 0.80  OK
extract     2,936 units -> 1,668 claims, 8 of 8 questions, 36 sources
review      Q04, 42 claims, claude-cli/claude-opus-5
synthesize  8 profiles, 1 adjudicable
```

### The profile

`Q04` (effect) — *"The effect survives preregistration and correction for multiple comparisons."*

```
  PMC005  CONTRADICTS   all tests two-tailed, no adjustment to alpha for multiple tests
  PMC006  QUALIFIES     preregistered studies' small associations unlikely to be of practical significance
  PMC006  CONTRADICTS   preregistered studies report a lack of sizable or meaningful associations
  PMC006  CONTRADICTS   (see below — this row should not be here)
  PMC024  QUALIFIES     Bonferroni within domain, .05 divided by the number of tests
  direction count   CONTRADICTS 3  QUALIFIES 2      (a count, not a strength)
  linkage           unestablished: 1 sample label, verbatim
  coverage          3 of 37 examined sources
  gate rejected     UNPARSEABLE_VALUE 19  VALUE_NOT_IN_QUOTE 1  SECONDHAND_CLAIM 1
  read, not used    NOT_APPLICABLE 36  OVERSTATED 1
  profile_sha256    8e93cbde7a5a11a2
  provisional       false
```

**Nothing supports the question and five results bear on it**, which is a profile, not a verdict. Whether
that is `CONTRADICTED` on three results from two independent papers, or `UNANSWERED_IN_LITERATURE` on a
coverage of 3 of 37, is the judgement `adjudicate` exists to record and this stage refuses to make.

### One review that should not have passed, found by reading the profile

The fourth row's claim reads *"This passage does not address whether any screen-use and wellbeing effect
survives preregistration or correction for multiple comparisons"* — a **meta-statement about the passage**,
not a finding, carrying `stance: CONTRADICTS` when it contradicts nothing. `claude-opus-5` marked it
`SUPPORTED`.

So the reviewer's 5 usable results contain one that is not a result, and the direction count is really 2
contradicting and 2 qualifying. Three things follow, and the third matters most.

The extractor produced a claim whose content is "this text does not answer the question", which no lane
asks for. The reviewer, asked whether the claim is what the quote supports, answered a narrower question
than the one that mattered and said yes — the quote does support the sentence, which is the wrong sentence
to be in a claim at all. And **a person reading the profile sees it immediately**, which is the argument for
the two-layer design in the verdict contract: layer 1 describes, and the failure a mechanical check and a
model reader both passed is visible to the adjudicator in one line.

### D40's open question, answered against the guess

D40 measured 23 of 41 `NOT_APPLICABLE` on `H15` and said the rate elsewhere was unmeasured, adding that
`method` is the kind a chunk about anything can most easily be made to gesture at — so an `effect` question
might come out very differently.

It came out **worse**: `Q04` is `effect` and **36 of 42 are `NOT_APPLICABLE`, 86%**. Over-attachment is not
a property of `method` questions. Every chunk is asked about every question of its kind and the model
answers rather than declining, and that is the dominant cost of the current call shape.

On this question the reviewer is probably right to say so: screen-time papers rarely speak to
preregistration and multiple-comparison correction, so a corpus that genuinely does not address it produced
42 claims anyway. **Which makes `coverage: 8 of 8 questions` after extraction a statement about the
extractor.** Post-review, `Q04`'s coverage is 3 sources of 37.

### What this round is, and is not

It is the pipeline working: an admissible corpus, verified quotes, a second reader, a profile with its
counts and its rejections and its hash, and no verdict invented anywhere in it.

It is not a finding about screen time. The round reads **40 of 199** candidates discovered on these topics,
restricted to what PubMed Central holds, and one of eight questions has been reviewed. A verdict recorded
against this profile is a verdict about PMC-deposited literature, on one question, at a coverage of 3
sources — and the rationale has to say all three.

## D45 — A drained queue is not a complete reading, and a saved profile is not current evidence

Date: 2026-09-28 · `profile_version 2` · corrects the completeness claim in D44

The functional review reproduced three ways to certify different evidence from what was read:
profiles ignored failed extraction readings, round filtering applied to admission but not the evidence,
and adjudication trusted a saved profile even after its corpus fell below the acquisition floor.
A registry rollback also passed when that older version had previously been recorded.

The baseline checks passed: 743 tests, 7 skipped; four projects validated; seven recorded instrument
versions acknowledged. Those checks did not establish completeness. Eight new regression cases all
failed before the correction, including a terminal failed call with no claims, an unharvested valid
answer, an unattempted fifth source above an 0.80 floor, evidence leaking across rounds, old-registry
claims relabelled current, signing after floor failure, stale evidence without rebuilding, and reopening
a previously recorded registry. Eleven further cases check empty successful answers, obsolete prompts,
manifest scope, scope-specific signatures, read-only reporting, CLI registry enforcement, re-gated
source exclusion, review rationale identity and old-registry reviews of reused annotation ids.

### The population and the reading obligation

A profile uses the same candidate selector as admission: `round` and `manifest_only`. Only confirmed
sources in that population enter the chunks, annotations and coverage. Claims from another registry
version are not relabelled with the current question. The question registry check runs at every CLI store
entry, including discovery and model commands, and checks rollback before its same-hash fast path.

For each non-operational question kind, every current chunk needs a valid answer to the current kind
prompt and schema. Matching valid readings from any batch or reader may fulfil that obligation; obsolete
prompts and incomplete historical experiments do not create extra obligations. A valid empty array is a
completed reading. A terminal failure is an unanswered reading. A nonempty answer must have reached the
gate for that chunk and reader. A confirmed source without chunks remains outstanding too.

This preserves D13's comparison primitive and D14's distinction between terminal work and successful
work. It does not change the extractor prompt, claim gate, review instrument or acquisition floor.

### Measured on the whole stored PMC corpus, without writing or calling anything

Derived by `synthesize.preview(load_project('projects/pmc-screen-time'), Store('pmc-screen-time'))`:

```
confirmed sources                  37/40 = 0.925; acquisition final, floor 0.80 met
current chunks                     734
expected extraction readings       734 per kind = 2,936
unanswered                         effect 10, heterogeneity 4, method 15, premise 5 = 34
valid but unharvested               0 in every kind
confirmed sources without chunks   0
Q04                                provisional; blocking: awaiting_extract
Q04 coverage                       3/37; no adjudication
```

The corrected read-only result agrees with the review's full queue audit. Q04 has no outstanding review
of the 42 harvested claims; that never established that every passage had been read. This **supersedes
D44's `provisional false` and "1 adjudicable"**, not its observations about the five displayed results or
the reviewer's bad fourth row. No prediction is made about what the ten missing readings will yield.
The eight historical profiles and all request and response ledgers remain untouched.

### What version 2 hashes and what a signature checks

`PROFILE_VERSION = 2` identifies the changed profile instrument, independently of decision contract v1.
The hash is calculated after adding the selector, population, acquisition accounting and per-kind
completion. A semantic digest binds each question's full claims, reviews, rejections and current chunks;
wall-clock build, harvest and review times are excluded. Recovered rejections are superseded by accepted
claims in the displayed denominator. Rebuilding identical evidence leaves the hash unchanged.

Profiles and signatures are selected separately by `(question_id, round, manifest_only)`. Signing requires
the hash the person was shown, a current project and a read-only fresh profile matching the saved one.
It refuses a current floor failure and any changed input. Reporting also recomputes in memory, so a
signature becomes stale without requiring the operator to first run `synthesize`. If the corpus is now
inadmissible, only an explicitly historical profile and stale signature may be displayed. Legacy profiles
need a rebuild and a new reading; no historical hash is silently upgraded.

The remaining review defects, including numeric token boundaries, answer re-judgement/harvest authority,
reader annotation identity, chunk generations, full-result review and acquisition auditing, are separate
work. This correction does not certify those instruments or authorize model calls, floor revisions or a
person's verdict.

## D46 — Whole numeric tokens, reversible gate decisions, and a profile that names its current gate

Date: 2026-09-28 · `claim_gate_version 4` · `profile_version 3`

R02 of the functional review demonstrated that the gate accepted a claim of positive `2` against a quote
of `-2`, `.2` or `2.7`. Digit-only boundaries also accepted fragments of thousands-grouped numbers and
exponents. Single-figure `*_as_written` fields had the same defect: verbatim substring membership is
necessary, but `2` is a substring of every one of those different values.

Version 4 compares whole numeric tokens, including signs, leading decimals, thousands grouping and
exponents. Single-figure fields keep their exact-string check and additionally verify those tokens.
D25's `reversals-3.7` typesetting and range endpoints are retained, as is D38's implicit-percent rule and
its different-unit refusal. Explicit positive signs do not change magnitude. No domain labels are added.

There are 57 new numeric regression cases. Of the first 49, thirty failed under version 3 before the
repair. Eight further cases protect typography exposed by the full replays. Six further cases verify append-only gate supersession, replay idempotence,
consumer exclusion and the inability to sign legacy annotations before their current gate runs.

### The measurement, including the false rejections it caught during development

The entire stored production batches were actually harvested twice on temporary copies of their JSONL
ledgers, once with gate v3 loaded from commit `9e402e5` and once with gate v4. Both use the current
converter and revision-aware harvester; the comparison isolates the gate, not every historical engine
version. A third pass verifies that replay appends nothing. Reproduce with:

```bash
.venv/bin/python tools/measure_claim_gate_reharvest.py projects/pmc-screen-time --batch pmc-round-2026-09-27
.venv/bin/python tools/measure_claim_gate_reharvest.py projects/alembic-s4 --batch full-shapes-2026-09-28
```

| batch | proposed | newly stamped v4 accepted | newly stamped v4 rejected | unchanged identity conflicts | v3 accepted annotations retired by v4 | recovered |
|---|---:|---:|---:|---:|---:|---:|
| PMC production | 1,927 | 1,668 | 259 | 0 | 0 | 0 |
| full shapes | 3,749 | 3,051 | 606 | 92 | 7 | 0 |

The seven retired annotations are six `NUMBER_NOT_IN_QUOTE` and one `VALUE_NOT_IN_QUOTE`. They include
`17.24` borrowed from `-17.24`, `0` borrowed from a decimal, and positive window offsets borrowed from
negative ones. They are not seven recovered claims. The full-shapes replay preserves 92 existing
annotations whose ids collide with different readers/content, reports those conflicts, and does not
pretend R09's annotation identity is repaired. The repeat passes wrote **zero** decisions. Hash snapshots
before and after the tool confirm the real JSONL ledgers did not change.

The first v4 measurement falsely retired four PMC annotations because the papers write `. 001`, with a
space after the leading decimal point. Reading the actual re-harvest output caught it. Supporting that
notation then exposed sentence punctuation, `vs. 2.89` and `... 1` being misread as decimals. The final
scanner distinguishes them, and the added regression cases cover them all. The final PMC result is
**zero retirements**, not the first development result's four. One existing PMC rejection changes its
first failing check, `NUMBER_NOT_IN_QUOTE` to `UNPARSEABLE_VALUE`; the accepted set stays identical.

The whole-store current counts in the normalized v3/v4 copies are 1,668/259 → 1,668/259 for PMC and
7,022/1,142 → 7,015/1,149 for alembic-s4. The latter includes annotations from other batches, so those
counts must not be substituted for the full-shapes row above. This is an actual replay of the named
batches under the harvester's existing historical-answer selection, not certification of model-answer
re-judgement authority (R05).

### A corrected rejection must be able to retire a former acceptance

Previously, a re-harvest could append a rejection while every consumer continued using the old accepted
row. A higher `gate_revision`, shared across the two ledgers for a claim id, now makes either outcome
authoritative. Identical decisions under the same instrument are not appended twice. A changed gate
version is recorded once even when the decision stays the same.

Legacy rows have revision zero and retain their established accepted-wins interpretation; chronology
between separate legacy logs is not invented. New revisions supersede them. Profiles, review queues,
extraction/review reports and secondhand discovery all use the same current-decision reader. Neither
ledger is rewritten and a previous review is preserved without keeping a newly rejected claim usable.

`profile_version 3` adds the current `claim_gate_version` and `extraction.unregated`. An annotation that
has not reached that gate keeps its kind's profiles provisional with `awaiting_regate`. Thus changing
the code cannot silently certify legacy accepted rows. Version 2's scope and live-signature checks remain.
The real PMC ledger still has 1,927 current annotations awaiting gate v4; Q04 shares 786 effect-kind
annotations and still has ten unanswered readings. Its historical hash remains unsignable.

No production re-harvest was applied: the comparison preserves the real record while R05 and R09 remain
open. Authoritative answer replay and immutable reader annotation identity are the next repair, before
applying that replay to real batches. No model or publisher was called, no floor was changed and no
adjudication was made.

## D47 — Authoritative answer replay and immutable reader annotations

Date: 2026-09-28 · `result_judge_version 2` · `annotation_version 2` · `profile_version 4`

R05 showed that harvest read physical attempts and skipped rejudgements: a schema-invalidated success
could remain usable forever. Replay itself could clear prompt mismatch, refusal or transport failures
merely because the returned bytes parsed. R09 showed that quote/result ids shared by different readers
could overwrite annotations, change their metadata or transfer a review to a different extraction.
D14's measured latest-result policy already decided replay authority; this applies it to consumers.

Results now record original transport/refusal/truncation facts and the effective judgement schema.
Rejudge restores those facts from the physical attempt, preserves requested-reader identity and prompt
verification, verifies stored bytes against their recorded hash and retains a schema override on repeat.
An unchanged repeat judgement appends nothing. Missing response bytes remain skipped and counted by
the measurement tool. A known failure or mismatched recorded prompt hash cannot be read as success.

Extraction and review harvest use current results per reader, including replay rows. Read-only consumers
also check those answers: a failed or empty extraction, changed annotation, or invalidated review retires
its cached evidence immediately without erasing ledger history. Complete original records identify
annotations, including optional metadata, together with chunk, call, reader and harness. New ids are
32 hex digits. Exact legacy records keep their ids and reviews; changed content or another reader gets
a new id. Batch provenance accumulates idempotently when the identical annotation is independently
returned for the same call in several batches. It is still one annotation, not another study.

Identical review prompts merge explicit annotation targets rather than dropping every target after the
first. Harvest applies an answer to each eligible target and checks reader independence separately.
A changed annotation cannot inherit its predecessor's review. This does not yet repair R10: the prompt
still asks about claim and quote without the full extracted metadata.

### Complete replay measurement

Reproduce offline, without model calls or mutations of the original ledgers:

```bash
.venv/bin/python tools/measure_answer_replay.py projects/pmc-screen-time
.venv/bin/python tools/measure_answer_replay.py projects/alembic-s4
```

The tool copies every JSONL ledger into a temporary store, rejudges every stored batch, runs both real
harvesters, and repeats both operations. Hash snapshots verify the original ledgers remain unchanged.

| corpus | extract/review batches | active claims/rejections before | active claims/rejections after | retained original claim ids | new claim ids | usable reviews after / retained original |
|---|---:|---:|---:|---:|---:|---:|
| PMC | 1 / 1 | 1,668 / 259 | 1,668 / 259 | 1,668 | 0 | 42 / 42 |
| alembic-s4 | 7 / 2 | 7,021 / 1,143 | 7,194 / 1,166 | 6,991 | 203 | 74 / 41 |

The historical alembic claim ledger contains 7,021 ids, all initially active. Thirty original ids
are absent after replay; 203 newly distinct annotations enter the accepted set. The after counts include
all seven extraction batches and all readers, not only D46's full-shapes batch. They must not be
interpreted as independent studies, gate quality, reviewer ground truth or new network acquisition.
All original 83 reviews across the two corpora remain attached to unchanged annotations; the additional
33 usable alembic reviews come from already stored results. Every repeat operation writes **zero** rows.

PMC rejudges 2,944 answers OK, 26 NOT_JSON, 5 SCHEMA_INVALID and 3 TRUNCATED; no response lacks stored
bytes. Alembic rejudges 3,874 OK, 29 NOT_JSON, 30 SCHEMA_INVALID and 18 TRUNCATED; 27 current results
have no stored response bytes and are skipped. These include byte-less failed calls; missing bytes
are not counted as successful empty answers. Extraction harvest reports 34 and 95 unanswered current
reader results respectively. Review harvest reports zero and nine. These are current-result counts,
not the number of historical paid attempts and not per-question completion counts.

Twenty-one regression cases cover invalidation before harvest, replay recovery, immutable metadata,
multiple readers, legacy record equality, merged review targets, independent batch provenance,
original failures, raw hash corruption, requested-reader identity and persistent schema tightening.
Existing fixture tests also verify exact legacy-id migration and repeat replay cost accounting.
`profile_version 4` changes authoritative evidence selection and whole-record completion; historical
profiles require a fresh build and reading. No adjudication was performed.

D46's numeric table describes the actual historical execution with its previous answer/identity
selection. `measure_claim_gate_reharvest.py` now reports these additional instrument versions because
running it with the new harvester measures a different instrument; its figures cannot silently replace
that dated table. The full D47 replay is the current migration measurement.

The real stores have not been reharvested. R06 chunk-generation identity and R10 full-result review
remain to be repaired before applying a production replay; this measurement does not certify them.


## D48 — Complete review repairs: active passages, full annotations and honest accounting

Date: 2026-09-28 · `chunk_version 2` · `review_version 2` · `profile_version 5`
· `fetch_version 2` · `discovery_version 2` · `admission_version 2`
· `audit_version 2` · `model_report_version 2`

The remaining counterexamples in the functional review (R06–R08, R10–R12, R14–R15)
are executable failures of the existing contract, not a new acquisition strategy or a change
of floor. D19's passage boundaries, D8's robots policy, D36's additional class floor and
D14's authoritative answer policy remain the measured choices.

### Immutable active passages and complete second reading

Normalization publishes generation-specific immutable chunk ids and commits their complete manifest
in the final document row. Consumers select exactly that manifest; an interrupted generation is
invisible and a shorter re-normalization cannot leave old trailing chunks active. Generation identity
includes source bytes, parsed payload, chunk version, thresholds and HTML parser version. The pure
chunker's boundaries/text are unchanged. Repeating the same generation writes no additional chunks.
Identical bytes belonging to different sources are normalized separately. Legacy positional ids remain
readable where their declared count is consistent; ambiguous legacy sets refuse instead of guessing.
A changed complete passage invalidates its old reading even if the quoted sentence still occurs.

Review v2 presents both the original model record and the engine's scientific annotation, including
converted numbers, uncertainty, sample, horizon, design, dependence and kind-specific metadata.
SUPPORTED attests the complete annotation in passage context. Review requests and rows carry the
annotation digest and review instrument. Missing optional metadata is not an assertion. Legacy reviews
attested a narrower task: they remain auditable but cannot certify v2. This is a new task requiring a
new independent reading; replaying its old bytes cannot supply that reading. Profile v5 reflects this
selection and the active passage set. Historical profiles require rebuilding and reading again.

### Request conduct and acquisition accounting

Fetcher v2 disables automatic redirects and checks exclusion (including subdomains), budget and
robots before each destination. Relative locations are resolved; loops, missing Location, non-HTTP
addresses and excess hops fail explicitly. Redirected robots requests also respect exclusions and
budgets. Robots caches are per scheme/host/port and the budget is rechecked after fetching rules.
D8's permissive handling of a genuinely unserved robots file remains unchanged.

Discovery, citation resolution and acquisition wrap the transport with an append-only request log.
Redirects, robots, transport failures, blocked destinations and parsed-response summaries are recorded
with context. Bodies available to the logger are content-addressed. Summary events are not additional
HTTP attempts. Query completion has a separate ledger: a valid empty search is successful, a malformed
API envelope or transport failure is not. Failed recorded queries block finality for their round;
a manifest-only population does not pretend that an unrelated search defines it. Older unlogged
requests remain unknown. The discovery CLI reports incomplete searches and returns exit 3.

Class rates use the same confirmed/obtained basis as the global rate, retaining both counts and the
unknown ceiling. Audits vary one project-configured threshold over the declared found population,
with class policy and explicit round/manifest scope; unattempted candidates stay in the denominator.
The hypothetical audit explicitly reports an obtained-byte basis, not stage-3 confirmation.
Regate applies the project's class policy too. QUALIFIES remains a displayed direction count and
contributes to neither directional class count. Model report totals use the same reader identity as
queue selection and equal the sum of their parts; replay rows, even with an empty origin timestamp,
are never physical paid attempts or retry increments. Wheels now include backend subpackages.

### Complete offline measurements

Reproduce the counterexamples and the distributed artifact:

```bash
.venv/bin/python docs/reviews/reproduce_review_2026_09_28.py
python3 docs/reviews/reproduce_wheel_2026_09_28.py
.venv/bin/pytest -q
.venv/bin/claimstone validate --all-projects
.venv/bin/python tools/check_instrument_versions.py
```

All **22 counterexamples pass**; the wheel contains five backend files and its CLI discovers every
backend in an isolated interpreter without editable-install hooks. The regression suite has
**878 passing tests, 7 skipped**; six project configurations validate and **16 instruments** are
acknowledged. Thirty-two new regression cases cover the remaining behaviors, using offline
transports and temporary stores. No production normalization or external sweep was performed.

Run `tools/measure_answer_replay.py` for each corpus, as in D47. It rejudges and harvests every stored
batch on a temporary copy, repeats both operations, and compares original ledger hashes:

| corpus | extraction/review batches | active claims/rejections before | after | original claim ids retained | new ids | original historical reviews retained | usable v2 reviews |
|---|---:|---:|---:|---:|---:|---:|---:|
| PMC | 1 / 1 | 1,668 / 259 | 1,668 / 259 | 1,668 | 0 | 42 | 0 |
| alembic-s4 | 7 / 2 | 7,021 / 1,143 | 7,194 / 1,166 | 6,991 | 203 | 41 | 0 |

The extraction counts match D47; the change is review eligibility. All original 83 review ids remain
on disk, as do replayed legacy responses, but none can attest the full annotation. Every repeat appends
zero rows and the real ledgers remain unchanged. PMC has zero missing raw answers; alembic has 27,
which remain skipped and counted. These are annotations and historical answer accounting, not
independent studies, a measurement of reviewer quality, or completed scientific evidence.

All fifteen software findings now have a repair and a reproducer. Applying offline replay to production,
finishing unanswered extraction, commissioning independent v2 reviews and rebuilding profiles remain
operational follow-up. Paid work, floor changes and adjudication remain the operator's decisions.
No publisher or model was called, no floor changed, and no verdict was signed.


## D49 — Apply the measured replay and measure the full-review workload

Date: 2026-09-28 · same instruments as D48: `result_judge_version 2`, `annotation_version 2`,
`claim_gate_version 4`, `review_version 2`, `chunk_version 2`, `profile_version 5`.

D48 established a complete, idempotent migration on temporary stores. The operator then authorized
applying it to production and measuring the remaining work without a model or publisher call.
`tools/replay_answers.py --apply` now performs that operation, verifies every original file prefix,
checks that only result/gate/review/registry ledgers grow, and repeats the replay to prove zero writes.
The measurement details and exact commands are in
[the production replay report](replays/2026-09-28-production-replay.md).

The actual accepted/rejected sets are 1,668/259 for PMC and 7,194/1,166 for alembic-s4, matching
D48. Original claim ids retained are 1,668 and 6,991, with zero and 203 new ids. All original 83
review ids remain, and 33 additional Alembic reviews are harvested from stored responses. None
attests the full-annotation v2 task. No original bytes are rewritten or deleted; both complete
repeat operations append zero rows. Missing raw answers remain zero and 27 respectively.

The scoped workload is **1,668 unique review calls and 34 unanswered readings** for PMC;
**6,183 review calls covering 6,188 annotations and 28 unanswered readings** for Alembic's curated
manifest. Those are measured by the real review builder on temporary copies, not estimated from a
sample. The manifest is 14/25 confirmed, still below its 0.80 floor; its whole-store annotation count
is a different population. Q04 currently needs 42 full-annotation reviews and shares 10 missing
effect readings. New extraction results can add review work.

Current scoped gate and harvest completion have zero outstanding annotations. The remaining
blocking work is successful extraction and independent full-result review. Historical profiles
were not rebuilt or signed. Reader selection, paid budget and adjudication remain the operator's
choices; the narrower historical review task cannot serve as full-field ground truth. This operation
changes no software instrument, parser, floor, registry or acquisition population.

## D50 — Delegated Q04 readers and bounded continuation, blocked before inference

Date: 2026-09-28 · Gate 4 / review 2 / profile 5, unchanged

The operator delegated choosing cloud models and continuing Q04. Extraction remains
`ollama-cloud/deepseek-v4.1-flash`; full-result independent review is assigned to
`ollama-cloud/mistral-large-3:675b`. The choice uses a separate reader with documented JSON
support and metered pricing; it is not a measurement of review accuracy or an engine default.

All ten missing effect responses were inspected: seven `NOT_JSON` stopped below the cap, three
`TRUNCATED` consumed all 2,500 output tokens. Ten current prompts/schemas are now queued with
a 7,500-token cap, a recorded change of call identity, not a prediction of recovery. The full v2
Q04 review queue has 42 calls and 319,562 prompt characters; new extraction can add annotations.

The first real attempt failed resolving `ollama.com` before reaching the service. It is recorded
as `BACKEND_ERROR`, with unknown usage/cost and no response bytes. No new annotations or reviews
were produced and no profile was rebuilt. Q04 remains provisional with both completeness blocks.

`tools/complete_question_round.py --plan <local-plan>` measures without calls; `--execute`
resumes extraction, harvests, extends independent review and rebuilds profiles only after Q04 is
complete. The dated plan imposes a USD 1 cumulative ceiling, reserves each whole call before
contact, retains conservative reservations for unknown-cost attempts, excludes replay rows from
cost and stops after the first failure. The DNS attempt reserves USD 0.339; that is an accounting
bound, not a claim that the provider charged it. The host command and measured state are in
[the continuation report](replays/2026-09-28-q04-continuation.md).

Five tests cover budget enforcement, unknown-cost attempts and resume, pre-payment reader
independence, newly harvested extraction extending review without repeated calls or adjudication,
and reading `.env` without executing it. All 16 existing instruments remain unchanged. Adjudication,
floor revision and extending expenditure beyond Q04 still belong to the operator.

## D51 — Cloud format is a request, not enforcement; harvest partial success and retry narrowly

Date: 2026-09-28 · Gate 4 / review 2 / profile 5 and all other instruments unchanged

The operator ran D50's host command. Six physical extraction attempts produced five valid answers
and one `NOT_JSON`. The failed body is `[]` followed by prose. Strict whole-response parsing rejects
it correctly; taking only the prefix would invent a reading. The official Ollama documentation now
explicitly says Cloud structured outputs are unsupported. The earlier assertion that sending
`format=schema` guarantees the shape was incorrect; the runner comment is corrected, while actual
transport, harness provenance and strict validation are unchanged.

Harvesting the five valid answers produced **20 accepted annotations and zero rejections**. Repeating
the harvest appends zero of either. The partial failure had left `awaiting_harvest`; the operational
driver now harvests successful extraction and review in `finally` even when another call stops a lane.
The measured PMC population is now 1,688 annotations / 259 rejections, with 1,688 unique prospective
review calls and 29 unanswered readings. Q04 remains 42 annotations; five effect readings are missing.
All harvest/regate obligations are current. No v2 review, new profile or adjudication exists yet.

The delegated cloud-reader choice extends to `gemma4:31b` only for primary JSON/schema failures that
have no valid response. Four untouched primary requests remain; successful calls are never sent to
the alternate reader. Prompts, schemas and caps are unchanged. Mistral stays independent of both
extractors. The v2 local plan retains all older attempts and the USD 1 ceiling; per-reader dated rates
account for both paid and unknown-cost attempts. The six host attempts are priced at USD 0.0054975
under the conservative plan rates, plus USD 0.339 reserved for the earlier unknown-cost failure.
Alternate-reader recovery and scientific accuracy remain unmeasured.

Three additional operational tests verify harvesting before failure propagates, targeting only failed
calls without repayment on resume, and cumulative mixed-reader/unknown-cost accounting. Full checks:
889 passed, 7 skipped; six valid project configurations; all 16 instrument versions acknowledged.
Commands, plan hashes, source documentation and current audits are in
[the continuation report](replays/2026-09-28-q04-continuation.md).

## D52 — Q04 completes its obligations; scientific interpretation remains human

Date: 2026-09-28 · All 16 instruments unchanged

The operator completed the bounded v2 host plan. Seven valid DeepSeek answers and three targeted
Gemma answers close all ten missing effect readings. All 734 current effect obligations have zero
unanswered, unharvested, unregated or unchunked backlog. The original invalid responses remain
invalid. Forty-two Mistral full-annotation v2 reviews are valid and current: 4 SUPPORTED, 31 OVERSTATED,
7 NOT_APPLICABLE. No narrower historical review was relabelled as a complete review.

The saved audit and live profile agree on
`9340389c9aac29b77e901c20e27434d211fe9e7825a68d99995d8c6fa5b20fdd`.
It is profile v5, not provisional, with no blocking reasons. Four results from four of 37 examined
sources remain; seven other profiles are still provisional and no adjudication exists.
Corpus counts are 1,721 accepted / 271 rejected, with 24 remaining readings and 1,679 prospective
full-review calls elsewhere. Repeated extract/review harvest appends zero annotations or reviews.

The host's original-byte check passed. Physical attempts are 14 extraction and 42 review. Conservative
plan pricing totals USD 0.0556299; the unknown-cost DNS attempt reserves USD 0.339. The USD 1 ceiling
accounts for USD 0.3946299. Agent verification made no additional model/publisher call or profile build.

Formal readiness does not decide Q04. Inspection of all four retained annotations/passages flags
preregistration/correction coverage, secondary attribution and stance relevance. In particular, PMC009
is a GRADE quality assessment labelled CONTRADICTS; its review reason restates the claim but does not
justify that stance on Q04's preregistration/multiple-comparison question. The other three passages
also require explicit examination of both conditions and the estimand. These are reading notes, not
new ledger decisions or a measured accuracy rate. The four accepted reasons do not establish both
conditions. A person alone chooses the verdict, states the PMC scope/coverage and signs the current hash.

Commands, exact current measurements and the local reading packet are in
[the completed round report](replays/2026-09-28-q04-ready.md). Required checks: 889 tests, 7 skipped;
six valid projects; 16 acknowledged versions. Scientific agreement on the complete v2 task remains
unmeasured, and spending on the other seven questions remains the operator's decision.

## D53 — Represent JATS locally before measuring another acquisition route

Date: 2026-09-28 · `jats_parser_version 1` · Existing 16 instruments unchanged

HANDOFF identifies Europe PMC after D39/D41's PMC acquisition measurements. Its fullTextXML
service serves the open-access subset. The current normalization route sends XML to HTML;
another URL would not establish that the acquired tables and bibliography were read correctly.

The pure JATS parser produces the shared Document shape, retaining primary-article paragraph
order, inline whitespace, nested headings, table geometry, notes and explicit citation metadata.
Unsupported tables leave the source awaiting without publishing partial document/chunk rows.
XML media types select JATS, XHTML stays HTML, and confirmation audits use the recorded format.

Measured with `pytest -q tests/test_jats.py`: **22 synthetic cases pass**, covering evidence
separation, cell alignment, malformed/unsupported inputs, offline normalization, unchanged replay,
confirmation thresholds and new chunk identity when the parser version changes. This is not a
publisher-corpus measurement. JATS generation identity records its parser version; previous
HTML/PDF generation inputs remain identical. The instrument checker tracks the new parser.

No production ledger, Q04 profile, registry, floor or model request was changed. No scholarly
acquisition or paid model call was made. A JATS-aware acquisition gate, Europe PMC resolver route,
operator-approved bounded pilot and live comparison remain pending; no improved acquisition rate
is claimed. [The specification](superpowers/specs/2026-09-28-jats-normalize-design.md) records the
implemented boundary and required next measurement.

Required checks after this change: **911 passed, 7 skipped**, six valid project configurations,
and all **17 instrument versions** acknowledged. Production profiles remain unchanged.

## D54 — Freeze a metadata population and record local reuse as local reuse

Date: 2026-09-28 · `population_version 1` · `discovery_version 3` · `reuse_version 1`

The operator requested starting two configured finance strands. Offline inspection found their
population predicate only in comments: naming a round did not restrict discovery. A new optional
`sources.yaml.population` declares exact hosts, source API names or exact venues, with a dated
version and rationale. Predicates never inspect acquisition success or scientific conclusions.
The predeclared manifest seed remains included. Unmatched discovery observations are retained
outside the candidate denominator in `discovery_population.jsonl`; the actual predicate and digest
are frozen per round in `populations.jsonl`. Changing or removing a held predicate refuses, and a
selector cannot be retrofitted onto a round that already has candidates. Citation discovery follows
the same predicate. Unconfigured projects retain their existing behaviour.

Local reuse must retain the original byte hash and provenance and be re-gated under the receiving
project's policy, with its declared source class. A local file is not an HTTP response; its acquisition
row records reuse separately, without fabricated requests. No floor or question registry is changed,
and archive membership does not certify a copy's identity or a trading strategy's profit.

Measurement: the first prepared instance has 19 predeclared seed sources. Eight exact-URL cached
PDFs pass hash, identity and receiving-gate checks; all eight confirm from cached TEI, without a new
HTTP or model request. Their 232 current chunks produce 232 effect and 232 method work units.
Coverage is 8/19 = 0.4210526316: admission remains INSUFFICIENT_ACQUISITION. A bounded 30-query
discovery pilot stops after its first recorded CONNECTION_ERROR rather than inventing a result or
repeating transport failures. No scientific annotation or signed verdict is produced.

Synthetic checks cover excluded metadata retained outside the denominator, exact-host matching,
policy drift/removal/retrofit refusal, citation and promoted-citation filtering, receiving-class
reuse, rejected-but-retained bytes, raw/parsed/input mismatches refused before appends, read-only
previews, fresh queues without transferred answers, and idempotent reapplication.

Verification for D53/D54: `pytest -q` passes 949 tests with 7 skips; all six project
configurations validate; all 19 instrument versions are acknowledged by the version checker.

## D55 — Meter a whole-document calibration without certifying the corpus

Date: 2026-09-28 · All 19 scientific instrument versions unchanged

The operator ran the bounded acquisition/normalization commands and explicitly authorized up to
USD 10 for calibration. The stored host results confirm all 19 seed sources; two discovered
candidates remain unattempted. Admission is 19/21 = 0.9047619, above the unchanged 0.80 floor,
but provisional: the latest 30 discovery queries include eight OpenAlex failures (five 429s,
three exhausted-domain budgets). There are 549 current chunks, not the earlier prepared 232.

Calibration reads every current chunk of two predeclared primary documents in the selected kinds:
18 effect readings and 22 method readings. It retains the full frozen registry task for each kind,
then reviews every mechanically accepted annotation from this sample with a different model.
`tools/run_calibration.py` distinguishes CALIBRATION_COMPLETE from a complete corpus profile:
it never builds profiles or adjudicates. No inference about recall or scientific accuracy follows
from valid JSON or agreement between two models without a reference assessment.

Extraction uses deepseek-v4.1-flash, with gemma4:31b only for JSON/schema failures without a valid
answer; full-result review uses mistral-large-3:675b. This reuses D51/D52's measured operational
choices; it is not a claim that those readers are scientifically calibrated on a new domain.
The unpaid preparation's 2,500-token cap becomes 7,500 in new call ids, following D50's measured
truncation problem; the original requests remain intact. Peak rates are verified on the
[provider pricing page](https://ollama.com/pricing) and retained in the private dated plan.

The plan freezes all four input hashes, the registry and extraction requests, and checks all sample
passages against current confirmed documents. One shared ceiling covers extraction, fallback and
review, including full-context reservations for unknown-cost attempts. Partial answers are harvested
even when the next call stops; successful calls are not repaid on resume. Review staging can contain
unrelated work, but only this sample's immutable annotation ids enter the paid review queue, retaining
all merged targets. Existing Q04 spending and authorization remain separate.

The first physical attempt fails DNS resolving ollama.com: BACKEND_ERROR, no valid reading or new
scientific annotation. Its USD 0.339 reservation is an accounting bound, not a provider charge.
The private content-addressed audit preserves the error and confirms every original byte remains.
Resume from the host using the same plan, rather than opening a second budget or discarding the error.

Operational tests cover shared-budget enforcement, sample-only review queues, merged annotation
targets, all declared review questions, partial-success harvest, idempotent resume without payment,
read-only preview, and input/passage drift refused before contact.

Verification: 979 tests pass with 7 skips; six project configurations validate; all 19
instrument versions remain acknowledged. No registry, floor or parser instrument is changed.

## D56 — The calibration runs; its reviewer labels are not a reference assessment

Date: 2026-09-28 · All 19 scientific instrument versions unchanged

The operator completed D55's same USD 10 plan on the host. Forty whole-document readings now have
valid answers: 39 primary successes and one alternate-reader recovery of a NOT_JSON answer. The
gate actually returns 80 accepted annotations and 13 rejections (two VALUE_NOT_IN_QUOTE, four
COMPARATIVE_NOT_IN_QUOTE, one QUOTE_NOT_FOUND, six NUMBER_NOT_IN_QUOTE). All 80 accepted
annotations have independent full-result reviews: 26 SUPPORTED, 53 OVERSTATED, one NOT_APPLICABLE.
No review is outstanding in this sample. These are annotations on two studies, not 26 independent
scientific confirmations. Priced attempts total USD 0.11250092 at the plan rates; the original
unknown-cost DNS attempt retains its USD 0.339 reservation. Cumulative accounting is USD 0.45150092,
not a provider invoice. Original bytes are preserved; no profile or adjudication is written.

Interactive inspection reads all 80 review reasons and claim sentences, all 26 SUPPORTED original
annotations with their current full chunks, and diagnostic rejected-by-review cases in context.
It finds problems on both sides: an extractor names the wrong company and strengthens uncertainty;
some claims describe a study without establishing the attached question. Reviewer reasons sometimes
ignore context they explicitly acknowledge, treat an inclusive condition as an exclusive one, or
criticize a missing horizon that the claim states. SUPPORTED rows can also carry an incoherent
question-relative stance or establish only a study design rather than the question's proposition.

Thus 53/80 is the observed label proportion, not a measured extractor-error rate. A bad rejection
reason does not justify promotion: the annotation may separately be inapplicable. The private reading
packet retains the original annotations, reviews, contexts and consultative flags without changing
any scientific ledger. It is not an adjudication or a validated independent gold reference.

Next measurement: test a prompt variant that checks question applicability, every asserted field
against the whole passage, and stance against the exact question, with an explicit reference
assessment and retained baseline. Do not relax the quote gate, relabel historical reviews, change
the production review-task version or scale to the full corpus on the basis of these counts.
The acquisition scope remains 19/21 confirmed (0.9048), with eight failed discovery queries and
two unattempted acquisitions; the round remains provisional. Whole-corpus unanswered readings
are 531 effect, 527 method, 549 heterogeneity and 549 premise. D55's calibration budget does not
silently authorize paying for them. Existing PMC profiles and all instruments remain unchanged.

## D57 — Compare prompt variants in isolation under the original calibration ceiling

Date: 2026-09-28 · All 19 scientific instrument versions unchanged

The operator authorizes D56's next comparison. `tools/run_prompt_comparison.py` reads a frozen
plan and defaults to offline preview. It rereads the same two documents through 40 extraction
tasks with an additional domain-neutral applicability, fidelity and stance checklist. An
independent reader reviews every accepted annotation using a corresponding checklist. Production
prompts, schemas, historical annotations, profiles and adjudications are untouched. Experimental
requests, raw answers and harvested annotations live in a separate store with nonoverlapping roots.

A second part sends the review variant 12 unchanged baseline annotations, including four positive
controls. Their agent-authored reference assessment records labels, rationales, original annotations
and baseline reviews in a hash-frozen private file. Cases were selected after inspecting errors:
this is a provisional development reference, not independent gold or a held-out accuracy estimate.
The baseline agrees on 4/12 selected cases; that fraction cannot estimate general accuracy.
Adopting a variant remains a separate decision after reading results, including positive controls.

The original USD 10 ceiling now aggregates physical attempts across both stores and all three
experimental queues: diagnostic review, extraction with its bounded alternate reader, and full-result
review. Prior priced costs and unknown-attempt reservations remain in the denominator. Model
identities, rates and reservation bounds remain the original plan's; no new USD 10 budget is opened.
Both input and copied source ledgers are frozen. On execution, production file hashes must remain
identical and every old experimental byte must remain intact. Successful work resumes without
another payment; unrelated or altered full-review requests refuse before contact.

The first diagnostic attempt fails resolving ollama.com: BACKEND_ERROR, no valid diagnostic
answer and no new extraction. Its USD 0.131672 unknown-cost reservation combines with the prior
USD 0.339 reserve and USD 0.11250092 priced attempts. Cumulative accounted spending is
USD 0.58317292, not a provider invoice. The content-addressed experimental audit confirms all
original bytes and the complete production store are unchanged. Resume the same plan on the host.

Tests exercise complete independent review with merged targets, production preservation,
idempotent resume, prior unknown-cost spending blocking new calls, input/request drift, budget
changes, overlapping stores and read-only preview. No gate, registry or floor is relaxed.

Verification: 987 tests pass with 7 skips; six project configurations validate; all 19
instrument versions are acknowledged. The prepared real-plan preview passes offline.

## D58 — The prompt comparison completes, but neither variant is adopted

Date: 2026-09-28 · All 19 scientific instrument versions unchanged

The operator resumes D57's frozen plan on the host. All 12 diagnostic reviews and all 40
experimental extraction tasks return valid answers; one SCHEMA_INVALID primary answer is recovered
by the bounded alternate reader. Harvest actually admits 41 annotations and rejects 15 (13
NUMBER_NOT_IN_QUOTE, two COMPARATIVE_NOT_IN_QUOTE). All 41 admitted annotations receive independent
full reviews: 10 SUPPORTED, 28 OVERSTATED, three NOT_APPLICABLE. The production store and every
original byte remain unchanged. Cumulative priced attempts are USD 0.20182786, unknown-cost
reservations USD 0.470672, cumulative original-budget accounting USD 0.67249986, not an invoice.

Agreement with the post-selected provisional development reference improves from 4/12 to 6/12.
Positive controls remain 3/4; challenge-case agreement improves from 1/8 to 3/8. The variant catches
a question-relative stance error and correctly withholds a result attached to a different
methodological proposition. It still misreads an inclusive condition as an exclusive restriction,
accepts regression design as evidence for a predictive proposition, and conflates predictive
information leakage with causal identification. The reference remains agent-authored, not held-out
or independent gold. These counts are not general scientific accuracy.

Inspection reads every new claim, quote and review reason, and complete annotations and supplied
contexts for the SUPPORTED cases and diagnostic concerns. A hypothetical mechanism remains admitted
and labelled SUPPORTED as an effect annotation; another SUPPORTED annotation does not establish the
incremental comparison required by its question. Some rejection reasons still add requirements the
annotation does not assert, or ignore explicit context. One daily-return rejection invokes absent
intraday timing despite the source expressly describing post-publication returns; the annotation
is independently inapplicable to a weeks-to-months question, so the bad reason does not promote it.

The fall from 80 to 41 admitted annotations, or from 26 to 10 SUPPORTED labels, cannot establish
better precision or retained recall: these are different extractions, and neither reviewer is a
reference oracle. Do not adopt either variant or scale reading on that basis. Preserve the isolated
experiment and consultative reading packet. The next targeted measurement should hold annotations
fixed and explicitly distinguish applicability, fidelity and question-relative stance, with
positive controls retained; another whole-document extraction is not yet justified. No production
prompt, task version, profile, adjudication, registry or floor changes.

Verification: 987 tests pass with seven skips; six project configurations validate; all 19
instrument versions are acknowledged.

## D59 — Hold annotations fixed and request independent diagnostic checks

Date: 2026-09-28 · All 19 production scientific instrument versions unchanged

The operator authorizes the targeted reviewer experiment after D58. Rather than rereading documents,
`tools/run_review_diagnostics.py` supplies unchanged complete annotations and their original entire
passages to the same independently measured reviewer. A new experimental schema requires separate
labels and reasons for applicability, fidelity and question-relative direction. The prompt is a
replacement experimental task, not another appendix to the production task's single-label instructions.
It does not privilege rejection, invent question requirements or treat a hypothetical mechanism as an
observed effect. Context may establish metadata; named entities, quantities and uncertainty still need
evidence. Fidelity can pass while applicability fails. Direction remains unclear for inapplicable work.

The private hash-frozen development reference retains the previous 12 cases and adds six inspected
annotations from D58, giving 18 tasks and seven positive controls. Extra cases cover hypotheses,
missing incremental comparisons, neutral-publication findings, inclusive conditions, short-horizon
applicability and a controlled positive-news finding. All were selected after inspecting results;
this remains provisional agent-authored development assessment, not held-out accuracy. Expected axes
are deliberately unscored where no defensible assessment was made: 18 applicability, 16 fidelity and
eight direction cases are scored. Reference labels and rationales are never supplied to the model.

Responses are saved only in a separate diagnostic queue. They are never harvested into reviews.jsonl,
used to build a profile or treated as signed question verdicts. The report derives an explicitly
experimental summary label for comparison: inapplicable first, then fidelity/direction failure,
then uncertainty, otherwise supported. Its uncertainty mapping is diagnostic and does not redefine
the production AMBIGUOUS contract. No production REVIEW_VERSION or gate changes. Both previous stores
must remain byte-identical; diagnostic history remains append-only. Annotation and passage hashes,
registry inputs, prepared requests and prior accounting histories are checked before contact.

The same original USD 10 budget includes every physical attempt from baseline calibration, D57/D58
comparison and this new diagnostic queue, including unknown-cost reservations. The preview returns
18 unanswered cases and USD 0.67249986 already accounted, with zero new physical attempts. Because
DNS access failed in this environment for both earlier experiments, no redundant attempt is made
here. The operator runs the hash-frozen prepared plan on the host. Successful answers resume without
payment; invalid terminal answers cannot falsely yield DIAGNOSTICS_COMPLETE on resume.

Tests cover the independent schema, diagnostic summary priority, retained merged annotation targets,
all prior priced and unknown spending, positive-control requirements, history/annotation/request
drift, overlapping stores, unscored axes, read-only preview, preserved previous stores, idempotent
resume and incomplete invalid answers. No extraction, production review, profile or adjudication
is written by this experiment.

Verification: 1,006 tests pass with seven skips; six project configurations validate; all 19
instrument versions are acknowledged. The prepared real-plan preview passes without new spending.

## D60 — Repair the diagnostic output instruction while retaining the failed attempt

Date: 2026-09-28 · All 19 production scientific instrument versions unchanged

D59's first host attempt returns SCHEMA_INVALID: `$: expected object, got list`. The retained raw
answer contains three check/verdict/reason objects in a Markdown-fenced array. The declared schema
requires one object keyed applicability/fidelity/direction, each with label/reason. The model was
sent that schema through the provider's format option, but D51 already establishes that this is
a request, not a guarantee. D59's prose named three independent checks without showing their exact
output structure. No diagnostic case has a valid answer yet; the stop is a formatting failure,
not a negative scientific assessment of 18 annotations.

Add explicit format version 2 to the experimental prompt, displaying the exact nested object shape
and prohibiting the observed array/check/verdict form. Keep the schema, model, semantic checks,
reference cases and budget unchanged. The original format version remains reproducible under its
original plan; new prompts get new call ids and a distinct queue. Do not reinterpret or transform
the old answer into a successful result. This is a diagnostic prompt repair, not a production
review-task revision or relaxed scientific gate.

The repaired plan freezes the prior diagnostic request and result files and includes their physical
attempts in cumulative spending. Prior queues must be distinct, nonduplicated and in the same
isolated diagnostic store; both main previous scientific stores remain frozen. The failed priced
attempt costs USD 0.00156 at plan rates: cumulative priced attempts USD 0.20338786, unknown reserves
USD 0.470672, original-budget accounting USD 0.67405986. The new 18-task preview passes offline,
with no new physical call here. Execute the repaired plan from the host; repeating the original
terminal-invalid task does not repair it.

Regression tests retain the old invalid result and request bytes, verify new prompt identities
under the unchanged schema, include failed spending, and refuse missing, duplicated, altered or
misplaced prior accounting queues. No production review, extraction, profile or adjudication is
written, and no quality improvement has yet been measured.

Verification: 1,012 tests pass with seven skips; six project configurations validate; all 19
instrument versions are acknowledged. Both original and repaired diagnostic previews remain readable.

## D61 — Separate reviewer checks recover positive cases but expose critical regressions

Date: 2026-09-28 · All 19 production scientific instrument versions unchanged

The operator completes all 18 repaired diagnostic tasks with valid responses. Both previous stores
and all original bytes remain unchanged; no extraction or production review is written. Cumulative
priced attempts total USD 0.22658886, unknown-cost reserves USD 0.470672, original-budget accounting
USD 0.69726086. The diagnostic task is operationally complete, not adopted as scientific review.

On the post-selected provisional reference, applicability agrees on 12/18 scored cases, fidelity
on 15/16 and direction on 6/8. Summary-label agreement moves from 6/18 to 10/18: positive controls
from 3/7 to 6/7, challenge cases from 3/11 to 4/11. On the original 12 cases, agreement remains 6/12.
Those are paired development-reference counts, not held-out accuracy or an independent gold score.
Separate checks correctly distinguish a faithfully quoted hypothesis from empirical evidence and
a faithful daily result from evidence about a longer horizon. They recover inclusive-sample and
neutral-publication positive controls previously rejected.

Two critical regressions block adoption. A claim names Facebook but its quote concerns the
Pfizer-Allergan example; the reviewer merges the entities and accepts both strengthened certainty
and a demonstrated-failure label. The single scored fidelity disagreement thus contains a serious
error, despite 15/16 aggregate agreement. Another annotation attaches CONTRADICTS to nonsignificant
pre-earnings returns when the question asks about concentration around earnings. The reviewer changes
around into prior to in its rationale and declares that direction coherent. Both were withheld by
the preceding reviewer task and become SUPPORTED in this one.

Inspection of the supplied contexts confirms continuing design/result, causal/predictive,
horizon and missing-comparison errors. A remaining rejected positive control has its negative-news
comparison in the immediately following sentence. Correct labels can also carry wrong reasons:
one NOT_APPLICABLE diagnosis interprets Week 0, the news formation period, as the return horizon;
its actual applicability defect is absence of coverage-versus-no-coverage evidence independent of
tone. A recovered positive control's rationale invents a no-news comparison that the question did
not require. Label agreement alone does not validate reasoning.

Retain the three-axis task as an isolated diagnostic aid, not production review. Do not scale
reading or promote annotations from these labels. The next discriminating measurement should
compare another eligible independent reader on the same frozen cases and inspect the critical
regressions and positive controls; before adoption, use additional cases not selected to tune the
prompt. The private consultative packet retains all 18 full annotations, replies and contexts,
including faulty rationales attached to matching labels. No historical label or question verdict
is changed, and no additional paid experiment is started by this assessment.

Verification: 1,012 tests pass with seven skips; six project configurations validate; all 19
instrument versions are acknowledged. Offline diagnostic measurement agrees with the completed audit.

## D62 — Compare an independent reviewer without changing the task or repricing history

Date: 2026-09-28 · All 19 production scientific instrument versions unchanged

The operator authorizes the next comparison after D61. Select Moonshot's `kimi-k2.6`, an independent
reader from the extractor and the existing Mistral reviewer, available through
[Ollama Cloud](https://ollama.com/library/kimi-k2.6). The dated
[Ollama pricing table](https://ollama.com/pricing) lists USD 0.95 input, 0.16 cached input and 4.00
output per million tokens. The provider's
[configuration](https://huggingface.co/moonshotai/Kimi-K2.6/raw/main/config.json) sets 262,144 context
positions; its [model card](https://huggingface.co/moonshotai/Kimi-K2.6) describes an instant mode.
Request thinking off through the existing harness and record that request honestly. This is model
selection for measurement, not evidence of better scientific review or verified endpoint support.

`tools/compare_reviewers.py` uses a fresh isolated results store and byte-identical requests from the
completed 18-case diagnostic queue. Schema, whole contexts, annotations, seven positive controls,
prompt hashes, merged targets and 1,200-token output caps are unchanged. Neither the reference nor
Mistral's answers enter the new reader's prompt. The baseline plan, diagnostic files, previous
scientific histories and reference are frozen before contact. Summary labels remain experimental;
no extraction, production review, profile or adjudication is written or automatically adopted.

Historical and new-reader attempts occupy separate accounting buckets, priced/reserved under their
own frozen reader configurations. A new model must not reprice an older unknown-cost attempt, and
none of the earlier queues can drop out of the cumulative USD 10 budget. Offline preview reproduces
USD 0.22658886 priced plus USD 0.470672 unknown-cost reserves: USD 0.69726086 accounted. All 18 first
attempts with unknown usage would reserve another USD 4.5690624, fitting within the same budget.
Actual execution reserves each next call before contact and stops after an invalid or failed attempt.
Successful answers resume without another payment; terminal-invalid answers stay incomplete.

Fourteen tests cover byte-identical requests, merged annotation targets, previous spending and
reader-specific unknown-cost bounds, refusal of drift/self-review/nested stores/invalid rates,
stopping before contact when prior spending exhausts the budget, offline preview, original-byte
preservation and complete/invalid resume. No Kimi model call is made here: prior measured DNS failures
establish that the operator must execute from the host. The next assessment must inspect reasons,
especially the two critical regressions and positive controls, before any unseen-case validation.

Verification: 1,026 tests pass with seven skips; six project configurations validate; all 19
instrument versions are acknowledged. The prepared preview has 18 unanswered cases and reproduces
Mistral's 10/18 label, 12/18 applicability, 15/16 fidelity and 6/8 direction reference agreement.

## D63 — The independent reader improves fixed-case review but still confuses testing with evidence

Date: 2026-09-28 · All 19 production scientific instrument versions unchanged

The operator completes all 18 byte-identical diagnostic requests with `kimi-k2.6`, with no invalid
responses. The existing harness records requested thinking off and schema enforcement. Earlier stores
and all original bytes remain unchanged; no production review, extraction, profile or adjudication is
written. The new attempts cost USD 0.04999230 at frozen plan rates. Cumulative priced attempts total
USD 0.27658116, unknown-cost reserves USD 0.470672 and original-budget accounting USD 0.74725316.
Those are plan-rate accounting figures, not a provider invoice.

Offline `tools/compare_reviewers.py --plan <v4-plan>` reproduces the completed audit: reference-label
agreement is 14/18 versus Mistral's 10/18, positive controls 7/7 versus 6/7 and challenge cases 7/11
versus 4/11. The original twelve-case subset improves to 8/12 from 6/12. The readers agree on 13/18
summary labels. Applicability agrees with the provisional reference on 14/18 scored axes, fidelity on
16/16 and direction on 8/8. This reference is post-selected and agent-authored, not held-out accuracy
or a human gold standard. Aggregate fidelity/direction agreement does not validate unscored axes.

Both critical D61 regressions are now withheld. The reader identifies the entity substitution between
Facebook and the Pfizer-Allergan example, plus speculative certainty being promoted to demonstrated
failure. It marks fidelity UNFAITHFUL, but additionally calls the annotation NOT_APPLICABLE, giving a
different summary label from the reference OVERSTATED. Preserve that disagreement: it successfully
detects the entity defect without agreeing with the provisional applicability classification. Its
applicability reason unnecessarily demands a cutoff-controlled returns comparison for a methodological
question. Separately, it correctly recognizes that negligible pre-earnings returns do not contradict
concentration around earnings and rejects the annotation's CONTRADICTS stance.

The recovered seventh positive control uses the adjacent negative-news sentence to establish the
required comparison. A daily finding is correctly withheld from a weeks-long question, and a generic
neural-network conclusion is withheld from an incremental-comparison question. The coverage-design
case keeps the right NOT_APPLICABLE label with a better reason about sentiment-sorted portfolios,
although its fidelity reason still calls Week 0 a matching horizon when it is the formation period.

Three false acceptances remain. A regression specification is described as an empirical predictive
result; a paper-organization sentence about future earnings is treated as a finding of concentration;
and an illustration of training-data knowledge is treated as causal identification of news effects.
In that last case the reason changes the question's conditional requirement into an assertion that
the relationship was causally identified, reversing the actual proposition. Its direction axis was
unscored, so the headline 8/8 cannot certify stance reasoning throughout the sample. Some otherwise
matching reasons add causal language to statistical controls or frame a semantic check as quote-only.
Read reasons and whole contexts, not just label totals.

Prefer Kimi as the candidate for the next validation, retaining the task unchanged so a new sample
tests transfer rather than further tuning these eighteen cases. Before production adoption, freeze
additional cases not used to tune this prompt, record the reference before obtaining model answers,
and inspect residual applicability/stance errors. Neither reader consensus nor an agent-written
reference replaces the person's adjudication. Do not scale corpus reading or promote annotations
from this development comparison. A private consultative packet retains all eighteen current
annotations, contexts, unchanged reference cases, both readers' reasons and these limitations.
No further paid experiment is launched by this assessment.

Verification: offline measurement matches the completed comparison audit and previous scientific and
diagnostic stores remain byte-identical during assessment. Six project configurations validate and
all 19 instrument versions are acknowledged. New dashboard/round-state files appear during this
assessment: the expanded full suite reports 1,036 passed, seven skipped, two failed round-state
assertions and four dashboard setup errors from sandbox-denied socket creation. The earlier suite,
excluding those two newly added test modules, passes 1,026 tests with seven skips. This is a scoped
verification, not a green full suite; the new dashboard work is not modified by this assessment.

## D64 — Begin real use with a traceable partial reading rather than an implicit corpus verdict

Date: 2026-09-28 · All 19 production scientific instrument versions unchanged

The operator asks to begin actual supervised use. Select one existing effect question and local sources;
make the first product a consultative dossier with concrete passages, interpretation and missing coverage.
`tools/build_consultative_dossier.py --plan <curated-plan> --write` reproduces its JSON/Markdown in
`audits/consultative/`. It pins registry/passage/document hashes, checks each record with existing
claim gate v4, carries source classes and preserves every original file. It has no model runner and
writes no production claim, review, profile or adjudication. The acquisition floor still blocks the
product below threshold; provisional admission remains explicitly provisional above it. The renderer
contains no domain rules, and the interactive curator is not misreported as a batch extractor.

The measured pilot selects nine passages from seven active chunks in three already confirmed working
papers. All nine mechanically pass. Repeating the build reproduces identical artifacts and appends no
scientific ledger rows. The named acquisition round stays 19/21 confirmed, above 0.80, with
awaiting_discovery and awaiting_acquire. Selected passages do not change this denominator or certify
that the full papers/corpus were read. No new network/model call is made, and the cumulative USD 10
calibration budget accounting remains USD 0.74725316.

The reading's useful outcome is a distinction among variables and units. A text-sentiment study
reports predictability up to thirteen weeks after weekly aggregation and different positive/negative
durations. A second reports a risk-adjusted next-month association; its multi-year news momentum
result concerns subsequent sentiment scores, not an equally long return forecast. A third forms
weekly portfolios on news-associated price reactions and converts daily returns to monthly display
units, separately examining long event-time drift. Neither that conversion nor the price-based signal
establishes long-horizon text-sentiment predictability. These are source-specific reading observations,
not source votes or a pooled effect, and do not establish net profitability today or causal identification.

Passages from two sources were outside the fixed diagnostic task, but selection is targeted and inspected
interactively. They are development material, not held-out model-validation cases. Freeze additional
cases and an independent reference before model answers for that subsequent step. The first dossier
can be used to refine the consuming research question without adopting a production reviewer or
changing any question-registry wording. Its contents and private project details remain gitignored.

Six focused tests verify exact quote/numeric/source identity, the acquisition floor, read-only preview,
original-file preservation and identical repeat output. The expanded full suite retains the unrelated
dashboard/round-state problems recorded in D63; no dashboard file is edited for this pilot. All six
project configurations validate and all 19 scientific instrument versions remain acknowledged.

## D65 — Measure a declared search protocol and preserve unknown literature recall

Date: 2026-09-29 · All 19 production scientific instrument versions unchanged

The operator requests a complete investigation of the pilot question and asks how to measure source
selection and maintain updates. Reuse D10's measurement rather than resurrecting capture-recapture:
its assumptions fail in this corpus. Correct GUIDE's contrary statement. Separate acquisition,
search execution, relevance screening and full reading. Two discovery channels expose gaps; their
agreement does not establish a completeness percentage. Current dashboard text that describes two
channels as making completeness estimable contradicts D10 too and must not be used as such a measure.

`tools/audit_research_search.py` is an offline audit of a frozen protocol, not a new admission or
scientific decision rule. It checks all four project input hashes and the registry, matches planned
API/topic/query combinations against logged outcomes, distinguishes failed, missing and shallower
queries, flags result caps, and carries existing admission/reading/review measurements without
reinterpreting them. It lists all current candidate identities and document generations and the
bibliography still requiring screening. Recall and screening precision remain null. Its optional
previous audit comparison separates new candidate keys, absent keys and changed document generations;
those identities are explicitly not deduplicated independent studies. Population differences are
reported rather than silently compared as identical scopes. `--write` creates only a content-addressed
research-search audit. No request, production ledger row, profile or signature is generated.

The initial measured inventory has 21 candidates, 19 confirmed documents and 549 active chunks.
Effect completion has 531 unanswered readings. The production ledger carries 17 annotations for the
selected question, all reviewed (six SUPPORTED and eleven OVERSTATED), and 896 bibliography identities.
Neither the reviewed labels nor selected D64 passages establish complete reading or semantic accuracy.
The first dedicated keyword wave freezes 57 query/API pairs across four existing topics at a cap of
25 results each; all 57 are NOT_RUN at baseline. Its metadata population, registry and floor are
unchanged. This is preparation, not a completed search. A successful capped search still requires
inspection for missed results, and the default citation threshold cannot substitute for screening
singly cited relevant works. Admitted candidates are never removed retrospectively because they
prove irrelevant. Population-excluded works remain limitations, not negative evidence.

Incremental use preserves dated discovery rounds plus cumulative corpus audits. Reuse identical
byte/prompt/schema work, inspect possible duplicates, and reread revised documents under current
instruments. Rebuild profiles after evidence changes; signatures on changed live evidence become
stale. Newly indexed/discovered is not necessarily newly published. A weekly explicit update is a
starting operational cadence, not an implemented autonomous watcher or scientific stopping rule.
A complete-round reading/review budget needs the post-discovery queue; the existing calibration
accounting of USD 0.74725316 is unchanged. The sandbox prohibits socket creation, so the prepared
57-query discovery command must run on the operator's host.

Four focused tests cover missing/failed/shallow/capped queries, document-generation deltas, immutable
offline measurement with unknown recall, and refusal of changed protocol/input hashes. Full-suite
baseline before these changes remains 1,042 passed, seven skipped, two round-state failures and four
socket-denied dashboard fixture errors. These existing failures do not certify the new dashboard.

Post-change verification: 1,046 tests pass and seven skip; the same two round-state failures and
four sandbox socket errors remain. All four new audit tests pass. Six project configurations validate,
all 19 instrument versions are acknowledged, and `git diff --check` passes. No model credit is spent.

## D66 — Resume failed discovery with scoped OpenAlex authentication and inspect population losses

Date: 2026-09-29 · `fetch_version 3` · discovery/population/admission instruments unchanged

The operator executes D65's dedicated 57-query wave. The recorded outcome is 40 completed and
17 failed, all failures OpenAlex (five RATE_LIMITED_429, twelve DOMAIN_BUDGET_EXHAUSTED).
Crossref completes 19 queries; arXiv completes 19 but returns zero records for every query.
The arXiv searcher wraps each multiword term as one exact phrase; this run cannot establish that
there is no relevant arXiv literature. Twenty-one completed queries reach the cap of 25 records.

Discovery records 525 observations, 462 distinct candidate identities. Only two observations are
admitted; 523 are excluded, comprising 460 distinct excluded identities, of which 437 have DOI
redirector URLs. Both admitted works are on an allowed host, but their titles concern consumption
and Chinese social media, not directly the selected predictive proposition. This is a title-level
screening flag, not full-text adjudication. Five excluded identities have exactly normalized titles
matching three held manifest sources, including an NBER working paper and the Federal Reserve seed.
The manifest copies are on admitted hosts while metadata contain doi.org links. Exact title matches
are audit signals, not evidence establishing publication-version identity or automatic deduplication.
The metadata predicate is working as declared but its URL representation constrains effective
coverage. Do not silently whitelist doi.org, remove admitted irrelevant works from denominators,
or fit the population to successful downloads. Inspect excluded works and declared copy identities
before a separately dated population/resolution revision.

Current cumulative acquisition is 19/23 (0.8261), but ACA is 2/4, below its 0.80 class floor, so
admission is INSUFFICIENT_ACQUISITION. Discovery failures and four unattempted candidates remain.
No corpus profile is ready. The audit and exclusion review are investigative records, not a verdict.

OpenAlex's current official authentication documentation permits a bearer header and states that
429 can reflect either daily-budget exhaustion or request rate. A free key increases the keyless
budget; it is not a guarantee that failed queries will succeed. Source:
https://help.openalex.org/api/authentication/ (checked 2026-09-29). The current fetcher does not use
an OpenAlex key. Add optional OPENALEX_API_KEY from the environment and container configuration.
`fetch_version 3` sends it as an Authorization header only to the exact HTTPS api.openalex.org
origin, recomputing headers on every redirect. It is never placed in request URLs or session-global
headers. Existing request logs remain unchanged; previous failures remain failures. Five synthetic
tests verify same-origin authentication, stripping on redirects, absence on HTTP/lookalike/other
origins, no secret in recorded request rows, and unchanged keyless requests. These tests measure
credential confinement, not a live acquisition gain or proof of the provider's quota cause.

`tools/resume_research_search.py` validates D65's frozen protocol and resumes only missing, failed
or shallower queries. Successful capped queries require a deeper protocol, not a routine retry.
It shares one fetcher and stops on the first search failure, preserving round/query identities and
recorded outcomes. Default is offline preview; execution requires the OpenAlex key when that API is
selected, with a one-query default limit. No acquisition, model call or scientific signature is
launched. The safe .env reader accepts the optional key alongside contact/Ollama credentials;
it never executes the file or assigns Docker UID. Population rules, registry, floors and scientific
prompts are unchanged. A full investigation remains pending authentication, search depth and
excluded-copy/bibliography screening.

Verification after implementation: 17 focused authentication/resume/network/search-audit tests pass.
The current full suite reports 1,055 passing, seven skipped and four dashboard fixture errors because
the sandbox forbids sockets. Concurrent dashboard/round-state fixes are outside this change; their
previous assertion failures no longer appear. Six configurations validate, all 19 instrument versions
are acknowledged and `git diff --check` passes. The resume preview selects exactly the 17 failed
queries, makes no network call and spends no model credit.

## D67 — Recover the keyword wave and make acquisition preview obey execution scope

Date: 2026-09-29 · All 19 scientific instrument versions unchanged

The authenticated host resume completes all 17 failed OpenAlex queries and records no model calls.
The dedicated wave now has 57/57 completed queries, 38 at their result cap, with arXiv still returning
zero for all nineteen exact-phrase searches. Resume admits eleven new candidate identities, making
thirteen in this wave and thirty-four across the project. The cumulative discovery-population log
contains 950 observations, sixteen admitted observations (including repeats), and 809 distinct
candidate identities. These are metadata counts, not independent studies or relevance precision.
The earlier round's eight failed queries remain outside this recovery and still block cumulative
admission finality. Search-depth, bibliography and excluded-copy identity investigation remain pending.

The new wave contains ten ACA and three WP candidates. The BERT/financial-sentiment title merits
full-text investigation; several other titles clearly concern different topics. Title inspection
neither adjudicates applicability nor validates the identity/version of an API-supplied PDF URL.
Acquisition and document inspection must precede new model spending. Current cumulative availability
is 19/34; ACA is 2/12 and WP 11/16, both below the unchanged class floor. Admitted irrelevant candidates
are not removed from the acquisition denominator after observing the search. Keep the population and
failures; any future population or relevance-admission instrument is a separately measured revision.

Preparing the bounded acquisition exposes a concrete preview defect. `acquire --round <new-wave>
--limit 13 --no-apis --dry-run` prints all 34 candidates, including nineteen already obtained and two
unrelated old-round candidates. Execution already applies scope, retry, OA/manifest filters and the
attempt cap. Extract its existing selection into `acquire.eligible_candidates` and use that same
function for both execution and preview. No eligibility, retry TTL, floor, source class, fetch/gate
version or resolver rule changes. The real corrected preview prints exactly thirteen new candidates
and performs no request with --no-apis. Do not interpret default --dry-run as network-free: resolver
metadata APIs remain enabled unless --no-apis is supplied.

Two regression cases compare CLI preview against actual acquisition with fake PDF responses,
combining round, manifest, OA and limit filters with completed work, recent transient failures and
terminal failures. The second explicitly authorizes a terminal retry in a named campaign. They also
verify unchanged files during offline preview. All 34 acquisition/CLI tests pass. No production bytes,
requests or scientific answers are generated by this preparation. The next authorized host step is
bounded acquisition of the thirteen candidates, followed by normalization and scope/cumulative reports.
The operator explicitly chooses continued manual calibration/debug; no full workflow orchestrator is
implemented by this change, and prior calibration budget accounting remains unchanged.

Post-change verification: 1,057 tests pass, seven skip and the same four dashboard fixtures cannot
open sockets in this sandbox. All 34 acquisition/CLI tests pass, six project configurations validate,
all 19 scientific instrument versions are acknowledged and `git diff --check` passes. The private
acquisition plan freezes the thirteen candidate rows and the unchanged registry before host execution.

## D68 — Audit question eligibility before preparing a new corpus, without fitting acquisition

Date: 2026-09-29 · All 19 production instrument versions unchanged

The operator identifies a distinction the URL-based population does not implement: discovery
relevance must precede the denominator used for acquisition, while relevant unavailable works
must remain in that denominator. D54 still forbids changing old round membership after outcomes.
The remedy is a dated, separately scoped selection protocol, not filtering an existing report
until it reaches its floor. D65's unknown literature recall remains unknown after screening.

The latest update obtains and confirms three of thirteen works, while ten publisher locations
fail through 403 or a redirected host's local budget. Manual full-text inspection finds a wrong
DOI attached to one actual downloaded work, already present in the saved upstream API response.
Independent archive/publisher records establish the distinct works and canonical identity.
The other new PDFs address a mismatching source/horizon or model-training data supply. Readable
document confirmation therefore does not establish identity or question relevance.

`tools/audit_source_selection.py` checks a frozen inventory and project inputs against a dated
manual screening protocol. Generic criterion dimensions exclude download success and result
direction. Assessments identify their reader, reason, criterion and evidence locator; INCLUDE,
EXCLUDE and UNCERTAIN remain distinct. Identity conflicts and unknown identity remain pending.
Corrections retain original identities, explicitly describe canonical metadata and never merge
colliding keys. The audit embeds the protocol and assessments, so immutable prior snapshots
preserve decisions as working files evolve. It does not verify scientific reasoning or evidence
locators automatically, classify sources, import a new production cohort, apply an identity
correction to stage-owned ledgers, compute an acquisition percentage, or write profiles.

The supervised development inventory contains 830 distinct candidate identities: 809 from the
dedicated discovery observations, including metadata exclusions, plus held identities not present
there. This is not 830 independent studies or a measured literature denominator. Initial eleven
assessments admit two direct-question sources and exclude nine contextual/unrelated sources.
Subsequent publisher metadata/abstract inspection screens all ten refused publisher works as
outside the selected question, independently of their failed acquisition. The resulting snapshot
contains 21 assessments: two included, nineteen excluded from this direct-effect cohort, and
809 pending. Methodological context remains available separately; it is not deleted.

Publisher pages for the blocked works advertise complimentary PDFs, so the historical HTTP
PAYWALL_403 classification must not be read as proof of paid-only access. Actual acquisition
failure remains recorded. No retry, model call, original-byte rewrite, floor revision or scientific
signature occurs. The new cohort is not closed, the original rates stay unchanged, and acquisition,
screening accuracy and literature recall are not substituted for one another.

The public preparatory contract is `docs/contracts/source_selection.md`; private protocol and
immutable snapshots are under the research store's `audits/source-selection/`. Screening still
needs inspection of unresolved metadata, duplicate/version relationships and prospective error
measurement before automated classification and production admission. A low-cost metadata screen
may reduce unnecessary acquisition work; this development inventory cannot certify its accuracy.

Seven focused tests cover pending/uncertain cases, immutable read-only preparation, frozen-input
drift, evidence/criterion requirements, acquisition-independent selection dimensions, explicit
canonical correction, refusal of duplicate corrected identities and nonempty closed cohorts.

Post-change verification: 1,070 tests pass, seven skip and the four existing dashboard fixtures
remain socket-denied in this sandbox. Seven new selection tests pass. Six project configurations
validate, all 19 production instruments are acknowledged and `git diff --check` passes.

## D69 — Cloud screening remains an isolated, budgeted experiment (2026-09-29)

The operator requested that Ollama Cloud screen the large L02 metadata inventory so interactive
agent effort can focus on implementation and calibration. The current inventory contains 830
candidate identities, 34 assessed and 796 unassessed, but the 796 have no cached abstracts:
OpenAlex discovery deliberately selected title, DOI, year and primary location. Sending titles
alone as if they were abstracts would produce apparent progress without evidence of relevance.

`tools/run_source_screening.py` declares screening_version 1 and uses experimental JSONL requests/results and the existing
`ollama-cloud` runner; it never writes production screening, extraction, review or admission.
A frozen 20-case development packet (current cloud-pilot-v2 plan, superseding a prepared-only v1 request format to carry source class) uses held source passages, with its prior agent assessments
stored separately from model prompts. Two distinct readers see identical inputs. The prompt
forces an explicit uncertainty option, the response schema restricts labels, and local checks
require a stated criterion, nonempty reason and exact supplied-text quote for an inclusion or
exclusion recommendation. These mechanical checks do not validate the semantic decision.

The existing USD 10 calibration ceiling and its USD 0.74725316 previously accounted amount
are carried forward. The 40-call pilot's conservative first-attempt reservation is USD
0.9128; execution stops before a call when its full reservation cannot fit. Every physical
attempt, including failed or unpriced attempts, remains in the append-only experimental ledger.
At implementation time, twelve focused tests pass for reference isolation, two-reader resume,
quote/missing-text gates, unknown-cost reservation, frozen input drift, queue tampering, store
isolation, and budget refusal. No cloud calls have run in this decision; there is no measured
screening accuracy, model winner or authorized automatic adoption. The shell sandbox refuses
network sockets, so the prepared pilot must run from the operator's network-capable host.
The original corpus, denominator, registry, floor, instrument assignments and past bytes are
unchanged. A separate recorded metadata fetch is still needed before full-inventory screening.

## D70 — First cloud screening pilot exposes semantic false inclusions (2026-09-29)

The operator executed the frozen D69 plan. All 40 cloud calls returned parseable schemas. At the
plan rates, this run cost USD 0.0875178; cumulative priced spending is USD 0.36409896, and
cumulative budget-accounted spending including earlier unknown-attempt reserves is USD 0.83477096
of the unchanged USD 10 calibration ceiling. The audit is
`store/source-screening-pilots/v1/alembic-s4-lungo/audits/screening/9c74eaf11ef0d065b1266bb634297fb5d4674615070a9d846a0ec34ae23083f7.json`.

DeepSeek supplied 20/20 mechanically valid recommendations and agreed with the development
reference on 13/20. Kimi supplied 17/20 valid recommendations, agreed on 11/17 valid cases,
and spliced or altered three evidence quotes, which the exact-substring gate rejected. These
are development-reference comparisons, not held-out accuracy estimates or human gold. The
experiment status is `AWAITING_VALID_SCREENING`; it wrote zero production screening rows.

The most consequential error is shared: both readers included *Stock Price Reaction to News and
No-News* as direct evidence for textual news sentiment, although the supplied study uses news
incidence and price reactions rather than a sentiment measure extracted from text. DeepSeek
also included *Bad News Travels Slowly* despite its own reason acknowledging that textual
sentiment is not measured. Kimi's exclusion of that work had an invalid quote. On *Lazy Prices*,
the readers disagree about whether tone in 10-K/10-Q filings fits the project's news exposure;
the development reference leaves it uncertain. This boundary is a protocol decision, not a
model vote. The pilot therefore does not justify unattended screening of the 796 metadata-only
records. Next calibration needs explicit evidence for the measured exposure and tested return
horizon, independent human reference cases, and recorded abstracts/full text where missing.

The same review found that `round_state` described two discovery channels as making literature
completeness estimable by capture-recapture, contradicting D10 and D65. The dashboard wording is
corrected to say completeness remains unknown; this changes no scientific instrument or ledger.

## D71 — Separate evidence spans and bounded abstract hydration (2026-09-29)

D70 measured one shared false inclusion, another by DeepSeek, and three non-verbatim Kimi
quotations. The experimental
screening_version 2 supersedes screening_version 1 for subsequent development comparisons.
Version 1 remains replayable with its original prompt,
schema and request identities. Version 2 asks for separate exact source spans identifying the
measured exposure and tested future-outcome horizon when the project criteria declare those
dimensions. Missing or non-verbatim spans invalidate an INCLUDE recommendation. This is a
traceability gate, **not** a semantic proof: a model can still quote real words and misinterpret
them. It writes no production decision, and no reader is adopted from the development reference.

The 796 unassessed records lack cached abstracts. `tools/fetch_screening_abstracts.py` prepares a
named, frozen ten-record lookup batch with an offline preview. Execution uses the project's
recorded HTTP transport, preserves raw payload bytes and every outcome, and appends a separate
metadata ledger. It checks candidate DOI and normalized title against the returned work before
making an abstract available; missing or conflicting metadata remain pending. Requests already
attempted in the same campaign are not repeated. The batch has only been previewed: ten pending,
zero network requests, zero model calls. It cannot establish recall or close source selection.
The operator chose media/newswire news only for L02 direct evidence; 10-K/10-Q filing tone stays
context. The dated selection-scope v2 records that answer without altering the question registry
or the already frozen v1 protocol. A seven-case v2 development regression is prepared under
`store/alembic-s4-lungo/audits/source-selection/l02-v2/cloud-regression-v1/plan.json`, with
USD 0.31948 reserved for its first 14 calls under the existing ceiling. Its reference is still
post-selected development material and no call has run. An independent human reference on new
cases remains necessary before any scaled screening run.

## D72 — Resume independent screening cases after a terminal format error (2026-09-29)

The operator ran D71's first ten OpenAlex metadata lookups. Four abstracts passed DOI/title
identity checks; six valid work responses supplied no abstract. All ten raw responses and
outcomes are preserved. `NO_ABSTRACT` is missing metadata, not an exclusion. A six-DOI Crossref
fallback is now prepared under
`store/alembic-s4-lungo/audits/source-selection/l02-v1/abstract-crossref-v1-plan.json`.
Its frozen keys require the recorded OpenAlex `NO_ABSTRACT` outcome. Offline preview shows six
pending, zero requests. No Crossref call has run in this decision.

The operator also started the seven-case screening_version 2 regression. DeepSeek's first two
INCLUDE outputs passed mechanical validation and matched the development reference. The third
response selected UNCERTAIN but omitted both newly required quote fields. The schema gate
correctly recorded `SCHEMA_INVALID` and the original bytes; no output was adopted. Execution
stopped after three of fourteen planned reader attempts. The new run is USD 0.0031386 at plan
rates, bringing cumulative accounted spending to USD 0.83790956 under the existing USD 10
ceiling. One of the valid INCLUDE outputs used a generic news-dataset sentence as its exposure
span; that span is exact but does not alone prove that sentiment was measured. The semantic
selection risk from D70 therefore remains.

The experimental driver now processes each frozen case independently. A terminal NOT_JSON or
SCHEMA_INVALID answer remains unanswered for that reader and is never retried automatically,
while subsequent cases and the second reader continue. Other stop reasons, including budget,
usage and transport failures, still stop execution. The instrument prompt/schema and v2 plan
are unchanged, as are the first three physical result rows. One focused regression test verifies
both reader completion and non-retry after an omitted-field response. Rerunning the same v2 plan
on the host resumes its remaining attempts; final model quality is not yet measured.

## D73 — Finished v2 regression rejects automatic screening; prepare independent reference (2026-09-29)

The operator completed both D72 host commands. Crossref supplied two additional identity-checked
abstracts, leaving four of the first ten metadata records without abstracts after both provider
lookups. These four remain pending for a legal authoritative copy or another recorded source;
they are not excluded. The six available abstracts do not represent the remaining inventory.

The completed seven-case screening_version 2 development regression cost USD 0.03971895 in total
at plan rates, including the earlier three attempts; cumulative budget-accounted spending is
USD 0.87448991 of the same USD 10 ceiling. DeepSeek had three mechanically valid answers,
four schema-invalid answers, and two of three valid labels matched the development reference.
Kimi had five schema-valid outputs, one of which failed the exact quote gate, leaving four
valid answers; two of four matched the development reference. DeepSeek again INCLUDED *Stock
Price Reaction to News and No-News*, using “at least one news story” as its exposure quote.
That text establishes news incidence, not sentiment measured from news text, and violates the
operator's E1 boundary. This is a measured semantic false inclusion despite exact quote checks.
No production selection row was written and neither reader is adopted.

The format failures are specific: DeepSeek omitted the two quote fields on three responses and
added an undeclared field on another; Kimi omitted `missing_information` on two. The experimental
screening_version 3 prompt now states explicitly that every schema field must appear for every
decision, with empty strings where appropriate, and warns that news incidence is not sentiment
measurement. It keeps versions 1 and 2 replayable and changes call identities. **No v3 model
result has been measured.** It is not a scientific fix until tested on new cases.

A new blind metadata plan selects twenty previously unassessed candidate identities from the
remaining queue: ten in existing priority order and ten by a fixed SHA-256 ordering, after
excluding the first ten lookups and normalized titles of all twenty development cases. The
plan freezes the queue and project inputs and has zero model calls. The unlabeled human packet
builder retains exact abstract text, provider and payload digest, or marks the abstract missing;
it supplies no model answer or agent reference label. This packet is preparation for an
independent human reference, not a held-out accuracy result yet. Further paid model comparison
waits for that reference rather than repeating prompt edits against the same seven cases.

## D74 — Held-out metadata acquired; missing abstracts remain pending (2026-09-30)

The operator ran the frozen twenty-key OpenAlex metadata plan. All twenty recorded requests
completed: thirteen supplied title/DOI-checked abstracts and seven returned `NO_ABSTRACT`.
`NO_ABSTRACT` is missing metadata, not an eligibility decision. The unlabeled human-reference
packet was written under `l02-v2/human-reference-packets/`; it contains the thirteen exact
abstracts with provider and raw-payload hashes and marks seven cases `metadata_only` with blank
human decisions. No model was called and no production selection decision was written.

A seven-DOI Crossref fallback is frozen in `l02-v2/heldout-crossref-v1-plan.json`. It requires
each key to have the prior OpenAlex `NO_ABSTRACT` outcome, uses a new named campaign, and
caps requests at seven. Its offline preview selected exactly seven pending keys with no
unresolvable target. The operator subsequently ran all seven recorded Crossref requests;
each returned an identity-checked abstract. Rebuilding the packet produced twenty available
abstracts, zero missing, with thirteen from OpenAlex and seven from Crossref. The original
thirteen-abstract packet remains intact beside the new content-addressed packet and its
unlabeled human review sheet. All twenty human decisions remain blank. An independent person
must assess them before any held-out model score or production adoption claim.

## D75 — Audit bibliographic relationships without merging candidates (2026-10-03)

The L02 selection inventory has 830 candidate keys, but those are not 830 independent
studies. An offline exact-title pass finds 61 nonempty groups with more than one key. They
include plausible preprint/journal versions and also unrelated records with the same short
title. A title-only merge would therefore silently alter the selection denominator.

`tools/audit_identity_relationships.py` reuses the frozen manual-selection validation and
records those groups as `REVIEW_REQUIRED`, along with appendix/supplement title leads and
the acquisitions touched by already assessed identity corrections. Its first immutable
report is under `store/alembic-s4-lungo/audits/source-selection/l02-v1/identity-audits/`.
It finds one assessed DOI correction, one acquired PDF still indexed by its original wrong
key, zero different-key pairs with identical acquired bytes, and one possible appendix parent
in the inventory. The correction is the already
documented Balahur/Tavares conflict; the report does not create a second independent
scientific judgment. The appendix and its parent carry separate DOI keys and are not
counted as a verified study relationship from title matching alone.

The source PDF's first page names Balahur and coauthors and “Sentiment Analysis in the
News”; the historical acquisition remains under Tavares's DOI. The original bytes and
all stage ledgers stay intact. The relationship audit makes zero merges, zero network or
model calls and no new production admission rule. Version, supplement and copy status
still require per-work evidence before any cohort closes. Its scope is preparatory, so
none of the production instrument versions changes.

## D76 — Verify held-copy identities while preserving unproven version links (2026-10-03)

D75's equal-title queue includes three keys for “News versus Sentiment” and two for
“Which News Moves Stock Prices”. Local first-page inspection finds two definite work
links. The Federal Reserve PDF held under the title-based `ACA001` key prints Heston,
Sinha, FEDS 2016-048 and DOI `10.17016/FEDS.2016.048`; the DOI candidate describes
that work. The NBER PDF held under title-based `ACA002` prints Working Paper 18725,
matching DOI key `10.3386/w18725`. Its January 2012 cover conflicts with the inventory's
2013 year, so the date discrepancy remains recorded rather than normalized away.

The 2013 SSRN “News versus Sentiment” DOI shares title and authors with FEDS 2016-048,
but neither local metadata record establishes that its text and results are the same;
it is a pending possible version. Crossref records for the pollution-news paper and a
separate “Online Appendix” DOI share the first two authors and the parent title, but
their relation fields are empty and no appendix text has been inspected; that link is
pending. Four located assessments, two verified work mappings and two pending leads,
are frozen in the new identity audit. No title-derived work merge is performed.

The `--relationships` option validates original keys, pair uniqueness, certainty labels,
reason and provenance before embedding the assessments and their input hash in the
content-addressed report. It does not independently check scientific or bibliographic
truth, transfer acquisitions, close L02 selection, change a denominator or spend on
network/model calls. The 20-case blinded human reference remains unlabelled.

## D77 — Route declared PMC articles to JATS without claiming an acquisition gain (2026-10-03)

D53 implemented the local parser but left the acquisition route unmeasured. Europe PMC's
documented `/{id}/fullTextXML` endpoint serves the open-access subset, not every PMC
article. Gate version 4 checks XML as a JATS article with front/article-meta/body,
minimum body text and the declared reference-list policy; a large XML error response
cannot pass as HTML full text. Unsupported JATS tables can still pass acquisition and
remain awaiting at stage 3, which records the parser limitation honestly.

For an explicit PMC article URL, the resolver proposes Europe PMC XML ahead of the PMC
HTML location, retaining the latter as fallback. The existing Fetcher applies robots,
timeouts, redirects, excluded hosts and failure budgets; `RecordingFetcher` logs its
outcomes. An XML article's declared licence URL is retained if present, and `null`
remains an unknown licence rather than an inferred Creative Commons grant. The gate
records `gate_version 4` on new rows; historical gate-3 rates are not recast.

A separate six-article pilot is frozen from the first six PMC manifest rows, with manifest
and source-policy hashes, a named campaign and offline preview. Its executable path
records requests and parse outcomes without writing acquisitions, documents, chunks or
profiles. Synthetic route/gate/fallback and refusal-resume tests pass; they establish
control flow, not live XML availability or parsing accuracy on publisher articles.
The operator must approve the bounded sweep before execution. Q04's profile and every
production ledger remain untouched.

## D78 — Six recorded Europe PMC requests expose body bibliographies and image tables (2026-10-03)

The operator authorized D77's frozen six-article pilot. Run with
`.venv/bin/python tools/pilot_europe_pmc_jats.py --plan store/pmc-screen-time/audits/europe-pmc/jats-pilot-v1-plan.json --execute`.
All six attempts and their responses were recorded under campaign
`europe-pmc-jats-pilot-2026-10-03-v1`; the pilot wrote no production acquisition,
document, chunk or profile. Two XML requests returned HTTP 200 and four returned
HTTP 500 (`SERVER_ERROR_5XX`). The HTTP 500s establish no absence of open XML;
their existing HTML documents remain confirmed.

The original `gate_version 4` accepted both XML articles. PMC001 could not be
normalized: its three `table-wrap` elements have graphics but no textual JATS
`table`, so dropping them would lose tabular evidence. PMC004 parsed with six
tables but zero references because its 45-entry `ref-list` is inside `body`, not
`back`. The first pilot outcome rows remain immutable.

`jats_parser_version 2` collects primary-article references from both `body` and
`back`, excluding nested articles and keeping references out of body prose.
`gate_version 5` recognizes those same body references for the short-article
reference signal. The declared licence URL can appear on a descendant
`ext-link` inside `license`; acquisition now retains it without inferring rights
from endpoint availability. Versioned gates and parsers mean old outcome figures
are not silently recast.

Reproduce the offline reassessment with
`.venv/bin/python tools/pilot_europe_pmc_jats.py --plan store/pmc-screen-time/audits/europe-pmc/jats-pilot-v1-plan.json --rejudge`.
It hashes and reads only the two retained XML payloads and makes zero requests.
PMC004 now has 45 JATS references and six tables, matching the stored HTML's
45 references and six tables; the JATS body has 35,022 characters against
56,837 in HTML, so character counts are not interchangeable. PMC001 remains
`JATS_UNSUPPORTED`; its XML declares CC BY 4.0. PMC004 declares CC BY 2.0.
Both XML files declare the PMCID in their frozen target URL. This checks the
article identifier, not every title, DOI or scientific attribution. No historical stage row was
rewritten, and this pilot does not establish a six-source acquisition gain.

## D79 — Keep AI screening observations append-only and outside admission (2026-10-05)

The operator asks to make the existing L02 audits usable for automation without
silently selecting a new corpus. The first versioned boundary is deliberately an
**advisory record**: `source_selection_version 1` owns append-only
`source_screening.jsonl` and `source_identity.jsonl`, but admission, candidate
denominators and verdicts do not read these ledgers yet. A content-derived row id
and explicit `supersedes` link make an edited assessment a new fact instead of a
rewrite. All rows retain original candidate keys and explicit source classes;
`UNCLASSIFIED` blocks the inference that a readable copy is automatically ACA.

The frozen L02 import plan hashes its 830-key inventory, 20-case abstract packet,
Claude Code's `AI_PROVISIONAL` output, project inputs, REIT full-text assessment
and extracted PDF text. Its importer verifies each abstract quote against the
packet and each full-text quote against saved text, the metadata and PDF hashes,
and the recorded successful copy campaign. Claude's model and harness version
are preserved; the exact interactive prompt hash is `null`, not invented.
The full-text row supersedes only the REIT abstract row. The title mismatch
between its DOI metadata and held PDF becomes `POSSIBLE_VERSION`, never a
canonical merge.

Reproduce the read-only preview with
`.venv/bin/python tools/import_source_selection.py --plan store/alembic-s4-lungo/audits/source-selection/l02-v2/source-selection-import-2026-10-05/plan.json`.
It shows 20 observed keys in this v2 scope: 15 provisional not-direct, one
provisional sector context (REIT), four provisional uncertain, zero direct
inclusions and 810 inventory keys not observed **in this ledger**. The older
34 agent assessments belong to the earlier protocol and are not mixed into
this count. `--apply` appended 21 screening rows and one identity row; a second
application appended zero. The 14 pre-existing top-level JSONL ledgers retained
their exact SHA-256 hashes; the pre-apply digest list is retained in the private
`source-selection-import-2026-10-05/stage-ledger-baseline.json`. No request,
model call, candidate admission, new
acquisition rate, screening accuracy or literature-recall claim resulted.

The next boundary is not a flag to treat these 15 AI exclusions as truth.
It is a measured selection policy and controlled import of a closed cohort,
after resolving protocol/version relationships and auditing false exclusions.

## D80 — Bind advisory evidence to retained bytes and serialize writers (2026-10-05)

Claude Code's read-only adversarial review supplied four reproducible counterexamples
to D79's first implementation. A packet could substitute invented `source_text`
while retaining a valid raw file hash; frozen text could diverge from the held PDF
and `copy_campaign` was optional; two writers could both replay before either
appended, permanently duplicating an ID; and the append API accepted keys outside
the inventory that preview would later reject. These are integrity failures even
though advisory rows still cannot admit candidates or change verdicts.

The importer now matches each packet abstract to a recorded `ABSTRACT_AVAILABLE`
metadata row and reconstructs it from the retained OpenAlex/Crossref response,
including the provider's title/DOI identity check. It regenerates full text from
the held PDF with `pdftotext -layout` and requires the named campaign to have a
`FULLTEXT_BYTES` outcome for those bytes. Empty PDF titles fail. The append API
requires scope, question and inventory, and holds a project-local `flock` across
both chain replays and appends. Reruns remain idempotent; the L02 frozen plan
still previews zero new rows after the change. Screening transitions now reject
a downgrade from full text to abstract or a registry/class change within one
scope. The record format stays `source_selection_version 1`; stored rows do not
need migration. A quote's scientific interpretation remains outside these checks.

Targeted regression tests cover forged packet text, unmatched PDF text, missing
campaign/outcome, empty title, out-of-inventory append and two competing writers.
The existing 14 production-stage ledgers remain outside this importer. A changed
AI output still needs an explicit supersession plan; it is not automatically
adopted when its input hash changes.

## D81 — Separate identity counterparts and require pinned rescreen links (2026-10-05)

The D80 review also exposed two workflow limits. The first identity view keyed
only by candidate, so a second possible relationship could hide the first.
The first importer could not replace an abstract after a new AI file was frozen:
its generated row always used `supersedes: null`, and the ledger correctly
rejected it. A naive replacement could also lower the REIT's PDF-backed
assessment to a new abstract.

`identity_relation_version 2` adds an explicit `related_kind` and `related_key`.
The current REIT v1 record replays as a relation to its held `copy_sha256`;
new candidate or copy relations get independent chains. The preview counts
current relationships, rather than collapsing them by subject candidate.
No candidate identities or old rows are rewritten, and a relationship still
does not merge works or transfer copy/claim evidence.

`source_selection_import_version 2` adds a frozen replacement map: every
abstract row names the current assessment ID it supersedes, and the REIT PDF
row is explicitly preserved by ID. Stale links, a changed REIT AI decision,
an unchanged AI file or a proposal to downgrade that full-text row fail.
The importer still checks original metadata responses, PDF bytes and campaign
provenance. A test batch with two abstract cases and one later PDF override
appended one replacement, zero identity rows and zero on rerun; a stale map
failed. The old version-1 plan still previews 20 observed keys and zero new
rows. These tests establish ledger behavior, not AI screening accuracy.

## D82 — A read-only multi-flow portal over scoped reads (2026-10-06)

The dashboard spec (`2026-09-22-dashboard-design.md`) said "no multi-project
view. One `serve` per project" (§13). This decision supersedes that clause for
the portal: `claimstone portal` serves every project under `--projects-dir`
over one loopback server. §1 and §8 rule 7 still hold — the portal is
read-only, GET is its only verb, no button starts work — and any mutating
route requires a later decision. The review that constrained this is
`2026-10-06-research-portal-review.md` (findings F1–F22); the implementation
spec is `2026-10-06-research-portal-implementation-spec.md`.

What the portal stands on is P0's scope work, because a multi-round project
made the dashboard's figures wrong before it: `round_state` counted claims,
reviews, chunks and confirmations across every round under a round-named
selector (F1), discover's selector disagreed with admission's `or "routine"`
variant (F3), and a damaged ledger rendered as zero acquired (F2). The
canonical selector now lives in `claimstone/scope.py`
(**scope_version 1**); the scope defects are demonstrated by
`test_round_state_claims_do_not_leak_between_rounds`,
`test_round_state_review_and_chunks_scoped`,
`test_scoped_activity_and_last_write_exclude_other_round`,
`test_round_less_candidate_is_not_routine` and
`test_corrupt_acquisitions_is_an_error_not_zero` in `tests/test_scope.py` and
`tests/test_round_state.py`.

A round's protocol is bound by a flow ledger
(`docs/contracts/flows.md`, **flow_version 1**): `flow_id` hashes the binding
alone, the binding is compared against the live project and never supplies a
value to a computation (F4), and drift is a named state. Exports
(`docs/contracts/exports.md`, **export_version 1**) freeze every ledger at its
last newline and verify by prefix plus recomputation, because no stage writer
shares the flows lock (F5).

`admissibility` still reads document confirmations and `ledger_repairs`
project-wide. That is disclosed in the portal's floor panel and in every
export's report, and deliberately **not** changed here: scoping it is an
`admission_version` decision that needs its own measured entry.

Measured page time for `/p/pmc-screen-time/legacy/pmc-oa-v1/` on this machine, one GET against
loopback with `curl -s -o /dev/null -w '%{time_total}'`. The first implementation took **15.43 s**
(repeat runs: 15.38 s and 15.66 s). The 2026-10-06 implementation review
(`2026-10-06-research-portal-implementation-review.md`) found the reason was not "re-read from disk
on every request". Under `cProfile` one flow page ran:

- `synthesize.verdicts` five times;
- `round_state.state` three times;
- `claim_records.current` sixteen times.

After the review, one `portal_state.compute` per selector per request shares those readings with
every panel, and `round_state.state` accepts the request's own `verdicts` result through
`precomputed_verdicts`. The same page now takes **3.89–4.05 s**. That is the identical computation
on the identical ledgers, so it is not a cache, and nothing outlives the request.

The index and `/inbox` compute every selector of every project, and take **28.9 s** and **29.1 s**
against the real store. That cost is known and recorded, not hidden. A per-project API that the
page loads lazily is the remedy (frontend design, 2026-10-06).

The same review found that `pmc-screen-time`'s current profiles, Q04 included, are recorded under
the **whole-store** selector (`round: null`). The first portal listed only candidate rounds, so it
never showed the one profile awaiting a person. `/p/<project>/legacy/-/` now shows it, together with
its adjudication card. That card carries the hash in `HANDOFF.md`
(`9340389c9aac29b77e901c20e27434d211fe9e7825a68d99995d8c6fa5b20fdd`).

Explicitly not built, each blocked by a named finding: intake, offers and
purchase decisions (F14, the operator's policy on operator-supplied copies),
jobs and subprocess execution (F11, code identity), locking across stage
writers (F5), a persistent per-host failure budget (F6), a non-global-address
URL guard on every redirect hop (F15), and authenticated signing (F16, a
`decision_contract_version` bump). P3 and P4 in the implementation spec's §10
are the reviewed specs those need.

## D83 — Declare an L02 university-host population before its copy checks (2026-10-06)

`source_selection_import_version 3` adds archived-population replay; plan
versions 1 and 2 remain readable and their observation format is unchanged.

The operator authorized a dated new L02 repository round. Offline inspection
of eleven works lacking abstracts from both checked providers found 52 cached
location URLs, none on the exact v1 host list. Two host candidates can be named
without a request or an outcome-dependent choice: retained OpenAlex payloads
give a Southampton ePrints landing page for a work with Southampton-affiliated
authors, and a Hannover university working-paper PDF for its Hannover-affiliated
author. UCD/ANU leads use `hdl.handle.net`, whose final host remains unknown;
BBVA's author/institution-copy eligibility is not established. Those three
routes are not added by inference.

`sources.yaml.population` is version 2, declared 2026-10-06. It preserves the
v1 host/API predicates and adds only `eprints.soton.ac.uk` and
`diskussionspapiere.wiwi.uni-hannover.de`. The new, empty round
`s4-l02-repository-copies-2026-10-06-v2` holds policy digest
`f53ed0699c770079d9d97e7992d661b14fb8448dd0600ba1ae3966a58d0b43ed`.
V1 project bytes were saved with SHA-256
`97cea1ebe253343d8c864833b3ecf85d3a2130bccc6706c8219b7d2fb5e4c59d`;
the new bytes hash to
`abb07e2fa08175ae557ec2416148008a5b64fba73a6579871698131767ffbb72`.
Old rounds retain their frozen predicates and candidate denominators. The old
selection and copy plans replay against the exact archived v1 bytes; changing
classes, floor or registry does not qualify as a population-only replay.

A host in this selector matches the discovery candidate's URL, not a copy URL
found later. All four inspected DOI-keyed candidates had `doi.org` discovery
URLs and were excluded in v1; the two newly listed copy hosts alone do not
import them into v2. Controlled candidate intake and copy identity remain
separate work. The new round currently has zero candidates, zero requests,
zero admitted sources and no acquisition rate.

The next network action is frozen in a two-target plan, SHA-256
`07f1176800b6fc940dfe78aa0a386dcc4ccbf125b1d2e002613527a9f0e9d72f`.
It is an isolated copy inspection with exact host checks, at most five physical
page/copy transfers and four robots transfers. Its offline preview shows two
pending targets and no writes. Operator approval of this specific campaign is
required by `AGENTS.md` before execution. No source-selection protocol,
floor, registry, acquisition or verdict changed here.

## D84 — A typed React frontend over a read-only JSON API, packaged as containers (2026-10-06)

The operator retired server-rendered Python HTML for the portal's new views and asked for a
real frontend, packaged with Docker Compose. Two measurements decided the shape:

- **Index time.** The stdlib portal's index and inbox take 28.9 s and 29.1 s on the real store
  (D82), because one request computes every selector of every project. The new
  `claimstone api` (`portal_api_version 1`) answers the project list without any `compute()`.
  The frontend then loads each selector's summary lazily: the first one arrives in 0.6 s, and
  all ten take 31.8 s with a peak of 1024 MB RSS in one API process.
- **The kit, not the framework.** The same flow page was rendered six ways on a design canvas,
  three visual directions and three component kits. shadcn-svelte and shadcn/ui render the
  same. The operator chose **React + shadcn/ui + Tremor**, for Tremor's dashboard components
  (tracker, category bar, bar list, donut). The chosen board is
  `docs/design/portal/flow-overview-react-tremor.html`. The SvelteKit build of S4–S5 is
  superseded; the API, schema, fixtures and transport were kept.

What holds the invariants on screen:

- **No meaning is derived in the browser.** Every chart is fed by a field the API returns. The
  reviews of R1 and R4 found two such derivations to correct server-side:
  `question_state_counts` and the per-row `display_state` share one function, so an unfinished
  reading is never headed NO_VERIFIED_CLAIM, and a question without a profile is never
  "awaiting a person". Source states read "not obtained", never "refused".
- **The signing command comes from the server.** `adjudication_card` is decided in one place,
  for the inbox and the question page. A client-built command once proposed signatures
  `adjudicate` refuses.
- **CSP.** A Vite build has no inline script, so nginx sends a strict header
  (`script-src 'self'; style-src 'self'`). `scripts/check-csp.mjs` fails the build on an inline
  script or style attribute, and test F10 bans injected `<style>`. Zero console violations were
  observed on the real store behind nginx.
- **Dependencies.** The shadcn CLI had entered `package.json`. Its stylesheet is now vendored,
  which took the production tree from 434 to 133 packages. Tremor Raw components are copied in
  (Apache-2.0); shadcn components are copied by its CLI run with `npx`.

Packaging (`compose.yaml`, `./portal.sh`):

- **`api`** runs from the same `claimstone:local` image as the stage job (D42: one code
  identity) and records `CLAIMSTONE_CODE_REVISION` at build time. It mounts `store/` and
  `projects/` **read-only**: a write attempt fails with "Read-only file system", verified. It
  sits on an internal network with no egress: a request to example.org fails, verified. It
  receives no secret: compose substitutes the word `present` for each configured key
  (`${VAR:+present}`), which is all the administration page shows. Memory is limited to 2 GB.
- **`web`** is nginx-unprivileged, pinned by digest like GROBID. It serves the SPA and proxies
  `/api/` with the one Host the API allows. It answers 421 to any other Host and 403 to non-GET,
  both verified, and it is the only published port, on `127.0.0.1`.
- **The `web` image build re-runs the gates:** contract freshness (`api-types.ts` against the
  committed schema), typecheck, tests, build and the CSP check.

This is consistent with `compose.yaml`'s refusal of a service per stage: the API is a read model
that writes nothing; every stage still runs as the `claimstone` CLI job and writes through files.
Node and npm exist only in the frontend image, behind a process boundary (D7); the Python engine
gains no dependency. `claimstone portal` and `claimstone serve` remain available. Nothing here
writes, signs or starts work. Intake, offers, jobs and signing remain P3/P4.

## D85 — Retain repository copy outcomes separately from population and DOI identity (2026-10-06)

The operator approved and the agent ran D83's frozen two-target plan. The
recorded campaign used three physical page/copy transfers and two robots
transfers, within the five/four ceilings, with no source adoption. Hannover
returned a PDF, SHA-256
`a1ff57d0107ab97ed5dec497ec313147561ccc04460ea9b7e052358021896385`.
Its cover identifies a November 2008 Discussion Paper No. 407 by Maik
Schmeling. Cached DOI metadata describes a 2009 publication with matching
title and author. This supports only `POSSIBLE_VERSION` until the publication
relationship is independently checked. The PDF abstract uses consumer
confidence as the exposure and forecasts aggregate country stock returns;
its full-text L02 screening is `AI_PROVISIONAL EXCLUDE`, not a scientific
admission decision. The targeted offline tool verifies raw bytes and quotes
before appending one screening and one identity observation; replay wrote
zero rows.

Southampton redirected on the same approved host and returned a retained HTML
record, SHA-256
`4a3e4a854c17fafca39c33d835c5f2d171980be9efa020da74a73ef12da5e74b`.
It says, “This record has no associated files available for download.” The
campaign ledger's generic `PDF_LINK_REVIEW_REQUIRED` status is preserved;
the separate content-addressed readout records the narrower offline finding
`NO_REPOSITORY_FILE_DECLARED`. The cached UCD handle for that DOI has an
unknown final host, so no request to it belongs to this campaign.

The new population round still has zero candidates. The old L02 advisory
scope now has 48 observed and 782 unobserved keys of 830, three provisional
direct candidates and six uncertain, zero admitted, and an open cohort.
These measurements do not establish a population acquisition rate or a
scientific result. The private readout is
`audits/source-selection/l02-v2/repository-copy-check-2026-10-06/readout-201241852336d5c697a07d7631b5257959048864038ce4c4bf8bb587d02acb94.json`.

## D86 — Begin scheduler work with a read-only flow preview (2026-10-06)

`scheduler_preview_version 1` derives one flow's proposed next work from the
same `portal_state.inbox_cards` and `round_state` readings as the portal. It
does not invent a second rule for admission, readiness or signing. The command
is `claimstone scheduler-preview PROJECT FLOW_ID [--store DIR]`. It reads
without recording registry state, creates no operation or network request, and
marks every proposal as unauthorized. Protocol drift, registry drift, damaged
ledgers, torn tails and a flow bound after data existed are explicit blockers.

Measured against the existing L02 university-repository flow
`ec6025eff94d39c25429eccc072decdeda5c2aa3ae59330abed12cb42e987700`,
the preview finds zero candidates in the new round and proposes discovery or
controlled intake. It says `EMPTY_NOT_A_CLOSED_COHORT` and withholds a floor
evaluation, even though the admission engine's raw zero-candidate object
reports `final: true` with a null rate. That raw flag does not establish cohort
closure or a scientific result. Tests in `tests/test_scheduler_preview.py` cover no writes,
cross-round candidate isolation, late binding, damaged acquisitions and
protocol drift. The schema is versioned because this is an operator-visible
interpretation of the next action.

The next implementation boundary is the append-only operation contract in
`docs/contracts/scheduler_operations.md`. It defines plan, authorization,
unit and lease events before an executor can use them. Execution still needs
the project-wide writer lock, persistent host budget, redirect guard and
round-scoped stage builders named in P3/P4. This entry does not authorize any
campaign or model spending.

## D87 — Serialize project writers and carry host refusals across restarts (2026-10-07)

`Store.writer_lock` uses one `.writer.lock` per project and is reentrant within
one thread. Flow and source-selection transactions use it; every Store append,
tail repair and content-addressed write uses it too. Mutating CLI commands hold
the lock across their read-modify-write stage. This is a conservative
serialization boundary for the existing CLI; a scheduler worker can narrow it
to one unit after the operation ledger exists. Existing `.flows.lock` and
`.source_selection.lock` are no longer acquired by those writers.

`fetch_version 4` reconstructs the recent host failure budget from physical
`transport` and `robots` events in `requests.jsonl` when `RecordingFetcher`
binds the transport to a project. Summary rows are ignored so one request
cannot count twice. A restart therefore sees the same 403, 429, 5xx, timeout
and connection failures within the configured TTL. The in-memory budget still
applies to unbound test and compatibility fetchers. The restart regression
records one timeout, constructs a new fetcher and verifies that it makes zero
further physical requests when the budget is one. This changes request
conduct, not the content gate or scientific denominator. Historical rows
remain under their recorded fetch version.

## D88 — Bind population before discovery and execute scoped offline plans (2026-10-07)

`flow_version 2` declares a configured population when a new, empty round is
bound. Previously a flow created before discovery stored a null population
digest, and the first discovery run declared the population and made that
flow appear drifted. Existing flows retain their recorded identity; no ledger
row is rewritten.

`scheduler_preview_version 2` describes extract and review as scoped offline
stage plans now that normalize, extract-build and review-build accept a shared
`Selector`. The code paths use `scope.source_ids` and leave other round sources
out of their work units. This changes queue construction for explicitly
scoped calls, not the claim gate, review verdict or admission rule.

`operations_version 1` introduces a bounded operation: plan,
OS-account authorization, started and completed/failed events in
`operations.jsonl`. Plans hash the flow binding, exact input ledger bytes,
the complete `claimstone/` Python package, stage and batch. Execution checks
the frozen inputs and holds the
project writer lock through the stage. An interrupted stage can resume from
the existing append-only stage rows; a completed operation returns its stored
result without repeating work. Local `llamacpp` drain plans freeze a named
batch, model, harness and at most N never-attempted call ids; each result is
recorded before its operation unit completes, so a crash can reconcile the
result without calling the model twice. A batch containing sources outside
the flow is refused. These plans allow zero external network requests and
zero metered spend. Tests prove a changed input refuses an already
authorized plan and a repeated completed execution appends no duplicate
events. No scientific verdict is created by these operations.

## D89 — A separate authenticated control service for portal writes (2026-10-07)

The v2.1 portal design (`docs/design/portal/v2/README.md`, §7) names the
controls that need backend work; the review
(`2026-10-06-research-portal-review.md`) named the defects that blocked them.
This decision authorizes a **write boundary** and records its shape; the
implementation spec is `2026-10-07-portal-backend-spec.md` (steps B0–B13), and
the progress log is `2026-10-07-portal-backend-progress.md`.

**What stays unchanged from D82/D84:** the read API (`claimstone api`) stays
read-only — GET only, store and projects mounted `:ro`, no secret, no
authentication, no network egress. Nothing in this work adds a write path to
`api.py` or `transport.BaseHandler`. D82's scoped reads and D84's "meaning is
decided on the server" clause both stand.

**Why two processes, not one.** D84 records "the API holds no secret and
mounts the store read-only" as a security property: a defect in a read route
can never write. Writes therefore live in a new, separate process,
`claimstone control` (`claimstone/control.py`), on prefix `/control/v1`,
with the store mounted read-write, an authenticated operator session, and
network egress only for the explicit admin checks and the operator URL
fetch of intake. It reuses `transport.py`'s Host/Origin checks and response
headers; it does not inherit "GET only".

**What the control server never does (spec §1.2):** it never signs for
anyone — a signature carries the authenticated operator, never a typed name;
it never preselects, suggests or defaults a verdict; it never starts network
or paid model work except the two explicit actions named above; it never
decides scientific policy — policies are declared in the project's input
files or recorded by the operator, and the server enforces them; it never
ranks access, intake or purchase items by anything derived from claims,
reviews or stances (F13); and it never runs stage commands — executing work
is the scheduler's job (B12).

**The rules every mutating route obeys (spec §1.3):** a valid session
cookie; CSRF via an `X-CSRF-Token` header plus a present, allowed `Origin`;
`Content-Type: application/json` bodies at most 64 KiB with unknown keys
refused; the project writer lock (B1, closing F5) held while re-reading the
ledgers a decision depends on and appending, with network calls outside the
lock; the live project reloaded and registry drift checked on every request
with `check_registry_drift(..., record=False)` (F9), any drift answering
409 with nothing written; every ledger row carrying `actor`,
`signer_auth: "portal-session"`, a UTC `recorded_at`, the code revision and
a `*_version` integer; optional `Idempotency-Key` semantics; and the read
API's `{"error": {"code", "message"}}` envelope with 401/403/404/409/413/422
as the answer set. The message is the engine's own sentence when there is
one, for example `StaleProfile`'s.

**The operator policies this work enforces but does not choose (spec §3):**
whether supplied copies count toward the floor is declared per project in
`sources.yaml: supplied_copies` and defaults to `separate` (F14); any
authenticated operator may record "bought externally", with `actor`; evidence
of possession is set only by an intake that passes the quarantine checks,
never by hand; PDFs with an unknown licence are excluded from exports and
listed (default excluded).

The scientific instruments this work introduces — the new record types
(drafts, intake, decisions, seen, control-side adjudication shape) and the
control API's payload — are each versioned like an instrument and registered
in `tools/check_instrument_versions.py`, so a bump is recorded, not silent.
B13 completes this entry with the measured test counts. This entry authorizes
no campaign or model spending. The scheduler implementation and remaining
gates are recorded separately in D88 and D90–D92 and
`docs/contracts/scheduler_operations.md`.

## D90 — Bound physical requests and reject non-global destinations (2026-10-07)

`fetch_version 5` adds opt-in exact-host allowlists, a physical request ceiling
that includes robots and redirect hops, and a preflight that rejects literal
or DNS-resolved non-global addresses at every hop. A bounded fetcher pins the
selected public IP in its HTTP transport, sends the original Host header and
verifies TLS against the original hostname. It disables environment proxies,
which could otherwise resolve the URL again. The default fetcher behavior is
unchanged for existing campaigns; a bounded scheduler plan must enable these
guards. Tests establish that localhost and out-of-plan hosts are refused
before a socket call, a zero request ceiling permits no transfer, and the
adapter selects the pinned IP while retaining the original TLS name. Bounded
plans also freeze permitted schemes: an HTTPS destination cannot redirect to
HTTP, and credentials or nonstandard ports are refused before a socket. This
version changes request conduct, not scientific interpretation.

The bounded path records `request_started` before each physical transfer.
After a restart, `RecordingFetcher` counts those rows for the named campaign
so the approved ceiling cannot reset. A start recorded before a crash but
before the socket opens is conservatively charged.

## D91 — One-candidate bounded acquisition operations (2026-10-07)

An `acquire` operation freezes one candidate key and row, the prior attempt,
the flow selector, exact allowed hosts and a maximum number of physical
requests. The plan ID is the campaign name. Local OS authorization records
that exact ceiling before a worker constructs a `fetch_version 5` transport.
The operation disables metadata API discovery, so it only attempts the held
candidate URL and any same-plan redirects or derived routes. Robots and each
redirect hop consume the same ceiling; an unapproved host is refused before
the socket. A 403 remains an access refusal, never evidence of a sale.

If the acquisition row exists after an interruption with the operation's
campaign, the worker reconciles it without another request. If a physical
`request_started` exists but no acquisition row does, the operation fails and
requires inspection rather than reissuing an uncertain request. Tests use a
fake transport to verify the robots+copy ceiling and that a repeated run adds
no requests. No live campaign was authorized or executed by this decision.

The same plan can opt into the existing metadata API cascade, still under the
exact host list and physical ceiling; an unknown OA destination is blocked
until a new plan names it. Reopening a terminal acquisition failure requires
the exact prior failure class and a recorded reason. The ordinary retry rule
is not relaxed. A test verifies that a prior 403 is ineligible without the
named retry and eligible only with both class and reason.

## D92 — Freeze one discovery query per authorized operation (2026-10-07)

A discovery plan names one existing topic ID, one verbatim term, one API,
one round, a per-query result cap, exact hosts and a physical request ceiling.
The plan ID is its campaign. The bounded transport records each robots,
redirect and API request start. `discover.run` accepts a term selector and
adds the campaign to both request and query rows, while the ordinary CLI
behavior remains unchanged when no campaign is supplied.

After a crash, a matching query row is reconciled without another transfer.
If a physical start exists without its query row, the worker refuses to rerun
the query automatically. Other queries may add candidates before it starts;
the shared frozen population and protocol still govern deduplication. The
test exercises a two-transfer robots+API query with
a fake transport, verifies the recorded outcome and proves a second run
opens no socket. No live search was authorized by this decision.

## D93 — Batch plans retain one ceiling per unit and one operator approval (2026-10-07)

`operation_batches.jsonl` groups at most the operator's declared number of
query or candidate plans. It hashes their exact operation IDs and records
skipped items, remaining unplanned units and the sum of physical request
ceilings. One local `authorize-batch` command appends an authorization event
to each plan under the project writer lock; it never broadens a host or a
ceiling. `scheduler tick` and the polling `scheduler worker` run only such
authorized plans. A changed prerequisite becomes a failed operation rather
than a worker that repeatedly tries it. Tests verify the total ceiling and
idempotent batch authorization in a temporary store. No real campaign was
created by this decision.

## D94 — One bounded local drive through the scientific stages (2026-10-07)

`scheduler drive PROJECT FLOW_ID --extract-model A --review-model B
--max-local-calls N` runs one operator-invoked pass. It first executes the
flow's network operations that were already authorized when the command
started, within each exact plan's ceiling. It then plans and records
authorization for scoped normalize, extract queue construction, at most N
local llama.cpp calls in total, answer harvest, independent-reader review
queue construction/harvest and profile building. A and B must differ.
Existing stage gates still decide whether a profile may be built. It stops
with `NEEDS_AUTHORIZED_DISCOVERY` or `NEEDS_ACQUISITION_FLOOR` instead of
inventing a completed research result. No scientific verdict is signed.
The tests start with an empty flow, a one-document flow and an already
authorized fake query; exactly one model call occurs under a local ceiling
of one, and the query runs before the local pass. Each offline
stage still has an exact operation plan and authorization event, so the
drive does not bypass the operation ledger. The test makes no live scholarly
request. The command permits only the scholarly requests already approved in
exact operation plans and makes no metered model call.

## D95 — Local model identity must be reported, not merely requested (2026-10-07)

The `llamacpp` scheduler wrapper adds `strict-model-report=1` to its recorded
harness identity. If the server reports a model different from the plan, the
raw answer is retained but the result is terminal
`MODEL_IDENTITY_MISMATCH` and cannot become a claim or review. This matters
because the review gate compares backend/model readers: two requested names
would falsely look independent if the same loaded model answered both. The
test simulates that mismatch and verifies `ok: false`, the failure class and
the strict harness marker. Existing non-scheduler model runs retain their
prior behavior and provenance; no historical result is rewritten.

## D96 — Reserve paid model work across worker restarts (2026-10-07)

`operations_version 2` permits an exact `ollama-cloud` extract or review drain
only when its plan freezes model, harness, queue hash, call IDs, a named
cumulative budget, per-call reservation and declared input/output price
ceilings. Authorization sums the full reservations of all previously
authorized plans under the same budget ID; failed and unused reservations are
not recycled. Before each provider call the worker appends `call_started`.
A crash after that event without a result stops automatic retry, because the
provider may have charged for a reply the process did not record. A reported
unknown or over-reservation cost stops further calls. The per-call estimate
uses UTF-8 prompt bytes plus 8192 tokens of allowance and the request's
output limit; it is a local guard, not a provider-enforced billing cap.
Tests with a fake remote runner verify that a second plan cannot exceed a
15-cent cumulative budget after a 10-cent authorization, that the call-start
event precedes its result, and that an unsettled call is never resent. No
paid call was made by these tests or this decision.

## D97 — Replan only pre-transport discovery failures (2026-10-07)

The first authorized L02 scheduler query (one OpenAlex T01 term, at most ten
results and three physical requests) was blocked by the sandbox DNS resolver:
the recorded `NON_GLOBAL_ADDRESS` outcome had zero `request_started` rows and
zero returned results. A DNS check outside the sandbox resolved only global
addresses. The completed operation correctly refused implicit replay, but
`operations_version 2` also refused every explicit query retry. Under
`operations_version 3`, a new plan may retry the same query only when its
latest result is a named pre-transport failure, no physical request for that
query exists, and the operator supplies both a run label and reason. The new
plan hashes the prior query row; a changed outcome invalidates it. Tests
exercise a successful named retry with fake transport and refusal when an
earlier physical request exists. This rule does not turn the sandbox failure
into an empty literature result and does not authorize the retry by itself.

## D98 — A verdict's provenance is a recorded field, not free text (2026-10-07)

`adjudication_version 2` adds `signer_auth` and `actor` to every new
`adjudications.jsonl` row (F16). The review that produced the portal plan found the
defect this closes: `adjudicated_by` is free text, so nothing in a signed verdict can
distinguish a person signing from the CLI — where the name is declared, not
authenticated — from a signature written by a portal operator session. Once B4 exists,
both will write verdicts; the row must say which produced it, or the one channel an
auditor has is the signer's own word. `signer_auth` is one of `cli-declared` or
`portal-session`; `actor` is the portal operator id and `null` from the CLI; the class
and the actor must agree, and a mismatched pairing is refused rather than recorded.
Both parameters are required with no default, so no caller can omit them silently.
Rows written before the version existed are read as version 1, `signer_auth:
"cli-declared"`, in memory only — historical rows are never rewritten. The read API's
verdict object exposes `signer_auth`; `adjudicated_by` keeps its meaning.

## D99 — Operator sessions are installation state, versioned like an instrument (2026-10-07)

B4 of the portal-backend spec (`2026-10-07-portal-backend-spec.md`, decided by D89)
builds `claimstone control` and the operator accounts its sessions authenticate. The
record type this introduces is `operators.jsonl`, an installation-level append-only
ledger under `CLAIMSTONE_STATE_DIR` (default `.claimstone/`, gitignored) — deliberately
not per project: who may write is a property of the installation, not of a corpus.
`operator_version 1` rows carry an id, a display name, the scrypt parameters (n=2^15,
r=8, p=1), a random salt and the hash; a disable row removes the id. Passwords are
compared constant-time, one sentence answers an unknown id and a wrong password alike,
and no password, hash or salt is ever printed, returned or logged — the login route's
answer is yes or no.

Sessions are in-memory only, expiring after 12 hours of inactivity, so a restart logs
everyone out by construction and no token ever touches a disk. The session cookie
(`claimstone_control`) is HttpOnly, SameSite=Strict, Path=/, and Secure on a TLS
connection or behind a proxy that says `X-Forwarded-Proto: https` — honoring that
header can only add the flag, never remove it. Five failed logins per id per 15
minutes answer 429; a success does not clear the window, because the count is of
failures. A non-loopback bind is refused outright unless `--allow-host` names the
authority in front: unlike the read-only servers, this process writes, so it does not
proceed on a warning. The route registry the anonymous-access test enumerates is the
contract that every POST route later steps add is covered the moment it is registered.


## D100 — Signing from the web binds to a current flow; drafts are kept and never exported (2026-10-07)

B5 of the portal-backend spec adds the first routes through which the control server (D89, D99)
writes a project ledger. `POST /control/v1/p/{p}/flows/{flow_id}/q/{question_id}/adjudicate`
calls `synthesize.adjudicate` with `signer_auth: "portal-session"`, the session's operator id as
`actor` and the operator's display name as `adjudicated_by` (D98). The route adds request rules
and nothing scientific:
- the verdict must be one of the five, sent explicitly; nothing is preselected or defaulted;
- `attest` must be the literal `true`;
- the rationale is checked at 120 trimmed characters before the engine runs;
- the profile hash must be well-formed.

Every other refusal is the engine's own sentence, as 409.

One rule is new and is this step's decision: **signing requires the flow's binding to be
`CURRENT`**. A flow names a selector bound to a protocol digest. When the registry, protocol or
population has drifted, the engine judges with the live project, so a signature recorded "in"
that flow would carry a meaning the operator did not select. The refusal names the drifted
digests and points to binding a new flow. The CLI, which signs by round rather than by flow, is
unchanged.

`drafts.jsonl` (`draft_version 1`) keeps an operator's unfinished reasoning with the hash of the
profile it was written against. That is what lets the reading desk keep the text when the
profile changes and still block signing until the change is read. Drafts are private to their
operator, never read by any stage, never a signature, and excluded from `export.snapshot` beside
`exports.jsonl`. The exclusion changes no existing export identity, because no store had drafts
before this step.

`Idempotency-Key`, deferred by B4, is implemented here for every authenticated POST:
- keys are per operator, in memory for 24 hours;
- the same key and request replay the first success;
- a different request under the same key, or a key still running, is a conflict;
- a refusal frees its key.

A double submission therefore cannot sign twice. Tests in `tests/test_control_signing.py`.

## D101 — Proposed material is routed by what the engine treats as frozen (2026-10-07)

B7a records DOIs, links and references an operator proposes for a flow, in `intake.jsonl`
(`intake_version 1`). It routes each item before anything could count. The spec said "frozen round
(a closed manifest or cohort)", but the engine has no closed-cohort state. A round freezes its
population predicate in `populations.jsonl`, and `discover` keeps adding candidates that match it
(review F10). The routing therefore uses the one fixed set the engine has: a `manifest_only` flow,
or a whole-store flow that names no round, cannot take a new work (`NEEDS_NEW_ROUND`, listing the
open flows). An open round takes it as `READY` for its next discover, which applies the population
predicate. The intake never decides admission.

The matching rules:
- an exact DOI or normalised-URL match with a scoped candidate is a `DUPLICATE`;
- a reference matching a candidate's folded title is a `POSSIBLE_VERSION`, left for a person (B8).
  A title shorter than 21 characters only counts as a match when it equals the reference outright,
  because a short title found inside a longer reference is not evidence of the same work.

A URL is refused unless every address it resolves to is global. `net.global_addresses` is now the
single rule shared with `Fetcher`'s per-hop check.

Two dependencies are named rather than invented:
- `discover` does not read `intake.jsonl` yet, so `READY` means recorded and routed, not admitted;
- the spec's single explicit fetch moves to B7b, which builds the quarantine its bytes need, so
  B7a sends no request.

## D102 — Supplied copies are counted only by declaration; a file earns its row through the engine's gates (2026-10-07)

B7b lets an authenticated operator upload a PDF for one candidate. Review F14 left one question
open: whether such a copy may raise the acquisition rate that gates verdicts. That is scientific
policy, and this step does not decide it. It is declared once per project as
`sources.yaml: supplied_copies` (`count` | `separate`). The default is `separate`: `admissibility.rate`
reads the ledger as if operator-supplied rows were absent, falling back to the candidate's other
rows, and lists them in `supplied_separately`. Under `count` they enter the numerator like any copy.
The denominator never changes. Because the numerator rule now depends on provenance,
**`admission_version 3`**.

The output is identical for every existing store, since none holds an operator-supplied row, and
no profile hash moves: profiles carry only named keys of the admission result, and the new keys are
not among them. The key enters the protocol digest **only when declared**, so every flow bound
before this step stays `CURRENT`. This was checked read-only against the real stores, including the
L02 flow. Declaring the key later, even as `separate`, is protocol drift, as it should be.

A file becomes an `acquisitions.jsonl` row with `provenance: operator-supplied` only after three
checks, all the engine's own and none new:
- its hash is not already held;
- `fulltext.classify` accepts it under the candidate's class policy;
- the candidate's folded title appears in the first three pages extracted by `pdftotext -layout`,
  the extraction the L02 identity inspection used (D80).

A missing title is `POSSIBLE_VERSION` for a person (B8), never a merge. A candidate that already
holds a confirmed copy, or one awaiting the document check, needs none. Refused files stay in
`quarantine/` for inspection. Identical bytes are one file and never a second study.

Correction to D101: the single explicit fetch of an operator-proposed URL was **not** built in
B7b. An operator who holds a copy uploads it. Fetching a URL someone proposed is a network request
on their behalf, so it waits for the scheduler's authorized operations (B12) rather than becoming a
route around them.

## D103 — Decisions are records; possession and plans come from the ledgers, never from a button (2026-10-07)

B8 adds `decisions.jsonl` (`decision_version 1`) for the three decisions the portal design puts in
front of a person. None of them executes anything.

- **Identity.** A `POSSIBLE_VERSION` intake item gets one of four answers, with a reason of at least
  20 characters except `not_sure`.
  - `same_work` accepts a file through the single acceptance path of B7b, the identity now
    confirmed by the decision, or marks a reference a `DUPLICATE`.
  - `version_of` records the relation. It is **not** a way for a version's file to become the
    candidate's copy, and it never changes the study count.
  - `different` rejects a file for that candidate, or routes a reference again as a new work.

  This step's decision: whether a version's full text may stand in for the work it versions is
  scientific policy, and nothing here grants it.
- **Retry campaigns.** The plan is built on the server from what was recorded: the candidate's
  last outcome and the hosts its attempts reached.
  - Excluded hosts, and hosts whose recorded failures reach the fetcher's budget, are refused in
    the preview. `net.recorded_host_failures` is now the one count both the fetcher and the preview
    use.
  - Approving stores the plan verbatim under a new campaign name with a request bound, and executes
    nothing. It becomes work only when an authorized operation names it (B12).
- **Purchase offers.**
  - An offer exists only when an operator records one they verified, with vendor, price, currency,
    terms, verification time and what it might resolve. A 403 is never one.
  - `approved`, `bought_externally` and `declined` are set by hand, in order.
  - `copy_provided` and `copy_verified` are derived from intake and never written: possession is a
    file that passed B7b's gates.
  - A changed offer is a new offer, and the old one becomes `obsolete` without its approval.

Deferring needs a future date and declining needs a reason. Both state a fixed consequence: a
declined campaign makes no request, and a declined offer buys nothing.

The open list is ordered without reading claims, reviews or stances (F13). Required identity
questions come first, then source class, candidate key and age. A test adds claims of both stances
and asserts that the order does not move.

## D104 — "Since your last visit" is an operator's marker, read against the rows' own times (2026-10-07)

B9 builds the Today view. The spec placed `seen.jsonl` under each project's store. It is installation
state instead (`seen_version 1`, in the state directory beside `operators.jsonl`, D99), because a
marker belongs to a person rather than to a corpus, and one marker may cover every project. Changes
are counted from each row's own timestamp. A row without one is counted as undated and reported,
never placed in time by a file's mtime (review F17). "Needs you" splits required items from
optional ones:
- required: questions ready to sign, integrity and protocol blocks, identity questions;
- optional: offers.

"Continues without you" is reported as unavailable, not as an empty list, until the
scheduler-facing routes (B12) can read the queue: an empty list there would be a claim nobody
checked.

## D105 — An export carries copies only under a licence that allows it, and only when asked (2026-10-07)

B10 makes export and verification explicit control-server actions. A snapshot may include held
copies, but only those whose recorded licence clearly allows passing an unmodified copy on:
`cc0`, `cc-by`, `cc-by-sa`, `cc-by-nd`, `pd` and `public-domain`. Every other held copy is listed in
the manifest with its reason. That includes an unknown licence and any non-commercial or
publisher-specific one, because whether a use is non-commercial is not something the code can know.
The option enters the export identity only when set, so no existing export id or manifest changes and
`export_version` stays 1. `verify` checks included copies against their recorded hashes. Portal-made
exports record the operator as `actor` beside the OS user in `created_by`. Verification never runs
as a side effect of reading: the list route (BR) only lists.
