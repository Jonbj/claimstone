"""Run the pure functions over real TEI, when there happens to be any.

The real files cannot live in this repository: they are the full text of copyrighted papers, the
same reason the stage 2 HTML fixtures are synthetic. But when a store is populated, running the
parser and the chunker over it catches what synthetic fixtures cannot — a real paper's structure is
stranger than anything anyone writes by hand.

`tests/test_chunk.py` asserts corpus totals and conservation across all of them at once. These are
parameterized per file, so a failure names the document rather than the corpus.
"""

import pathlib

import pytest

from claimstone import chunk, tei
from claimstone.store import sha256_text

TEI_FILES = sorted(pathlib.Path("store").glob("*/tei/*.xml"))

pytestmark = pytest.mark.skipif(
    not TEI_FILES, reason="no normalized TEI in store/; run `claimstone normalize` first"
)


@pytest.mark.parametrize("path", TEI_FILES, ids=lambda p: p.parent.parent.name + "/" + p.stem[:8])
def test_every_stored_tei_parses_and_chunks(path):
    doc = tei.parse(path.read_bytes())
    result = chunk.chunk_document(doc, source_id="X")
    assert result.chunks, "a stored TEI that yields no chunks would be silently unreadable"
    for one in result.chunks:
        # The hash must match the text, or stage 4's gate checks a different string from the one
        # the model was shown.
        assert one.text_sha256 == sha256_text(one.text)
        assert one.text.strip(), f"{one.chunk_id} is empty"
        assert one.kind in (chunk.PROSE, chunk.TABLE, chunk.NOTE)


@pytest.mark.parametrize("path", TEI_FILES, ids=lambda p: p.stem[:8])
def test_no_table_rendering_loses_a_cell(path):
    doc = tei.parse(path.read_bytes())
    for table in doc.tables:
        rendered = chunk.render_table(table)
        for row in table.rows:
            for cell in row:
                if cell:
                    assert cell in rendered, f"cell {cell!r} vanished from table {table.number}"
