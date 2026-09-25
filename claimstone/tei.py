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
