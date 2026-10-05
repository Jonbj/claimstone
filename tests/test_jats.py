"""Synthetic JATS: cell geometry and separate evidence, with no scholarly requests."""

import pytest

from claimstone import chunk, jats, normalize
from claimstone.store import Store
from tests.test_normalize import FakeGrobid, acquired


ARTICLE = b'''<?xml version="1.0"?>
<!DOCTYPE article PUBLIC "-//NLM//DTD JATS 1.3//EN" "https://invalid.example/article.dtd">
<article xmlns:xlink="http://www.w3.org/1999/xlink">
 <front><journal-meta><journal-title>Not the article title</journal-title></journal-meta>
  <article-meta><title-group><article-title>A <italic>synthetic</italic> study</article-title></title-group>
   <abstract><p>Abstract only.</p></abstract></article-meta></front>
 <body><p>Opening without a heading.</p><sec><title>Methods</title>
  <p>Before <bold>formatting</bold>, after <xref ref-type="bibr">1</xref>.</p>
  <sec><title>Nested</title><p>Nested evidence.</p></sec>
  <p>Following nested evidence.</p>
  <list><list-item><p>List evidence.</p></list-item></list>
  <p>Inline note<fn id="inline"><label>a</label><p>Separate inline note.</p></fn> remains prose.</p>
  <table-wrap id="T1"><label>Table 1</label><caption><title>Results</title><p>Measured values.</p></caption>
   <table><thead><tr><th rowspan="2">Group</th><th colspan="2">Estimate</th></tr>
    <tr><th>Value</th><th>Uncertainty</th></tr></thead><tbody>
    <tr><td>A</td><td>2.4%</td><td>0.8</td></tr>
    <tr><td>B</td><td>3.1%</td></tr></tbody></table>
   <table-wrap-foot><fn id="t1"><p>Table footnote.</p></fn></table-wrap-foot></table-wrap>
  <fig id="F1"><label>Figure 1</label><caption><p>Figure caption.</p></caption><graphic xlink:href="image.png"/></fig>
 </sec></body>
 <back><app-group><app><title>Appendix</title><p>Appendix evidence.</p></app></app-group>
  <fn-group><fn id="n1"><label>1</label><p>Back footnote.</p></fn></fn-group>
  <ref-list><ref id="r1"><element-citation publication-type="journal">
   <person-group person-group-type="author"><name><surname>Reader</surname></name></person-group>
   <article-title>Reference study</article-title><source>Journal name</source><year>2024</year>
   <pub-id pub-id-type="doi">10.1234/example</pub-id></element-citation></ref>
  <ref id="r2"><mixed-citation>Verbatim unstructured reference, 2020.</mixed-citation></ref>
  <ref id="empty"/></ref-list></back>
 <sub-article><body><p>Another article's evidence.</p></body></sub-article>
</article>'''


def test_primary_structure_keeps_paragraphs_and_inline_text_separate():
    doc = jats.parse(ARTICLE)
    assert doc.title == "A synthetic study"
    assert doc.abstract == "Abstract only."
    assert [(s.head, s.paragraphs) for s in doc.sections] == [
        ("", ("Opening without a heading.",)),
        ("Methods", ("Before formatting, after 1.",)),
        ("Methods / Nested", ("Nested evidence.",)),
        ("Methods", ("Following nested evidence.",)),
        ("Methods", ("List evidence.",)),
        ("Methods", ("Inline note remains prose.",)),
        ("Appendix", ("Appendix evidence.",)),
    ]
    assert doc.body_chars == sum(len(p) for s in doc.sections for p in s.paragraphs)


def test_table_spans_and_ragged_rows_preserve_column_positions():
    table, = jats.parse(ARTICLE).tables
    assert table.caption == "Results Measured values."
    assert table.rows == (("Group", "Estimate", ""), ("", "Value", "Uncertainty"),
                          ("A", "2.4%", "0.8"), ("B", "3.1%", ""))
    assert "| A | 2.4% | 0.8 |" in chunk.render_table(table)
    assert "|  | Value | Uncertainty |" in chunk.render_table(table)


def test_inline_whitespace_is_preserved_before_normalization():
    payload = ARTICLE.replace(b"Before <bold>formatting</bold>, after", b"Before<bold> formatting </bold>and after")
    assert jats.parse(payload).sections[1].paragraphs == ("Before formatting and after 1.",)


def test_notes_and_reference_metadata_are_not_body_prose():
    doc = jats.parse(ARTICLE)
    assert [(n.marker, n.text) for n in doc.notes] == [
        ("a", "Separate inline note."), ("t1", "Table footnote."),
        ("Figure 1", "Figure caption."), ("1", "Back footnote.")]
    first, mixed = doc.references
    assert (first.title, first.year, first.authors, first.doi, first.key) == (
        "Reference study", 2024, ("Reader",), "10.1234/example", "doi:10.1234/example")
    assert mixed.title == "Verbatim unstructured reference, 2020."
    assert mixed.year is None
    rendered = "\n".join(c.text for c in chunk.chunks(doc, source_id="X"))
    assert "Another article's evidence" not in rendered
    assert "Reference study" not in rendered
    assert rendered.count("Separate inline note.") == 1
    assert rendered.count("2.4%") == 1


