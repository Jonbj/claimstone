from __future__ import annotations

import pytest

from claimstone import autopilot, network_schedule, operations, periodic, runners
from claimstone.runners.base import RawAnswer
from tests.test_periodic import _setup


def _series(tmp_path):
    project, store, source, rounds = _setup(tmp_path)
    plan = periodic.plan(project, store, source, rounds,
                         apis=['crossref'], allowed_hosts=['api.crossref.org'],
                         max_units_each=1, max_requests_each=2)
    network_schedule.authorize(store, plan['schedule_id'])
    return project, store, plan


def test_one_series_mandate_names_all_child_flows_and_one_lifetime_cap(tmp_path):
    project, store, plan = _series(tmp_path)
    grant = autopilot.enable_series(
        project, store, plan['schedule_id'], extract_model='reader-a',
        review_model='reader-b', max_total_local_calls=3)
    mandate_id = grant['mandate_id']
    child_flows = [row['flow_id'] for row in plan['rounds']]
    assert grant['mandate']['flow_ids'] == child_flows
    assert autopilot.status(store, mandate_id)['remaining_local_calls'] == 3
    with pytest.raises(operations.OperationError, match='active local mandate'):
        autopilot.enable(project, store, child_flows[1], extract_model='reader-a',
                         review_model='reader-b', max_total_local_calls=1)
    result = autopilot.tick(project, store, mandate_id)
    assert [row['flow_id'] for row in result['children']] == child_flows
    assert result['network']['processed'] == 0
    assert result['local_calls'] == 0
    assert result['remaining_total_local_calls'] == 3
    assert result['periodic_dossiers'][0]['state'] == 'INSUFFICIENT_ACQUISITION'
    assert not list(store.read('requests.jsonl'))
    assert not list(store.read('periodic_dossiers.jsonl'))
    assert autopilot.disable(store, mandate_id)['state'] == 'DISABLED'
    assert autopilot.tick(project, store, mandate_id)['stopped_reason'] == 'MANDATE_DISABLED'


def test_series_requires_an_approved_schedule_and_distinct_models(tmp_path):
    project, store, source, rounds = _setup(tmp_path)
    plan = periodic.plan(project, store, source, rounds,
                         apis=['crossref'], allowed_hosts=['api.crossref.org'],
                         max_units_each=1, max_requests_each=2)
    with pytest.raises(operations.OperationError, match='authorized schedule'):
        autopilot.enable_series(project, store, plan['schedule_id'],
                                extract_model='a', review_model='b',
                                max_total_local_calls=3)
    network_schedule.authorize(store, plan['schedule_id'])
    with pytest.raises(operations.OperationError, match='distinct models'):
        autopilot.enable_series(project, store, plan['schedule_id'],
                                extract_model='a', review_model='a',
                                max_total_local_calls=3)
    assert not list(store.read(autopilot.LEDGER))


def test_series_stops_after_schedule_revocation(tmp_path):
    project, store, plan = _series(tmp_path)
    grant = autopilot.enable_series(
        project, store, plan['schedule_id'], extract_model='reader-a',
        review_model='reader-b', max_total_local_calls=3)
    network_schedule.revoke(store, plan['schedule_id'])
    result = autopilot.tick(project, store, grant['mandate_id'])
    assert result['stopped_reason'] == 'SCHEDULE_NOT_AUTHORIZED'
    assert result['steps'] == []
    assert not list(store.read('requests.jsonl'))


def test_series_uses_one_call_budget_across_both_child_flows(tmp_path, monkeypatch):
    project, store, plan = _series(tmp_path)
    flow_ids = [row['flow_id'] for row in plan['rounds']]
    grant = autopilot.enable_series(
        project, store, plan['schedule_id'], extract_model='reader-a',
        review_model='reader-b', max_total_local_calls=1)
    for index, row in enumerate(plan['rounds'], start=1):
        source = f'S{index:02d}'
        store.append('candidates.jsonl', {'candidate_key': f'doi:10.1/{index}',
                                          'source_id': source, 'source_class': 'ACA',
                                          'round': row['round']})
        store.append('documents.jsonl', {'source_id': source,
                                         'fulltext_confirmed': True})
        store.append('chunks.jsonl', {'source_id': source,
                                      'chunk_id': source + '#one',
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
    result = autopilot.tick(project, store, grant['mandate_id'])
    assert [row['flow_id'] for row in result['children']] == flow_ids
    assert result['local_calls'] == 1
    assert result['remaining_total_local_calls'] == 0
    assert len(calls) == 1
    assert autopilot.status(store, grant['mandate_id'])['reserved_local_calls'] == 1
    assert autopilot.tick(project, store, grant['mandate_id'])['local_calls'] == 0
    assert len(calls) == 1
