"""Ephemeral worker liveness, separate from authoritative operation ledgers.

The sidecar is replaced atomically so a heartbeat thread can run while a
long operation holds the project writer lock. It proves recent process
activity only; stage completion is always read from the append-only ledgers.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import pathlib
import re
import tempfile
import threading
import time
from typing import Any

from claimstone import operations
from claimstone.store import Store

INTERVAL_SECONDS = 3
STALE_SECONDS = 15
KEY = re.compile(r"^(operations|[0-9a-f]{64})$")


def _path(store: Store, key: str) -> pathlib.Path:
    if not KEY.fullmatch(key):
        raise operations.OperationError('invalid worker key')
    return store.root / 'runtime' / 'workers' / f'{key}.json'


def status(store: Store, key: str, *, now: float | None = None) -> dict[str, Any]:
    """Conservative view: stale or damaged sidecars never mean RUNNING."""
    path = _path(store, key)
    result: dict[str, Any] = {'worker_key': key, 'state': 'NOT_STARTED',
                              'last_seen_at': None, 'phase': None,
                              'age_seconds': None}
    try:
        row = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return result
    except (OSError, ValueError, UnicodeError):
        return result | {'state': 'UNKNOWN'}
    if (not isinstance(row, dict) or row.get('worker_key') != key or
            row.get('phase') not in {'IDLE', 'DRIVING', 'STOPPED'} or
            type(row.get('epoch')) not in {int, float} or
            not 0 < row['epoch'] < 10**11 or
            not isinstance(row.get('at'), str)):
        return result | {'state': 'UNKNOWN'}
    current = time.time() if now is None else now
    if row['epoch'] > current + STALE_SECONDS:
        return result | {'state': 'UNKNOWN', 'last_seen_at': row['at'],
                         'phase': row['phase']}
    age = max(0.0, current - row['epoch'])
    state = ('STOPPED' if row['phase'] == 'STOPPED' else
             'ALIVE' if age <= STALE_SECONDS else 'STALE')
    return {'worker_key': key, 'state': state, 'last_seen_at': row['at'],
            'phase': row['phase'], 'age_seconds': round(age, 3)}


class Beacon:
    """One process per worker key, with a heartbeat independent of stage locks."""

    def __init__(self, store: Store, key: str) -> None:
        self.path = _path(store, key)
        self.key = key
        self.phase = 'IDLE'
        self._mutex = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock_fd: int | None = None

    def _write(self) -> None:
        with self._mutex:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix='.heartbeat-', dir=self.path.parent)
            try:
                now = time.time()
                body = {'worker_key': self.key, 'phase': self.phase, 'epoch': now,
                        'at': dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(),
                        'pid': os.getpid()}
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump(body, stream, sort_keys=True)
                    stream.write('\n')
                os.replace(name, self.path)
            finally:
                if os.path.exists(name):
                    os.unlink(name)

    def _pulse(self) -> None:
        while not self._stop.wait(INTERVAL_SECONDS):
            try:
                self._write()
            except OSError:
                # A failed heartbeat becomes STALE; never report false liveness.
                return

    def __enter__(self) -> Beacon:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_fd = os.open(self.path.with_suffix('.lock'), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._write()
            self._thread = threading.Thread(target=self._pulse, daemon=True)
            self._thread.start()
            return self
        except (BlockingIOError, OSError) as exc:
            os.close(self._lock_fd)
            self._lock_fd = None
            raise operations.OperationError('worker already running or heartbeat unavailable') from exc

    def set_phase(self, phase: str) -> None:
        if phase not in {'IDLE', 'DRIVING'}:
            raise ValueError('invalid worker phase')
        self.phase = phase
        self._write()

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=INTERVAL_SECONDS + 1)
        self.phase = 'STOPPED'
        try:
            self._write()
        finally:
            if self._lock_fd is not None:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
