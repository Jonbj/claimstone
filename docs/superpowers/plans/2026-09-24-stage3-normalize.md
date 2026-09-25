# Stage 3 — normalize: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the bytes stage 2 obtained into chunks stage 4 can quote from — where the text a chunk carries is byte-for-byte the text the quote gate will check against, and where a PDF that is not a document says so.

**Architecture:** `grobid.py` talks to the container and owns the "is it up?" question. `tei.py` renders TEI into a `Document` and does no I/O. `chunk.py` turns a `Document` into chunks and owns every rule with judgement in it — including the deterministic table rendering that makes a claim about a number possible. `normalize.py` orchestrates and writes three ledgers it alone owns.

**Tech Stack:** Python ≥ 3.11, stdlib (`xml.etree.ElementTree`) plus `requests`. One GROBID container over HTTP. pytest.

**Spec:** `docs/superpowers/specs/2026-09-24-stage3-normalize-design.md`. Read it before Task 1; every task cites the section it implements.

---

## Conventions for every task

- Run tests with `.venv/bin/pytest`, the CLI with `.venv/bin/claimstone`.
- **Every commit message ends with the trailer** `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`, shown in full in Task 1 and abbreviated as `<trailer>` afterwards.
- **No test starts a container or opens a socket.** `grobid.py` takes its transport as a parameter; `tei.py` and `chunk.py` are pure.
- **No real TEI in the repository.** Those files are the full text of copyrighted papers. Fixtures are synthetic; `tests/test_real_tei.py` validates against `store/*/tei/` when the store happens to be populated and skips otherwise.
- Commit after every task. A task that leaves the suite red is not finished.

## Three spec corrections this plan makes

Measuring the TEI more closely while planning turned up three structural facts the spec did not have. All three land in the spec in Task 8.

**1. Figures are siblings of sections, not children.** In `<body>`, `<div>`, `<figure>` and `<note>` are all direct children; a `<figure>` never nests inside a `<div>`. So prose extracted from a section excludes tables **for free** — §5's concern about tables diluting prose chunks needs no filtering code.

**2. Footnotes are a fourth content source, and a substantive one.** `<body>` carries `<note place="foot">` children: **103 of them across the 14 documents, 19,453 characters**, outside the 775,266 the spec counts because that figure sums paragraphs only. They are not decoration — `ACA008`'s single note reads "We obtained similar results using other random strings", which is a robustness check a claim could rest on. They become `kind="note"` chunks, packed per document.

This also narrows §4's caption-marker rule: real notes arrive already labelled by GROBID, so the marker list exists only to catch the **two** notes that were mis-parsed as body divs.

**3. A reference's title lives in `analytic/title` for an article and `monogr/title` for a book.** A bare `.//title` picks whichever comes first, which is right for articles and wrong for books.

## File structure

| File | Action | Responsibility |
|---|---|---|
| `claimstone/grobid.py` | create | HTTP to the container; the liveness check and its error message. |
| `claimstone/tei.py` | create | TEI bytes → `Document`. Pure, no I/O, no rendering. |
| `claimstone/chunk.py` | create | `Document` → `[Chunk]`. Pure. The five rules and the canonical rendering. |
| `claimstone/html_doc.py` | create | markup → the same `Document` TEI produces. No tables, no references. |
| `claimstone/normalize.py` | create | orchestration of both parsers, the three ledgers, `fulltext_confirmed`, the confirm sweep. |
| `claimstone/admissibility.py` | done in `7490f6d` | already prefers the confirmed rate; Task 6 only verifies it against real rows. |
| `claimstone/cli.py` | modify | `normalize`, `normalize --confirm-audit`; `report` gains the confirmed line. |
| `claimstone/config.py` | modify | `normalize:` thresholds, beside `acquisition:`. |
| `tests/test_grobid.py` | create | liveness, the helpful error, the injected transport |
| `tests/test_tei.py` | create | parsing, on synthetic TEI |
| `tests/test_chunk.py` | create | the five rules and the rendering |
| `tests/test_normalize.py` | create | orchestration, ledgers, idempotence, confirmation |
| `tests/test_html_doc.py` | create | headings into sections, skipped elements, no-text refusal |
| `tests/test_real_tei.py` | create | the pure functions over real TEI when present |
| `docs/contracts/normalize.md` | create | the three ledgers stage 4 will read |

---

### Task 1: The GROBID client

Implements spec §7's liveness message.

**Files:**
- Create: `claimstone/grobid.py`
- Create: `tests/test_grobid.py`

- [x] **Step 1: Write the failing tests**

Create `tests/test_grobid.py`:

```python
"""The container client. No container is started and no socket is opened."""

import pytest

from claimstone import grobid


class FakeTransport:
    """Stands in for the two requests calls grobid makes."""

    def __init__(self, alive=True, tei=b"<TEI/>", status=200):
        self.alive, self.tei, self.status = alive, tei, status
        self.posted: list[tuple[str, dict]] = []

    def get(self, url, timeout=None):
        class R:
            status_code = 200 if self.alive else 503
            text = "true" if self.alive else ""
        return R()

    def post(self, url, files=None, data=None, timeout=None):
        self.posted.append((url, dict(data or {})))
        outer = self

        class R:
            status_code = outer.status
            content = outer.tei
            text = "server said no"
        return R()


def test_a_live_server_reports_alive():
    assert grobid.Grobid(transport=FakeTransport()).is_alive() is True


def test_a_dead_server_reports_not_alive():
    assert grobid.Grobid(transport=FakeTransport(alive=False)).is_alive() is False


def test_the_error_names_the_workaround_not_just_the_url():
    # The cgroup v2 failure cost twenty minutes to diagnose. The error message is where that
    # belongs, not in someone's memory.
    client = grobid.Grobid(transport=FakeTransport(alive=False))
    with pytest.raises(grobid.GrobidUnavailable) as caught:
        client.full_text(b"%PDF-1.4")
    message = str(caught.value)
    assert "JAVA_TOOL_OPTIONS=-XX:-UseContainerSupport" in message
    assert "docker run" in message
    assert "cgroup v2" in message


def test_a_pdf_comes_back_as_tei():
    transport = FakeTransport(tei=b"<TEI>ok</TEI>")
    assert grobid.Grobid(transport=transport).full_text(b"%PDF-1.4") == b"<TEI>ok</TEI>"


def test_consolidation_is_off_by_default():
    # 817 references across 14 documents would be 817 Crossref lookups, and this stage is
    # otherwise pure local parsing. Resolution is not stage 3's job (spec §6).
    transport = FakeTransport()
    grobid.Grobid(transport=transport).full_text(b"%PDF-1.4")
    _, data = transport.posted[-1]
    assert data["consolidateHeader"] == "0"
    assert data["consolidateCitations"] == "0"


def test_a_server_error_is_reported_with_its_status():
    client = grobid.Grobid(transport=FakeTransport(status=500))
    with pytest.raises(grobid.GrobidFailed, match="500"):
        client.full_text(b"%PDF-1.4")
```

- [x] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_grobid.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claimstone.grobid'`

- [x] **Step 3: Write `claimstone/grobid.py`**

```python
"""The GROBID container, over HTTP.

Consolidation is off. Resolving 817 references through Crossref is not this stage's job — stage 3
is otherwise pure local parsing, and which references become candidates is a decision that
belongs to `discover` (spec §6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

DEFAULT_URL = "http://localhost:8070"

START_COMMAND = (
    "  docker run -d --name claimstone-grobid -p 8070:8070 \\\n"
    "    -e JAVA_TOOL_OPTIONS=-XX:-UseContainerSupport lfoppiano/grobid:0.8.1"
)

# Measured 2026-09-24: without the flag the image's JVM dies at startup on this machine with
# "CgroupV2Subsystem.getInstance … anyController is null". Twenty minutes to find; one line to
# pass on.
WORKAROUND_NOTE = (
    "JAVA_TOOL_OPTIONS is required: the image's JVM cannot read cgroup v2 under\n"
    "Docker 29 and the container dies at startup."
)


class GrobidUnavailable(RuntimeError):
    """The server is not answering, with instructions rather than a bare timeout."""


class GrobidFailed(RuntimeError):
    """The server answered, and refused."""


def _default_transport() -> Any:
    import requests

    return requests


@dataclass
class Grobid:
    url: str = DEFAULT_URL
    timeout_s: int = 300
    transport: Any = field(default_factory=_default_transport)

    def is_alive(self) -> bool:
        try:
            response = self.transport.get(f"{self.url}/api/isalive", timeout=10)
        except Exception:
            return False
        return getattr(response, "status_code", 0) == 200

    def _unavailable(self) -> GrobidUnavailable:
        return GrobidUnavailable(
            f"GROBID is not answering on {self.url}.\nStart it with:\n{START_COMMAND}\n"
            f"{WORKAROUND_NOTE}"
        )

    def full_text(self, pdf: bytes, *, filename: str = "document.pdf") -> bytes:
        """PDF bytes in, TEI bytes out. Raises rather than returning something unusable."""
        if not self.is_alive():
            raise self._unavailable()
        try:
            response = self.transport.post(
                f"{self.url}/api/processFulltextDocument",
                files={"input": (filename, pdf, "application/pdf")},
                data={"consolidateHeader": "0", "consolidateCitations": "0"},
                timeout=self.timeout_s,
            )
        except Exception as exc:
            raise self._unavailable() from exc

        status = getattr(response, "status_code", 0)
        if status != 200:
            raise GrobidFailed(
                f"GROBID returned {status}: {getattr(response, 'text', '')[:200]}"
            )
        return response.content
```

