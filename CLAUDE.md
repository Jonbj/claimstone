# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this project is

Claimstone takes a set of **topics** and a frozen list of numbered **questions**, finds and
legally obtains the readable literature on those topics, extracts what each source claims —
every claim bound to a verbatim quote — weighs the claims per question, and returns a
**verdict per question** with its coverage.

Read `README.md` for the contract and the six stages. Read `docs/DESIGN_DECISIONS.md`
before proposing any architectural change: it records dated decisions **with the
measurement that decided each**, so they are not relitigated from first principles.

## Non-negotiable invariants

Violating any of these silently destroys the value of everything downstream. They are not
style preferences.

1. **No claim without a verified quote.** Every claim carries an `evidence_quote` that is
   checked, in code, to be an exact substring of the chunk it came from. Every number and
   every inequality in the claim must also appear in that quote. Failures go to the
   rejection ledger — they are never softened, defaulted, or passed through with a warning.
2. **Five verdict states, and none of them collapses into another.** `SUPPORTED`,
   `CONTRADICTED`, `CONTESTED_IN_LITERATURE`, `UNANSWERED_IN_LITERATURE`, `NEVER_ASKED`.
   Reporting "we found no evidence" as "there is no effect" is the specific error this project
   exists to prevent; reporting a live disagreement as "we found no evidence" is the same error
   one category over, which is why the fifth state was added (2026-09-25). A question of
   `kind: operational` receives **no** verdict rather than a sixth state — see the verdict
   contract spec.
3. **The acquisition floor gates verdicts.** A round that obtained less than
   `acquisition_floor` of what it found is `INSUFFICIENT_ACQUISITION` and produces no
   verdicts. Do not add a flag to override this. A corpus read at 42% that certifies itself
   complete is worse than no corpus, and that is the real state that motivated the project.
4. **The engine holds no domain knowledge.** Topics, questions and source classes are input
   data under `projects/`. If something finance-specific or biology-specific is appearing in
   `claimstone/`, it is in the wrong place. Test: a project in an unrelated field must be
   expressible without touching the package.
5. **A question registry change is a dated bump.** Never a silent insert; otherwise every
   round-over-round figure and every multiplicity correction loses its meaning. Enforced, not
   merely asked: the registry carries a digest of its questions — ids, texts **and kinds** — and
   every command that opens a store refuses to run when the digest changed under an unchanged
   version. `kind` is in the digest because it decides which rule judges the question.
6. **Source class travels with every item.** A blog post and a refereed paper never share a
   pool without it being recorded which is which.
7. **Vote counting is not synthesis.** "Four papers say yes, one says no" is not a result, and
   neither is counting sources — D16 records arriving at that mistake twice. Stage 6 therefore
   emits an **evidence profile** and no verdict: every result with its estimand, the direction
   count *labelled a count*, coverage, what the gate rejected, and what a second reader would not
   pass. A person reads it and signs. There is **no pooling and no R**: D17 measured that the
   verdict contract's rules are counting and coverage rules, so an aggregated estimate would be
   additional information and the basis of no verdict the contract defines. D6's reasoning for
   `metafor` over hand-written pooling still holds for whenever a magnitude is wanted; it is
   deferred, not built.

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
tools/               scripts that derive a reported figure from the store, committed
                     because the data they read cannot be
tests/
```

A number quoted in a spec names the command that produces it. `tools/derive_corpus_figures.py`
exists because the corpus figures were once measured outside the repository and could not be
checked — and running it corrected one of them on the first attempt.

## Storage model

**Append-only JSONL is the source of truth** — hashable, diffable, auditable with `grep`, and
resumable after a crash in one specific sense: a process killed mid-append leaves a final line
with no newline, which `Store.read` skips and records and `Store.repair` truncates. Damage
anywhere else raises, because silently skipping a row removes it from a denominator. SQLite, if introduced, is a derived read model rebuildable from the
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
| `registry.jsonl` | any command | one row per question-registry version seen, with its hash. A changed hash under an unchanged version refuses to run (invariant 5) |

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

## Model backends

**One boundary, several backends** (D13). A stage that needs a model writes work units to
JSONL and reads results from JSONL; it never imports a vendor SDK. Backends available on this
machine: the local `llama.cpp` server, `claude -p --output-format json`, `codex exec`,
`opencode`, Ollama Cloud (API key, $60/month of credit on the $20 plan), and a metered API if
one is opened. Every result row records `backend`, `model`, `harness_version` and
`prompt_sha256`.

Which backend serves which lane is **a measurement, not a decision**: the same work units go
to two backends and the results are compared. Do not hard-code a lane to a vendor.

Two standing constraints. High-volume lanes go where throughput is priced per token —
interactive subscription plans are not batch infrastructure and are not driven as though they
were. And a CLI inserts its own harness between the prompt and the model, so where a result
must be exactly reproducible, prefer the metered API and always record `harness_version`.

**The local backend's operating point**, when it is the one serving a lane: narrow window,
many calls, short structured outputs. Measured at Q8_0, 11.6 min per call on ~8K-token
prompts, ~5 calls/hour, 1.43 tok/s generation against 121 tok/s prefill, with harvest per
call roughly constant at ~2 claims regardless of window size — so widening the window reduces
total harvest and "one JSON per document" is the worst available call shape. This is the
operating point of *that machine*, not a general property of models: see the perimeter note
on D4 before applying it to any other backend.

## Status

**Not restated here.** `README.md` holds it and `docs/HANDOFF.md` holds what is running and what is
pending. This section used to carry its own copy, which drifted: it claimed stage 6 refuses every corpus
after `pmc-screen-time` had cleared its floor at 0.93 and produced the project's first evidence profile.

One sentence that belongs here rather than there: **all six stages are implemented**, one round has run end
to end, and **no verdict exists** — `adjudicate` is the only command that writes one and it takes a person's
signature. An agent does not sign.
