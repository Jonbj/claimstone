"""HTML into the same `Document` that `tei.py` produces.

Some sources have no PDF and are still documents — a regulatory filing, a technical standard, an
agency page. Recording them as `NOT_PDF` drops a real document out of the corpus count, which is
what the first draft of stage 3 did to a 247,993-character SEC filing.

This produces the same dataclasses as `tei.py`, so `chunk.py` and the confirmation rule do not
know or care which parser they came from. It extracts no footnotes.

**It did extract no references, and that was wrong once the corpus changed.** The original reason —
"a filing has no bibliography, and the confirmation rule's second clause admits these documents
honestly" — was measured against one HTML document, an SEC prospectus. A PMC article in HTML has a
bibliography, and not reading it recorded `0 references` for 32 of 38 documents in the PMC round
while all 6 of its PDFs, parsed by GROBID, reported theirs. It also cost a document: `PMC040`
carries a `ref-list` and a `References` heading and was refused as `NOT_A_DOCUMENT` for "0
references and body_chars 12334". A limitation of this parser had been recorded as a property of
the source, which is the defect shape `ARTIFACT_UNREADABLE` and `BOT_CHALLENGE` were both added for.

So a reference list is read where the markup declares one. Loosely and on purpose: a DOI where the
entry carries one, a year where it is unambiguous, and the entry's text as the title when nothing
better is available. A reference that can be **counted** fixes the confirmation rule; one that can
be **resolved** needs a title or a DOI, and this says which it got rather than inventing the rest.

It does extract tables, against the plan's original decision. That decision was made before anyone
opened the corpus's one HTML document: a Credit Suisse 424B2 prospectus supplement with **140
tables holding 18% of its 247,391 characters**, and 549 of its 1,256 paragraphs under twenty
characters. Leaving tables out does not leave them out — `td` is a block, so every cell arrives as
its own prose paragraph, and a bare "4.2" packed next to unrelated prose is a number a model will
attribute to whatever sentence precedes it. A table goes through `chunk.render_table` and becomes
its own chunk, exactly as a TEI table does.

Two rules earn their place by what they prevent.

**A heading is text inside a heading element, never the first text of a section.** The simpler
rule — "the first text after a section opens is its head" — cannot tell a section opened by an
`<h1>` from one opened because text appeared with no heading at all, and so it turns the only
paragraph of a heading-less document into a heading with no body.

**A paragraph is flushed at block boundaries, not at every text node.** `<p>Hello <b>world</b></p>`
arrives as two data events. Emitting two paragraphs would make a quote spanning the bold word
unmatchable against any chunk, and the quote gate would reject a true claim.
"""

from __future__ import annotations

import re
from dataclasses import replace as _replace
from html.parser import HTMLParser

from claimstone.ids import normalize_doi, normalize_title
from claimstone.tei import Document, Reference, Section, Table, TeiError

# This parser is an instrument, on the same footing as the GROBID image pinned by digest in
# `compose.yaml`: what it extracts decides `body_chars` and `references`, and those decide
# `fulltext_confirmed`. Two documents confirmed under different versions of it are not the same kind of
# row, and a corpus figure that mixes them silently is what `tools/check_instrument_versions.py` exists
# to stop. Rows written before this constant existed carry no `html_parser_version` and are version 1.
#
#   1  sections, paragraphs and tables. No references — "a filing has no bibliography".
#   2  a reference list where the markup declares one, after that reasoning was measured against a
#      corpus of PMC articles and cost `PMC040` its admission.
HTML_PARSER_VERSION = 2

_SKIP = frozenset({"script", "style", "nav", "header", "footer", "aside", "noscript"})
_HEADINGS = frozenset({"h1", "h2", "h3"})
# `div` is here because a filing's prose often sits in bare divs. Flushing at both ends of one
# splits nested divs into separate paragraphs, which is right: gluing a whole filing into a single
# paragraph would put every chunk over budget at once.
_BLOCKS = frozenset({"p", "li", "dd", "dt", "blockquote", "div", "pre"})
_CELLS = frozenset({"td", "th"})


