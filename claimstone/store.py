"""Append-only JSONL storage, content-addressed bytes.

Append-only is the point: a row is never rewritten, so a crashed run is resumable and a published
series can never be silently revised. Readers deduplicate on a declared key, keeping the last row
for that key — which makes a retry a new fact rather than a mutation.

**What "resumable after a crash" guarantees, precisely.** A process killed mid-append leaves a
final line with no trailing newline. `read()` skips exactly that line and records which ledger it
was in, and `repair()` truncates it so the next append is clean. Incompleteness is judged by the
missing newline and never by whether the line parses: a row truncated at `{"k": 2}` is valid JSON
and still half-written, so parseability would silently accept a fragment as a whole row.

Damage anywhere but the last line is **not** a crash artefact and raises. Skipping it would drop a
row out of a denominator without telling anyone, which is the class of failure this project exists
to refuse.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any, Iterable, Iterator


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LedgerCorrupt(ValueError):
    """A ledger line is damaged somewhere other than the end, so it is not a crash artefact."""


class Store:
    """The generated artefacts of one project. Nothing here is tracked in git."""

    def __init__(self, project: str, base: str | pathlib.Path = "store") -> None:
        self.root = pathlib.Path(base) / project
        self.raw = self.root / "raw"
        # Ledgers whose final line was found half-written, in read order. A caller that cares
        # can report it; `repair()` clears it.
        self.torn_tail: list[str] = []

    def path(self, name: str) -> pathlib.Path:
        return self.root / name

    def append(self, name: str, row: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / name).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def append_many(self, name: str, rows: Iterable[dict[str, Any]]) -> int:
        count = 0
        for row in rows:
            self.append(name, row)
            count += 1
        return count

    def read(self, name: str) -> Iterator[dict[str, Any]]:
        """Every row. Skips a half-written final line; raises on damage anywhere else."""
        path = self.root / name
        if not path.exists():
            return
        if name in self.torn_tail:
            self.torn_tail.remove(name)
        with path.open(encoding="utf-8") as handle:
            lines = handle.readlines()
        for number, raw in enumerate(lines, start=1):
            complete = raw.endswith("\n")
            line = raw.strip()
            if not line:
                continue
            if not complete:
                # The writer was interrupted here. Nothing follows it by definition.
                self.torn_tail.append(name)
                return
            try:
                yield json.loads(line)
            except ValueError as exc:
                raise LedgerCorrupt(f"{name}: line {number} is not valid JSON: {exc}") from exc

    def repair(self, name: str) -> bool:
        """Drop a half-written final line so the next append starts on a clean boundary.

        Returns whether anything was removed. Truncation is the only mutation this class
        performs, and it removes only a line no reader ever accepted.
        """
        path = self.root / name
        if not path.exists():
            return False
        data = path.read_bytes()
        if not data or data.endswith(b"\n"):
            return False
        cut = data.rfind(b"\n")
        path.write_bytes(data[: cut + 1] if cut >= 0 else b"")
        if name in self.torn_tail:
            self.torn_tail.remove(name)
        return True

    def latest_by(self, name: str, key: str) -> dict[str, dict[str, Any]]:
        """Collapse an append-only log to the most recent row per key."""
        out: dict[str, dict[str, Any]] = {}
        for row in self.read(name):
            identifier = row.get(key)
            if identifier is not None:
                out[str(identifier)] = row
        return out

    def store_bytes(self, data: bytes, suffix: str) -> tuple[str, pathlib.Path]:
        """Write bytes under their own hash. Re-fetching the same bytes is a no-op."""
        digest = sha256_bytes(data)
        self.raw.mkdir(parents=True, exist_ok=True)
        target = self.raw / f"{digest}{suffix}"
        if not target.exists():
            target.write_bytes(data)
        return digest, target
