"""HTML into the same Document tei.py produces, so chunking and confirmation do not care."""

from claimstone import html_doc

FILING = """<html><head><title>FORM 10-K ANNUAL REPORT</title></head><body>
  <nav>Skip to content</nav>
  <h1>Item 1. Business</h1>
  <p>The registrant operates a news analytics service.</p>
  <p>Revenue is recognised when the service is delivered.</p>
  <h2>Item 1A. Risk Factors</h2>
  <p>Competition in this market is intense.</p>
  <script>var tracking = 1;</script>
</body></html>""".encode()

FLAT = b"<html><body><p>One paragraph and no headings at all.</p></body></html>"


def test_the_title_comes_from_the_title_element():
    assert html_doc.parse(FILING).title == "FORM 10-K ANNUAL REPORT"


def test_headings_become_sections():
    doc = html_doc.parse(FILING)
    assert [s.head for s in doc.sections] == ["Item 1. Business", "Item 1A. Risk Factors"]
    assert doc.sections[0].paragraphs == (
        "The registrant operates a news analytics service.",
        "Revenue is recognised when the service is delivered.",
    )


def test_script_and_nav_are_not_text():
    doc = html_doc.parse(FILING)
    joined = " ".join(p for s in doc.sections for p in s.paragraphs)
    assert "tracking" not in joined
    assert "Skip to content" not in joined


def test_a_document_with_no_headings_is_one_section():
    doc = html_doc.parse(FLAT)
    assert len(doc.sections) == 1
    assert doc.sections[0].head == ""
    assert doc.sections[0].paragraphs == ("One paragraph and no headings at all.",)


def test_html_carries_no_tables_or_references():
    # Both are real problems and neither is this path's. A filing has no bibliography, and its
    # tables need work that PDF tables already got; saying so beats pretending to extract them.
    doc = html_doc.parse(FILING)
    assert doc.tables == ()
    assert doc.references == ()
    assert doc.notes == ()


def test_body_chars_counts_the_paragraphs():
    doc = html_doc.parse(FILING)
    assert doc.body_chars == sum(len(p) for s in doc.sections for p in s.paragraphs)


def test_markup_with_no_body_raises_rather_than_returning_nothing():
    import pytest

    from claimstone import tei

    with pytest.raises(tei.TeiError, match="no text"):
        html_doc.parse(b"<html><head><title>Only a head</title></head></html>")


# These two cover the defects the tests above let through. Both were in the plan's parser.

def test_inline_markup_does_not_split_a_paragraph():
    """A quote spanning the bold word has to match some chunk, or the gate rejects a true claim."""
    doc = html_doc.parse(
        b"<html><body><h1>H</h1><p>Returns rose by <b>4.2</b> per cent in the week.</p></body></html>"
    )
    assert doc.sections[0].paragraphs == ("Returns rose by 4.2 per cent in the week.",)


def test_text_before_the_first_heading_is_a_paragraph_and_not_a_heading():
    doc = html_doc.parse(
        b"<html><body><p>A preamble.</p><h1>Item 1</h1><p>Body.</p></body></html>"
    )
    assert [(s.head, s.paragraphs) for s in doc.sections] == [
        ("", ("A preamble.",)),
        ("Item 1", ("Body.",)),
    ]


# --- Tables ------------------------------------------------------------------------------------
#
# The plan decided not to extract these. It decided that before anyone opened the corpus's one HTML
# document, which turned out to be 140 tables holding 18% of its characters. Not extracting a table
# does not remove it: `td` is a block, so every cell arrives as its own prose paragraph.

TABLED = b"""<html><body><h1>Returns</h1>
  <p>The index is described below.</p>
  <table><caption>Annualised return by year</caption>
    <tr><th>Year</th><th>Return</th></tr>
    <tr><td>2019</td><td>4.2%</td></tr>
    <tr><td>2020</td><td>-1.7%</td></tr>
  </table>
  <p>Past performance is not indicative.</p>
</body></html>"""


def test_a_table_becomes_a_table_and_not_paragraphs_of_prose():
    doc = html_doc.parse(TABLED)
    assert len(doc.tables) == 1
    assert doc.tables[0].caption == "Annualised return by year"
    assert doc.tables[0].rows == (("Year", "Return"), ("2019", "4.2%"), ("2020", "-1.7%"))


def test_cell_text_never_leaks_into_the_prose_around_the_table():
    """A bare "4.2%" packed next to unrelated prose is a number a model will misattribute."""
    doc = html_doc.parse(TABLED)
    prose = [p for s in doc.sections for p in s.paragraphs]
    assert prose == ["The index is described below.", "Past performance is not indicative."]
    assert not any("4.2%" in p for p in prose)


