# `candidates.jsonl` — the contract

Written by stage 1 (`claimstone discover`, `claimstone import-manifest`). Append-only. A candidate
whose recorded facts change gets a new row rather than an edit, and `latest_by` prefers it.

**Stage 2 depends on `candidate_key`, `url`, `doi`, `title` and `source_class`** — and it refuses a row
whose `source_class` is null, which is invariant 6 enforced at the boundary rather than documented.

| field | meaning |
|---|---|
| `candidate_key` | identity: DOI, else folded title, else normalised URL |
| `title`, `url`, `doi`, `year`, `venue` | the work, as the channel reported it |
| `venue_type` | what the API called the venue; only meaningful beside `source_api` |
| `source_class` | assigned by the project's `assign_when` rules. **Null means no rule covered it** |
| `source_api` | `openalex`, `crossref`, `arxiv`, `citation`, `manifest` |
| `channel` | `keyword` or `citation` — the two channels D10 keeps independent |
| `query`, `query_hash`, `topic_id` | which search found it, so a round is reproducible |
| `cited_by`, `citations_in_corpus` | citation channel only: which corpus documents cite it |
| `possible_duplicate_of` | a near-match on title. **A note. Nothing is ever merged on it** |
| `round` | which round wrote this row; `routine` unless named |
| `source_id`, `declared_format` | manifest only |
| `is_oa`, `citations` | as the API reported, where it did |
| `found_at` | UTC, ISO 8601, seconds |

## The class comes from the project, never from the engine

`assign_when` on a source class in `sources.yaml` declares the conditions that assign a candidate to
it. Four predicates: `source_api`, `openalex_source_type`, `crossref_type`, `host`. A venue type only
counts alongside the API that reported it, because "journal" from OpenAlex and "journal-article" from
Crossref are different vocabularies, and arXiv speaks neither.

The **first declared class to match wins**, which needs no priority system: `sources.yaml` declares
classes most-authoritative-first. That gives the right answer on the case that matters — a refereed
paper whose only open copy sits on a preprint host stays `ACA`, where reading the host first would
demote every such paper.

A candidate no rule covers is written with a null class and counted. It is not guessed, because
guessing is what invariant 6 exists to prevent, and it is not discarded, because the remedy is to
declare a rule. `discover-report` prints which attribute values went unmatched, keyed by the predicate
a rule would have to use.

## A near-match is a note

Title matching fails in both directions and both failures were measured. GROBID took an NBER cover
banner as a title, so one work has two keys — 15 such cases in the first corpus. And "And the
Cross-Section of Expected Returns" is contained in "Media coverage and the cross-section of expected
returns" while being a different paper, so the containment rule that fixes the first produces the
second.

The rule is kept and its outcome is weakened to a note, on an asymmetry: a duplicate costs one wasted
fetch and not even a second download, since bytes are content-addressed, while a wrong merge loses a
source permanently and attributes its claims to another work. One is noise; the other corrupts the
evidence.

## Measured, 2026-09-26 — and the gap it found

The citation channel run against the real corpus, reading the 710 references stage 3 deduplicated:

```
references read          710
admitted by the rule      39      >=2 citations in corpus, >=25 title chars, year >=1990
written as candidates     37      2 already present
noted as duplicates        2      none merged
overlap with keyword       4      works both channels found
source_class assigned      0 of 37
carrying any URL          12 of 37
```

**The channel works and its output is not yet usable.** All 37 candidates are unclassified: a
reference carries no venue type, so no declared predicate can read anything, and the only rule that
could fire would be one naming `source_api: [citation]` — which would assign every reference to a
single class regardless of what it is. 25 of the 37 carry no URL at all, so stage 2 would have nothing
to fetch even if they were classified.

So a resolution step is missing: reference title or DOI to a venue and an address, through the same
APIs the keyword channel already queries. Stage 3's spec says it resolves nothing, deliberately — 817
references would be 817 Crossref lookups — and it never said who does. This contract records that it
is stage 1's, and that it is not built.

Until it is, `--channel citation` produces rows that are honest, counted, and refused downstream. That
is the correct failure: invariant 6 refusing an unclassified source is the boundary working, and a
channel that guessed a class to get past it would be the defect.
