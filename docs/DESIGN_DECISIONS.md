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

## D9 — Append-only JSONL is the source of truth
Hashable, diffable, resumable after a crash, and auditable with grep. SQLite is a derived
read model, rebuildable from the JSONL. No Postgres (single writer, megabytes of data),
no vector database (a few hundred documents: similarity is one matrix multiplication), no
graph database (a citation graph is a table of edges).

## D10 — Two independent discovery channels, by construction
Keyword search over metadata APIs, and backward citations extracted by GROBID. Two
independent channels make corpus completeness **estimable** — capture-recapture — instead
of merely asserted from a round-over-round delta. That delta is confounded with
acquisition failure: a blocked downloader produces "0% new" and reads as saturation.

## D11 — Admissibility gates verdicts
Acquisition rate is computed every round and reported. Below the declared floor the round
is `INSUFFICIENT_ACQUISITION` and produces no verdicts. The corpus that motivated this
project stands at 0.42 with 20 sources lost to 403 and connection failures, and the
criterion it was using would have declared it saturated.

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
one machine. Measured against real rates instead: extraction of the 26-source manifest is
~130 calls, and of a 300-source corpus ~1,500. On Ollama Cloud's hosted open models at
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
