"""Standing local permission is bounded across worker restarts."""

import shutil

import pytest

from claimstone import autopilot, operations, runners
from claimstone.config import load_project
from claimstone.runners.base import RawAnswer
from claimstone.scope import Selector
from claimstone.store import Store
from claimstone import flows


def _fixture(tmp_path):
    root = tmp_path / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    project = load_project(root)
    store = Store(project.name, base=tmp_path / 'store')
    flow, _ = flows.create(project, store, selector=Selector('new'), title='new')
    return project, store, flow['flow_id']


def test_local_mandate_waits_for_data_and_reserves_calls_across_ticks(tmp_path, monkeypatch):
    project, store, flow_id = _fixture(tmp_path)
    grant = autopilot.enable(project, store, flow_id, extract_model='reader-a',
                             review_model='reader-b', max_total_local_calls=1)
    mandate_id = grant['mandate_id']
    assert autopilot.tick(project, store, mandate_id)['stopped_reason'] == 'NEEDS_AUTHORIZED_DISCOVERY'
    assert autopilot.status(store, mandate_id)['remaining_local_calls'] == 1
    with pytest.raises(operations.OperationError, match='active local mandate'):
        autopilot.enable(project, store, flow_id, extract_model='reader-a',
                         review_model='reader-b', max_total_local_calls=2)

    store.append('candidates.jsonl', {'candidate_key': 'doi:10.1/one',
                                      'source_id': 'S01', 'source_class': 'ACA',
                                      'round': 'new'})
    store.append('documents.jsonl', {'source_id': 'S01', 'fulltext_confirmed': True})
    store.append('chunks.jsonl', {'source_id': 'S01', 'chunk_id': 'S01#one',
                                  'text': 'News predicts future returns.'})
    calls = []

    class Local:
        name = 'llamacpp'
        max_concurrency = 1
        min_interval_s = 0

        def __init__(self, model):
            self.model = model

        def harness_version(self):
            return 'llamacpp/test'

        def run(self, request):
            calls.append(request['call_id'])
            return RawAnswer(body=b'[]', model=self.model)

    monkeypatch.setattr(runners, 'build', lambda name, *, model: Local(model))
    first = autopilot.tick(project, store, mandate_id)
    assert first['local_calls'] == 1
    assert first['remaining_total_local_calls'] == 0
    assert len(calls) == 1
    assert autopilot.status(Store(project.name, base=tmp_path / 'store'), mandate_id)[
        'remaining_local_calls'] == 0
    assert autopilot.tick(project, store, mandate_id)['local_calls'] == 0
    assert len(calls) == 1
    assert autopilot.disable(store, mandate_id)['state'] == 'DISABLED'
    assert autopilot.tick(project, store, mandate_id)['stopped_reason'] == 'MANDATE_DISABLED'


def test_local_mandate_refuses_changed_code_and_never_authorizes_network(tmp_path, monkeypatch):
    project, store, flow_id = _fixture(tmp_path)
    mandate_id = autopilot.enable(project, store, flow_id, extract_model='reader-a',
                                  review_model='reader-b', max_total_local_calls=0)['mandate_id']
    assert list(store.read(operations.LEDGER)) == []
    assert autopilot.tick(project, store, mandate_id)['stopped_reason'] == 'NEEDS_AUTHORIZED_DISCOVERY'
    assert list(store.read(operations.LEDGER)) == []
    monkeypatch.setattr(operations, '_code_identity', lambda: 'changed')
    with pytest.raises(operations.OperationError, match='renew the local mandate'):
        autopilot.tick(project, store, mandate_id)


