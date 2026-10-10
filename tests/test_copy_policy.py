from __future__ import annotations

import dataclasses
import datetime as dt
import shutil

import pytest

from claimstone import copy_policy, flows, network_schedule, operations, periodic
from claimstone.config import load_project
from claimstone.scope import Selector
from claimstone.store import Store


def _fixture(tmp_path):
    root = tmp_path / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    original = load_project(root)
    project = dataclasses.replace(original, topics=(dataclasses.replace(
        original.topics[0], terms=(original.topics[0].terms[0],)),))
    store = Store(project.name, base=tmp_path / 'store')
    source, _ = flows.create(project, store, selector=Selector('initial'), title='Initial')
    now = dt.datetime.now(dt.timezone.utc)
    rounds = [{'round': 'future', 'title': 'Future',
               'not_before': (now + dt.timedelta(days=1)).isoformat(),
               'expires_at': (now + dt.timedelta(days=1, hours=1)).isoformat()}]
    scheduled = periodic.plan(project, store, source['flow_id'], rounds,
                              apis=['crossref'], allowed_hosts=['api.crossref.org'],
                              max_units_each=1, max_requests_each=2)
    batch = list(store.read('operation_batches.jsonl'))[0]
    discovery_op = batch['operation_ids'][0]
    query_id = operations._events(store)[discovery_op][0]['plan']['query']['query_id']
    return project, store, scheduled, discovery_op, query_id, now


def _policy(project, store, scheduled, now, *, max_candidates=1):
    return copy_policy.plan(project, store, scheduled['schedule_id'],
                            allowed_hosts=['repo.example.org'],
                            source_classes=['MET'], max_candidates=max_candidates,
                            max_requests_each=2,
                            not_before=(now - dt.timedelta(minutes=1)).isoformat(),
                            expires_at=(now + dt.timedelta(hours=1)).isoformat())


def _found(store, query_id, discovery_op, key, *, host='repo.example.org',
           class_id='MET', campaign=None):
    store.append('candidates.jsonl', {'candidate_key': key, 'round': 'future',
                                      'source_class': class_id,
                                      'url': f'https://{host}/{key}.pdf',
                                      'title': key, 'channel': 'keyword'})
    store.append('query_hits.jsonl', {'hit_id': f'hit-{key}', 'round': 'future',
                                      'candidate_key': key, 'query_id': query_id,
                                      'query_hit_version': 2,
                                      'url': f'https://{host}/{key}.pdf',
                                      'title': key, 'doi': None,
                                      'source_class': class_id,
                                      'population_in_scope': True})
    if campaign is not None:
        store.append('queries.jsonl', {'query_id': query_id, 'round': 'future',
                                       'ok': True, 'campaign': campaign})


def _completed_discovery(store, scheduled, discovery_op):
    flow_id = scheduled['rounds'][0]['flow_id']
    operations._append(store, discovery_op, flow_id, 'started', 'test', worker_pid=1)
    operations._append(store, discovery_op, flow_id, 'unit_completed', 'test', result={'ok': True})
    operations._append(store, discovery_op, flow_id, 'completed', 'test', result={'ok': True})


def test_future_copy_policy_reserves_only_scheduled_hits_and_is_revocable(tmp_path):
    project, store, scheduled, discovery_op, query_id, now = _fixture(tmp_path)
    policy = _policy(project, store, scheduled, now)
    assert policy['state'] == 'PLANNED'
    assert _policy(project, store, scheduled, now)['policy_id'] == policy['policy_id']
    copy_policy.authorize(store, policy['policy_id'])
    _found(store, query_id, discovery_op, 'first', campaign='another-operation')
    assert copy_policy.materialize_due(project, store) == []
    network_schedule.authorize(store, scheduled['schedule_id'])
    _completed_discovery(store, scheduled, discovery_op)
    assert copy_policy.materialize_due(project, store) == []  # wrong query campaign
    store.append('queries.jsonl', {'query_id': query_id, 'round': 'future',
                                   'ok': True, 'campaign': discovery_op})
    _found(store, query_id, discovery_op, 'wrong-host', host='other.example.org')
    selected = copy_policy.materialize_due(project, store)
    assert len(selected) == 1
    operation_id = selected[0]
    rows = operations._events(store)[operation_id]
    assert rows[0]['plan']['candidate_key'] == 'first'
    assert rows[1]['identity']['copy_policy_id'] == policy['policy_id']
    assert rows[0]['plan']['allowed_hosts'] == ['repo.example.org']
    assert copy_policy.materialize_due(project, store) == []
    assert copy_policy.status(store, policy['policy_id'])['reserved_requests'] == 2
    _found(store, query_id, discovery_op, 'second')
    restarted = Store(project.name, base=store.root.parent)
    assert copy_policy.materialize_due(project, restarted) == []
    assert copy_policy.status(restarted, policy['policy_id'])['remaining_candidates'] == 0
    assert not list(store.read('requests.jsonl'))
    copy_policy.revoke(store, policy['policy_id'])
    assert not copy_policy.due(store, policy['policy_id'])
    with pytest.raises(operations.OperationError, match='not currently active'):
        operations.execute(project, store, operation_id)
    assert not list(store.read('requests.jsonl'))


