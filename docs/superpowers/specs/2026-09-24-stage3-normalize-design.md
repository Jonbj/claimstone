# Stage 3 — normalize: design

Date: 2026-09-24 · Scope: stage 3 only · Status: approved, not implemented

**Corrected 2026-09-28 (D48):** D48 publishes complete chunk-generation manifests atomically; active consumers use chunk_sets.current, preserving immutable history.

Between the bytes stage 2 obtained and the chunks stage 4 will read. Every number below was
measured on the 14 acquired PDFs of `alembic-s4`, not estimated.

## 1. What the measurement established

GROBID 0.8.1 over those 14 PDFs:

| | |
|---|---|
| Speed | **39 seconds for 14 documents**, 1-6s each. Not a constraint. |
| Body text | **775,266 characters** of paragraph prose across 14 documents |
| Chunks at 9,000 chars | **~86**, so a round of `extract` is ~86 calls (~$0.20 on a hosted open model) |
| Sections | 318, of which 95 under 800 characters — but see below: only 30 are junk |
| References | **817** across 14 documents, **711** distinct; 413 of them from one survey |
| Tables | **117** |

**GROBID needs a workaround on this machine.** The image's JVM cannot read cgroup v2 under
Docker 29 and dies at startup with `CgroupV2Subsystem.getInstance … anyController is null`. It
starts with `-e JAVA_TOOL_OPTIONS=-XX:-UseContainerSupport`, ready in ~15s. That flag belongs in
the error message, not in someone's memory.

**One acquired PDF is not a document.** `IND008` is `lseg-machine-readable-news-fact-sheet.pdf`:
around 4,600 characters of body, **1 reference**, sections titled "Key use cases" and "Find out
more". It passed stage 2 because the PDF gate there is structural, which that spec declares. It
is the PDF twin of the six HTML abstract pages, and the same signal catches it.

**Length is not the signal for a junk section either.** A first reading of this spec called all
95 short divs "captions and table fragments" on the strength of their length alone — the same
mistake the content gate made about HTML abstract pages, made again by the same author two days
later. Looking at them:

| of the 95 short divs | count | what they are |
|---|---|---|
| bare head, **no paragraphs at all** | 28 | genuine junk: a heading GROBID could attach nothing to |
| text begins with a caption marker | 2 | figure and table notes: `2.14` → "Notes: We sort all stocks…", `Weeks` → "The figure plots the cumulative coefficients from Table 5…" |
| everything else | **65** | **real short sections**: `II. Short-Horizon Return…`, `Other Adjustments`, `III. Understanding Retur…` |

So the junk is 30 of 318 (9%), not 95 (30%). And the two notes are real prose — a methods note
under a table can support a claim — so discarding them loses content, while merging them into a
neighbouring section would file a figure's commentary under a heading that has nothing to do with
it.

**Naive text extraction destroys tables.** `itertext()` over a TEI table yields
`Sentiment variableMeanStandard deviation2.4%39.0%` — words fused, no separators. A claim
quoting "the average net firm sentiment is 2.4%" could never match its chunk, so invariant 1
would reject a true claim and the rejection ledger — which is the denominator — would fill with
artefacts of the parser.

**Figures and notes are siblings of sections.** In `<body>`, `<div>`, `<figure>` and `<note>` are all
direct children; a `<figure>` never nests inside a `<div>`. So prose extracted from a section
excludes tables by construction, with no filtering.

**Footnotes are a fourth content source.** `<note place="foot">` children of `<body>`: **103 across
the 14 documents, 19,453 characters**, outside the 775,266 counted above because that figure sums
paragraphs only. `ACA008`'s single note reads "We obtained similar results using other random
strings" — a robustness check a claim could rest on. They become `kind="note"` chunks, packed per
document, each keeping its marker.

### Where these figures come from

`tools/derive_corpus_figures.py alembic-s4` prints every number above from
`store/<project>/tei/`, which `claimstone normalize` writes. The TEI itself cannot be committed —
it is the full text of copyrighted papers — so the derivation is committed instead.

A review pointed out that the figures had been measured outside the repository and were not
reproducible from it. Making them reproducible immediately corrected one: an earlier draft said
**818,678** body characters, counted from rendered `<div>` text including section headings, while
`Document.body_chars` counts paragraphs only. The number did not match its own definition. It is
775,266.

## 2. Module boundaries

```
grobid.py     HTTP to the container. No domain logic. Owns the "is GROBID up?" question.
tei.py        TEI bytes → Document. Pure: no I/O, no store.
chunk.py      Document → [Chunk]. Pure. Where pack, split and table rendering live.
normalize.py  orchestration: call GROBID, store the TEI, build chunks, write three ledgers.
```

Only `normalize.py` touches the network or the store, so the rules — which are the part with
judgement in them — are tested offline against synthetic TEI.

