"""The scheduler's shared-writer and per-flow stage boundaries."""

from __future__ import annotations

import threading

from claimstone import extract, model_call, review
from claimstone.config import Question
from claimstone.scope import Selector
from claimstone.store import Store


class Project:
    questions = (Question(id='H02', text='Does news predict returns?', kind='effect'),)
    registry_version = 1


def _two_rounds(store):
    for round_name, source in (('first', 'S01'), ('second', 'S02')):
        store.append('candidates.jsonl', {'candidate_key': f'doi:{source}',
                                          'source_id': source, 'round': round_name})
        store.append('documents.jsonl', {'source_id': source, 'fulltext_confirmed': True})
        store.append('chunks.jsonl', {'source_id': source, 'chunk_id': f'{source}#one',
                                      'text': 'News predicts next month returns.'})


def test_extract_and_review_build_only_selected_flow(tmp_path):
    store = Store('one', base=tmp_path)
    _two_rounds(store)
    result = extract.build(Project(), store, batch='first', selector=Selector('first'))
    assert result['chunks'] == 1
    assert {row['source_id'] for row in model_call.Queue(store, lane='extract',
                                                         batch='first').requests()} == {'S01'}

    for source in ('S01', 'S02'):
        store.append('claims.jsonl', {'claim_id': f'{source}-claim', 'source_id': source,
                                     'question_id': 'H02', 'chunk_id': f'{source}#one',
                                     'claim': 'News predicts returns.',
                                     'evidence_quote': 'News predicts next month returns.',
                                     'backend': 'claude-cli', 'model': 'one'})
    result = review.build(Project(), store, batch='first', selector=Selector('first'))
    assert result['units'] == 1
    assert {row['source_id'] for row in model_call.Queue(store, lane='review',
                                                         batch='first').requests()} == {'S01'}


def test_shared_writer_lock_is_reentrant_and_serializes_store_instances(tmp_path):
    first = Store('one', base=tmp_path)
    second = Store('one', base=tmp_path)
    started = threading.Event()
    release = threading.Event()
    entered = threading.Event()

    def holder():
        with first.writer_lock():
            with first.writer_lock():
                started.set()
                release.wait(2)

    def waiter():
        started.wait(2)
        with second.writer_lock():
            entered.set()

    a = threading.Thread(target=holder)
    b = threading.Thread(target=waiter)
    a.start()
    b.start()
    assert started.wait(2)
    assert not entered.wait(0.05)
    release.set()
    a.join(2)
    b.join(2)
    assert entered.is_set()


def test_worker_finishes_current_tick_on_sigterm(monkeypatch):
    import argparse
    import signal

    from claimstone import cli, operations

    project = object()
    store = object()
    monkeypatch.setattr(cli, '_flow_open', lambda args: (project, store))
    monkeypatch.setattr(cli, 'load_project', lambda path: project)
    called = []

    def tick(actual_project, actual_store, *, max_operations):
        called.append((actual_project, actual_store, max_operations))
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        return {'processed': 0}

    monkeypatch.setattr(operations, 'tick', tick)
    args = argparse.Namespace(scheduler_command='worker', project='example',
                              poll_seconds=30, max_operations=1)
    assert cli._scheduler_operation(args) == 0
    assert called == [(project, store, 1)]
