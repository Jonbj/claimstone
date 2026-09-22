"""Append-only JSONL storage, content-addressed bytes.

Append-only is the point: a row is never rewritten, so a crashed run is resumable and a
published series can never be silently revised. Readers deduplicate on a declared key,
keeping the last row for that key — which makes a retry a new fact rather than a mutation.
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


class Store:
    """The generated artefacts of one project. Nothing here is tracked in git."""

    def __init__(self, project: str, base: str | pathlib.Path = "store") -> None:
        self.root = pathlib.Path(base) / project
        self.raw = self.root / "raw"

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
        path = self.root / name
        if not path.exists():
            return
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)

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