## 3. The Document

`tei.py` renders TEI into Python and knows nothing about chunking:

```python
Document(title, abstract, sections, tables, notes, references)   # .body_chars sums paragraphs
Section(head, paragraphs)               # paragraphs kept apart, never pre-joined
Table(number, head, caption, rows)      # rows: tuple[tuple[str, ...]] — cells stay cells
Note(marker, text)                      # a footnote keeps its marker, so a quote traces back
Reference(key, title, year, authors, doi)
```

A reference's title lives in `analytic/title` for an article and `monogr/title` for a book. A bare
`.//title` takes whichever comes first, which is right for the first case and silently takes the
journal name in the second.

**Cells stay cells until the last possible moment.** That is the lesson of §1's table finding:
the fused text comes from calling `itertext()` too early. Nothing in `tei.py` concatenates.

## 4. Chunking



Five declared rules, applied in this order. The first three decide what a short div *is*, which
§1 shows cannot be read off its length:

| rule | condition | outcome |
|---|---|---|
| 1. a note | short **and** its text after the head begins with a caption marker | its own chunk, `kind="note"` — kept and labelled, never merged into a section it does not belong to |
| 2. junk | short **and** it has no paragraphs at all | dropped, counted in `documents.jsonl` stats |
| 3. a short section | short, has paragraphs, no caption marker | merged into the **following** section, or the preceding one when it is last |
| 4. split | `chars > max_chunk_chars` (9000) | split at paragraph boundaries, never mid-sentence |
| 5. a table | always | its own chunk, `kind="table"` — the numbers are what stage 6 pools |

"short" means `chars < min_section_chars` (800). Caption markers are a declared list — `Notes:`,
`Note:`, `This table`, `This figure`, `The figure`, `The table`, `Source:`, `Sources:`,
`Standard errors`, `T-statistics` — matched case-folded against the text following the head, in
the same style as the content gate's paywall phrases. On the measured corpus this list catches
exactly the two notes and nothing else; a marker list that grew to catch more would need the same
by-hand check the gate's rejections got.

The list exists only for **mis-parsed** notes. GROBID labels real footnotes itself, as `<note>`
siblings of the sections, and those need no marker matching; rule 1 catches the div that was a figure
note in disguise.

Merging into the *following* section rather than the preceding one is deliberate: a short
`II. Short-Horizon Return` heading is the opening of what follows, not the tail of what came
before. When it is last there is no following section, so it merges backwards — and its head travels
with it as a line of text rather than being dropped, which is what the first implementation did.

A chunk carries its `section` name, so a claim's provenance is "Predicting Returns" rather than
"characters 18000-27000". One is information; the other is an offset.

**The thresholds and `chunk_version` are written onto every chunk.** Two rounds under different
thresholds are not comparable, and without recording them the difference is invisible — the same
rule the content gate follows.

## 5. The chunk's text is the canonical text

This section protects invariant 1.

**A chunk carries its text, exactly as the extractor will see it, with that text's hash.** Not a
pointer to an offset in the TEI from which the text can be rebuilt: the text. Stage 4's gate
checks that `evidence_quote` is an exact substring **of the chunk**, so if the chunk were
rendered twice — once for the prompt and once for the check — any difference between the two
renderings would reject a true claim.

Prose rendering: paragraphs joined with a blank line, internal whitespace normalised, nothing
else.

Table rendering, deterministic and declared:

```
Table 1: Characteristics of News Sentiment Variables
This table shows the average net firm sentiment (positive minus negative)…

| Sentiment variable | Mean | Standard deviation |
| Thomson Reuters net sentiment | 2.4% | 39.0% |
| Thomson Reuters positive | 24.6% |  |
```

Ragged rows are padded with empty cells to the widest row. In the measured table, row 1 has three
cells and row 3 has two; a rendering that skipped the missing cell would shift the columns and
silently move a number into the wrong one.

## 6. The three ledgers

Stage 3 owns these and no other stage writes them:

| file | one row per | carries |
|---|---|---|
| `documents.jsonl` | normalized document | `source_id`, byte `sha256`, the parsed path, stats, `fulltext_confirmed` and its reason |
| `chunks.jsonl` | chunk | `chunk_id`, `kind`, `section`, the **text**, `text_sha256`, thresholds, `chunk_version` |
| `references.jsonl` | distinct reference in the corpus | `key`, title, year, authors, `cited_by`, `citations_in_corpus`, `doi: null` |

### `fulltext_confirmed`

Same shape as the HTML gate, because it is the same question asked of a different format:

```
fulltext_confirmed = references >= min_references (5)  or  body_chars >= confirm_chars (15000)
```