def test_mandate_does_not_reuse_a_manual_stage_authorization(tmp_path):
    project, store, flow_id = _fixture(tmp_path)
    store.append('candidates.jsonl', {'candidate_key': 'doi:10.1/one',
                                      'source_id': 'S01', 'source_class': 'ACA',
                                      'round': 'new'})
    store.append('documents.jsonl', {'source_id': 'S01', 'fulltext_confirmed': True})
    store.append('chunks.jsonl', {'source_id': 'S01', 'chunk_id': 'S01#one',
                                  'text': 'News predicts future returns.'})
    batch = f'{flow_id[:16]}-extract'
    manual = operations.plan(project, store, flow_id, 'extract-build', batch=batch)
    operations.authorize(store, operations._digest(manual))
    mandate_id = autopilot.enable(project, store, flow_id, extract_model='reader-a',
                                  review_model='reader-b', max_total_local_calls=0)['mandate_id']
    result = autopilot.tick(project, store, mandate_id)
    auto_plan = operations.status(store, result['steps'][0]['operation_id'])['plan']
    assert auto_plan['run_label'] == mandate_id
    assert operations._digest(auto_plan) != operations._digest(manual)
    assert autopilot.status(store, mandate_id)['reserved_local_calls'] == 0


def test_worker_proposes_network_batches_without_authorizing_them(tmp_path, monkeypatch):
    from claimstone import discover

    project, store, flow_id = _fixture(tmp_path)
    mandate_id = autopilot.enable(
        project, store, flow_id, extract_model='reader-a', review_model='reader-b',
        max_total_local_calls=0, discover_apis=['openalex'],
        discover_hosts=['api.openalex.org'], acquire_hosts=['example.org'],
        proposal_max_units=1, proposal_max_requests_each=2,
        proposal_per_query=1)['mandate_id']
    first = autopilot.tick(project, store, mandate_id)
    assert first['stopped_reason'] == 'NEEDS_AUTHORIZED_DISCOVERY'
    assert first['proposals'] == [{
        'stage': 'discover', 'batch_id': first['proposals'][0]['batch_id'],
        'units': 1, 'max_total_requests': 2, 'new': True}]
    batch_id = first['proposals'][0]['batch_id']
    batch = next(row for row in store.read(operations.BATCH_LEDGER)
                 if row['batch_id'] == batch_id)
    assert operations.status(store, batch['operation_ids'][0])['state'] == 'PLANNED'
    assert list(store.read('requests.jsonl')) == []
    assert autopilot.tick(project, store, mandate_id)['proposals'][0]['new'] is False
    assert len(autopilot.status(store, mandate_id)['pending_batches']) == 1

    operations.authorize_batch(store, batch_id)
    monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'test@example.org')

    def fake_run(project, store, fetcher, *, apis, topics, terms,
                 per_query, round_name, campaign):
        planned = operations.status(store, campaign)['plan']
        store.append('queries.jsonl', {'query_id': planned['query']['query_id'],
                                      'campaign': campaign, 'ok': True, 'returned': 1})
        store.append('candidates.jsonl', {
            'candidate_key': 'doi:10.1/new', 'source_id': 'S01',
            'source_class': 'ACA', 'round': round_name,
            'url': 'https://example.org/paper.pdf'})
        return {'queries': 1}

    monkeypatch.setattr(discover, 'run', fake_run)
    next_pass = autopilot.tick(project, store, mandate_id)
    assert next_pass['network']['processed'] == 1
    acquisition = next(item for item in next_pass['proposals']
                       if item['stage'] == 'acquire')
    acquisition_batch = next(row for row in store.read(operations.BATCH_LEDGER)
                             if row['batch_id'] == acquisition['batch_id'])
    assert operations.status(store, acquisition_batch['operation_ids'][0])['state'] == 'PLANNED'
    assert list(store.read('acquisitions.jsonl')) == []
    assert list(store.read('requests.jsonl')) == []


def test_mandate_proposals_reject_incomplete_discovery_scope(tmp_path):
    project, store, flow_id = _fixture(tmp_path)
    with pytest.raises(operations.OperationError, match='both APIs and exact hosts'):
        autopilot.enable(project, store, flow_id, extract_model='reader-a',
                         review_model='reader-b', max_total_local_calls=1,
                         discover_apis=['openalex'])
    assert list(store.read(autopilot.LEDGER)) == []