- [x] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_grobid.py -q`
Expected: PASS, 6 passed

- [x] **Step 5: Commit**

```bash
git add claimstone/grobid.py tests/test_grobid.py
git commit -m "grobid: the client, and the workaround in the error message

The image's JVM cannot read cgroup v2 under Docker 29 and the container dies at
startup; it needs JAVA_TOOL_OPTIONS=-XX:-UseContainerSupport. That took twenty
minutes to diagnose, so the failure path prints the whole docker run line and says
why the flag is there rather than reporting a bare timeout.

Consolidation is off: resolving 817 references through Crossref is not this stage's
job, and which of them become candidates belongs to discover.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: TEI into a Document

Implements spec §3, plus corrections 1, 2 and 3.

**Files:**
- Create: `claimstone/tei.py`
- Create: `tests/test_tei.py`

- [x] **Step 1: Write the failing tests**

Create `tests/test_tei.py`:

```python
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
```

- [x] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_tei.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claimstone.tei'`

- [x] **Step 3: Write `claimstone/tei.py`**

```python
"""TEI as Python. No I/O, no rendering, no judgement.

One rule governs this module: **cells stay cells and paragraphs stay apart.** Measured on real
output, `itertext()` over a TEI table yields `Sentiment variableMeanStandard deviation2.4%39.0%`
— words fused with no separators. A claim quoting a number from that table could never match its
chunk, so the quote gate would reject a true claim and the rejection ledger, which is the
denominator, would fill with artefacts of this parser. Separators are the renderer's decision
(`chunk.py`), taken once, at the last possible moment.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterator

from claimstone.ids import normalize_doi, normalize_title

NS = "{http://www.tei-c.org/ns/1.0}"

_TABLE_NUMBER = re.compile(r"(\d+)")


class TeiError(ValueError):
    """The TEI could not be read. Never softened into an empty document."""


@dataclass(frozen=True)
class Section:
    head: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class Table:
    number: str
    head: str
    caption: str
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Note:
    marker: str
    text: str


@dataclass(frozen=True)
class Reference:
    key: str
    title: str
    year: int | None
    authors: tuple[str, ...]
    doi: str | None


@dataclass(frozen=True)
class Document:
    title: str
    abstract: str
    sections: tuple[Section, ...]
    tables: tuple[Table, ...]
    notes: tuple[Note, ...]
    references: tuple[Reference, ...]

    @property
    def body_chars(self) -> int:
        """Section prose only. Figures and notes are siblings of divs, not children."""
        return sum(len(p) for s in self.sections for p in s.paragraphs)


def _text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def _paragraphs(div: ET.Element) -> tuple[str, ...]:
    return tuple(t for t in (_text(p) for p in div.findall(f"{NS}p")) if t)


def _tables(body: ET.Element) -> Iterator[Table]:
    for figure in body:
        if figure.tag != f"{NS}figure" or figure.get("type") != "table":
            continue
        head = _text(figure.find(f"{NS}head"))
        found = _TABLE_NUMBER.search(head)
        table = figure.find(f"{NS}table")
        rows = tuple(
            tuple(_text(cell) for cell in row.findall(f"{NS}cell"))
            for row in (table.findall(f"{NS}row") if table is not None else [])
        )
        yield Table(
            number=found.group(1) if found else "",
            head=head,
            caption=_text(figure.find(f"{NS}figDesc")),
            rows=rows,
        )


def _notes(body: ET.Element) -> Iterator[Note]:
    for note in body:
        if note.tag != f"{NS}note":
            continue
        body_text = _text(note)
        if body_text:
            yield Note(marker=note.get("n") or "", text=body_text)


def _reference(entry: ET.Element) -> Reference:
    analytic = entry.find(f"{NS}analytic")
    monogr = entry.find(f"{NS}monogr")
    # An article's title is in analytic; a book's is in monogr. A bare .//title picks whichever
    # comes first, which is right for the first case and wrong for the second.
    title = ""
    for holder in (analytic, monogr):
        if holder is not None:
            title = _text(holder.find(f"{NS}title"))
            if title:
                break

    year: int | None = None
    for date in entry.iter(f"{NS}date"):
        when = (date.get("when") or "")[:4]
        if when.isdigit():
            year = int(when)
            break

    authors = tuple(
        _text(surname) for surname in entry.iter(f"{NS}surname") if _text(surname)
    )
    doi = None
    for idno in entry.iter(f"{NS}idno"):
        if (idno.get("type") or "").upper() == "DOI":
            doi = normalize_doi(_text(idno))
            break

    folded = normalize_title(title)
    return Reference(
        key=f"title:{folded}" if folded else "",
        title=title,
        year=year,
        authors=authors,
        doi=doi,
    )


def parse(payload: bytes) -> Document:
    """TEI bytes into a Document. Raises TeiError rather than returning something empty."""
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise TeiError(f"not well-formed XML: {exc}") from exc

    body = root.find(f".//{NS}body")
    if body is None:
        raise TeiError("no body element: GROBID returned a document with no text")

    sections = tuple(
        Section(head=_text(div.find(f"{NS}head")), paragraphs=_paragraphs(div))
        for div in body
        if div.tag == f"{NS}div"
    )

    return Document(
        title=_text(root.find(f".//{NS}titleStmt/{NS}title")),
        abstract=_text(root.find(f".//{NS}abstract")),
        sections=sections,
        tables=tuple(_tables(body)),
        notes=tuple(_notes(body)),
        references=tuple(
            _reference(entry) for entry in root.iter(f"{NS}biblStruct")
        ),
    )
```

- [x] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_tei.py -q`
Expected: PASS, 12 passed

- [x] **Step 5: Commit**

```bash
git add claimstone/tei.py tests/test_tei.py
git commit -m "tei: cells stay cells and paragraphs stay apart

itertext() over a real TEI table yields "MeanStandard deviation2.4%39.0%" — words
fused, no separators — so a claim quoting a number could never match its chunk and
the quote gate would reject a true claim. Separators are the renderer's decision,
taken once, later. This module reports structure and nothing else.

Three things the real TEI taught: figures and notes are siblings of divs rather
than children, so section prose excludes tables for free; footnotes are a real
content source (103 across 14 documents) and carry robustness checks a claim could
rest on; and a reference's title is in analytic for an article and monogr for a
book, where a bare .//title would silently take the journal name.

Malformed TEI raises. An empty Document standing in for an unreadable one is a
claim that a paper said nothing.

<trailer>"
```

---

### Task 3: Chunking and the canonical rendering

Implements spec §4 and §5 — the sections that decide whether stage 4 can quote a number.

**Files:**
- Create: `claimstone/chunk.py`
- Create: `tests/test_chunk.py`

- [x] **Step 1: Write the failing tests**

Create `tests/test_chunk.py`:

```python
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
```

- [x] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_chunk.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claimstone.chunk'`

- [x] **Step 3: Write `claimstone/chunk.py`**

