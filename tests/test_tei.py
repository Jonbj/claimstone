"""Parsing TEI. Synthetic throughout: real TEI is the full text of copyrighted papers."""

import pytest

from claimstone import tei

DOC = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader><fileDesc><titleStmt>
    <title level="a" type="main">News versus Sentiment</title>
  </titleStmt>
  <profileDesc><abstract><div><p>We study whether news predicts returns.</p></div></abstract>
  </profileDesc></fileDesc></teiHeader>
  <text><body>
    <div><head>Introduction</head><p>First paragraph.</p><p>Second paragraph.</p></div>
    <div><head n="2.">Data</head><p>We use a panel.</p></div>
    <div><head>2.14</head><p>Notes: We sort all stocks by sentiment.</p></div>
    <div><head>Bare</head></div>
    <figure type="table" xml:id="tab_1">
      <head>Table 1 :</head>
      <figDesc>Characteristics of News Sentiment</figDesc>
      <table>
        <row><cell>Variable</cell><cell>Mean</cell><cell>SD</cell></row>
        <row><cell>net sentiment</cell><cell>2.4%</cell><cell>39.0%</cell></row>
        <row><cell>positive</cell><cell>24.6%</cell></row>
      </table>
    </figure>
    <figure xml:id="fig_1"><head>Figure 1 :</head><figDesc>A plot.</figDesc></figure>
    <note place="foot" n="1">We obtained similar results using other strings.</note>
    <note place="foot" n="2">See Loughran and Ritter (2000).</note>
  </body>
  <back><div type="references"><listBibl>
    <biblStruct xml:id="b0"><analytic>
      <title level="a" type="main">Is all that talk just noise?</title>
      <author><persName><forename>W</forename><surname>Antweiler</surname></persName></author>
      <author><persName><forename>M</forename><surname>Frank</surname></persName></author>
      <idno type="DOI">10.1111/j.1540-6261.2004.00662.x</idno>
    </analytic><monogr><title level="j">Journal of Finance</title>
      <imprint><date type="published" when="2004"/></imprint></monogr></biblStruct>
    <biblStruct xml:id="b1"><monogr>
      <title level="m">Econometric Analysis</title>
      <author><persName><surname>Greene</surname></persName></author>
      <imprint><date type="published" when="2018"/></imprint></monogr></biblStruct>
  </listBibl></div></back></text>
</TEI>
""".encode()


def test_the_title_and_abstract_are_read():
    doc = tei.parse(DOC)
    assert doc.title == "News versus Sentiment"
    assert doc.abstract == "We study whether news predicts returns."


def test_sections_keep_their_paragraphs_apart():
    # Joining them early is what fuses words together; the renderer decides separators, later.
    doc = tei.parse(DOC)
    intro = doc.sections[0]
    assert intro.head == "Introduction"
    assert intro.paragraphs == ("First paragraph.", "Second paragraph.")


def test_a_section_with_no_paragraphs_is_still_parsed():
    # chunk.py decides it is junk. tei.py only reports what is there.
    doc = tei.parse(DOC)
    bare = [s for s in doc.sections if s.head == "Bare"][0]
    assert bare.paragraphs == ()


def test_a_table_keeps_its_cells_as_cells():
    doc = tei.parse(DOC)
    table = doc.tables[0]
    assert table.number == "1"
    assert table.caption == "Characteristics of News Sentiment"
    assert table.rows[0] == ("Variable", "Mean", "SD")
    assert table.rows[2] == ("positive", "24.6%")   # ragged, padded by the renderer


def test_a_figure_that_is_not_a_table_is_not_a_table():
    assert len(tei.parse(DOC).tables) == 1


def test_footnotes_are_collected_with_their_markers():
    doc = tei.parse(DOC)
    assert [n.marker for n in doc.notes] == ["1", "2"]
    assert doc.notes[0].text.startswith("We obtained similar results")


def test_an_article_reference_takes_its_title_from_analytic():
    first = tei.parse(DOC).references[0]
    assert first.title == "Is all that talk just noise?"
    assert first.year == 2004
    assert first.authors == ("Antweiler", "Frank")
    assert first.doi == "10.1111/j.1540-6261.2004.00662.x"


def test_a_book_reference_takes_its_title_from_monogr():
    # A bare .//title would pick whichever came first, which is wrong for a book.
    second = tei.parse(DOC).references[1]
    assert second.title == "Econometric Analysis"
    assert second.authors == ("Greene",)
    assert second.doi is None


def test_a_reference_key_folds_its_title():
    assert tei.parse(DOC).references[0].key == "title:is all that talk just noise"


def test_body_chars_counts_sections_only():
    # Figures and notes are siblings of divs, not children, so section text excludes them by
    # construction — and the stat has to match that or it describes something else.
    doc = tei.parse(DOC)
    assert doc.body_chars == sum(len(p) for s in doc.sections for p in s.paragraphs)


def test_malformed_xml_raises_rather_than_returning_an_empty_document():
    with pytest.raises(tei.TeiError):
        tei.parse(b"<TEI><body><div>unclosed")


def test_a_tei_with_no_body_raises():
    with pytest.raises(tei.TeiError, match="no body"):
        tei.parse(b'<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader/></TEI>')