def test_changed_candidate_and_existing_authorization_are_not_reauthorized(tmp_path):
    project, store, scheduled, discovery_op, query_id, now = _fixture(tmp_path)
    policy = _policy(project, store, scheduled, now, max_candidates=2)
    network_schedule.authorize(store, scheduled['schedule_id'])
    _completed_discovery(store, scheduled, discovery_op)
    copy_policy.authorize(store, policy['policy_id'])
    _found(store, query_id, discovery_op, 'changed', campaign=discovery_op)
    store.append('candidates.jsonl', {'candidate_key': 'changed', 'round': 'future',
                                      'source_class': 'MET',
                                      'url': 'https://repo.example.org/replaced.pdf',
                                      'title': 'changed', 'channel': 'keyword'})
    _found(store, query_id, discovery_op, 'malformed', host='[broken')
    assert copy_policy.materialize_due(project, store) == []
    _found(store, query_id, discovery_op, 'already-approved')
    flow_id = scheduled['rounds'][0]['flow_id']
    frozen = operations.plan(project, store, flow_id, 'acquire',
                             candidate_key='already-approved',
                             allowed_hosts=['repo.example.org'], max_requests=2,
                             use_apis=False)
    operations.authorize(store, operations._digest(frozen))
    assert copy_policy.materialize_due(project, store) == []
    assert copy_policy.status(store, policy['policy_id'])['reserved_candidates'] == 0


def test_worker_materializes_only_with_authorized_policy(tmp_path, monkeypatch):
    project, store, scheduled, discovery_op, query_id, now = _fixture(tmp_path)
    policy = _policy(project, store, scheduled, now)
    network_schedule.authorize(store, scheduled['schedule_id'])
    _completed_discovery(store, scheduled, discovery_op)
    _found(store, query_id, discovery_op, 'found', campaign=discovery_op)
    assert copy_policy.materialize_due(project, store) == []
    copy_policy.authorize(store, policy['policy_id'])
    called = []
    monkeypatch.setattr(operations, 'execute', lambda _p, _s, op: called.append(op) or {'ok': True})
    result = operations.tick(project, store, max_operations=1,
                             stages=frozenset({'acquire'}))
    assert result['processed'] == 1
    assert called == [result['operations'][0]['operation_id']]
    assert not list(store.read('requests.jsonl'))


def test_batch_planner_skips_bad_provider_url_and_reaches_next_candidate(tmp_path):
    project, store, scheduled, _, _, _ = _fixture(tmp_path)
    store.append('candidates.jsonl', {'candidate_key': 'a-bad', 'round': 'future',
                                      'source_class': 'MET', 'url': 'https://[broken/x.pdf'})
    store.append('candidates.jsonl', {'candidate_key': 'z-good', 'round': 'future',
                                      'source_class': 'MET',
                                      'url': 'https://repo.example.org/good.pdf'})
    batch = operations.plan_batch(project, store, scheduled['rounds'][0]['flow_id'],
                                  'acquire', allowed_hosts=['repo.example.org'],
                                  max_units=1, max_requests_each=2)
    assert len(batch['operation_ids']) == 1
    assert batch['units'][0]['subject'] == 'z-good'
    assert batch['skipped'][0]['subject'] == 'a-bad'
    assert not list(store.read('requests.jsonl'))
