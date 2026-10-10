from __future__ import annotations

import shutil

from claimstone import periodic_dossier, synthesize
from claimstone.config import load_project
from claimstone.store import Store


def test_finalization_waits_for_schedule_and_evidence_then_is_idempotent(tmp_path, monkeypatch):
    root = tmp_path / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    project = load_project(root)
    store = Store(project.name, base=tmp_path / 'store')
    audit = {'schedule_id': 'schedule', 'ready_for_evidence_review': False,
             'cumulative_admission': {'status': 'OK'}, 'verdict': None}
    profile = {'question_id': 'Q01', 'kind': 'effect', 'state': 'NO_VERIFIED_CLAIM',
               'provisional': True, 'profile_sha256': 'first'}
    monkeypatch.setattr('claimstone.periodic.audit', lambda *a: dict(audit))
    monkeypatch.setattr(synthesize, 'preview', lambda *a, **k: ([dict(profile)], {}))
    monkeypatch.setattr(synthesize, 'verdicts', lambda *a, **k: {'rows': []})
    def build(*args, **kwargs):
        store.append(synthesize.PROFILES, dict(profile))
    monkeypatch.setattr(synthesize, 'build', build)

    waiting = periodic_dossier.finalize(project, store, 'schedule')
    assert waiting['state'] == 'WAITING_FOR_SCHEDULE'
    assert waiting['blockers'] == ['SCHEDULE_OR_ROUND_INCOMPLETE',
                                   'INCOMPLETE_CUMULATIVE_EVIDENCE']
    assert not list(store.read(periodic_dossier.LEDGER))
    assert not list(store.read(synthesize.PROFILES))

    audit['ready_for_evidence_review'] = True
    profile['provisional'] = False
    first = periodic_dossier.finalize(project, store, 'schedule')
    assert first['state'] == periodic_dossier.READY
    assert first['history_count'] == 1
    assert first['needs_finalization'] is False
    assert first['verdict'] is None
    assert len(list(store.read(synthesize.PROFILES))) == 1
    assert periodic_dossier.finalize(project, store, 'schedule')['history_count'] == 1

    profile['profile_sha256'] = 'second'
    changed = periodic_dossier.preview(project, store, 'schedule')
    assert changed['snapshot_stale'] and changed['needs_finalization']
    second = periodic_dossier.finalize(project, store, 'schedule')
    assert second['history_count'] == 2
    assert second['finalized_dossier_id'] != first['finalized_dossier_id']
    assert len(list(store.read(synthesize.PROFILES))) == 2


def test_insufficient_acquisition_never_writes_a_profile(tmp_path, monkeypatch):
    root = tmp_path / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    project = load_project(root)
    store = Store(project.name, base=tmp_path / 'store')
    monkeypatch.setattr('claimstone.periodic.audit', lambda *a: {
        'ready_for_evidence_review': False, 'cumulative_admission': {
            'status': 'INSUFFICIENT_ACQUISITION'}, 'verdict': None})
    def refuse(*args, **kwargs):
        raise synthesize.NotAdmissible('below floor')
    monkeypatch.setattr(synthesize, 'preview', refuse)
    report = periodic_dossier.finalize(project, store, 'schedule')
    assert report['state'] == 'INSUFFICIENT_ACQUISITION'
    assert report['profiles'] == []
    assert not list(store.read(periodic_dossier.LEDGER))
    assert not list(store.read(synthesize.PROFILES))