def test_a_table_chunks_as_a_table_exactly_as_a_tei_table_does():
    from claimstone import chunk

    pieces = chunk.chunks(html_doc.parse(TABLED), source_id="IND001")
    tables = [c for c in pieces if c.kind == chunk.TABLE]
    assert len(tables) == 1
    assert "| 2019 | 4.2% |" in tables[0].text


def test_a_layout_table_with_no_text_is_not_a_table():
    """EDGAR nests empty tables for spacing. An empty chunk is noise stage 4 pays for."""
    doc = html_doc.parse(
        b"<html><body><table><tr><td></td></tr></table><p>" + b"x" * 60 + b"</p></body></html>"
    )
    assert doc.tables == ()


def test_a_nested_table_does_not_swallow_the_cell_that_holds_it():
    """A cell interrupted mid-text by a nested table keeps its words: a lost cell is a lost number."""
    doc = html_doc.parse(
        b"<html><body><table>"
        b"<tr><td>outer left<table><tr><th>in a</th><th>in b</th></tr>"
        b"<tr><td>in c</td><td>in d</td></tr></table></td><td>outer right</td></tr>"
        b"<tr><td>second left</td><td>second right</td></tr>"
        b"</table><p>" + b"x" * 60 + b"</p></body></html>"
    )
    assert [t.rows for t in doc.tables] == [
        (("in a", "in b"), ("in c", "in d")),
        (("outer left", "outer right"), ("second left", "second right")),
    ]


def test_a_layout_box_is_prose_and_not_a_table():
    """104 of the corpus document's 140 tables are 1x3 spacing boxes. A chunk each is 104 calls."""
    doc = html_doc.parse(
        b"<html><body><p>" + b"x" * 60 + b"</p>"
        b"<table><tr><td>A sentence that a publisher put in a box.</td>"
        b"<td></td><td></td></tr></table></body></html>"
    )
    assert doc.tables == ()
    assert "A sentence that a publisher put in a box." in doc.sections[0].paragraphs


def test_a_single_column_list_is_prose_too():
    doc = html_doc.parse(
        b"<html><body><p>" + b"x" * 60 + b"</p><table>"
        b"<tr><td>First line.</td></tr><tr><td>Second line.</td></tr></table></body></html>"
    )
    assert doc.tables == ()
    assert doc.sections[0].paragraphs[-2:] == ("First line.", "Second line.")


# --- Against the real document ------------------------------------------------------------------
#
# The corpus holds exactly one HTML full text, and it is why this module exists. It cannot be
# committed, so this skips when it is absent. Figures from
# `.venv/bin/python tools/derive_corpus_figures.py alembic-s4`.

import json
import pathlib

import pytest


def _the_html_full_text():
    ledger = pathlib.Path("store/alembic-s4/acquisitions.jsonl")
    if not ledger.exists():
        return None
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        gate = row.get("gate") or {}
        stored = row.get("stored_path") or ""
        if gate.get("kind") == "HTML_FULLTEXT" and pathlib.Path(stored).exists():
            return pathlib.Path(stored)
    return None


REAL = _the_html_full_text()
needs_real = pytest.mark.skipif(REAL is None, reason="no HTML_FULLTEXT artifact in store/")


@needs_real
def test_the_prospectus_parses_to_the_figures_the_derivation_prints():
    from claimstone import chunk

    doc = html_doc.parse(REAL.read_bytes())
    # No h1/h2/h3 anywhere in it: EDGAR renders headings with font weight. One unnamed section is
    # the honest result, and it is why the table rule matters more here than a heading rule would.
    assert len(doc.sections) == 1
    assert doc.body_chars == 232_084
    assert len(doc.tables) == 30
    assert sum(len(t.rows) for t in doc.tables) == 222

    pieces = chunk.chunk_document(doc, source_id="IND001")
    assert len(pieces.chunks) == 57
    assert max(len(c.text) for c in pieces.chunks) <= chunk.DEFAULT_THRESHOLDS["max_chunk_chars"]


@needs_real
def test_no_cell_of_the_real_document_leaves_without_being_carried():
    """A layout box demoted to prose must still be somewhere. A dropped cell is a dropped number."""
    from claimstone import chunk

    doc = html_doc.parse(REAL.read_bytes())
    carried = "\n\n".join(c.text for c in chunk.chunks(doc, source_id="IND001"))
    for table in doc.tables:
        for row in table.rows:
            for cell in row:
                assert not cell or cell in carried
