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

import datetime as _dt
import fcntl
import hashlib
import json
import pathlib
import threading
from contextlib import contextmanager
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

    REPAIR_LEDGER = "ledger_repairs.jsonl"

    _process_locks: dict[pathlib.Path, threading.RLock] = {}
    _lock_guard = threading.Lock()
    _held = threading.local()

    @contextmanager
    def writer_lock(self):
        """Serialize project writers across threads, Store instances and processes.

        Reentrant in one thread so a stage can hold the lock while appending several
        ledgers. Every read-modify-write operation must hold this lock throughout.
        """
        key = self.root.resolve()
        with self._lock_guard:
            local = self._process_locks.setdefault(key, threading.RLock())
        with local:
            held = getattr(self._held, "files", None)
            if held is None:
                held = self._held.files = {}
            if key in held:
                yield
                return
            self.root.mkdir(parents=True, exist_ok=True)
            with (self.root / ".writer.lock").open("a+b") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                held[key] = handle
                try:
                    yield
                finally:
                    del held[key]
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def writer_busy(self) -> bool:
        """Whether another thread or process currently holds the project writer lock."""
        key = self.root.resolve()
        with self._lock_guard:
            local = self._process_locks.setdefault(key, threading.RLock())
        if not local.acquire(blocking=False):
            return True
        try:
            path = self.root / ".writer.lock"
            if not path.exists():
                return False
            with path.open("rb") as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return True
                fcntl.flock(handle, fcntl.LOCK_UN)
                return False
        finally:
            local.release()

    def append(self, name: str, row: dict[str, Any]) -> None:
        """Append one row, repairing a half-written tail first.

        Detecting a torn tail is not enough on its own: appending after one turns a recoverable
        crash artefact into interior corruption that no reader can get past. The torn line was
        never accepted by any reader, so discarding it loses nothing — but work between the last
        complete row and the restart is gone, which is why the repair leaves an audit row.
        """
        # The row's own directory, not just the project root: a ledger may sit under a subpath —
        # `calls/<lane>/<batch>/requests.jsonl` is one — and creating only the root leaves the
        # append raising FileNotFoundError on a name that is otherwise perfectly valid.
        with self.writer_lock():
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            self._ensure_clean_tail(name)
            with (self.root / name).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def _ensure_clean_tail(self, name: str) -> None:
        path = self.root / name
        if not path.exists():
            return
        data = path.read_bytes()
        if not data or data.endswith(b"\n"):
            return
        cut = data.rfind(b"\n")
        discarded = len(data) - (cut + 1)
        path.write_bytes(data[: cut + 1] if cut >= 0 else b"")
        if name in self.torn_tail:
            self.torn_tail.remove(name)
        if name == self.REPAIR_LEDGER:
            # The audit ledger repairs itself and does not record having done so: a recursive
            # audit would be the only thing the audit ever recorded.
            return
        with (self.root / self.REPAIR_LEDGER).open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "ledger": name,
                        "discarded_bytes": discarded,
                        "repaired_at": _dt.datetime.now(_dt.timezone.utc).isoformat(
                            timespec="seconds"
                        ),
                        "note": "a half-written row was discarded; work since the last "
                                "complete row needs redoing",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )

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
        with self.writer_lock():
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

    def store_bytes_at(self, where: str, data: bytes, suffix: str) -> tuple[str, pathlib.Path]:
        """Write bytes under their own hash, inside `where`. Re-storing the same bytes is a no-op,
        so a re-drain that gets an identical answer costs nothing."""
        with self.writer_lock():
            digest = sha256_bytes(data)
            directory = self.root / where
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / f"{digest}{suffix}"
            if not target.exists():
                target.write_bytes(data)
            return digest, target

    def store_bytes(self, data: bytes, suffix: str) -> tuple[str, pathlib.Path]:
        """Write bytes under their own hash. Re-fetching the same bytes is a no-op."""
        return self.store_bytes_at("raw", data, suffix)
