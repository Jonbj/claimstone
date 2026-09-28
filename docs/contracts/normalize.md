# `documents.jsonl`, `chunks.jsonl`, `references.jsonl` — the contract

Written by stage 3 (`claimstone normalize`). Append-only. Stage 3 owns all three; no other stage
writes them.

**Stage 4 depends on `chunks.jsonl` and on one property of it: `text` is exactly the string the
model will be shown and exactly the string a quote is checked against.** Rendering it a second time
anywhere would turn a difference between the two renderings into the rejection of a true claim.

Under D48 (`chunk_version 2`), read `chunk_sets.current(store)`. A document publishes its complete
`chunk_ids` manifest after all rows of a generation have been appended. Only this generation is active;
old and uncommitted chunks stay historical. `normalize --force` with identical inputs reuses chunk rows.
Legacy rows without a manifest use positional ids only when their recorded count is consistent;
an ambiguous set raises an error requesting explicit normalization rather than guessing.

## `documents.jsonl`

One row per normalized document, keyed by `source_id`.

| field | meaning |
|---|---|
| `source_id`, `sha256` | the source, and the hash of the bytes normalized |
| `format` | `pdf` or `html` — which parser read it, recorded rather than inferred |
| `tei_path` | the TEI under `store/<project>/tei/<sha256>.xml`, or the stored markup for `html` |
| `fulltext_confirmed` | `true`, `false`, or **`null` when nothing was established** |
| `failure_class` | `NOT_A_DOCUMENT`, `TEI_UNREADABLE`, or null |
| `reason` | the counts that decided it, so the verdict can be argued with |
| `title`, `body_chars`, `references`, `tables`, `notes` | what the parser found |
| `chunks`, `dropped_sections`, `merged_sections`, `oversized_chunks` | what chunking did |
| `chunk_version`, `thresholds` | under which rules |
| `generation_sha256`, `chunk_ids` | generation digest and complete active manifest, committed last |

A document that does not confirm produces **no chunks** and stays in this file. "We obtained it and
it was not a document" is a different failure from "we never obtained it", with a different remedy,
and collapsing them would hide which one happened.

`format` is recorded and never read back off the stored suffix. The confirmation sweep has to pick a
parser, and a source whose extension disagreed with its content type would be handed the wrong one
and counted unreadable — which on this corpus would silently exclude the only document confirmed by
character count.

### The state that is not a row

When the stored bytes are gone or unreadable, stage 3 writes **no `documents.jsonl` row at all**. It
reports `ARTIFACT_UNREADABLE` on the run and moves to the next source. This is deliberate:
`admissibility` counts every unconfirmed document row as an established negative, so recording an
absent file as unconfirmed would lower the acquisition rate on an infrastructure failure. With no
row, the source stays *awaiting* — which raises the ceiling, never moves the figure, and keeps
`final` false so the round cannot certify itself until someone looks.

## `chunks.jsonl`

| field | meaning |
|---|---|
| `chunk_id` | `<source_id>#<generation_sha256>#c3`, `#t1`, `#n1`; legacy ids omit generation |
| `generation_sha256`, `document_sha256` | generation and original acquired-byte identity |
| `kind` | `prose`, `table`, `note` |
| `section` | the section heading, so a claim's provenance is a place and not an offset |
| `text` | **the canonical text.** What the model sees; what the gate checks |
| `text_sha256`, `chars` | identity and size |
| `oversized` | a single paragraph over budget, emitted whole rather than cut |
| `chunk_version`, `thresholds` | under which rules |

Table text is rendered deterministically: a heading line, a blank line, then one `| a | b |` row per
table row, ragged rows padded to the widest. Padding matters — in the measured corpus row 1 of a
table has three cells and row 3 has two, and dropping the gap would shift a number under the wrong
heading.

A table needs at least two rows and two columns to be a table. Below that, in HTML, it is a
publisher's spacing box and its text returns to the prose at the position it occupied. On the
corpus's one HTML document that rule turns 140 tables into 30 tables and 110 boxes, and 164 chunks
into 57. See D20.

## `references.jsonl`

| field | meaning |
|---|---|
| `key` | `title:<folded title>` |
| `title`, `year`, `authors` | as GROBID read them |
| `doi` | usually `null`: stage 3 resolves nothing |
| `cited_by`, `citations_in_corpus` | which corpus documents cite it, and how many |

A reference's title lives in `analytic/title` for an article and `monogr/title` for a book. A bare
`.//title` takes whichever comes first, which is right for the first case and silently takes the
journal name in the second.

Only a **confirmed** document contributes references. The measured corpus holds 710 distinct
references from 13 confirmed PDFs; the 14 TEI files together hold 711, the extra one belonging to
`IND008`, which is not a document.

**Stage 3 decides no candidacy.** Which references become candidates belongs to `discover`, and
capture-recapture needs care that is not settled here: the two channels must sample the same
population, and 710 references include statistics textbooks. `citations_in_corpus` is what makes the
question answerable — a work three corpus documents cite is a different kind of candidate from one a
survey cites once.

## Measured, 2026-09-25

The first real run, on `alembic-s4`. Reproduce the corpus figures with
`.venv/bin/python tools/derive_corpus_figures.py alembic-s4`.

```
15 sources normalized   14 confirmed · 1 NOT_A_DOCUMENT · 0 awaiting
406 chunks              prose 249 · table 146 · note 11
710 references          distinct, deduplicated across the corpus
rate                    14/25 = 0.56, final, against a floor of 0.80
```

GROBID was not running. Every TEI was already on disk under its PDF's hash, so the stage needed no
container and no network — which is why the command does not demand one before it is needed.
