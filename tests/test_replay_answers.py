"""Offline operational replay preserves history and never calls a backend."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from claimstone import model_call
from claimstone.runners.base import RawAnswer
from tools import replay_answers
from tests.test_answer_authority import PROJECT, RECORD, corpus
from tests.test_synthesize import _project, _store, claim


def test_apply_preserves_original_files_and_is_idempotent(tmp_path):
    store = corpus(tmp_path)
    project = SimpleNamespace(**PROJECT.__dict__, name='t', registry_sha256='test-registry', frozen_at='2026-09-28')
    queue = model_call.Queue(store, lane='extract', batch='e')
    body = json.dumps([RECORD]).encode()
    digest, path = store.store_bytes(body, '.txt')
    row = model_call.build_result(queue.requests()[0], RawAnswer(body=body, model='m'),
        backend='fake', model='m', harness_version='fake/1', raw_sha256=digest, raw_path=str(path),
        started_at='2026-09-28T10:00:00Z', finished_at='2026-09-28T10:00:01Z', latency_s=1)
    store.append(queue.results_name, row)
    original = {p: p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    result = replay_answers.apply(project, store)
    assert result['accepted'] == 1
    assert result['all_original_bytes_preserved']
    assert not any(result['repeat_appends'].values())
    assert all(p.read_bytes().startswith(body) for p, body in original.items())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    assert not replay_answers.apply(project, store)['changed_files']


def test_read_only_queue_measurement_leaves_store_unchanged(tmp_path):
    project = _project(tmp_path)
    store = _store(tmp_path, claims=[claim()])
    before = replay_answers.files_snapshot(store)
    result = replay_answers.residual(project, store)
    assert result['review_annotations'] == result['review_calls'] == 1
    question = result['review_calls_by_question']['H02']
    assert question['annotations'] == question['calls'] == 1
    assert question['prompt_chars'] > 0 and question['max_output_tokens_total'] > 0
    assert result['price_estimate'] is None and not result['reviewer_chosen']
    assert result['queue_built_in_temporary_copy']
    assert replay_answers.files_snapshot(store) == before


def test_apply_refuses_torn_history_before_writing_anything(tmp_path):
    store = corpus(tmp_path)
    project = SimpleNamespace(**PROJECT.__dict__, name='t', registry_sha256='test-registry', frozen_at='2026-09-28')
    store.path('rejections.jsonl').write_bytes(b'{"unfinished": true}')
    before = replay_answers.files_snapshot(store)
    with pytest.raises(RuntimeError, match='complete ledger tails'):
        replay_answers.apply(project, store)
    assert replay_answers.files_snapshot(store) == before
