"""HTML into the same `Document` that `tei.py` produces.

Some sources have no PDF and are still documents — a regulatory filing, a technical standard, an
agency page. Recording them as `NOT_PDF` drops a real document out of the corpus count, which is
what the first draft of stage 3 did to a 247,993-character SEC filing.

This produces the same dataclasses as `tei.py`, so `chunk.py` and the confirmation rule do not
know or care which parser they came from. It extracts **no references and no footnotes**: a filing
has no bibliography, and the confirmation rule's second clause — long enough to stand without a
reference list — is what admits these documents honestly.

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

from html.parser import HTMLParser

from claimstone.tei import Document, Section, Table, TeiError

_SKIP = frozenset({"script", "style", "nav", "header", "footer", "aside", "noscript"})
_HEADINGS = frozenset({"h1", "h2", "h3"})
# `div` is here because a filing's prose often sits in bare divs. Flushing at both ends of one
# splits nested divs into separate paragraphs, which is right: gluing a whole filing into a single
# paragraph would put every chunk over budget at once.
_BLOCKS = frozenset({"p", "li", "dd", "dt", "blockquote", "div", "pre"})
_CELLS = frozenset({"td", "th"})


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
