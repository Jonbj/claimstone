"""JATS XML into the shared Document shape, without I/O or inferred study metadata.

Unsupported tables raise separately from malformed XML: a parser limitation establishes
nothing about the source. Normalization leaves such sources awaiting, rather than confirming
a document whose tabular evidence disappeared.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from claimstone.ids import normalize_doi, normalize_title
from claimstone.tei import Document, Note, Reference, Section, Table, TeiError

JATS_PARSER_VERSION = 2


class JatsError(TeiError):
    """Malformed XML or an input that is not a full-text JATS article."""


class UnsupportedJats(JatsError):
    """Valid structure outside this parser's supported representation."""


def _tag(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _children(node: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in node if _tag(child) == name]


def _first(node: ET.Element, name: str) -> ET.Element | None:
    return next(iter(_children(node, name)), None)


def _text(node: ET.Element | None, exclude: frozenset[str] = frozenset()) -> str:
    if node is None:
        return ""
    def raw(element: ET.Element) -> str:
        parts = [element.text or ""]
        for child in element:
            if _tag(child) not in exclude:
                block = _tag(child) in {"p", "title", "list-item", "break"}
                parts.append((" " if block else "") + raw(child) + (" " if block else ""))
            parts.append(child.tail or "")
        return "".join(parts)
    # Strip once, after inline elements have been joined; stripping each element fuses words.
    return " ".join(raw(node).split())


_SEPARATE = frozenset({"table-wrap", "fig", "fn", "ref-list", "sub-article", "response"})


def _walk(node: ET.Element):
    """Primary article only; bibliography and nested articles are separate evidence."""
    yield node
    for child in node:
        if _tag(child) not in {"ref-list", "sub-article", "response"}:
            yield from _walk(child)


def _sections(node: ET.Element, head: str = "") -> list[Section]:
    result: list[Section] = []
    paragraphs: list[str] = []

    def flush() -> None:
        if paragraphs:
            result.append(Section(head, tuple(paragraphs)))
            paragraphs.clear()

    for child in node:
        name = _tag(child)
        if name in _SEPARATE or name in {"title", "label", "fn-group"}:
            continue
        if name in {"sec", "app"}:
            flush()
            title = _text(_first(child, "title")) or _text(_first(child, "label"))
            section_head = " / ".join(part for part in (head, title) if part)
            result.extend(_sections(child, section_head))
        elif name == "p":
            text = _text(child, _SEPARATE)
            if text:
                paragraphs.append(text)
        else:
            # Lists, quotations, boxes and appendix groups retain paragraph order.
            flush()
            result.extend(_sections(child, head))
    flush()
    return result


def _span(cell: ET.Element, attribute: str) -> int:
    raw = cell.get(attribute, "1")
    if not raw.isdigit() or not 1 <= int(raw) <= 1000:
        raise UnsupportedJats(f"invalid {attribute}: {raw!r}")
    return int(raw)


def _table(wrapper: ET.Element) -> Table:
    tables = [node for node in _walk(wrapper) if _tag(node) == "table"]
    if len(tables) != 1:
        raise UnsupportedJats("table-wrap requires exactly one textual JATS table")
    table = tables[0]
    if any(_tag(node) == "tgroup" for node in table.iter()):
        raise UnsupportedJats("CALS tables are not supported")
    rows = [node for node in table.iter() if _tag(node) == "tr"]
    if not rows:
        raise UnsupportedJats("table contains no textual rows")
    grid: dict[tuple[int, int], str] = {}
    width = 0
    for r, row in enumerate(rows):
        column = 0
        for cell in row:
            if _tag(cell) not in {"td", "th"}:
                continue
            while (r, column) in grid:
                column += 1
            down, across = _span(cell, "rowspan"), _span(cell, "colspan")
            if r + down > len(rows):
                raise UnsupportedJats("rowspan extends beyond the table")
            for dr in range(down):
                for dc in range(across):
                    position = (r + dr, column + dc)
                    if position in grid:
                        raise UnsupportedJats("overlapping table spans")
                    grid[position] = _text(cell, _SEPARATE) if dr == dc == 0 else ""
            column += across
            width = max(width, column)
    if not width:
        raise UnsupportedJats("table rows contain no cells")
    label = _text(_first(wrapper, "label"))
    number = re.search(r"\d+", label)
    return Table(
        number=number.group(0) if number else "", head=label,
        caption=_text(_first(wrapper, "caption")),
        rows=tuple(tuple(grid.get((r, c), "") for c in range(width)) for r in range(len(rows))),
    )


def _reference(entry: ET.Element) -> Reference | None:
    citation = next((node for node in entry if _tag(node) in {
        "element-citation", "mixed-citation", "nlm-citation"}), None)
    if citation is None or not _text(citation):
        return None
    title = _text(_first(citation, "article-title"))
    if not title:
        # A mixed citation without a tagged title stays verbatim, just like HTML references.
        title = _text(citation)
    year_text = _text(_first(citation, "year"))
    doi = next((normalize_doi(_text(node)) for node in citation.iter()
                if _tag(node) == "pub-id" and node.get("pub-id-type", "").lower() == "doi"), None)
    authors = tuple(_text(node) for group in _children(citation, "person-group")
                    if group.get("person-group-type", "author") == "author"
                    for node in group.iter() if _tag(node) == "surname" and _text(node))
    return Reference(
        key=f"doi:{doi}" if doi else f"title:{normalize_title(title)}",
        title=title, year=int(year_text) if len(year_text) == 4 and year_text.isdigit() else None,
        authors=authors, doi=doi,
    )


def parse(payload: bytes) -> Document:
    """Parse a primary article; retain structured cells and separate ancillary text."""
    # ElementTree does not fetch external DTDs. Refuse internal entity declarations too.
    if re.search(br"<!ENTITY\s", payload, re.I):
        raise JatsError("entity declarations are not supported")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise JatsError(f"not well-formed XML: {exc}") from exc
    if _tag(root) != "article":
        raise JatsError("root is not a JATS article")
    front, body, back = (_first(root, name) for name in ("front", "body", "back"))
    if front is None or body is None:
        raise JatsError("JATS full text requires front and body")
    meta = _first(front, "article-meta")
    if meta is None:
        raise JatsError("no article-meta")
    titles = _first(meta, "title-group")
    title = _text(_first(titles, "article-title")) if titles is not None else ""
    containers = [body] + ([back] if back is not None else []) + _children(root, "floats-group")
    nodes = [node for container in containers for node in _walk(container)]
    tables = tuple(_table(node) for node in nodes if _tag(node) == "table-wrap")
    notes = []
    for node in nodes:
        name = _tag(node)
        if name == "fn":
            text = _text(node, frozenset({"label"}))
            marker = _text(_first(node, "label")) or node.get("id", "")
        elif name == "fig":
            text = _text(_first(node, "caption"))
            marker = _text(_first(node, "label")) or node.get("id", "")
        else:
            continue
        if text:
            notes.append(Note(marker, text))
    references = []
    # Europe PMC also places the primary bibliography inside body in some JATS.
    # Walk each container once, excluding nested articles and their bibliographies.
    def collect(node: ET.Element) -> None:
        if _tag(node) in {"sub-article", "response"}:
            return
        if _tag(node) == "ref":
            reference = _reference(node)
            if reference is not None:
                references.append(reference)
            return
        for child in node:
            collect(child)
    collect(body)
    if back is not None:
        collect(back)
    sections = _sections(body) + (_sections(back) if back is not None else [])
    if not sections and not tables:
        raise JatsError("no readable body paragraphs or tables")
    return Document(title, "\n\n".join(_text(node) for node in _children(meta, "abstract")),
                    tuple(sections), tables, tuple(notes), tuple(references))