# A container the markup itself declares to be the bibliography. Matched on the attribute rather than
# on a heading's text, because a heading match would also catch a prose section discussing references.
_REF_CONTAINER = re.compile(
    r"""<(ol|ul|section|div)\b[^>]*(?:class|id)\s*=\s*["'][^"']*\b(?:ref-list|reflist|"""
    r"""references|bibliography)\b[^"']*["'][^>]*>(.*?)</\1>""",
    re.I | re.S)

# One entry. A reference list is a list, and the entries that are not `li` are not entries.
_REF_ENTRY = re.compile(r"<li\b[^>]*>(.*?)</li>", re.I | re.S)

_TAGS = re.compile(r"<[^>]+>")
_DOI_IN_TEXT = re.compile(r"\b10\.\d{4,9}/[^\s\"'<>,;)\]]+", re.I)
_YEAR_IN_TEXT = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")

# Enough to be a citation and not a stray list item. Measured on PMC HTML: the shortest real entry in
# the round's reference lists is 41 characters; a navigation `li` is typically under 20.
MIN_REFERENCE_CHARS = 30


def _visible(markup: str) -> str:
    return re.sub(r"\s+", " ", _TAGS.sub(" ", markup)).strip()


def references_from(markup: str) -> tuple[Reference, ...]:
    """The bibliography a page declares, read loosely and honestly.

    A reference that can be **counted** is what the confirmation rule needs; one that can be
    **resolved** needs a title or a DOI. Where only the entry's text is available it becomes the title,
    because inventing a structured citation out of free text is the guessing this project refuses —
    and a reference whose title is its whole entry still counts, and still says so.
    """
    found: list[Reference] = []
    seen: set[str] = set()
    for container in _REF_CONTAINER.finditer(markup):
        for entry in _REF_ENTRY.finditer(container.group(2)):
            text = _visible(entry.group(1))
            if len(text) < MIN_REFERENCE_CHARS or text in seen:
                continue
            seen.add(text)
            doi_match = _DOI_IN_TEXT.search(text)
            doi = normalize_doi(doi_match.group(0).rstrip(".")) if doi_match else None
            years = _YEAR_IN_TEXT.findall(text)
            # Only when the entry names exactly one candidate year. Two is a page range or a volume
            # that looks like a year, and picking one of them would be a coin toss recorded as a fact.
            year = int(years[0]) if len(set(years)) == 1 else None
            folded = normalize_title(text)
            found.append(Reference(
                key=f"doi:{doi}" if doi else (f"title:{folded}" if folded else ""),
                title=text,
                year=year,
                authors=(),
                doi=doi,
            ))
    return tuple(found)