```python
"""A Document becomes chunks. Every rule with judgement in it lives here.

Two things this module is responsible for getting right.

**What a short section is.** It cannot be read off its length — a first draft of the spec called
all 95 short divs in the measured corpus "captions and fragments" on length alone, and looking at
them showed 28 bare heads, 2 figure notes, and 65 genuine short sections. So the rules ask what a
div *is*: a caption marker makes it a note, no paragraphs at all makes it junk, and anything else
is a real section that merges forward.

**The text a chunk carries.** It is exactly what stage 4 will put in a prompt and exactly what
the quote gate will check a quote against. Rendered once, stored with its hash. Rendering it twice
— once for the prompt, once for the check — would turn any difference between the two renderings
into the rejection of a true claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from claimstone import tei
from claimstone.store import sha256_text

CHUNK_VERSION = 1

PROSE = "prose"
TABLE = "table"
NOTE = "note"

DEFAULT_THRESHOLDS: dict[str, int] = {
    # Below this a div is "short" and rules 1-3 decide what it is.
    "min_section_chars": 800,
    # A section this small is an opening, not a chunk: it merges into its neighbour.
    "merge_below": 1200,
    # The budget for one chunk. Splitting happens at paragraph boundaries, never inside one.
    "max_chunk_chars": 9000,
}

# Matched case-folded against the text following the head, in the style of the content gate's
# paywall phrases. On the measured corpus this catches exactly the two mis-parsed figure notes.
CAPTION_MARKERS = (
    "notes:", "note:", "this table", "this figure", "the figure", "the table",
    "source:", "sources:", "standard errors", "t-statistics",
)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source_id: str
    kind: str
    section: str
    text: str
    text_sha256: str
    oversized: bool = False
    thresholds: dict[str, int] = field(default_factory=dict)

    def as_row(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "kind": self.kind,
            "section": self.section,
            "text": self.text,
            "text_sha256": self.text_sha256,
            "chars": len(self.text),
            "oversized": self.oversized,
            "chunk_version": CHUNK_VERSION,
            "thresholds": dict(self.thresholds),
        }


@dataclass
class ChunkResult:
    chunks: list[Chunk]
    dropped_sections: int = 0
    merged_sections: int = 0
    oversized_chunks: int = 0


def render_section(head: str, paragraphs: tuple[str, ...]) -> str:
    """Head, a blank line, then paragraphs separated by blank lines. Nothing else."""
    body = "\n\n".join(paragraphs)
    return f"{head}\n\n{body}" if head and body else (head or body)


def render_table(table: tei.Table) -> str:
    """Deterministic and declared, because a quote from a table must be able to match.

    Ragged rows are padded to the widest row: in the measured table row 1 has three cells and
    row 3 has two, and a rendering that skipped the missing cell would shift the columns and
    move a number under the wrong heading.
    """
    label = f"Table {table.number}" if table.number else (table.head.rstrip(" :") or "Table")
    heading = f"{label}: {table.caption}".rstrip(": ").strip()
    width = max((len(row) for row in table.rows), default=0)
    lines = [
        "| " + " | ".join(list(row) + [""] * (width - len(row))) + " |"
        for row in table.rows
    ]
    return f"{heading}\n\n" + "\n".join(lines) if lines else heading


def render_notes(notes: tuple[tei.Note, ...]) -> str:
    """Footnotes packed together, each keeping its marker so a quote can be traced back."""
    return "\n\n".join(
        f"[{note.marker}] {note.text}" if note.marker else note.text for note in notes
    )


def _is_note(section: tei.Section) -> bool:
    joined = " ".join(section.paragraphs).lower()
    return any(joined.startswith(marker) for marker in CAPTION_MARKERS)


def _split_paragraphs(paragraphs: tuple[str, ...], budget: int) -> list[tuple[str, ...]]:
    """Pack paragraphs up to the budget. A paragraph is never cut."""
    groups: list[tuple[str, ...]] = []
    current: list[str] = []
    size = 0
    for paragraph in paragraphs:
        if current and size + len(paragraph) > budget:
            groups.append(tuple(current))
            current, size = [], 0
        current.append(paragraph)
        size += len(paragraph) + 2
    if current:
        groups.append(tuple(current))
    return groups or [()]


def chunk_document(
    doc: tei.Document, *, source_id: str, thresholds: dict[str, int] | None = None
) -> ChunkResult:
    """Apply the five rules. Returns the chunks and what happened to what is not there."""
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    result = ChunkResult(chunks=[])
    position = 0

    def emit(kind: str, section_name: str, text: str, *, oversized: bool = False) -> None:
        nonlocal position
        position += 1
        prefix = {PROSE: "c", TABLE: "t", NOTE: "n"}[kind]
        result.chunks.append(
            Chunk(
                chunk_id=f"{source_id}#{prefix}{position}",
                source_id=source_id,
                kind=kind,
                section=section_name,
                text=text,
                text_sha256=sha256_text(text),
                oversized=oversized,
                thresholds=th,
            )
        )

    # Rules 1-3 first: decide what each div is, and carry a merge forward.
    pending: tuple[str, tuple[str, ...]] | None = None
    keep: list[tuple[str, tuple[str, ...]]] = []
    notes_from_divs: list[tei.Section] = []

    for section in doc.sections:
        chars = len(render_section(section.head, section.paragraphs))
        short = chars < th["min_section_chars"]

        if short and section.paragraphs and _is_note(section):
            notes_from_divs.append(section)
            continue
        if short and not section.paragraphs:
            result.dropped_sections += 1
            continue

        head, paragraphs = section.head, section.paragraphs
        if pending is not None:
            head = f"{pending[0]}\n\n{head}".strip()
            paragraphs = pending[1] + paragraphs
            pending = None
            result.merged_sections += 1

        if len(render_section(head, paragraphs)) < th["merge_below"]:
            pending = (head, paragraphs)
            continue
        keep.append((head, paragraphs))

    if pending is not None:
        # Nothing followed it, so it belongs to what came before. Its head travels with it as a
        # line of text: dropping it would lose the provenance of the paragraphs that follow, and
        # the forward merge keeps it.
        if keep:
            head, paragraphs = keep[-1]
            trailing = ((pending[0],) if pending[0] else ()) + pending[1]
            keep[-1] = (head, paragraphs + trailing)
            result.merged_sections += 1
        else:
            keep.append(pending)

    # Rule 4: split what is over budget, at paragraph boundaries.
    for head, paragraphs in keep:
        for group in _split_paragraphs(paragraphs, th["max_chunk_chars"]):
            text = render_section(head, group)
            oversized = len(text) > th["max_chunk_chars"]
            if oversized:
                result.oversized_chunks += 1
            emit(PROSE, head.splitlines()[0] if head else "", text, oversized=oversized)

    # Rule 5: a table is always its own chunk.
    for table in doc.tables:
        emit(TABLE, f"Table {table.number}".strip(), render_table(table))

    # Notes come from two places. GROBID labels real footnotes itself, so those pack into one
    # chunk per document; rule 1 reclassified any div that was a figure note in disguise, and
    # each of those keeps its own head as its section so its provenance survives.
    for section in notes_from_divs:
        note = tei.Note(marker=section.head, text=" ".join(section.paragraphs))
        emit(NOTE, section.head, render_notes((note,)))
    if doc.notes:
        emit(NOTE, "footnotes", render_notes(doc.notes))

    return result


def chunks(
    doc: tei.Document, *, source_id: str, thresholds: dict[str, int] | None = None
) -> list[Chunk]:
    return chunk_document(doc, source_id=source_id, thresholds=thresholds).chunks
```

- [x] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_chunk.py -q`
Expected: PASS, 19 passed

- [x] **Step 5: Commit**

```bash
git add claimstone/chunk.py tests/test_chunk.py
git commit -m "chunk: ask what a div is, not how long it is

Length is not the signal. A first draft of the spec called all 95 short divs in the
measured corpus captions and fragments on length alone; they are 28 bare heads, 2
figure notes, and 65 genuine short sections. So a caption marker makes a note, no
paragraphs at all makes junk, and anything else is a real section that merges
forward — forward because a short "II. Short-Horizon Return" heading opens what
follows rather than closing what came before.

The table rendering is exact and tested byte for byte, with ragged rows padded to
the widest. In the measured table row 1 has three cells and row 3 has two; skipping
the missing cell would shift the columns and put a number under the wrong heading,
and a claim would then quote the wrong figure.

A paragraph is never cut. One longer than the budget is emitted oversized and says
so, because splitting mid-sentence is what the whole section rule exists to avoid.

<trailer>"
```

---

### Task 4: The HTML path

Implements the second parser, before the orchestration that will call it.

Spec §1 counts **14 of 25** as the honest figure. The corpus holds 15 obtained sources: 14 PDFs and
one HTML full text, `IND001`, a Credit Suisse 424B2 prospectus supplement filed on EDGAR, 247,993 characters by the content gate's count. An earlier draft of this
plan had orchestration record every non-PDF as `NOT_PDF`, which would have reported **13** once
`IND008` was correctly rejected — dropping a real document, silently. A review caught the
contradiction between the two documents, and the fix is a parser rather than a state.

The confirmation rule already anticipates this case. Its second clause — long enough to stand
without a bibliography — is exactly what a regulatory filing is. What was missing is a `Document`
to apply it to.

**Files:**
- Create: `claimstone/html_doc.py`
- Create: `tests/test_html_doc.py`

- [x] **Step 1: Write the failing tests**

Create `tests/test_html_doc.py`:

```python
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
```

- [x] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_html_doc.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claimstone.html_doc'`

