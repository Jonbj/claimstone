"""Search completeness cannot be inferred from acquisition or empty query logs."""
from dataclasses import replace
import hashlib

import pytest

from claimstone.config import Topic
from tests.test_synthesize import _project, _store
from tools import audit_research_search as audit
from tools.replay_answers import files_snapshot


def test_declared_search_depth_failures_and_missing_queries_stay_distinct():
    planned = [{'topic_id': 'T1', 'query': q, 'source_api': 'arxiv', 'per_query': 25}
               for q in ['missing', 'failed', 'shallow', 'complete']]
    recorded = [dict(p, ok=p['query'] != 'failed',
                     per_query=5 if p['query'] == 'shallow' else 25)
                for p in planned[1:]]
    assert [r['status'] for r in audit.query_status(planned, recorded)] == [
        'NOT_RUN', 'FAILED', 'SHALLOWER_THAN_PLANNED', 'COMPLETED']
    recorded[-1]['returned'] = 25
    assert audit.query_status(planned, recorded)[-1]['result_cap_reached'] is True


def test_incremental_inventory_keeps_added_removed_and_revised_separate():
    old = [{'candidate_key': 'same', 'document_sha256': 'a', 'generation_sha256': 'x'},
           {'candidate_key': 'removed'}]
    new = [{'candidate_key': 'same', 'document_sha256': 'a', 'generation_sha256': 'y'},
           {'candidate_key': 'added'}]
    delta = audit.inventory_delta(new, old)
    assert delta['new_candidate_keys'] == ['added']
    assert delta['absent_candidate_keys'] == ['removed']
    assert delta['changed_document_keys'] == ['same']


def fixture(tmp_path):
    project = replace(_project(tmp_path), topics=(Topic(id='T1', label='Public topic', terms=('news',)),))
    store = _store(tmp_path, final=False)
    hashes = {}
    for name in ['topics.yaml', 'questions.yaml', 'sources.yaml', 'manifest.tsv']:
        (tmp_path/name).write_text('{}\n')
        hashes[name] = hashlib.sha256((tmp_path/name).read_bytes()).hexdigest()
    plan = {'question_id': 'H02', 'registry_sha256': project.registry_sha256,
            'search_round': 'new-round', 'topic_ids': ['T1'], 'apis': ['arxiv'],
            'per_query': 25, 'input_sha256': hashes,
            'queries': [{'topic_id': 'T1', 'query': 'news', 'source_api': 'arxiv', 'per_query': 25}]}
    return project, store, plan


def test_offline_audit_keeps_unknown_metrics_null_and_does_not_change_ledgers(tmp_path):
    project, store, plan = fixture(tmp_path)
    before = files_snapshot(store)
    report = audit.build(project, store, plan)
    assert report['query_status_counts'] == {'NOT_RUN': 1}
    assert report['literature_recall'] is report['screening_precision'] is None
    assert report['model_calls'] == report['production_ledger_rows_written'] == 0
    assert files_snapshot(store) == before
    assert not audit.build(project, store, plan, report)['delta']['new_candidate_keys']


def test_changed_scope_is_refused_before_audit(tmp_path):
    project, store, plan = fixture(tmp_path)
    with pytest.raises(ValueError, match='matrix'):
        audit.build(project, store, dict(plan, per_query=50))
    (tmp_path/'sources.yaml').write_text('changed')
    with pytest.raises(ValueError, match='input changed'):
        audit.build(project, store, plan)