Against the 14 measured documents the lowest legitimate reference count is `MET005` with **9**, so
all fourteen confirm on the first clause. `IND008` has 1 reference and 4,377 characters of div
prose and satisfies neither. Measured after the fact, **neither constant decides this**: the
corpus separates at 1 reference against 9, and at 4,377 characters against 20,844. See D21.

**Markup is normalized too, by a different parser.** GROBID reads PDFs, so an HTML source goes
through `html_doc`, which produces the same `Document` dataclasses and extracts less: sections,
paragraphs and tables, but no references and no footnotes. That is honest rather than limiting — a
regulatory filing has no bibliography, and the confirmation rule's second clause exists for exactly
that case. A first draft of the plan recorded every non-PDF as `NOT_PDF`, which would have dropped
a 247,993-character EDGAR prospectus supplement out of the corpus and turned the 14 of 25 below into 13 with nobody
noticing.

A document that does not confirm **produces no chunks** and is recorded in `documents.jsonl` with
`NOT_A_DOCUMENT` and its reason. It does not disappear: it stays counted, as stage 2's
`ABSTRACT_ONLY` rows do. "We obtained it and it was not a document" is a different failure from
"we never obtained it", with a different remedy.

### The thresholds are sweepable

`min_references: 5` and `confirm_chars: 15000` were chosen by looking at fourteen documents. The
TEI is stored content-addressed and parsing does no I/O, so
`claimstone normalize --confirm-audit` re-runs the confirmation across a range of one threshold
without re-fetching or re-calling GROBID — the same arrangement as `gate-audit`, for the same
reason. Two constants chosen at a desk are two constants to interrogate.

### References

One row per distinct reference, deduplicated on normalised title, carrying which corpus
documents cite it and how many do. **Stage 3 resolves no DOIs and decides no candidacy.**

Which references become candidates is a declared rule belonging to `discover`, and it needs care
that this spec does not settle: capture-recapture requires the two channels to sample the *same*
population, and 711 distinct references include statistics textbooks and unrelated fields. Filtering them
by topic terms would fix the population and destroy the independence D10 needs. `citations_in_corpus`
is the signal that makes the question answerable later — a work three corpus documents cite is
not the same kind of candidate as one a survey cites once — and `synthesize` must state what its
completeness estimate can and cannot claim. Recorded here as an open decision, not a solved one.

## 7. CLI

```
claimstone normalize <project> [--limit N] [--grobid-url URL] [--force]
claimstone normalize --confirm-audit <project> [--sweep NAME]
```

**Idempotent by content hash**: a document whose `sha256` is already in `documents.jsonl` is not
re-normalized. `--force` exists for when `chunk_version` changes, and it needs no network because
the TEI is already on disk — the same arrangement as `regate`.

`grobid.py` fails usefully. When `/api/isalive` does not answer:

```
GROBID is not answering on http://localhost:8070.
Start it with:
  docker run -d --name claimstone-grobid -p 8070:8070 \
    -e JAVA_TOOL_OPTIONS=-XX:-UseContainerSupport lfoppiano/grobid:0.8.1
JAVA_TOOL_OPTIONS is required: the image's JVM cannot read cgroup v2 under
Docker 29 and the container dies at startup.
```

`report` gains two lines and names the difference:

```
  obtained      15/25  0.60
  confirmed     14/25  0.56   <- the figure
                1 obtained but not a document: IND008
```

`admissibility.admit()` uses the confirmed rate where `documents.jsonl` exists and the obtained
rate where it does not, **stating which of the two it used**. A rate without its denominator is
what the honesty rules forbid.

## 8. Testing

The 14 real TEI files **do not enter the repository**: they are the full text of copyrighted
papers, the same reason the stage 2 HTML fixtures are synthetic.

| file | covers |
|---|---|
| `test_tei.py` | synthetic TEI: sections, tables with ragged rows, references, malformed XML, a TEI with no body |
| `test_chunk.py` | the five rules, including a note kept as a note and a bare head dropped; the canonical rendering byte for byte; thresholds on every chunk; a ragged table does not shift its columns |
| `test_normalize.py` | orchestration against a fake GROBID; idempotence by `sha256`; the three ledgers; `fulltext_confirmed` on an `IND008`-shaped document; markup routed away from GROBID |
| `test_html_doc.py` | headings into sections; skipped elements; no-text refusal |
| `test_grobid.py` | the `isalive` check, and the error message naming the workaround |
| `test_real_tei.py` | runs the pure functions over `store/*/tei/*.xml` **when the store is populated**, skipped otherwise — the real-data validation that cannot be committed |

## 9. Out of scope, deliberately

No OCR: a scanned PDF fails confirmation and says so. No formula parsing, though `MET002` carries
60 of them — a formula is not a claim. No figure images. And no citation *context*: which
paragraph cited which reference would make the citation graph much richer, and is exactly the
kind of thing to add when something needs it.
