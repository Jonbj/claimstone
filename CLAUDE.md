# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this project is

Claimstone takes a set of **topics** and a frozen list of numbered **questions**, finds and
legally obtains the readable literature on those topics, extracts what each source claims —
every claim bound to a verbatim quote — weighs the claims per question, and returns a
**verdict per question** with its coverage.

Read `README.md` for the contract and the six stages. Read `docs/DESIGN_DECISIONS.md`
before proposing any architectural change: it records twelve decisions **with the
measurement that decided each**, so they are not relitigated from first principles.

## Non-negotiable invariants

Violating any of these silently destroys the value of everything downstream. They are not
style preferences.

1. **No claim without a verified quote.** Every claim carries an `evidence_quote` that is
   checked, in code, to be an exact substring of the chunk it came from. Every number and
   every inequality in the claim must also appear in that quote. Failures go to the
   rejection ledger — they are never softened, defaulted, or passed through with a warning.
2. **Four verdict states, not three.** `SUPPORTED`, `CONTRADICTED`,
   `UNANSWERED_IN_LITERATURE`, `NEVER_ASKED`. Reporting "we found no evidence" as "there is
   no effect" is the specific error this project exists to prevent.
3. **The acquisition floor gates verdicts.** A round that obtained less than
   `acquisition_floor` of what it found is `INSUFFICIENT_ACQUISITION` and produces no
   verdicts. Do not add a flag to override this. A corpus read at 42% that certifies itself
   complete is worse than no corpus, and that is the real state that motivated the project.
4. **The engine holds no domain knowledge.** Topics, questions and source classes are input
   data under `projects/`. If something finance-specific or biology-specific is appearing in
   `claimstone/`, it is in the wrong place. Test: a project in an unrelated field must be
   expressible without touching the package.
5. **A question registry change is a dated bump.** Never a silent insert; otherwise every
   round-over-round figure and every multiplicity correction loses its meaning.
6. **Source class travels with every item.** A blog post and a refereed paper never share a
   pool without it being recorded which is which.
7. **Vote counting is not synthesis.** Pooling is precision-weighted with publication-bias
   correction, delegated to R. "Four papers say yes, one says no" is not a result.

## Acquisition conduct

Honour `robots.txt`. Respect the per-domain failure budget: a host that returned 403 is not
re-requested outside a named campaign. Never route through a shadow library — the
`excluded_hosts` list in a project's `sources.yaml` is deliberate, not a placeholder.
Prefer the open-access copy by construction; record `licence`, `oa_status` and
`failure_class` for every attempt, successful or not.

## Privacy rule

**This repository is public.** Real project instances under `projects/` are gitignored
because they encode a consuming system's internal design. Only
`projects/example-news-and-returns/` ships. Before committing anything under `projects/`,
check that it does not disclose someone's internal architecture. If a fresh instance is
needed for a test, build it from public literature.

## Layout

```
claimstone/          the engine — no domain knowledge, ever
  config.py          loads and validates a project's three input files
  cli.py             entry point; unimplemented stages say so rather than pretending
projects/<name>/     one instance: topics.yaml, questions.yaml, sources.yaml
store/<project>/     generated, gitignored; append-only JSONL plus fetched bytes
docs/                DESIGN_DECISIONS.md and data contracts
tests/
```

## Storage model

**Append-only JSONL is the source of truth** — hashable, diffable, resumable after a crash,
auditable with `grep`. SQLite, if introduced, is a derived read model rebuildable from the
JSONL, never the primary. Do not add Postgres (single writer, megabytes of data), a vector
database (a few hundred documents: similarity is one matrix multiplication) or a graph
database (a citation graph is a table of edges).

Per project under `store/<project>/`:

| File | Written by | Contains |
|---|---|---|
| `candidates.jsonl` | discover | one row per candidate, with source class and the hash of the query that found it |
| `acquisitions.jsonl` | acquire | one row per attempt: `http_status`, resolved OA location, licence, `failure_class` |
| `raw/<sha256>.<ext>` | acquire | the fetched bytes, content-addressed |
| `rejections.jsonl` | extract | what was discarded and why — this is the denominator |

## Working conventions

- Python ≥ 3.11, stdlib plus `requests`, `PyYAML`, `numpy`. **No framework.** Dependencies
  must sit behind a process or file boundary — see D7. PaperQA2, ASReview, ASySD, statcheck
  and prismAId were each evaluated and rejected with reasons; do not reintroduce them
  without addressing those reasons.
- Every network call: explicit timeout, a descriptive User-Agent with contact, and a
  recorded outcome. A silent `except: pass` around a fetch is a defect here, because a
  swallowed failure inflates the acquisition rate.
- Idempotent and resumable by content hash. Never re-fetch or re-extract the same bytes.
- Run `.venv/bin/pytest -q` and `.venv/bin/claimstone validate --all-projects`.

## Local model operating point

When a stage uses the local `llama.cpp` server: **narrow window, many calls, short
structured outputs.** Measured on the target machine at Q8_0: 11.6 min per call on ~8K-token
prompts, ~5 calls/hour, 1.43 tok/s generation against 121 tok/s prefill — it reads far
faster than it writes. A pre-registered probe showed harvest per call is roughly constant
at ~2 claims **regardless of window size**, so widening the window reduces total harvest.
"One JSON per document" is therefore the worst available call shape. Long prose, ideation
and agentic iteration are out of scope for the local model by arithmetic.

## Status

The contract and its validator exist. The six pipeline stages are specified in the README
and **not implemented**; the CLI exits with a message for each. Acquisition (stage 2) is the
first milestone, not extraction — it is the binding constraint on the science. The first
deliverable is a sentence with a number in it: the acquisition rate on a real 26-source
manifest currently sitting at 0.42, with OA status, licence and failure reason recorded per
source. If that number does not move, the rest is theatre.
