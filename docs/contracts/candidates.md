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

**Before resolution existed, all 37 were unclassified and 25 had no URL.** A reference carries a title,
sometimes a DOI, and nothing else — no venue, no venue type, no address — so no declared predicate could
read anything and there was nothing to request. Stage 3 resolves nothing by design and no spec said who
does. Stage 1 does, and it is opt-in.

## Resolution

`discover --channel citation --resolve` looks each admitted reference up. Without `--resolve` the
channel reads a ledger and opens no socket, which is the promise that lets it re-run for free.

| `resolution` | meaning |
|---|---|
| `BY_DOI` | the reference's DOI resolved to a work **whose title matches** |
| `BY_TITLE` | matched on an exact folded title |
| `NO_MATCH` | looked up, nothing carried this title. Not a failure — a fact about the reference |
| `TITLE_TOO_SHORT` | under 15 folded characters; not requested, because a fragment matches many works |
| `LOOKUP_FAILED` | the request failed. Worth retrying, which `NO_MATCH` is not |
| `NOT_ATTEMPTED` | no `--resolve` |

**A title match is exact on both paths, including the DOI path.** GROBID mis-parses a DOI often enough
that a confident lookup can return a real, different paper, and attaching the wrong work would attribute
its claims to a source that never made it — worse than a candidate stage 2 refuses. A DOI whose work does
not carry the reference's title falls back to the title search rather than being believed.

A resolved row carries the **resolver** as its `source_api`, not `citation`. `classify` refuses to read a
venue type without knowing whose vocabulary it is, and after resolution the word is OpenAlex's; `channel`
is what records that the reference came from a bibliography. With `source_api` left as `citation` the
resolved venue type was a word nobody owned and the class stayed null anyway.

## The citation channel's key is the reference's key

`candidate_key` prefers a DOI, and resolution **adds** one — so a derived key would move the moment a
candidate resolved, and the same work would become two candidates with nothing superseding either.
Citation rows therefore key on the reference stage 3 gave them, which is stable across resolution.

That derivation is an instrument: see `candidate_key_version` in D24, and the 13 ghost rows measured when
the rule changed under an existing store. A shared DOI under two keys is now reachable and is noted as a
certain duplicate — still only noted, for the same asymmetry as a near-match.

## The floor is judged per round

`round` is the round that **first** found a candidate. A discovery sweep changes the denominator by
design, so `report --round <name>` is how a settled population is read: measured, one citation sweep took
`alembic-s4` from 14/25 = 0.56 to 14/75 = 0.19, and only the first compares like with like. See D24.
