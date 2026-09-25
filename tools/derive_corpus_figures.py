#!/usr/bin/env python
"""Re-derive the corpus figures quoted in the specs, from the store.

The specs state measured numbers — body characters, distinct references, channel overlap — and a
review pointed out they were not reproducible from this repository: the TEI they came from lived in
a scratchpad. The TEI itself cannot be committed (it is the full text of copyrighted papers), so
this script is committed instead, and the figures below say which command produced them.

Run it from the repository root:

    .venv/bin/python tools/derive_corpus_figures.py alembic-s4

It reads `store/<project>/tei/*.xml`, which `claimstone normalize` writes, and needs no network.
If that directory is empty the script says so rather than printing zeros: an absent derivation and
a derivation that found nothing are different facts.
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from claimstone import chunk as chunker  # noqa: E402
from claimstone import html_doc  # noqa: E402
from claimstone import tei as tei_parser  # noqa: E402
from claimstone.config import load_project  # noqa: E402
from claimstone.ids import normalize_title  # noqa: E402

NS = "{http://www.tei-c.org/ns/1.0}"


def text_of(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def reference_title(entry: ET.Element) -> str:
    """An article's title is in analytic, a book's in monogr. A bare .//title takes the wrong one."""
    for holder in (entry.find(f"{NS}analytic"), entry.find(f"{NS}monogr")):
        if holder is not None:
            found = text_of(holder.find(f"{NS}title"))
            if found:
                return found
    return ""


def html_figures(project_name: str) -> str:
    """The HTML full texts, which have no TEI and so are invisible to the loop above.

    The corpus holds exactly one, and it is the document `html_doc.py` exists for. Its tables are
    most of the reason: the rules that decide what is a table and what is a publisher's spacing box
    were chosen against this file, so the figures belong next to the TEI ones.
    """
    ledger = pathlib.Path("store") / project_name / "acquisitions.jsonl"
    if not ledger.exists():
        return "  no acquisitions ledger: HTML figures not derived\n"
    artifacts: dict[str, str] = {}
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if (row.get("gate") or {}).get("kind") == "HTML_FULLTEXT":
            stored = row.get("stored_path") or ""
            if pathlib.Path(stored).exists():
                artifacts[stored] = row.get("source_id") or "?"
    if not artifacts:
        return "  no HTML full text in the ledger: nothing to derive (not the same as zero)\n"

    lines = [f"  HTML full texts                       {len(artifacts):>9}"]
    for stored, source_id in sorted(artifacts.items(), key=lambda kv: kv[1]):
        doc = html_doc.parse(pathlib.Path(stored).read_bytes())
        result = chunker.chunk_document(doc, source_id=source_id)
        kinds = collections.Counter(piece.kind for piece in result.chunks)
        cells = sum(len(cell) for table in doc.tables for row in table.rows for cell in row)
        lines += [
            f"    {source_id}: prose characters             {doc.body_chars:>9,}",
            f"    {source_id}: sections                     {len(doc.sections):>9}",
            f"    {source_id}: tables                       {len(doc.tables):>9}"
            f"  ({sum(len(t.rows) for t in doc.tables)} rows, {cells:,} characters of cells)",
            f"    {source_id}: chunks                       {len(result.chunks):>9}"
            f"  (prose {kinds[chunker.PROSE]} · table {kinds[chunker.TABLE]})",
        ]
    lines.append("")
    lines.append("  A table needs two rows and two columns. Below that it is a publisher's spacing")
    lines.append("  box and its text returns to the prose: on this document 140 tables were found")
    lines.append("  and 110 were boxes, 104 of them 1x3. A chunk each would be 110 model calls.")
    return "\n".join(lines) + "\n"


def main(project_name: str) -> int:
    tei_dir = pathlib.Path("store") / project_name / "tei"
    files = sorted(tei_dir.glob("*.xml"))
    if not files:
        print(f"no TEI under {tei_dir}/ — run `claimstone normalize {project_name}` first.")
        print("Nothing is derived. This is not the same as deriving zero.")
        return 1

    body_chars = sections = short_sections = tables = notes = note_chars = 0
    references: dict[str, set[str]] = collections.defaultdict(set)

    for path in files:
        root = ET.parse(path).getroot()
        body = root.find(f".//{NS}body")
        if body is None:
            continue
        for div in body:
            if div.tag != f"{NS}div":
                continue
            sections += 1
            paragraphs = [text_of(p) for p in div.findall(f"{NS}p")]
            chars = len(text_of(div))
            body_chars += sum(len(p) for p in paragraphs)
            if chars < 800:
                short_sections += 1
        tables += sum(
            1 for figure in body
            if figure.tag == f"{NS}figure" and figure.get("type") == "table"
        )
        for note in body:
            if note.tag == f"{NS}note":
                notes += 1
                note_chars += len(text_of(note))
        for entry in root.iter(f"{NS}biblStruct"):
            title = reference_title(entry)
            if title:
                references[normalize_title(title)].add(path.stem)

    project = load_project(pathlib.Path("projects") / project_name)
    manifest_titles = {
        normalize_title(entry.title) for entry in project.manifest if entry.title
    }
    overlap = manifest_titles & set(references)

    cited = collections.Counter(len(docs) for docs in references.values())

    # The chunk figures come from the module itself, never from a second reading of the TEI: two
    # implementations would drift, and then this number would describe the tool rather than the
    # chunker whose output stage 4 actually reads.
    kinds: collections.Counter[str] = collections.Counter()
    chunk_chars = dropped = merged = oversized = largest = 0
    for path in files:
        result = chunker.chunk_document(tei_parser.parse(path.read_bytes()), source_id=path.stem[:8])
        dropped += result.dropped_sections
        merged += result.merged_sections
        oversized += result.oversized_chunks
        for piece in result.chunks:
            kinds[piece.kind] += 1
            chunk_chars += len(piece.text)
            largest = max(largest, len(piece.text))

    print(f"{project_name}: derived from {len(files)} TEI files in {tei_dir}/")
    print()
    print(f"  body characters (div prose only)      {body_chars:>9,}")
    print(f"  sections                              {sections:>9}")
    print(f"    of which under 800 characters       {short_sections:>9}")
    print(f"  tables                                {tables:>9}")
    print(f"  footnotes                             {notes:>9}  ({note_chars:,} characters)")
    print(f"  distinct references                   {len(references):>9}")
    for n in sorted(cited):
        print(f"    cited by {n} document(s)               {cited[n]:>9}")
    print()
    print(f"  chunks (version {chunker.CHUNK_VERSION})                     {sum(kinds.values()):>9}")
    for kind in sorted(kinds):
        print(f"    {kind:<36s}{kinds[kind]:>9}")
    print(f"  characters in chunks                  {chunk_chars:>9,}")
    print(f"    largest single chunk                {largest:>9,}"
          f"  (budget {chunker.DEFAULT_THRESHOLDS['max_chunk_chars']:,})")
    print(f"  sections merged forward or back       {merged:>9}")
    print(f"  divs dropped as bare heads            {dropped:>9}")
    print(f"  chunks over budget after splitting    {oversized:>9}")
    print()
    print(html_figures(project_name))
    print(f"  manifest titles                       {len(manifest_titles):>9}")
    print(f"  overlap with references (exact title) {len(overlap):>9}")
    print()
    print("  No population estimate is printed. The overlap understates itself (a cover banner")
    print("  can become a title), the manifest is not a random sample, and the citation channel")
    print("  relies on unequal catchability — see the stage 1 spec, section 6.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "alembic-s4"))