- [x] **Step 3: Write `claimstone/html_doc.py`**

```python
"""HTML into the same `Document` that `tei.py` produces.

Some sources have no PDF and are still documents — a regulatory filing, a technical standard, an
agency page. Recording them as `NOT_PDF` drops a real document out of the corpus count, which is
what the first draft of stage 3 did to a 247,993-character EDGAR prospectus supplement.

This produces the same dataclasses as `tei.py`, so `chunk.py` and the confirmation rule do not
know or care which parser they came from. It extracts **no references and no footnotes**: a filing
has no bibliography, and the confirmation rule's second clause — long enough to stand without a
reference list — is what admits these documents honestly.

It does extract tables. This plan originally said it would not, on the reasoning that a filing's
tables need the work TEI tables already received — written before anyone opened the file. See D20:
140 tables hold 18% of its characters, and not extracting them does not leave them out, because
`td` is a block and every cell then arrives as its own prose paragraph.
"""

from __future__ import annotations

from html.parser import HTMLParser

from claimstone.tei import Document, Section, TeiError

_SKIP = frozenset({"script", "style", "nav", "header", "footer", "aside", "noscript"})
_HEADINGS = ("h1", "h2", "h3")
_BLOCKS = ("p", "li", "dd", "blockquote")


class _Reader(HTMLParser):
    """Headings open sections; block elements inside them become paragraphs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.sections: list[tuple[str, list[str]]] = []
        self._muted = 0
        self._sink: list[str] | None = None
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag in _SKIP:
            self._muted += 1
            return
        if tag == "title":
            self._in_title = True
            return
        if tag in _HEADINGS:
            self.sections.append(("", []))
            self._sink = None
        elif tag in _BLOCKS:
            self._sink = None

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP and self._muted:
            self._muted -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in _HEADINGS or tag in _BLOCKS:
            self._sink = None

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text or self._muted:
            return
        if self._in_title:
            self.title = f"{self.title} {text}".strip()
            return
        if not self.sections:
            # Text before any heading belongs to an unnamed opening section.
            self.sections.append(("", []))
        head, paragraphs = self.sections[-1]
        if not head:
            # The first text after a heading tag *is* the heading.
            self.sections[-1] = (text, paragraphs)
        else:
            paragraphs.append(text)

    def document(self) -> Document:
        sections = tuple(
            Section(head=head if paragraphs else "", paragraphs=tuple(paragraphs))
            if paragraphs or head
            else Section(head="", paragraphs=())
            for head, paragraphs in self.sections
        )
        return Document(
            title=self.title,
            abstract="",
            sections=tuple(s for s in sections if s.head or s.paragraphs),
            tables=(),
            notes=(),
            references=(),
        )


def parse(payload: bytes) -> Document:
    """Markup in, the same Document a TEI parse produces. Raises when there is no text."""
    reader = _Reader()
    try:
        reader.feed(payload.decode("utf-8", "replace"))
    except Exception:
        # Malformed markup is ordinary on the web and is not itself a verdict; take what parsed.
        pass
    doc = reader.document()
    if not any(section.paragraphs for section in doc.sections):
        raise TeiError("no text found in the markup: nothing to chunk")
    return doc
```

The heading handling deserves a note: a heading element's own text arrives as the first data after
its start tag, which is why `handle_data` treats the first text of a freshly opened section as the
head. It is the simplest rule that keeps `<h1>Item 1</h1><p>body</p>` and
`<h1><span>Item 1</span></h1><p>body</p>` behaving the same.

- [x] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_html_doc.py -q`
Expected: PASS, 7 passed

- [x] **Step 5: Commit**

```bash
git add claimstone/html_doc.py tests/test_html_doc.py
git commit -m "html_doc: a source without a PDF can still be a document

An earlier draft of this plan had normalize record every non-PDF as NOT_PDF, which
drops a 247,993-character EDGAR prospectus supplement out of the corpus and turns 14 of 25
into 13 with nobody noticing.

This produces the same dataclasses tei does, so chunking and confirmation cannot tell
which parser they came from. It extracts no references and no footnotes: a filing has
no bibliography, which is precisely the case the confirmation rule's second clause
exists for. It does extract tables, against this plan's original decision — see D20.

<trailer>"
```

---

### Task 5: Orchestration and the three ledgers

Implements spec §6 and §7's idempotence.

**Files:**
- Create: `claimstone/normalize.py`
- Create: `tests/test_normalize.py`
- Modify: `claimstone/config.py`

- [x] **Step 1: Add the `normalize:` thresholds to `claimstone/config.py`**

Beside `load_gate_thresholds`, which this mirrors:

```python
NORMALIZE_THRESHOLD_NAMES = (
    "min_section_chars", "merge_below", "max_chunk_chars",
    "min_references", "confirm_chars",
)


def load_normalize_thresholds(root: pathlib.Path) -> dict[str, int]:
    """Per-project overrides for chunking and confirmation. Absent means engine defaults.

    A misspelt key is an error rather than a silent no-op, for the same reason as the gate's:
    a threshold the operator believed they had changed produces a figure they would trust
    wrongly.
    """
    raw = _read_yaml(pathlib.Path(root) / "sources.yaml").get("normalize") or {}
    if not isinstance(raw, dict):
        raise ConfigError("sources.yaml: 'normalize' must be a mapping")
    unknown = sorted(set(raw) - set(NORMALIZE_THRESHOLD_NAMES))
    if unknown:
        raise ConfigError(
            f"sources.yaml: unknown normalize threshold(s): {', '.join(unknown)} "
            f"(known: {', '.join(NORMALIZE_THRESHOLD_NAMES)})"
        )
    for name, value in raw.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ConfigError(f"sources.yaml: normalize.{name} must be a non-negative integer")
    return {str(k): int(v) for k, v in raw.items()}
```

Add `normalize_thresholds: dict[str, int] = field(default_factory=dict)` to `Project`, and set it
in `load_project` with `normalize_thresholds=load_normalize_thresholds(path)`.

- [x] **Step 2: Write the failing tests**

Create `tests/test_normalize.py`:

```python
"""Orchestration: GROBID, the TEI on disk, the three ledgers."""

import pytest

from claimstone import normalize
from claimstone.store import Store
from tests.test_tei import DOC

# `DOC` has two references and 87 body characters, so it satisfies neither clause of the
# confirmation rule. A test that needed a confirmed document and used it anyway would be testing
# a rule nobody runs. `PAPER` is `DOC` with three more references, and it confirms for a stated
# reason: five references, not enough text.
PAPER = DOC.replace(
    b"</listBibl>",
    b"".join(
        b"<biblStruct><monogr><title level=\"m\">Filler study %d</title>"
        b"<imprint><date type=\"published\" when=\"20%02d\"/></imprint></monogr></biblStruct>" % (n, n)
        for n in range(10, 13)
    ) + b"</listBibl>",
)


class FakeGrobid:
    """Returns prepared TEI. Counts calls, so idempotence is observable."""

    def __init__(self, tei_by_call=None, tei=PAPER):
        self.tei, self.tei_by_call = tei, tei_by_call or {}
        self.calls = 0

    def is_alive(self):
        return True

    def full_text(self, pdf, *, filename="document.pdf"):
        self.calls += 1
        return self.tei_by_call.get(self.calls, self.tei)


FACT_SHEET = """<?xml version="1.0"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
  <div><head>Key use cases</head><p>Proactively detect and manage market abuse.</p></div>
  <div><head>Find out more</head><p>Contact your account manager today.</p></div>
</body></text></TEI>
""".encode()


def _store(tmp_path, rows):
    store = Store("t", base=tmp_path)
    for row in rows:
        store.append("acquisitions.jsonl", row)
    return store


def acquired(source_id, store, body=b"%PDF-1.4 fake", klass="ACA"):
    digest, path = store.store_bytes(body, ".pdf")
    return {"candidate_key": f"k:{source_id}", "source_id": source_id, "source_class": klass,
            "acquired": True, "sha256": digest, "stored_path": str(path),
            "content_type": "application/pdf", "url": f"https://x.example/{source_id}",
            "gate": {"kind": "PDF_FULLTEXT"}}


def test_a_document_produces_chunks_and_a_documents_row(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store))
    rows = list(normalize.run(store, FakeGrobid()))
    assert rows[0]["fulltext_confirmed"] is True
    assert rows[0]["chunks"] > 0
    assert len(list(store.read("chunks.jsonl"))) == rows[0]["chunks"]


def test_the_tei_is_stored_content_addressed(tmp_path):
    import pathlib

    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store))
    row = next(iter(normalize.run(store, FakeGrobid())))
    assert pathlib.Path(row["tei_path"]).exists()


