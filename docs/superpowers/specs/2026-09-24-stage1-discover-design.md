# Stage 1 — discover: design

Date: 2026-09-24 · Scope: stage 1 only · Status: approved, not implemented

**Corrected 2026-09-28 (D48):** D48 records every request and distinguishes empty successful searches from failed or malformed queries; recorded failures block round finality.

The only stage with code and no spec. `discover.py` already searches OpenAlex, Crossref and arXiv
and imports a manifest; this document says what it should do, which turns out to differ from what
it does in one blocking respect.

Every number below was measured on `alembic-s4`: the 25-source manifest and the 817 references
GROBID extracted from its 14 acquired PDFs.

## 1. The blocking defect

**`discover` produces candidates that `acquire` refuses.** `_row` assigns no `source_class`; only
`import_manifest` adds one, through `extra`. Stage 2 raises `MissingSourceClass` on a candidate
without one — deliberately, because invariant 6 says a class travels with every item — so every
candidate the three API searchers produce is unusable.

Nothing is wrong with stage 2 here. The gap is that nobody ever decided how a candidate found by
an API gets a class, and §3 decides it.

## 2. What the citation channel actually is

`CHANNEL_CITATION` is declared in the code and never used. Measured, it would carry this:

| | |
|---|---|
| Raw references across 14 documents | **817** |
| Distinct, deduplicated on normalised title | **711** |
| Carrying a DOI in the TEI | **30 (4%)** — consolidation is off, by stage 3's design |
| Carrying a year | 684 (96%) |
| Cited by exactly one corpus document | **657** |
| Cited by two or more | **54** |

The most-cited are the canonical works of this literature — Chan 2003 on price reaction to news
and no-news, Jegadeesh and Titman 1993, Loughran and McDonald 2011, Tetlock 2007 — which is
evidence the channel finds the right kind of thing.

**Overlap with the keyword channel: 6 of the 25 manifest sources appear among the 711
references.** That number matters in §6, and mostly for what it does not license.

### Where these figures come from

`tools/derive_corpus_figures.py alembic-s4` prints all of them from `store/<project>/tei/`, which
`claimstone normalize` writes. The TEI cannot be committed — it is the full text of copyrighted
papers — so the derivation is, and a review was right that quoting them without it made them
unauditable.

## 3. Assigning a source class

`classify.py` exposes `classify(candidate, classes) -> str | None`. The rules live in
`sources.yaml`, so the engine applies rules it does not know — the same arrangement as the
manifest's class aliases:

```yaml
classes:
  - id: ACA
    name: peer-reviewed academic
    assign_when:
      openalex_source_type: [journal]
      crossref_type: [journal-article]
  - id: WP
    name: working paper / preprint
    assign_when:
      source_api: [arxiv]
      openalex_source_type: [repository]
      host: [papers.ssrn.com, nber.org]
```

Three predicates and no others:

| predicate | compares against |
|---|---|
| `source_api` | `openalex`, `crossref`, `arxiv`, `citation`, `manifest` |
| `openalex_source_type` / `crossref_type` | the venue type as that API reports it |
| `host` | the URL's domain, matched on suffix |

A class matches when **any** of its declared predicates matches. **The first class in declaration
order wins**: `sources.yaml` already declares classes most-authoritative-first, so the ordering is
the right one and no separate priority system is needed.

A candidate no rule covers gets `source_class: null` and is written anyway, counted as
`UNCLASSIFIED`. It is neither discarded nor guessed: `discover-report` says how many there are
**and which attribute values were uncovered**, so the remedy is to declare a rule. `acquire` goes
on refusing it, which is correct — a classless candidate entering a pool is invariant 6 broken
silently, and that is worse than a candidate that stops at the gate.

## 4. The two channels, and the round

**Keyword.** Unchanged in substance: every term of every topic against the three APIs. A candidate
already carries `query`, `query_hash`, `topic_id`, `source_api` and `channel`.

**Citation.** Reads stage 3's `references.jsonl` and admits by declared rule:

```yaml
citation_channel:
  min_citations_in_corpus: 2   # 54 of the 711 measured
  min_year: 1990
  require_title_chars: 25      # discards parsing fragments
```

An admitted reference becomes a candidate with `channel: "citation"`, `source_api: "citation"`,
and `cited_by` preserved so its provenance survives.

`discover` **reads** another stage's ledger and **writes** only its own. Reading is allowed;
writing is not, and this is the loop the README describes — the extracted bibliography returning
as a second channel.

**Threshold choice and its cost.** `min_citations_in_corpus: 2` does not reuse the topic terms, so
it leaves the two channels independent. What it does do is bias the second channel toward
canonical works, and §6 records that as a limit rather than hiding it.

**The round.** `--round NAME`, written on every candidate, as `--campaign` is in `acquire`.
"How many are new this round" is a round-over-round figure, and without a name on the row it has
to be reconstructed from timestamps — which append-only storage exists to make unnecessary. The
default is `routine`.

Topics carry no version. Widening a topic cannot by itself change a verdict, so unlike the
question registry there is nothing to bump.

## 5. Matching, and why nothing is merged

`ids.candidate_key` already orders identity by trustworthiness: DOI, then folded title, then URL.
The citation channel uses it like everything else. But only **3%** of references carry a DOI, so
nearly all deduplication falls on the title — where both ways of being wrong were measured.