def test_body_bibliography_is_collected_once_and_excluded_from_prose():
    start = ARTICLE.index(b"<ref-list>")
    end = ARTICLE.index(b"</ref-list>") + len(b"</ref-list>")
    bibliography = ARTICLE[start:end]
    payload = ARTICLE[:start] + ARTICLE[end:]
    payload = payload.replace(b"</body>", bibliography + b"</body>", 1)
    doc = jats.parse(payload)
    assert len(doc.references) == 2
    assert doc.references == jats.parse(ARTICLE).references
    assert "Reference study" not in " ".join(p for s in doc.sections for p in s.paragraphs)


def test_namespaced_article_has_the_same_representation():
    namespaced = ARTICLE.replace(b"<article xmlns:xlink=", b'<article xmlns="urn:jats" xmlns:xlink=')
    assert jats.parse(namespaced) == jats.parse(ARTICLE)


@pytest.mark.parametrize("payload", [b"<article>", b"<error>Not found</error>",
    b"<article><front><article-meta/></front></article>",
    b"<article><front/><body><p>Text</p></body></article>",
    b"<article><front><article-meta/></front><body/></article>",
    b'<!DOCTYPE article [<!ENTITY x "secret">]><article/>'])
def test_invalid_or_abstract_only_xml_never_becomes_an_empty_document(payload):
    with pytest.raises(jats.JatsError):
        jats.parse(payload)


@pytest.mark.parametrize("replacement", [
    b'<graphic xlink:href="table.png"/>', b"<table><tgroup><tbody/></tgroup></table>",
    b'<table><tr><td rowspan="0">x</td></tr></table>',
    b'<table><tr><td rowspan="2">x</td></tr></table>',
    b'<table><tr><td colspan="1001">x</td></tr></table>',
    b'<table><tr><td rowspan="2">x</td><td>y</td><td rowspan="2">z</td></tr>'
    b'<tr><td colspan="2">overlap</td></tr></table>',
])
def test_unsupported_table_never_silently_loses_evidence(replacement):
    start, end = ARTICLE.index(b"<table>"), ARTICLE.index(b"</table>") + len(b"</table>")
    with pytest.raises(jats.UnsupportedJats):
        jats.parse(ARTICLE[:start] + replacement + ARTICLE[end:])


def _xml_store(tmp_path, payload=ARTICLE, content_type="application/xml; charset=utf-8"):
    store = Store("t", base=tmp_path)
    row = acquired("S01", store, body=payload)
    row["content_type"] = content_type  # Stored suffix deliberately disagrees.
    store.append("acquisitions.jsonl", row)
    return store


def test_normalize_and_confirmation_sweep_use_jats_without_grobid(tmp_path):
    store = _xml_store(tmp_path)
    grobid = FakeGrobid()
    row, = normalize.run(store, grobid, thresholds={"min_references": 2})
    assert row["format"] == "jats" and row["jats_parser_version"] == jats.JATS_PARSER_VERSION
    assert row["html_parser_version"] is None
    assert row["fulltext_confirmed"] and grobid.calls == 0
    points = normalize.confirm_sweep(store, "min_references", [2, 3])
    assert [p["confirmed"] for p in points] == [1, 0]
    assert all(p["unreadable"] == 0 for p in points)
    held = list(store.read("chunks.jsonl"))
    assert list(normalize.run(store, grobid)) == []
    list(normalize.run(store, grobid, force=True, thresholds={"min_references": 2}))
    assert list(store.read("chunks.jsonl")) == held


def test_parser_version_changes_chunk_generation_only_when_rebuilt(tmp_path, monkeypatch):
    store = _xml_store(tmp_path)
    old, = normalize.run(store, FakeGrobid(), thresholds={"min_references": 2})
    monkeypatch.setattr(jats, "JATS_PARSER_VERSION", jats.JATS_PARSER_VERSION + 1)
    new, = normalize.run(store, FakeGrobid(), force=True, thresholds={"min_references": 2})
    assert old["generation_sha256"] != new["generation_sha256"]
    assert not set(old["chunk_ids"]) & set(new["chunk_ids"])
    assert new["jats_parser_version"] == old["jats_parser_version"] + 1


def test_unsupported_structure_remains_awaiting_without_a_document_row(tmp_path):
    store = _xml_store(tmp_path, ARTICLE.replace(b"<table>", b"<table><tgroup/>"))
    row, = normalize.run(store, FakeGrobid())
    assert row["fulltext_confirmed"] is None and row["failure_class"] == "JATS_UNSUPPORTED"
    assert list(store.read("documents.jsonl")) == list(store.read("chunks.jsonl")) == []


def test_malformed_xml_is_recorded_with_its_parser_failure(tmp_path):
    store = _xml_store(tmp_path, b"<article>")
    row, = normalize.run(store, FakeGrobid())
    assert row["failure_class"] == "JATS_UNREADABLE"
    assert not row["fulltext_confirmed"] and not list(store.read("chunks.jsonl"))


def test_xhtml_still_uses_html_parser(tmp_path):
    store = _xml_store(tmp_path, b"<html><body><p>HTML text</p></body></html>", "application/xhtml+xml")
    row, = normalize.run(store, FakeGrobid(), thresholds={"confirm_chars": 1})
    assert row["format"] == "html" and "jats_parser_version" not in row