def test_the_same_bytes_are_never_normalized_twice(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store))
    grobid = FakeGrobid()
    list(normalize.run(store, grobid))
    again = list(normalize.run(store, grobid))
    assert again == []
    assert grobid.calls == 1


def test_force_re_normalizes_without_calling_grobid_again(tmp_path):
    # The TEI is already on disk, so a chunk_version bump needs no network — the same
    # arrangement as regate.
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store))
    grobid = FakeGrobid()
    list(normalize.run(store, grobid))
    rows = list(normalize.run(store, grobid, force=True))
    assert len(rows) == 1
    assert grobid.calls == 1


def test_a_fact_sheet_is_not_confirmed_and_produces_no_chunks(tmp_path):
    # Measured: IND008 is a vendor fact sheet with 1 reference and 4,377 characters of prose. It
    # passed stage 2 because that gate is structural, and this is the signal stage 2 promised.
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("IND008", store))
    row = next(iter(normalize.run(store, FakeGrobid(tei=FACT_SHEET))))
    assert row["fulltext_confirmed"] is False
    assert row["failure_class"] == "NOT_A_DOCUMENT"
    assert row["chunks"] == 0
    assert list(store.read("chunks.jsonl")) == []


def test_the_confirmation_reason_names_both_counts(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("IND008", store))
    row = next(iter(normalize.run(store, FakeGrobid(tei=FACT_SHEET))))
    assert "0 references" in row["reason"]
    assert "body_chars" in row["reason"]


def test_references_are_deduplicated_across_documents_with_a_count(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store, body=b"%PDF one"))
    store.append("acquisitions.jsonl", acquired("S02", store, body=b"%PDF two"))
    list(normalize.run(store, FakeGrobid()))
    refs = store.latest_by("references.jsonl", "key")
    talk = refs["title:is all that talk just noise"]
    assert sorted(talk["cited_by"]) == ["S01", "S02"]
    assert talk["citations_in_corpus"] == 2
    assert talk["doi"] == "10.1111/j.1540-6261.2004.00662.x"


def test_an_unacquired_source_is_not_attempted(tmp_path):
    store = _store(tmp_path, [{"candidate_key": "k", "source_id": "S09", "acquired": False,
                               "failure_class": "PAYWALL_403"}])
    assert list(normalize.run(store, FakeGrobid())) == []


FILING_HTML = """<html><head><title>FORM 10-K</title></head><body>
  <h1>Item 1. Business</h1>
  <p>%s</p>
</body></html>""" % ("The registrant operates a service. " * 600)


def test_a_long_html_document_is_confirmed(tmp_path):
    # IND001 in the real corpus: an EDGAR prospectus supplement, 247,993 characters by the
    # content gate's count, with no bibliography. The
    # confirmation rule's second clause is for exactly this, and marking it NOT_PDF dropped a
    # real document out of the count.
    store = Store("t", base=tmp_path)
    row = acquired("IND001", store, body=FILING_HTML.encode())
    row["content_type"] = "text/html"
    store.append("acquisitions.jsonl", row)
    result = next(iter(normalize.run(store, FakeGrobid())))
    assert result["fulltext_confirmed"] is True
    assert result["chunks"] > 0
    assert result["failure_class"] is None


def test_a_short_html_document_is_not_confirmed(tmp_path):
    store = Store("t", base=tmp_path)
    row = acquired("NEW009", store, body=b"<html><body><p>A brief note.</p></body></html>")
    row["content_type"] = "text/html"
    store.append("acquisitions.jsonl", row)
    result = next(iter(normalize.run(store, FakeGrobid())))
    assert result["fulltext_confirmed"] is False
    assert result["failure_class"] == "NOT_A_DOCUMENT"


def test_html_does_not_call_grobid(tmp_path):
    # GROBID reads PDFs. Sending it markup would be a request that cannot succeed.
    store = Store("t", base=tmp_path)
    row = acquired("IND001", store, body=FILING_HTML.encode())
    row["content_type"] = "text/html"
    store.append("acquisitions.jsonl", row)
    grobid = FakeGrobid()
    list(normalize.run(store, grobid))
    assert grobid.calls == 0


def test_malformed_tei_is_recorded_not_raised(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store))
    row = next(iter(normalize.run(store, FakeGrobid(tei=b"<TEI><body>unclosed"))))
    assert row["fulltext_confirmed"] is False
    assert row["failure_class"] == "TEI_UNREADABLE"
```

- [x] **Step 3: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_normalize.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claimstone.normalize'`

- [x] **Step 4: Write `claimstone/normalize.py`**

```python
"""Stage 3 — normalize: bytes become chunks, and a PDF that is not a document says so.

Three ledgers, owned here and written by nothing else: `documents.jsonl`, `chunks.jsonl` and
`references.jsonl`.

The confirmation rule has the same shape as the content gate's HTML rule, because it is the same
question asked of a different format: does this argue from evidence, or is it a page about a
product? A document with no reference list and little text is the PDF twin of an abstract page,
and stage 2's gate cannot see it — which is exactly what that spec said stage 3 would send back.
"""

from __future__ import annotations

import datetime as _dt
import pathlib
from typing import Any, Iterator

from claimstone import chunk as chunking
from claimstone import html_doc, tei
from claimstone.store import Store

CONFIRM_DEFAULTS: dict[str, int] = {
    # The lowest legitimate reference count in the measured corpus is 9 (MET005); the fact
    # sheet has 0.
    "min_references": 5,
    # A long document without a reference list is still a document — a regulatory filing, say.
    "confirm_chars": 15000,
}

NOT_A_DOCUMENT = "NOT_A_DOCUMENT"
TEI_UNREADABLE = "TEI_UNREADABLE"
# Not a verdict about the source. It writes no `documents.jsonl` row, so admissibility leaves the
# source awaiting: the ceiling rises, the figure does not move, and the round cannot certify itself
# until someone looks. Recording it as unconfirmed instead would count an absent file as an
# established negative and lower the rate on an infrastructure failure.
ARTIFACT_UNREADABLE = "ARTIFACT_UNREADABLE"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def confirm(doc: tei.Document, thresholds: dict[str, int]) -> tuple[bool, str]:
    """Is this a document? Same rule shape as the HTML gate, on a different format."""
    references = len(doc.references)
    body_chars = doc.body_chars
    if references >= thresholds["min_references"]:
        return True, f"{references} references"
    if body_chars >= thresholds["confirm_chars"]:
        return True, f"{body_chars} body_chars without a reference list"
    return False, (
        f"{references} references and body_chars {body_chars}: below both "
        f"min_references {thresholds['min_references']} and "
        f"confirm_chars {thresholds['confirm_chars']}"
    )


def _acquired(store: Store) -> list[dict[str, Any]]:
    from claimstone import admissibility

    return [row for row in admissibility.collapse(store).values() if row.get("acquired")]


def _reference_rows(store: Store) -> dict[str, dict[str, Any]]:
    return store.latest_by("references.jsonl", "key")


def run(
    store: Store,
    grobid: Any,
    *,
    thresholds: dict[str, int] | None = None,
    force: bool = False,
    limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Normalize every acquired source not already done. Idempotent by content hash."""
    th = {**chunking.DEFAULT_THRESHOLDS, **CONFIRM_DEFAULTS, **(thresholds or {})}
    done = {
        str(row.get("sha256"))
        for row in store.latest_by("documents.jsonl", "source_id").values()
    }
    references = _reference_rows(store)
    attempted = 0

    for source in _acquired(store):
        if limit is not None and attempted >= limit:
            return
        digest = str(source.get("sha256") or "")
        source_id = str(source.get("source_id") or source.get("candidate_key"))
        if digest in done and not force:
            continue

        common = {
            "source_id": source_id,
            "sha256": digest,
            "source_class": source.get("source_class"),
            "normalized_at": _now(),
        }
        stored = source.get("stored_path") or source.get("stored_at")

        # Decided on the recorded content type, not on the stored suffix: the suffix is chosen
        # by acquire from that same type, so reading it back would just be the answer twice.
        is_pdf = "pdf" in str(source.get("content_type") or "").lower()
        tei_path = store.root / "tei" / f"{digest}.xml"

        if is_pdf:
            if tei_path.exists():
                payload = tei_path.read_bytes()
            else:
                payload = grobid.full_text(pathlib.Path(stored).read_bytes(),
                                           filename=f"{source_id}.pdf")
                tei_path.parent.mkdir(parents=True, exist_ok=True)
                tei_path.write_bytes(payload)
            parse, parsed_from = tei.parse, str(tei_path)
        else:
            # GROBID reads PDFs; handing it markup is a request that cannot succeed. And a source
            # without a PDF is still a document — the confirmation rule's second clause, long
            # enough to stand without a bibliography, is what admits a regulatory filing.
            payload = pathlib.Path(stored).read_bytes()
            parse, parsed_from = html_doc.parse, str(stored)

        try:
            doc = parse(payload)
        except tei.TeiError as exc:
            row = common | {"fulltext_confirmed": False, "failure_class": TEI_UNREADABLE,
                            "reason": str(exc)[:200], "chunks": 0, "tei_path": parsed_from}
            store.append("documents.jsonl", row)
            attempted += 1
            yield row
            continue

        confirmed, reason = confirm(doc, th)
        result = chunking.chunk_document(doc, source_id=source_id, thresholds=th) if confirmed \
            else chunking.ChunkResult(chunks=[])

        for one in result.chunks:
            store.append("chunks.jsonl", one.as_row())

        if confirmed:
            for reference in doc.references:
                if not reference.key:
                    continue
                held = references.get(reference.key)
                cited_by = sorted(set((held or {}).get("cited_by", [])) | {source_id})
                references[reference.key] = {
                    "key": reference.key,
                    "title": reference.title,
                    "year": reference.year,
                    "authors": list(reference.authors),
                    "doi": reference.doi or (held or {}).get("doi"),
                    "cited_by": cited_by,
                    "citations_in_corpus": len(cited_by),
                    "seen_at": _now(),
                }
                store.append("references.jsonl", references[reference.key])

        row = common | {
            "tei_path": parsed_from,
            "format": "pdf" if is_pdf else "html",
            "fulltext_confirmed": confirmed,
            "failure_class": None if confirmed else NOT_A_DOCUMENT,
            "reason": reason,
            "title": doc.title,
            "body_chars": doc.body_chars,
            "references": len(doc.references),
            "tables": len(doc.tables),
            "notes": len(doc.notes),
            "chunks": len(result.chunks),
            "dropped_sections": result.dropped_sections,
            "merged_sections": result.merged_sections,
            "oversized_chunks": result.oversized_chunks,
            "chunk_version": chunking.CHUNK_VERSION,
            "thresholds": {k: th[k] for k in sorted(th)},
        }
        store.append("documents.jsonl", row)
        done.add(digest)
        attempted += 1
        yield row
```

