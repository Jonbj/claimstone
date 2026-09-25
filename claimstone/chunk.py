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
