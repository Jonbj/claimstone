"""Worker liveness is a process observation, never evidence of stage success."""

import json
import time

import pytest

from claimstone import operations, worker_runtime
from claimstone.store import Store


def test_beacon_is_exclusive_and_expiry_is_conservative(tmp_path):
    store = Store('example', base=tmp_path)
    key = 'a' * 64
    assert worker_runtime.status(store, key)['state'] == 'NOT_STARTED'
    with worker_runtime.Beacon(store, key) as beacon:
        alive = worker_runtime.status(store, key)
        assert alive['state'] == 'ALIVE' and alive['phase'] == 'IDLE'
        with pytest.raises(operations.OperationError, match='already running'):
            with worker_runtime.Beacon(store, key):
                pass
        beacon.set_phase('DRIVING')
        assert worker_runtime.status(store, key)['phase'] == 'DRIVING'
        assert worker_runtime.status(store, key, now=10**12)['state'] == 'STALE'
    assert worker_runtime.status(store, key)['state'] == 'STOPPED'
    with worker_runtime.Beacon(store, key):
        assert worker_runtime.status(store, key)['state'] == 'ALIVE'


def test_damaged_sidecar_is_unknown_not_alive(tmp_path):
    store = Store('example', base=tmp_path)
    path = worker_runtime._path(store, 'operations')
    path.parent.mkdir(parents=True)
    path.write_text('{bad json', encoding='utf-8')
    assert worker_runtime.status(store, 'operations')['state'] == 'UNKNOWN'
    path.write_text(json.dumps({'worker_key': 'different', 'phase': 'IDLE',
                                'epoch': 0, 'at': 'now'}), encoding='utf-8')
    assert worker_runtime.status(store, 'operations')['state'] == 'UNKNOWN'
    path.write_text(json.dumps({'worker_key': 'operations', 'phase': 'IDLE',
                                'epoch': 10**12, 'at': 'future'}), encoding='utf-8')
    assert worker_runtime.status(store, 'operations')['state'] == 'UNKNOWN'


def test_heartbeat_continues_while_stage_holds_project_writer_lock(tmp_path, monkeypatch):
    store = Store('example', base=tmp_path)
    monkeypatch.setattr(worker_runtime, 'INTERVAL_SECONDS', 0.02)
    with worker_runtime.Beacon(store, 'operations'):
        before = json.loads(worker_runtime._path(store, 'operations').read_text())['epoch']
        with store.writer_lock():
            time.sleep(0.08)
            assert worker_runtime.status(store, 'operations')['state'] == 'ALIVE'
            row = json.loads(worker_runtime._path(store, 'operations').read_text())
            assert row['epoch'] > before