- [x] **Step 5: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_normalize.py -q`
Expected: PASS, 12 passed

- [x] **Step 6: Commit**

```bash
git add claimstone/normalize.py claimstone/config.py tests/test_normalize.py
git commit -m "normalize: three ledgers, and a fact sheet that says it is not a document

The confirmation rule has the HTML gate's shape because it is the same question on
a different format: references, or enough text to stand without them. Measured, the
lowest legitimate reference count is 8 and the vendor fact sheet has 0, so it
confirms as NOT_A_DOCUMENT, produces no chunks, and stays counted rather than
disappearing.

Idempotent by content hash, and --force re-chunks without calling GROBID because
the TEI is already on disk — the same arrangement as regate. Malformed TEI is
recorded, never raised: an empty document standing in for an unreadable one is a
claim that a paper said nothing.

<trailer>"
```

---

### Task 6: The confirmation sweep

Implements spec §6's "the thresholds are sweepable".

**Files:**
- Modify: `claimstone/normalize.py`
- Modify: `tests/test_normalize.py`

- [x] **Step 1: Write the failing tests**

Append to `tests/test_normalize.py`:

```python
def test_the_confirm_sweep_reports_a_count_per_threshold_value(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store, body=b"%PDF one"))
    store.append("acquisitions.jsonl", acquired("IND008", store, body=b"%PDF two"))
    list(normalize.run(store, FakeGrobid(tei_by_call={1: DOC, 2: FACT_SHEET})))
    points = normalize.confirm_sweep(store, "min_references", [1, 2, 5, 40])
    assert [p["value"] for p in points] == [1, 2, 5, 40]
    assert points[0]["confirmed"] == 1      # DOC has 2 references, the fact sheet none
    assert points[-1]["confirmed"] == 0     # nothing has 40


