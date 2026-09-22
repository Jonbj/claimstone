# Claimstone

Give it a set of **topics** and a frozen list of **questions**. It finds the readable
literature on those topics, obtains the full text legally, extracts what each source
actually claims — each claim tied to a verbatim quote from the source — weighs the
claims per question, and returns a verdict for each question.

Its defining constraint: **nothing enters the evidence base unless a verbatim excerpt
backs it, verified mechanically.** A claim whose quote is not an exact substring of the
source text is rejected, not softened.

It is domain-agnostic. The topics, the questions and the admissible source classes are
**input data**, not code.

## Why this exists

Two existing pipelines do this same work for two different domains — one on spirulina
cultivation, one on financial news and price behaviour. The machinery in the middle
(obtaining texts, defeating paywalls legally, deduplicating, extracting with
verification, weighing evidence) knows nothing about either domain. Claimstone is that
machinery, extracted once so the third topic costs a config file instead of a project.

## The contract

Per project, three input files — all data:

| File | Purpose |
|---|---|
| `topics.yaml` | broad search terms; used to **find** things |
| `questions.yaml` | numbered, frozen before results are seen; used to **say what was learned** |
| `sources.yaml` | admissible source classes and their hierarchy |

Output: one verdict per question, from
`SUPPORTED` / `CONTRADICTED` / `UNANSWERED_IN_LITERATURE` / `NEVER_ASKED`,
with the evidence attached and the coverage reported.

**Topics in, questions out.** A tool whose job is "gather information on topics" has no
stopping condition and no way to say "we don't know" — because *not knowing* is only
definable relative to a question. The questions are what make this an instrument rather
than a scraper.

## The six stages

Each stage reads and writes JSONL. No stage owns another stage's data.

1. **discover** — topics → candidates. Direct HTTP against OpenAlex, Crossref, arXiv for
   scholarly work; a SearXNG container for the rest. Deterministic; no model involved.
   Every candidate carries its source class and the hash of the query that found it, so
   "how many are new this round" is reproducible.
2. **acquire** — candidates → frozen texts. Unpaywall and OpenAlex resolve the legal open
   copy; a cascade of OA sources is tried in order; a publisher 403/429 with a known DOI
   falls back to OpenAlex locations. Per-domain circuit breaker and failure TTL stop the
   crawler hammering a paywall. Records `http_status`, licence, OA status and failure
   class for every attempt.
3. **normalize** — PDF/HTML → text, tables, references. GROBID over REST for scholarly
   PDFs; a plain path for everything else. Chunks get stable ids and hashes.
   The extracted bibliography feeds back into `discover` as a **second, independent
   discovery channel** — which is what makes completeness estimable rather than merely
   asserted.
4. **extract** — chunks → claims bound to questions. The question registry is in every
   prompt; a claim must cite an existing question id and carry the exact sentence it came
   from. Two lanes writing one schema: a local model for volume, a frontier model for the
   few decisive sources. Then the gate, which is code and not judgement: the quote must be
   an exact substring; every number and inequality in the claim must appear in the quote;
   the question id must exist. Rejects go to a ledger — that ledger is the denominator.
5. **review** — an adversarial second read marking each claim
   `SUPPORTED` / `OVERSTATED` / `AMBIGUOUS` / `NOT_APPLICABLE`. Compact input, short
   output. On the existing finance corpus this step caught roughly a quarter of the claims
   that had already passed the mechanical gate; it is the control that pays best.
6. **synthesize** — claims → a verdict per question. Deterministic Python for coverage,
   acquisition and completeness metrics. The statistics are delegated to an R script using
   `metafor`, called across a file boundary: random-effects pooling plus publication-bias
   correction in the form economics uses (PET-PEESE, MAIVE), which exists precisely because
   reported standard errors in observational research are not trustworthy.

## Admissibility

A round that could not obtain enough of what it found cannot produce verdicts. The
acquisition rate is reported every round and gates the rest: below the declared floor the
round is `INSUFFICIENT_ACQUISITION`. This is deliberate — a corpus read at 42% that
certifies itself as complete is worse than no corpus, and that is the observed state of
the corpus that motivated this project.

Counting how many sources agree is not a method. Vote counting ignores precision, effect
magnitude and the fact that significant results are the ones that get published.

## Tools

Python spine (`requests`, `numpy`; no framework) · one GROBID container · one SearXNG
container · one R script using `metafor` · a local `llama.cpp` server · a frontier model
for selection and the decisive sources.

Storage is **append-only JSONL as the source of truth** — hashable, diffable, resumable
after a crash — with SQLite as a derived view that can be rebuilt from it. No Postgres,
no vector database, no graph database: this is a few hundred documents, similarity is a
matrix multiplication and a citation graph is a table of edges.

## What it is not

Not a search engine, not a chatbot over papers, not a backtester. It does not touch the
consuming project's data or decisions. And it is not a machine for justifying a
hypothesis: concluding that a question is unsupported, or that an effect exists only at
horizons that do not apply, or that it disappears once costs are counted, is a successful
outcome and not a failure.

## Status

Early. Stage 1–3 first, measured against a real 26-source manifest whose current
acquisition rate is 0.42. The first deliverable is a sentence with a number in it: the
rate after, with OA status, licence and failure reason recorded per source. If that number
does not move, the rest is theatre.
