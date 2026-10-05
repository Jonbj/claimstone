"""Curated reading never silently changes evidence or becomes production adjudication."""
from dataclasses import replace
import json

import pytest

from claimstone.config import ManifestEntry
from tests.test_synthesize import _project, _store
from tools import build_consultative_dossier as run
from tools.replay_answers import files_snapshot


def fixture(tmp_path):
    project = replace(_project(tmp_path), manifest=(ManifestEntry(
        source_id='ACA001', source_class='ACA', declared_format='pdf',
        url='https://example.org/paper.pdf', title='Synthetic public paper'),))
    store = _store(tmp_path, final=False)
    text = 'News sentiment predicts returns over 13 weeks.'
    store.append('documents.jsonl', {'source_id': 'ACA001', 'source_class': 'ACA',
        'sha256': 'a'*64, 'fulltext_confirmed': True, 'chunks': 1})
    store.append('chunks.jsonl', {'source_id': 'ACA001', 'chunk_id': 'ACA001#c1',
        'section': 'Results', 'kind': 'prose', 'text': text})
    plan = {'question_id': 'H02', 'round': None, 'registry_sha256': project.registry_sha256,
        'title': 'Consultative reading', 'curation': 'synthetic interactive', 'scope_note': 'Selected only.',
        'summary_it': 'Consultative summary.', 'next_steps_it': ['Read independently.'], 'passages': [{
            'id': 'P01', 'chunk_id': 'ACA001#c1', 'text_sha256': run.sha(text.encode()),
            'document_sha256': 'a'*64, 'label_it': 'Finding', 'note_it': 'Inspect the design.',
            'record': {'question_id': 'H02', 'stance': 'SUPPORTS', 'claim': text, 'evidence_quote': text}}]}
    return project, store, plan


def test_preview_is_read_only_and_gate_does_not_become_semantic_certification(tmp_path):
    project, store, plan = fixture(tmp_path)
    before = files_snapshot(store)
    report = run.build(project, store, plan)
    assert report['verified_passages'] == report['selected_sources'] == 1
    assert report['model_calls'] == report['production_ledger_rows_written'] == 0
    assert report['status'] == 'consultative_reading_not_profile_or_adjudication'
    assert not report['admission']['final']
    assert 'non una lettura integrale' in run.markdown(report)
    assert files_snapshot(store) == before


@pytest.mark.parametrize('damage', ['quote', 'number', 'document'])
def test_changed_quote_number_or_source_cannot_be_published(tmp_path, damage):
    project, store, plan = fixture(tmp_path)
    passage = plan['passages'][0]
    if damage == 'quote': passage['record']['evidence_quote'] = 'invented quote'
    elif damage == 'number': passage['record']['claim'] = 'News sentiment predicts returns over 14 weeks.'
    else: passage['document_sha256'] = 'changed'
    with pytest.raises(ValueError): run.build(project, store, plan)


def test_floor_is_not_bypassed_by_selected_readings(tmp_path):
    project, store, plan = fixture(tmp_path)
    with pytest.raises(ValueError, match='floor'):
        run.build(replace(project, acquisition_floor=.8), store, plan)


def test_writing_dossier_preserves_all_ledgers_and_repeat_is_identical(tmp_path, monkeypatch, capsys):
    project, store, plan = fixture(tmp_path)
    plan.update(project=str(project.root), store=str(store.root.parent))
    path = tmp_path/'plan.json'; path.write_text(json.dumps(plan))
    monkeypatch.setattr(run, 'load_project', lambda _: project)
    monkeypatch.setattr('sys.argv', ['dossier', '--plan', str(path), '--write'])
    before = files_snapshot(store)
    assert run.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report['dossier_path'].endswith('.md')
    after = files_snapshot(store)
    assert all(after[k] == v for k, v in before.items())
    assert all(k.startswith('audits/consultative/') for k in after.keys()-before.keys())
    assert run.main() == 0
    assert files_snapshot(store) == after
