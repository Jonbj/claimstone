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
