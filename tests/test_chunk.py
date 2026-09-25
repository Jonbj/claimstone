"""The five rules, and the rendering the quote gate will check against."""

from claimstone import chunk, tei


def section(head, *paragraphs):
    return tei.Section(head=head, paragraphs=tuple(paragraphs))


def para(chars, word="sentence"):
    one = f"{word} "
    return (one * (chars // len(one) + 1))[:chars].strip()


def document(*, sections=(), tables=(), notes=()):
    return tei.Document(title="A paper", abstract="An abstract.", sections=tuple(sections),
                        tables=tuple(tables), notes=tuple(notes), references=())


TABLE = tei.Table(
    number="1", head="Table 1 :", caption="Characteristics of News Sentiment",
    rows=(("Variable", "Mean", "SD"), ("net sentiment", "2.4%", "39.0%"), ("positive", "24.6%")),
)


# --- rule 1: a note stays a note ---------------------------------------------

def test_a_div_beginning_with_a_caption_marker_is_a_note_not_a_section():
    # Measured: ACA001 has "2.14" → "Notes: We sort all stocks…" and "Weeks" → "The figure
    # plots…". Real prose, but a figure's commentary, and merging it into a neighbouring
    # section would file it under a heading it has nothing to do with.
    doc = document(sections=[section("2.14", "Notes: We sort all stocks by sentiment."),
                             section("Introduction", para(4000))])
    kinds = [(c.kind, c.section) for c in chunk.chunks(doc, source_id="S01")]
    assert ("note", "2.14") in kinds


def test_a_caption_marker_is_matched_case_folded():
    doc = document(sections=[section("Weeks", "THE FIGURE PLOTS the coefficients."),
                             section("Introduction", para(4000))])
    assert any(c.kind == "note" for c in chunk.chunks(doc, source_id="S01"))


# --- rule 2: a bare head is junk ---------------------------------------------

def test_a_short_div_with_no_paragraphs_is_dropped():
    doc = document(sections=[section("Bare"), section("Introduction", para(4000))])
    assert [c.section for c in chunk.chunks(doc, source_id="S01")] == ["Introduction"]


def test_dropped_sections_are_counted_not_silently_lost():
    doc = document(sections=[section("Bare"), section("Also bare"),
                             section("Introduction", para(4000))])
    result = chunk.chunk_document(doc, source_id="S01")
    assert result.dropped_sections == 2


# --- rule 3: a short real section merges forward -----------------------------

def test_a_short_section_merges_into_the_following_one():
    # "II. Short-Horizon Return" is the opening of what follows, not the tail of what came
    # before — 65 of the 95 short divs measured are real sections like this.
    doc = document(sections=[section("II. Short-Horizon Return", para(400)),
                             section("Discussion", para(3000))])
    chunks = chunk.chunks(doc, source_id="S01")
    assert len(chunks) == 1
    assert "II. Short-Horizon Return" in chunks[0].text
    assert "Discussion" in chunks[0].text


def test_a_short_last_section_merges_into_the_preceding_one():
    doc = document(sections=[section("Discussion", para(3000)),
                             section("Coda", para(300))])
    chunks = chunk.chunks(doc, source_id="S01")
    assert len(chunks) == 1
    assert "Coda" in chunks[0].text


def test_a_section_above_the_merge_threshold_stands_alone():
    doc = document(sections=[section("Conclusion", para(1908)), section("Notes on data",
                                                                       para(3000))])
    assert len(chunk.chunks(doc, source_id="S01")) == 2


# --- rule 4: splitting ------------------------------------------------------

def test_a_long_section_splits_at_paragraph_boundaries():
    # Three 5,000-character paragraphs against a 9,000 budget: no two fit together, so each
    # gets its own chunk. Packing never exceeds the budget by adding a paragraph to a group.
    doc = document(sections=[section("Results", para(5000, "alpha"), para(5000, "beta"),
                                     para(5000, "gamma"))])
    chunks = chunk.chunks(doc, source_id="S01")
    assert len(chunks) == 3
    # Every paragraph lands wholly inside exactly one chunk: nothing is cut, nothing duplicated.
    for word in ("alpha", "beta", "gamma"):
        assert sum(1 for c in chunks if word in c.text) == 1


def test_paragraphs_that_fit_together_share_a_chunk():
    doc = document(sections=[section("Results", para(3000, "alpha"), para(3000, "beta"),
                                     para(3000, "gamma"), para(3000, "delta"))])
    chunks = chunk.chunks(doc, source_id="S01")
    assert len(chunks) == 2
    assert all(len(c.text) <= chunk.DEFAULT_THRESHOLDS["max_chunk_chars"] + 100 for c in chunks)


def test_a_single_paragraph_longer_than_the_budget_is_not_cut():
    # Cutting mid-sentence is what the section rule exists to avoid; an oversized paragraph is
    # reported rather than silently split.
    doc = document(sections=[section("Wall", para(20000))])
    chunks = chunk.chunks(doc, source_id="S01")
    assert len(chunks) == 1
    assert chunks[0].oversized is True


def test_every_split_chunk_names_the_same_section():
    doc = document(sections=[section("Results", para(5000), para(5000), para(5000))])
    assert {c.section for c in chunk.chunks(doc, source_id="S01")} == {"Results"}


# --- rule 5: tables ---------------------------------------------------------

def test_a_table_is_its_own_chunk():
    doc = document(sections=[section("Results", para(4000))], tables=[TABLE])
    kinds = [c.kind for c in chunk.chunks(doc, source_id="S01")]
    assert kinds.count("table") == 1


def test_the_table_rendering_is_exact():
    doc = document(tables=[TABLE])
    text = [c for c in chunk.chunks(doc, source_id="S01") if c.kind == "table"][0].text
    assert text == (
        "Table 1: Characteristics of News Sentiment\n"
        "\n"
        "| Variable | Mean | SD |\n"
        "| net sentiment | 2.4% | 39.0% |\n"
        "| positive | 24.6% |  |"
    )


def test_a_ragged_row_is_padded_so_columns_do_not_shift():
    # Measured: row 1 has three cells, row 3 has two. Skipping the missing cell would move a
    # number into the wrong column, and a claim would then quote the wrong figure.
    doc = document(tables=[TABLE])
    text = [c for c in chunk.chunks(doc, source_id="S01") if c.kind == "table"][0].text
    assert text.splitlines()[-1].count("|") == 4


# --- notes ------------------------------------------------------------------

def test_footnotes_are_packed_into_one_chunk_with_their_markers():
    doc = document(sections=[section("Results", para(4000))],
                   notes=[tei.Note("1", "We obtained similar results."),
                          tei.Note("2", "See Loughran and Ritter (2000).")])
    note = [c for c in chunk.chunks(doc, source_id="S01") if c.kind == "note"][0]
    assert "[1] We obtained similar results." in note.text
    assert "[2] See Loughran and Ritter (2000)." in note.text


# --- identity and provenance ------------------------------------------------

def test_a_chunk_carries_its_own_text_hash():
    doc = document(sections=[section("Results", para(4000))])
    one = chunk.chunks(doc, source_id="S01")[0]
    from claimstone.store import sha256_text
    assert one.text_sha256 == sha256_text(one.text)


def test_a_chunk_id_names_its_source_and_position():
    doc = document(sections=[section("Results", para(4000))], tables=[TABLE])
    ids = [c.chunk_id for c in chunk.chunks(doc, source_id="S01")]
    assert ids[0].startswith("S01#")
    assert len(set(ids)) == len(ids)


def test_the_thresholds_and_version_ride_on_every_chunk():
    doc = document(sections=[section("Results", para(4000))])
    row = chunk.chunks(doc, source_id="S01")[0].as_row()
    assert row["chunk_version"] == chunk.CHUNK_VERSION
    assert row["thresholds"]["max_chunk_chars"] == chunk.DEFAULT_THRESHOLDS["max_chunk_chars"]


def test_thresholds_can_be_overridden_per_project():
    doc = document(sections=[section("Results", para(5000), para(5000))])
    assert len(chunk.chunks(doc, source_id="S01", thresholds={"max_chunk_chars": 4000})) == 2


# --- Against the real corpus -------------------------------------------------------------------
#
# The TEI cannot be committed: it is the full text of copyrighted papers. So this is skipped when
# the store is empty, and the figures it asserts are the ones
# `tools/derive_corpus_figures.py alembic-s4` prints. A rule change that moves any of them has to
# move them here too, deliberately.

import pathlib

import pytest

CORPUS = sorted(pathlib.Path("store").glob("*/tei/*.xml"))
needs_corpus = pytest.mark.skipif(not CORPUS, reason="no TEI in store/ — run normalize first")


def _documents():
    return [(path.stem[:8], tei.parse(path.read_bytes())) for path in CORPUS]


@needs_corpus
def test_no_paragraph_is_lost_or_multiplied_by_chunking():
    """A lost paragraph is a claim that can never be made; a doubled one is a claim counted twice.

    Both sides are counted with the same instrument. Counting exact paragraph equality in the
    source against substring occurrence in the chunks reported 48 duplicates on this corpus, all
    of them artefacts of the mismatch — the same mistake as judging a short div by its length.
    """
    for source_id, doc in _documents():
        result = chunk.chunk_document(doc, source_id=source_id)
        source_text = "\n\n".join(chunk.render_section(s.head, s.paragraphs) for s in doc.sections)
        carried = "\n\n".join(
            piece.text for piece in result.chunks if piece.kind in (chunk.PROSE, chunk.NOTE)
        )
        for paragraph in (p for s in doc.sections for p in s.paragraphs if len(p) >= 40):
            assert carried.count(paragraph) == source_text.count(paragraph), (
                f"{source_id}: multiplicity changed for {paragraph[:60]!r}"
            )


@needs_corpus
def test_every_chunk_hashes_to_the_text_it_carries():
    """Stage 4 prompts with `text` and the quote gate checks against it. One rendering, one hash."""
    from claimstone.store import sha256_text

    for source_id, doc in _documents():
        for piece in chunk.chunks(doc, source_id=source_id):
            assert piece.text_sha256 == sha256_text(piece.text)
            assert piece.text == piece.as_row()["text"]


@needs_corpus
def test_the_corpus_chunks_to_the_figures_the_derivation_prints():
    if len(CORPUS) != 14:
        pytest.skip(f"figures were measured on 14 documents, store has {len(CORPUS)}")
    kinds = {chunk.PROSE: 0, chunk.TABLE: 0, chunk.NOTE: 0}
    dropped = merged = oversized = 0
    largest = 0
    for source_id, doc in _documents():
        result = chunk.chunk_document(doc, source_id=source_id)
        dropped += result.dropped_sections
        merged += result.merged_sections
        oversized += result.oversized_chunks
        for piece in result.chunks:
            kinds[piece.kind] += 1
            largest = max(largest, len(piece.text))

    assert kinds == {chunk.PROSE: 224, chunk.TABLE: 117, chunk.NOTE: 11}
    assert (dropped, merged, oversized) == (28, 77, 0)
    # 117 tables and 28 bare heads are exactly what the TEI measurement found: the chunker keeps
    # every table and drops nothing else.
    assert largest <= chunk.DEFAULT_THRESHOLDS["max_chunk_chars"]
    assert largest == 8983