def test_the_sweep_opens_no_socket_and_calls_no_grobid(tmp_path, monkeypatch):
    import socket

    store = Store("t", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store))
    list(normalize.run(store, FakeGrobid()))

    def refuse(*args, **kwargs):
        raise AssertionError("the sweep must re-read the TEI on disk, not the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    normalize.confirm_sweep(store, "confirm_chars", [1000, 50000])


def test_an_unknown_threshold_is_refused(tmp_path):
    store = Store("t", base=tmp_path)
    with pytest.raises(ValueError, match="nonsense"):
        normalize.confirm_sweep(store, "nonsense", [1])
```

- [x] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_normalize.py -q -k sweep`
Expected: FAIL with `AttributeError: module 'claimstone.normalize' has no attribute 'confirm_sweep'`

- [x] **Step 3: Append to `claimstone/normalize.py`**

```python
def confirm_sweep(store: Store, name: str, values: list[int]) -> list[dict[str, Any]]:
    """How many documents confirm as one threshold moves. Re-reads the TEI; no network.

    `min_references: 5` and `confirm_chars: 15000` were chosen by looking at fourteen
    documents. Two constants chosen at a desk are two constants to interrogate, and the TEI is
    on disk under its hash, so interrogating them is free — the same arrangement as gate-audit.
    """
    if name not in CONFIRM_DEFAULTS:
        raise ValueError(f"unknown threshold {name!r}: {sorted(CONFIRM_DEFAULTS)}")

    parsed: list[tei.Document] = []
    missing = 0
    for row in store.latest_by("documents.jsonl", "source_id").values():
        path = pathlib.Path(str(row.get("tei_path") or ""))
        if not path.exists():
            missing += 1
            continue
        # The parser follows the recorded format, never the stored suffix. Handing markup to the TEI
        # parser would count the one source confirmed by characters as unreadable, and a sweep of
        # `confirm_chars` that excludes it would report that the threshold decides nothing.
        parse = html_doc.parse if row.get("format") == "html" else tei.parse
        try:
            parsed.append(parse(path.read_bytes()))
        except tei.TeiError:
            missing += 1

    points = []
    for value in values:
        th = {**CONFIRM_DEFAULTS, name: value}
        confirmed = sum(1 for doc in parsed if confirm(doc, th)[0])
        points.append({
            "value": value,
            "confirmed": confirmed,
            "documents": len(parsed),
            # Counted, not hidden: a TEI that cannot be re-read is a gap in the audit, and an
            # audit that silently skips what it cannot read reports a cleaner corpus than exists.
            "unreadable": missing,
        })
    return points
```

- [x] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_normalize.py -q`
Expected: PASS, 13 passed

- [x] **Step 5: Commit**

```bash
git add claimstone/normalize.py tests/test_normalize.py
git commit -m "normalize: the confirmation thresholds are sweepable too

min_references and confirm_chars were chosen by looking at fourteen documents. The
TEI is on disk under its hash and parsing does no I/O, so asking whether those
constants decide anything costs nothing — the same arrangement gate-audit uses, for
the same reason. A TEI that cannot be re-read is counted as unreadable rather than
skipped: an audit that drops what it cannot read reports a cleaner corpus than
exists.

<trailer>"
```

---

### Task 7: Verify the confirmed basis against real documents

Implements spec §7's report lines — **most of which already exist.**

`admissibility.rate()` gained `confirmed`, `awaiting_normalize`, `not_a_document` and `basis` in
commit `7490f6d`, alongside a separate fix: the denominator became the candidate set rather than
the acquisition rows, because dividing by acquisitions let one obtained source out of twenty-five
found report 1.00 and pass an 0.80 floor. `cli._report` prints the whole chain already.

So this task does not build that machinery. It checks that the machinery agrees with what stage 3
actually writes, which nothing has yet verified end to end — `admissibility` was written against
hand-made `documents.jsonl` rows, not against rows `normalize.run()` produced.

**Files:**
- Modify: `tests/test_normalize.py`

- [x] **Step 1: Write the failing test**

Append to `tests/test_normalize.py`:

```python
def test_the_confirmed_rate_matches_what_normalize_wrote(tmp_path):
    """End to end: acquire's ledger, normalize's verdicts, admissibility's arithmetic.

    Each side was tested against fixtures of the other's shape. This asserts they agree on rows
    one of them really produced — which is where a field name or a join key silently diverges.
    """
    from claimstone import admissibility
    from claimstone.config import load_project

    store = Store("t", base=tmp_path)
    for source_id, body in (("S01", b"%PDF one"), ("S02", b"%PDF two"),
                            ("IND008", b"%PDF three")):
        acq = acquired(source_id, store, body=body)
        store.append("candidates.jsonl", {"candidate_key": acq["candidate_key"],
                                          "source_id": source_id, "source_class": "ACA"})
        store.append("acquisitions.jsonl", acq)
    # Two real documents and one vendor fact sheet.
    list(normalize.run(store, FakeGrobid(tei_by_call={1: DOC, 2: DOC, 3: FACT_SHEET})))

    result = admissibility.rate(store)
    assert result["found"] == 3
    assert result["obtained"] == 3
    assert result["confirmed"] == 2
    assert result["basis"] == "confirmed"
    assert result["not_a_document"] == ["IND008"]
    assert result["awaiting_normalize"] == 0
    assert result["rate"] == 2 / 3


def test_a_source_normalize_has_not_reached_is_not_counted_against_the_corpus(tmp_path):
    from claimstone import admissibility

    store = Store("t", base=tmp_path)
    for source_id in ("S01", "S02"):
        acq = acquired(source_id, store, body=f"%PDF {source_id}".encode())
        store.append("candidates.jsonl", {"candidate_key": acq["candidate_key"],
                                          "source_id": source_id, "source_class": "ACA"})
        store.append("acquisitions.jsonl", acq)
    list(normalize.run(store, FakeGrobid(), limit=1))

    result = admissibility.rate(store)
    # One normalized and confirmed, one not reached. Counting the second as unconfirmed would
    # make the rate fall because stage 3 had not finished — measuring our progress and calling
    # it a property of the corpus.
    assert result["confirmed"] == 2
    assert result["awaiting_normalize"] == 1
```

- [x] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_normalize.py -q -k "confirmed_rate or has_not_reached"`
Expected: FAIL. The likely cause is the join key: `admissibility` looks up `documents.jsonl` by
`source_id`, and `normalize.run()` must write that field with the same value the acquisition row
carries. If the test fails on `not_a_document == []`, that join is what to fix.

- [x] **Step 3: Make them pass**

No new module. Reconcile whichever side is wrong:

- If `normalize.run()` writes a `source_id` that differs from the acquisition row's, fix
  `normalize.run()` — the acquisition row is the authority, since `acquire` wrote it from the
  candidate.
- If `admissibility.confirmations()` keys on the wrong field, fix that.

Do not make the test pass by loosening the assertion. The number this produces is the project's
headline figure.

- [x] **Step 4: Run the whole suite**

Run: `.venv/bin/pytest -q`
Expected: PASS, all tests

- [x] **Step 5: Commit**

```bash
git add tests/test_normalize.py claimstone/normalize.py claimstone/admissibility.py
git commit -m "normalize: the confirmed rate agrees with the rows normalize really writes

Both sides were tested against fixtures shaped like the other. This joins them on
rows one of them actually produced, which is where a field name or a join key
diverges without any test noticing.

<trailer>"
```

### Task 8: Wiring the CLI

Implements spec §7's commands.

**Files:**
- Modify: `claimstone/cli.py`
- Create: `tests/test_cli_normalize.py`

- [x] **Step 1: Write the failing tests**

Create `tests/test_cli_normalize.py`:

```python
"""normalize and --confirm-audit at the command line."""

from claimstone.cli import build_parser, main


def test_normalize_is_no_longer_a_placeholder():
    args = build_parser().parse_args(["normalize", "projects/example-news-and-returns"])
    assert args.func.__name__ != "_not_implemented"


def test_a_dead_grobid_is_reported_with_the_workaround(tmp_path, capsys, monkeypatch):
    from claimstone import grobid

    monkeypatch.setattr(grobid.Grobid, "is_alive", lambda self: False)
    code = main(["normalize", "projects/example-news-and-returns", "--store", str(tmp_path)])
    assert code == 2
    error = capsys.readouterr().err
    assert "JAVA_TOOL_OPTIONS=-XX:-UseContainerSupport" in error
    assert "cgroup v2" in error


def test_progress_goes_to_stderr_and_the_summary_to_stdout(tmp_path, capsys, monkeypatch):
    from claimstone import cli, normalize

    monkeypatch.setattr(
        normalize, "run",
        lambda *a, **k: iter([
            {"source_id": "S01", "fulltext_confirmed": True, "chunks": 5, "references": 41,
             "tables": 8, "body_chars": 36137, "reason": "41 references"},
            {"source_id": "IND008", "fulltext_confirmed": False, "chunks": 0, "references": 0,
             "tables": 1, "body_chars": 4618, "failure_class": "NOT_A_DOCUMENT",
             "reason": "0 references and body_chars 4618"},
        ]),
    )
    monkeypatch.setattr("claimstone.grobid.Grobid.is_alive", lambda self: True)
    cli.main(["normalize", "projects/example-news-and-returns", "--store", str(tmp_path)])
    captured = capsys.readouterr()
    assert "S01" in captured.err and "IND008" in captured.err
    assert "S01" not in captured.out
    assert "1 confirmed" in captured.out


def test_confirm_audit_does_not_need_grobid(tmp_path, capsys, monkeypatch):
    from claimstone import grobid

    monkeypatch.setattr(grobid.Grobid, "is_alive", lambda self: False)
    code = main(["normalize", "projects/example-news-and-returns", "--confirm-audit",
                 "--store", str(tmp_path)])
    assert code == 0
    assert "no documents" in capsys.readouterr().out
```

- [x] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_cli_normalize.py -q`
Expected: FAIL — `normalize` is still bound to `_not_implemented`

- [x] **Step 3: Add the handler to `claimstone/cli.py`**

```python
# The boundaries the corpus actually separates at are 1 vs 2 references and 4,377 vs 4,378
# characters, so both ranges reach below the default: an audit whose lowest value already confirms
# everything reports "flat" without ever finding the edge. See D21.
CONFIRM_SWEEP_VALUES = {
    "min_references": [1, 2, 3, 5, 8, 12, 20],
    "confirm_chars": [2000, 5000, 10000, 15000, 25000, 40000],
}


def _normalize(args: argparse.Namespace) -> int:
    from claimstone import grobid as grobid_mod
    from claimstone import normalize
    from claimstone.store import Store

    project = load_project(args.project)
    store = Store(project.name, base=args.store)

    if args.confirm_audit:
        # No GROBID and no network: the TEI is on disk under its hash.
        name = args.sweep or "min_references"
        points = normalize.confirm_sweep(store, name, CONFIRM_SWEEP_VALUES[name])
        if not points or not points[0]["documents"]:
            print(f"{project.name}: no documents normalized yet")
            return 0
        print(f"{name:<18}" + "".join(f"{p['value']:>8}" for p in points))
        print(f"{'confirmed':<18}" + "".join(f"{p['confirmed']:>8}" for p in points))
        counts = [p["confirmed"] for p in points]
        total = points[0]["documents"]
        if max(counts) - min(counts) > 1:
            print(f"\n  this threshold is deciding confirmation (spread "
                  f"{max(counts) - min(counts)} of {total}) — read the boundary cases by hand")
        else:
            print(f"\n  flat across the range: the chosen value is not load-bearing "
                  f"({total} documents)")
        if points[0]["unreadable"]:
            print(f"  {points[0]['unreadable']} TEI could not be re-read and are excluded")
        return 0

    # The container is not checked up front. `full_text` refuses when GROBID is not answering, and a
    # source whose TEI is already on disk never reaches it — the whole corpus can be re-chunked with
    # nothing running, which is the point of storing the TEI under its hash. Demanding a container
    # that will never be contacted is a wall in front of an offline operation. So the run is stepped
    # and `GrobidUnavailable` is caught, printing the same message and exiting 2.

    done = confirmed = 0
    for row in normalize.run(store, client, thresholds=project.normalize_thresholds,
                             force=args.force, limit=args.limit):
        done += 1
        if row["fulltext_confirmed"]:
            confirmed += 1
            detail = (f"{row['chunks']} chunks, {row['references']} refs, "
                      f"{row['tables']} tables, {row['body_chars']} chars")
        else:
            detail = f"{row.get('failure_class')}  {row.get('reason', '')[:60]}"
        mark = "ok  " if row["fulltext_confirmed"] else "fail"
        print(f"[{done:>3}] {mark}  {row['source_id']:<8} {detail}", file=sys.stderr)
    print(f"{done} normalized, {confirmed} confirmed as documents")
    return 0
```

Register it by adding to the command loop's tuple:

```python
        ("normalize", _normalize, "stage 3: TEI, chunks and references"),
```

and its own flags:

```python
        if name == "normalize":
            command.add_argument("--grobid-url", default=grobid_url_default())
            command.add_argument("--force", action="store_true",
                                 help="re-chunk from the stored TEI; no network")
            command.add_argument("--limit", type=int, default=None)
            command.add_argument("--confirm-audit", action="store_true",
                                 help="sweep a confirmation threshold; needs no GROBID")
            command.add_argument("--sweep", choices=sorted(CONFIRM_SWEEP_VALUES))
```

with, near `BACKENDS`:

```python
def grobid_url_default() -> str:
    import os

    return os.environ.get("CLAIMSTONE_GROBID_URL") or "http://localhost:8070"
```

Finally remove `"normalize"` from `STAGES` so it stops registering a placeholder:

```python
STAGES = ("extract", "review", "synthesize")
```

- [x] **Step 4: Run everything**

Run: `.venv/bin/pytest -q`
Expected: PASS, all tests

Run: `.venv/bin/claimstone normalize --help`
Expected: usage showing `--confirm-audit` and `--grobid-url`

- [x] **Step 5: Commit**

```bash
git add claimstone/cli.py tests/test_cli_normalize.py
git commit -m "cli: normalize, and an audit that does not need the container

Progress on stderr with the per-document counts, summary on stdout. A dead GROBID
exits 2 printing the docker run line and why the JVM flag is there. --confirm-audit
needs no container at all: the TEI is on disk under its hash, so asking whether the
confirmation thresholds decide anything is free.

normalize leaves the placeholder list, which is now extract, review and synthesize.

<trailer>"
```

---

### Task 9: The contract, the real-TEI check, and the spec corrections

Implements spec §8 and lands the four corrections this plan made.

**Files:**
- Create: `docs/contracts/normalize.md`
- Create: `tests/test_real_tei.py`
- Modify: `docs/superpowers/specs/2026-09-24-stage3-normalize-design.md`

- [x] **Step 1: Write `tests/test_real_tei.py`**

```python
"""Run the pure functions over real TEI, when there happens to be any.

The real files cannot live in this repository: they are the full text of copyrighted papers, the
same reason the stage 2 HTML fixtures are synthetic. But when a store is populated, running the
parser and the chunker over it catches what synthetic fixtures cannot — a real paper's structure
is stranger than anything anyone writes by hand.
"""

import pathlib

import pytest

from claimstone import chunk, tei

TEI_FILES = sorted(pathlib.Path("store").glob("*/tei/*.xml"))

pytestmark = pytest.mark.skipif(
    not TEI_FILES, reason="no normalized TEI in store/; run `claimstone normalize` first"
)


@pytest.mark.parametrize("path", TEI_FILES, ids=lambda p: p.parent.parent.name + "/" + p.stem[:8])
def test_every_stored_tei_parses_and_chunks(path):
    doc = tei.parse(path.read_bytes())
    result = chunk.chunk_document(doc, source_id="X")
    for one in result.chunks:
        # The hash must match the text, or stage 4's gate is checking a different string from
        # the one the model was shown.
        from claimstone.store import sha256_text

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
```

- [x] **Step 2: Verify it skips on a clean checkout**

Run: `.venv/bin/pytest tests/test_real_tei.py -q`
Expected: `no tests ran` or all skipped, depending on whether `store/` is populated. Both are
correct; the test states its own precondition.

- [x] **Step 3: Land the three corrections in the spec**

In `docs/superpowers/specs/2026-09-24-stage3-normalize-design.md`:

Add to §1, after the table-fusing paragraph:

> **Figures and notes are siblings of sections.** In `<body>`, `<div>`, `<figure>` and `<note>`
> are all direct children; a `<figure>` never nests inside a `<div>`. So prose extracted from a
> section excludes tables by construction, with no filtering.
>
> **Footnotes are a fourth content source.** `<note place="foot">` children of `<body>`: **103
> across the 14 documents, 19,453 characters**, outside the 775,266 counted above because that
> figure sums paragraphs only. `ACA008`'s single note reads "We obtained similar results
> using other random strings" — a robustness check a claim could rest on. They become
> `kind="note"` chunks, packed per document, each keeping its marker.

In §3, replace the `Document` fields line to include notes, and add:

> A reference's title lives in `analytic/title` for an article and `monogr/title` for a book. A
> bare `.//title` takes whichever comes first, which is right for the first case and silently
> takes the journal name in the second.

In §4, note that rule 1's marker list exists only for **mis-parsed** notes, since GROBID labels
real ones itself.

- [x] **Step 4: Write `docs/contracts/normalize.md`**

```markdown
# `documents.jsonl`, `chunks.jsonl`, `references.jsonl` — the contract

Written by stage 3 (`claimstone normalize`). Append-only. Stage 3 owns all three; no other stage
writes them.

**Stage 4 depends on `chunks.jsonl` and on one property of it: `text` is exactly the string the
model will be shown and exactly the string a quote is checked against.** Rendering it a second
time anywhere would turn a difference between the two renderings into the rejection of a true
claim.

## `documents.jsonl`

One row per normalized document, keyed by `source_id`.

| field | meaning |
|---|---|
| `source_id`, `sha256` | the source, and the hash of the bytes normalized |
| `tei_path` | the TEI under `store/<project>/tei/<sha256>.xml` |
| `fulltext_confirmed` | whether this is a document at all |
| `failure_class` | `NOT_A_DOCUMENT`, `TEI_UNREADABLE`, or null |
| `reason` | the counts that decided it, so the verdict can be argued with |
| `title`, `body_chars`, `references`, `tables`, `notes` | what GROBID found |
| `chunks`, `dropped_sections`, `merged_sections`, `oversized_chunks` | what chunking did |
| `chunk_version`, `thresholds` | under which rules |

A document that does not confirm produces **no chunks** and stays in this file. "We obtained it
and it was not a document" is a different failure from "we never obtained it", with a different
remedy, and collapsing them would hide which one happened.

## `chunks.jsonl`

| field | meaning |
|---|---|
| `chunk_id` | `<source_id>#c3`, `#t1`, `#n1` — prose, table, note |
| `kind` | `prose`, `table`, `note` |
| `section` | the section heading, so a claim's provenance is a place and not an offset |
| `text` | **the canonical text.** What the model sees; what the gate checks |
| `text_sha256`, `chars` | identity and size |
| `oversized` | a single paragraph over budget, emitted whole rather than cut |
| `chunk_version`, `thresholds` | under which rules |

Table text is rendered deterministically: a heading line, a blank line, then one `| a | b |` row
per table row, ragged rows padded to the widest. Padding matters — in the measured corpus row 1
of a table has three cells and row 3 has two, and dropping the gap would shift a number under
the wrong heading.

## `references.jsonl`

| field | meaning |
|---|---|
| `key` | `title:<folded title>` |
| `title`, `year`, `authors` | as GROBID read them |
| `doi` | usually `null`: stage 3 resolves nothing |
| `cited_by`, `citations_in_corpus` | which corpus documents cite it, and how many |

**Stage 3 decides no candidacy.** Which references become candidates belongs to `discover`, and
capture-recapture needs care that is not settled here: the two channels must sample the same
population, and 710 references include statistics textbooks. `citations_in_corpus` is what makes
the question answerable — a work three corpus documents cite is a different kind of candidate
from one a survey cites once.
```

- [x] **Step 5: Run everything and commit**

Run: `.venv/bin/pytest -q` — expected: all pass
Run: `.venv/bin/claimstone validate --all-projects` — expected: OK for both

```bash
git add docs/contracts/normalize.md tests/test_real_tei.py \
        docs/superpowers/specs/2026-09-24-stage3-normalize-design.md
git commit -m "docs: the normalize contract, and the three corrections this plan made

Figures and notes are siblings of sections rather than children, so prose excludes
tables for free. Footnotes are a fourth content source — 103 across the 14
documents, outside the body count because that summed div text only — and they
carry robustness checks a claim could rest on. And a reference's title is in
analytic for an article and monogr for a book, where a bare .//title silently takes
the journal name.

test_real_tei.py runs the parser and chunker over whatever TEI a populated store
holds and skips otherwise. The real files cannot be committed — they are the full
text of copyrighted papers — but a real paper's structure is stranger than anything
written by hand, and the two properties worth asserting are that a chunk's hash
matches its text and that no table cell vanishes in rendering.

<trailer>"
```

---

## What this plan does not do

- **No HTML references.** `html_doc` extracts sections, paragraphs and tables; a filing has no bibliography to extract. It does extract tables, against this plan's original decision — see D20, and the measurement that changed it.
- **No DOI resolution for references** (spec §6). 710 references would be 710 Crossref lookups, and which of them become candidates is `discover`'s declared rule, not stage 3's.
- **No OCR, no formula parsing, no figure images, no citation context** (spec §9). A scanned PDF fails confirmation and says so.
- **No stage 4.** This produces chunks; nothing here builds a prompt or extracts a claim. `model_call` (planned separately) is the boundary that carries them to a model.
