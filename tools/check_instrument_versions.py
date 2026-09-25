#!/usr/bin/env python
"""Refuse a gate or chunk version bump that no recorded measurement acknowledges.

Every rate this project publishes was produced by an instrument: the content gate at some
`GATE_VERSION` under some thresholds, and the chunker at some `CHUNK_VERSION`. Two figures are
comparable only if they came from the same instrument, and a version can be bumped in one commit
while `docs/DESIGN_DECISIONS.md` still quotes figures from the previous one — at which point a
trend is two different measurements wearing the same label.

So: if a version constant has a value, the design record must mention that value. This is a
reminder to write down what changed, not a proof that anything is correct.

Exit 0 when satisfied, 1 with an explanation otherwise.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RECORD = ROOT / "docs" / "DESIGN_DECISIONS.md"

# Each instrument: the module holding its version, the constant, and the phrase the record must
# use so the mention is deliberate rather than accidental.
INSTRUMENTS = (
    ("claimstone/fulltext.py", "GATE_VERSION", "gate_version"),
    ("claimstone/chunk.py", "CHUNK_VERSION", "chunk_version"),
)

# The parser is an instrument too, and a string rather than a number. Measured: lfoppiano/grobid
# latest-crf produced 508 KB of TEI against 0.8.1's 91 KB on the same PDF, so a switch would change
# every body-character, section and reference count without touching a version number.
PARSERS = (("claimstone/grobid.py", "IMAGE"),)


def declared(path: pathlib.Path, constant: str) -> int | None:
    if not path.exists():
        return None
    found = re.search(rf"^{constant}\s*=\s*(\d+)", path.read_text(encoding="utf-8"), re.M)
    return int(found.group(1)) if found else None


def declared_string(path: pathlib.Path, constant: str) -> str | None:
    if not path.exists():
        return None
    found = re.search(
        rf'^{constant}\s*=\s*["\']([^"\']+)["\']', path.read_text(encoding="utf-8"), re.M
    )
    return found.group(1) if found else None


def main() -> int:
    if not RECORD.exists():
        print(f"missing {RECORD.relative_to(ROOT)}")
        return 1
    record = RECORD.read_text(encoding="utf-8")

    problems: list[str] = []
    checked = 0
    for relative, constant, phrase in INSTRUMENTS:
        version = declared(ROOT / relative, constant)
        if version is None:
            # The module does not exist yet, or does not declare it. Both are fine; this script
            # reminds, it does not require a stage to be built.
            continue
        checked += 1
        if not re.search(rf"{phrase}\D{{0,40}}{version}\b", record, re.I):
            problems.append(
                f"{relative} declares {constant} = {version}, and "
                f"docs/DESIGN_DECISIONS.md never mentions {phrase} {version}. "
                f"A figure measured under a different instrument is not comparable to one "
                f"measured under this; record what changed and which figures it supersedes."
            )

    for relative, constant in PARSERS:
        image = declared_string(ROOT / relative, constant)
        if image is None:
            continue
        checked += 1
        if image not in record:
            problems.append(
                f"{relative} declares {constant} = {image!r}, and "
                f"docs/DESIGN_DECISIONS.md never names it. Figures measured with a different "
                f"parser build are not comparable to figures measured with this one."
            )

    for problem in problems:
        print(f"error: {problem}")
    if problems:
        return 1
    print(f"{checked} instrument version(s) acknowledged in the design record")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