**False negatives.** `Which News Moves Stock Prices? A Textual Analysis` against
`NBER WORKING PAPER SERIES WHICH NEWS MOVES STOCK PRICE…` — one work, two keys, because GROBID
took the cover banner as the title. That is a stage 3 extraction artefact and **the fix does not
belong here**; 15 such near-matches were found.

**False positives.** `And the Cross-Section of Expected Returns` (Harvey, Liu and Zhu) against
`Media coverage and the cross-section of expected returns` (Fang and Peress). One title contains
the other and they are different papers — so a containment rule, which would have fixed the
banner problem, produces wrong merges.

**Therefore: nothing is ever merged on an approximate match.** A candidate records
`possible_duplicate_of: <key>` and **stays a distinct candidate**.

"Approximate" is defined, not left to judgement: one folded title contains the other and the
shorter of the two is at least 25 characters. That is exactly the check that found both the 15
banner cases and the Harvey/Fang-Peress false positive, so its error rate on this corpus is known
rather than assumed — and since the outcome is a note and never a merge, a false positive costs a
line in a report.

The asymmetry decides it. A duplicate costs one wasted acquisition attempt — and not even a second
download, since bytes are content-addressed. A wrong merge **loses a source permanently** and
attributes its claims to a different work. The first is noise; the second corrupts the evidence.

## 6. What `discover-report` says, and what it must not

```
alembic-s4 — round routine
  keyword channel    312 candidates   16 topics, 96 queries
  citation channel    54 candidates   of 711 references, threshold 2 citations
  unclassified         7              openalex_source_type: conference, book-series
  overlap              6 works found by both channels
```

**A single completeness figure is forbidden here, and that is a requirement, not an omission.**
Lincoln-Petersen is computable from the measured numbers — (25 × 711) / 6 ≈ 2962 works, a corpus
covering 0.8% — and publishing it would be fabricated precision. Three reasons, all measured:

1. Exact-title overlap is 6 while near-matches number 15, so the denominator is understated by an
   unknown amount, and the estimate moves inversely with it.
2. The manifest was curated by hand. It is not a random sample of anything.
3. Catchability is unequal by construction — a canonical paper is cited by everyone, an obscure one
   by nobody — and `min_citations_in_corpus` **relies on** that inequality, so our own filter
   violates the assumption the estimate needs.

So the report gives the three quantities separately: channel 1 size, channel 2 size, overlap.
What may be concluded from them is `synthesize`'s problem, and its spec inherits the obligation to
state what the estimate can and cannot claim. D10 says two independent channels make completeness
*estimable*; it does not say the first estimate available is trustworthy.

What **is** solid and belongs in the report: **705 of the 711 references were not in the
manifest.** The second channel finds hundreds of things the first missed, and no population
estimate is needed to know that.

## 7. Module boundaries

```
searchers.py  (new)        search_openalex, search_crossref, search_arxiv — moved from
                           discover.py, plus the fields classify needs (venue type, host).
classify.py   (new)        declared rules → source_class. Pure.
discover.py   (rewritten)  orchestration: the two channels, the round, the ledger.
config.py     (modified)   assign_when per class; citation_channel thresholds.
cli.py        (modified)   the discover and discover-report commands, which do not exist yet.
```

The searchers are the part that ages — APIs change shape — so isolating them makes them testable
against saved responses without touching anything else.

## 8. CLI

```
claimstone discover <project> [--round NAME] [--topics T01,T05] [--api openalex]
                             [--per-query N] [--channel keyword|citation|both]
claimstone discover-report <project> [--round NAME] [--json]
```

`--topics` takes a comma-separated list and `--api` is repeatable; omitting either means all of
them. `--channel` defaults to `both`, and `both` with no `references.jsonl` present runs the
keyword channel and says the citation channel had nothing to read — rather than reporting zero
citation candidates, which would read as "the bibliography found nothing".

`--channel citation` opens no socket: it reads `references.jsonl` and writes candidates. So it is
re-runnable at no cost when the threshold changes — the same arrangement as `gate-audit` and
`normalize --confirm-audit`.

## 9. Testing

| file | covers |
|---|---|
| `test_searchers.py` | the three APIs against saved fake responses: row shape, an empty payload, malformed JSON, arXiv's Atom, the fields `classify` needs |
| `test_classify.py` | each predicate; declaration order deciding; an uncovered candidate staying null rather than being guessed |
| `test_discover.py` | both channels; the round on the row; dedup by `candidate_key`; `possible_duplicate_of` recorded and **never** merged; the citation threshold |
| `test_discover_report.py` | the three quantities separately; and an assertion that the module contains **no** population estimate — the cheapest way to make a future contributor argue with §6 rather than quietly add one |

No test reaches a real API. The fetcher is injected, as in stage 2.

## 10. Out of scope, deliberately

**SearXNG and web search.** The README promises a container "for the rest", and `NEW`, `IND` and
`DOC` have no scholarly API. They come from the manifest, curated by hand, which is how they have
arrived so far. The measured reason: web search on these topics returns product pages — six of six
HTML sources in this corpus were classified `ABSTRACT_ONLY` — so another container would buy
candidates the gate then discards. Revisit when a class needs sources the manifest cannot supply.

**DOI resolution for references.** `acquire` already has `resolve_doi_by_title`, and resolving 711
titles through Crossref belongs to the stage that is about to fetch them, not to the stage that
listed them.

**Banner-title correction.** A stage 3 TEI extraction artefact. Fixed there or not at all.

**A published completeness figure** (§6).
