"""Frozen cumulative reports remain verifiable and omit source-copy bytes."""

import shutil
import zipfile
from io import BytesIO

import pytest

from claimstone import operations, periodic_dossier, periodic_export
from claimstone.config import load_project
from claimstone.store import Store


def _report(_project, _store, schedule_id):
    return {'schedule_id': schedule_id,
            'state': periodic_dossier.READY, 'snapshot_stale': False,
            'finalized_dossier_id': 'a' * 64,
            'profiles': [{'question_id': 'Q01', 'state': 'NO_VERIFIED_CLAIM',
                          'provisional': False, 'profile_sha256': 'p' * 64}],
            'human_decisions': [{'question_id': 'Q01', 'verdict': None, 'stale': False}],
            'verdict': None}


def test_cumulative_export_is_idempotent_verifiable_and_downloadable(tmp_path, monkeypatch):
    root = tmp_path / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    project = load_project(root)
    store = Store(project.name, base=tmp_path / 'store')
    store.append('claims.jsonl', {'note': 'frozen evidence byte prefix'})
    monkeypatch.setattr(periodic_dossier, 'preview', _report)

    directory, created = periodic_export.create(project, store, 'schedule',
                                                dossier_id='a' * 64, actor='op1')
    assert created
    assert periodic_export.verify(project, store, directory.name) == []
    assert periodic_export.create(project, store, 'schedule',
                                  dossier_id='a' * 64)[1] is False
    assert len(list(store.read(periodic_export.LEDGER))) == 1
    with zipfile.ZipFile(BytesIO(periodic_export.archive(directory))) as package:
        assert set(package.namelist()) == set(periodic_export.FILES)
        assert b'Q01' in package.read('questions.csv')
        assert b'"verdict": null' in package.read('dossier.json')

    manifest = (directory / 'manifest.json').read_bytes()
    (directory / 'manifest.json').write_bytes(manifest + b' ')
    assert periodic_export.verify(project, store, directory.name) == ['MANIFEST_CHANGED']
    (directory / 'manifest.json').write_bytes(manifest)

    (directory / 'questions.csv').write_text('changed', encoding='utf-8')
    assert 'OUTPUT_DIFFERS questions.csv' in periodic_export.verify(project, store,
                                                                     directory.name)
    with pytest.raises(operations.OperationError, match='failed verification'):
        periodic_export.create(project, store, 'schedule', dossier_id='a' * 64)
    store.path('claims.jsonl').write_text('rewritten\n', encoding='utf-8')
    assert 'PREFIX_CHANGED claims.jsonl' in periodic_export.verify(project, store,
                                                                    directory.name)


def test_export_refuses_an_unfinalized_or_changed_dossier(tmp_path, monkeypatch):
    root = tmp_path / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    project = load_project(root)
    store = Store(project.name, base=tmp_path / 'store')
    monkeypatch.setattr(periodic_dossier, 'preview', _report)
    with pytest.raises(operations.OperationError, match='not finalized'):
        periodic_export.create(project, store, 'schedule', dossier_id='b' * 64)
    assert not list(store.read(periodic_export.LEDGER))