class _Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.sections: list[tuple[str, list[str]]] = []
        self._muted = 0
        self._heading = 0
        self._in_title = False
        self._buffer: list[str] = []
        self.tables: list[tuple[str, list[tuple[str, ...]]]] = []
        # A stack, because EDGAR nests tables for layout. Cells belong to the innermost open one,
        # which closes first, so each level keeps its own rows instead of merging into its parent.
        self._open: list[dict[str, object]] = []
        self._in_caption = False

    def _flush(self) -> None:
        """Whatever has accumulated becomes one paragraph of the current section."""
        if self._open:
            # Text inside a table belongs to a cell, never to the prose around it.
            self._buffer.clear()
            return
        self._flush_into_section()

    def _flush_into_section(self) -> None:
        text = " ".join(self._buffer).strip()
        self._buffer.clear()
        if not text:
            return
        if not self.sections:
            # Text before any heading belongs to an unnamed opening section.
            self.sections.append(("", []))
        self.sections[-1][1].append(text)

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag in _SKIP:
            self._muted += 1
            return
        if tag == "title":
            self._in_title = True
            return
        if tag == "table":
            if not self._open:
                self._flush()
            # A nested table interrupts a cell mid-text. The cell's words are held here and given
            # back when the inner table closes; flushing instead would drop them, and a dropped
            # cell is a number that left the document without anyone recording it.
            frame = {"caption": "", "rows": [], "cells": None, "held": list(self._buffer)}
            self._buffer.clear()
            self._open.append(frame)
        elif tag == "caption" and self._open:
            self._flush()
            self._in_caption = True
        elif tag == "tr" and self._open:
            self._flush()
            self._open[-1]["cells"] = []
        elif tag in _CELLS:
            self._flush()
        elif tag in _HEADINGS:
            self._flush()
            self.sections.append(("", []))
            self._heading += 1
        elif tag in _BLOCKS or tag == "br":
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP:
            self._muted = max(0, self._muted - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in _HEADINGS:
            head = " ".join(self._buffer).strip()
            self._buffer.clear()
            if self.sections:
                self.sections[-1] = (head, self.sections[-1][1])
            self._heading = max(0, self._heading - 1)
        elif tag == "table" and self._open:
            table = self._open.pop()
            self._close_row(table)
            rows = [row for row in table["rows"] if any(cell for cell in row)]
            self._buffer[:] = table["held"]
            if not rows:
                return
            if len(rows) >= 2 and max(len(row) for row in rows) >= 2:
                self.tables.append((str(table["caption"]), rows))
                return
            # A layout box, not a table. Its text is prose and goes back to the section at the
            # position it occupied — dropping it would lose real sentences, and keeping it as a
            # table would make stage 4 pay for a chunk per spacing element. Measured on the
            # corpus's one HTML document: 140 tables, of which 110 are boxes and 104 are 1x3.
            for row in rows:
                for cell in row:
                    if cell:
                        self._buffer.append(cell)
                        self._flush_into_section()
        elif tag == "caption":
            if self._open:
                self._open[-1]["caption"] = " ".join(self._buffer).strip()
            self._buffer.clear()
            self._in_caption = False
        elif tag == "tr" and self._open:
            self._close_row(self._open[-1])
        elif tag in _CELLS and self._open:
            cells = self._open[-1]["cells"]
            if cells is None:
                # A cell outside any row still holds text; give it a row of its own rather than
                # dropping it, so no number leaves the document silently.
                cells = self._open[-1]["cells"] = []
            cells.append(" ".join(self._buffer).strip())
            self._buffer.clear()
        elif tag in _BLOCKS:
            self._flush()

    @staticmethod
    def _close_row(table: dict[str, object]) -> None:
        cells = table["cells"]
        if cells:
            table["rows"].append(tuple(cells))
        table["cells"] = None

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text or self._muted:
            return
        if self._in_title:
            self.title = f"{self.title} {text}".strip()
            return
        self._buffer.append(text)

    def document(self) -> Document:
        self._flush()
        return Document(
            title=self.title,
            abstract="",
            sections=tuple(
                Section(head=head, paragraphs=tuple(paragraphs))
                for head, paragraphs in self.sections
                if head or paragraphs
            ),
            tables=tuple(
                Table(number=str(n), head="", caption=caption, rows=tuple(rows))
                for n, (caption, rows) in enumerate(self.tables, start=1)
            ),
            notes=(),
            references=(),
        )


def parse(payload: bytes) -> Document:
    """Markup in, the same Document a TEI parse produces. Raises when there is no text."""
    markup = payload.decode("utf-8", "replace")
    reader = _Reader()
    try:
        reader.feed(markup)
    except Exception:
        # Malformed markup is ordinary on the web and is not itself a verdict; take what parsed.
        pass
    doc = reader.document()
    if not any(section.paragraphs for section in doc.sections):
        raise TeiError("no text found in the markup: nothing to chunk")
    # From the markup rather than from the reader's stream: a bibliography is a structure, and the
    # streaming pass flattens it into paragraphs like any other list.
    return _replace(doc, references=references_from(markup))
