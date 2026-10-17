from __future__ import annotations

import datetime as dt
import shutil

import pytest

from claimstone import acquire, flows, net, operations, retry_policy
from claimstone.config import load_project
from claimstone.scope import Selector
from claimstone.store import Store


def _fixture(tmp_path):
    root = tmp_path / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    project = load_project(root)
    store = Store(project.name, base=tmp_path / 'store')
    flow, _ = flows.create(project, store, selector=Selector('round-one'), title='Round one')
    return project, store, flow['flow_id']


def _plan(project, store, flow_id, **changes):
    args = {'allowed_hosts': ['repo.example.org'], 'max_retries': 3,
            'max_attempts_each': 2, 'max_requests_each': 2, 'use_apis': False,
            'base_delay_hours': 1, 'max_delay_hours': 4,
            'expires_at': (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).isoformat()}
    return retry_policy.plan(project, store, flow_id, **(args | changes))


def _candidate(store, key, *, failure=net.SERVER_ERROR, attempts=None, hours=10,
               host='repo.example.org'):
    store.append('candidates.jsonl', {'candidate_key': key, 'round': 'round-one',
                                      'source_class': 'MET', 'url': f'https://{host}/{key}.pdf',
                                      'title': key, 'channel': 'keyword'})
    store.append('acquisitions.jsonl', {'candidate_key': key, 'acquired': False,
                                        'failure_class': failure,
                                        'attempts': attempts if attempts is not None else
                                        [{'failure_class': failure}],
                                        'fetched_at': (dt.datetime.now(dt.timezone.utc) -
                                                       dt.timedelta(hours=hours)).isoformat()})


def test_transient_unfinished_and_age_gate():
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=7)).isoformat()
    row = {'acquired': False, 'failure_class': net.EXCLUDED,
           'attempts': [{'failure_class': net.SERVER_ERROR}, {'failure_class': net.EXCLUDED}],
           'fetched_at': old}
    assert acquire.should_attempt(row, retry_classes=frozenset())
    assert acquire.should_attempt(row | {'failure_class': net.SERVER_ERROR}, retry_classes=frozenset())
    assert not acquire.should_attempt(row | {'attempts': [{'failure_class': net.EXCLUDED}]},
                                      retry_classes=frozenset())
    assert not acquire.should_attempt(row | {'acquired': True}, retry_classes=frozenset())
    assert not acquire.should_attempt(row | {'fetched_at': dt.datetime.now(dt.timezone.utc).isoformat()},
                                      retry_classes=frozenset())


def test_delay_is_deterministic_capped_and_honours_retry_after():
    stamp = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    spec = {'base_delay_hours': 2, 'max_delay_hours': 5}
    previous = {'fetched_at': stamp.isoformat(), 'attempts': []}
    values = [(retry_policy.next_earliest(spec, 'policy', 'candidate', n, previous) - stamp).total_seconds()
              for n in (1, 2, 3, 4)]
    assert 3600 <= values[0] < 7200
    assert values[0] == 5743.897181
    assert 7200 <= values[1] < 14400
    assert 9000 <= values[2] < 18000
    assert 9000 <= values[3] < 18000
    assert values[0] == (retry_policy.next_earliest(spec, 'policy', 'candidate', 1, previous) - stamp).total_seconds()
    assert (retry_policy.next_earliest(spec, 'policy', 'candidate', 1,
                                      previous | {'attempts': [{'retry_after_s': 10000}]}) - stamp).total_seconds() == 10000
    assert (retry_policy.next_earliest(spec, 'policy', 'candidate', 1,
                                      previous | {'attempts': [{'retry_after_s': 1}]}) - stamp).total_seconds() == values[0]


def test_retry_after_parser():
    now = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    assert net.parse_retry_after('42', now=now) == 42
    assert net.parse_retry_after('Thu, 01 Jan 2026 00:01:00 GMT', now=now) == 60
    assert net.parse_retry_after('nonsense', now=now) is None
    assert net.parse_retry_after('-1', now=now) is None
    assert net.parse_retry_after('99999999', now=now) == 604800


def test_validation_event_order_and_tamper(tmp_path):
    project, store, flow_id = _fixture(tmp_path)
    for change in ({'max_retries': 0}, {'max_attempts_each': 6},
                   {'max_requests_each': 21}, {'base_delay_hours': 0},
                   {'max_delay_hours': 169}, {'allowed_hosts': ['sci-hub.se']},
                   {'use_apis': True},
                   {'expires_at': (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat()}):
        with pytest.raises(operations.OperationError):
            _plan(project, store, flow_id, **change)
    with pytest.raises(operations.OperationError):
        _plan(project, store, 'unknown')
    policy = _plan(project, store, flow_id)
    policy_id = policy['policy_id']
    assert retry_policy.authorize(store, policy_id)['state'] == 'AUTHORIZED'
    assert len(retry_policy.authorize(store, policy_id)['events']) == 1
    assert retry_policy.revoke(store, policy_id)['state'] == 'REVOKED'
    assert not retry_policy.due(store, policy_id)
    assert len(retry_policy.revoke(store, policy_id)['events']) == 2
    row = next(store.read(retry_policy.LEDGER))
    store.append(retry_policy.LEDGER, row | {'event_id': 'bad'})
    with pytest.raises(operations.OperationError, match='invalid retry policy event'):
        retry_policy.status(store, policy_id)
    second = Store(project.name, base=tmp_path / 'second-store')
    second_flow, _ = flows.create(project, second, selector=Selector('round-one'), title='Round one')
    second_id = _plan(project, second, second_flow['flow_id'])['policy_id']
    retry_policy.authorize(second, second_id)
    retry_policy._append(second, 'authorized', second_id, identity={'operator': 'duplicate'})
    with pytest.raises(operations.OperationError, match='invalid retry policy authorization'):
        retry_policy.status(second, second_id)


def test_materialize_respects_scope_caps_and_revocation(tmp_path, monkeypatch):
    project, store, flow_id = _fixture(tmp_path)
    _candidate(store, 'transient')
    _candidate(store, 'mixed', failure=net.EXCLUDED,
               attempts=[{'failure_class': net.SERVER_ERROR}, {'failure_class': net.EXCLUDED}])
    _candidate(store, 'terminal', failure=net.PAYWALL)
    _candidate(store, 'other-host', host='other.example.org')
    policy = _plan(project, store, flow_id, max_retries=1)
    assert retry_policy.materialize_due(project, store) == []
    retry_policy.authorize(store, policy['policy_id'])
    made = retry_policy.materialize_due(project, store)
    assert len(made) == 1
    assert operations.status(store, made[0])['plan']['candidate_key'] == 'mixed'
    assert retry_policy.materialize_due(project, store) == []
    assert retry_policy.status(store, policy['policy_id'])['reserved_retries'] == 1
    retry_policy.revoke(store, policy['policy_id'])
    with pytest.raises(operations.OperationError, match='retry policy authorization'):
        operations.execute(project, store, made[0])


def test_open_host_breaker_reserves_nothing_then_reconsiders(tmp_path, monkeypatch):
    project, store, flow_id = _fixture(tmp_path)
    _candidate(store, 'one')
    policy = _plan(project, store, flow_id)
    retry_policy.authorize(store, policy['policy_id'])
    monkeypatch.setattr(net, 'recorded_host_failures', lambda *_: net.Fetcher.max_403_per_host)
    assert retry_policy.materialize_due(project, store) == []
    assert retry_policy.status(store, policy['policy_id'])['reserved_retries'] == 0
    monkeypatch.setattr(net, 'recorded_host_failures', lambda *_: 0)
    assert len(retry_policy.materialize_due(project, store)) == 1


def test_delay_and_per_candidate_ceiling_after_completed_retry(tmp_path, monkeypatch):
    project, store, flow_id = _fixture(tmp_path)
    _candidate(store, 'one')
    policy = _plan(project, store, flow_id, max_attempts_each=1)
    retry_policy.authorize(store, policy['policy_id'])
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)
    real = retry_policy.next_earliest
    monkeypatch.setattr(retry_policy, 'next_earliest', lambda *_args: future)
    assert retry_policy.materialize_due(project, store) == []
    assert retry_policy.status(store, policy['policy_id'])['reserved_retries'] == 0
    monkeypatch.setattr(retry_policy, 'next_earliest', real)
    first = retry_policy.materialize_due(project, store)
    assert len(first) == 1
    operations._append(store, first[0], flow_id, 'failed', 'test', detail='transient')
    store.append('acquisitions.jsonl', {'candidate_key': 'one', 'acquired': False,
                                        'failure_class': net.SERVER_ERROR,
                                        'attempts': [{'failure_class': net.SERVER_ERROR}],
                                        'fetched_at': (dt.datetime.now(dt.timezone.utc) -
                                                       dt.timedelta(hours=10)).isoformat()})
    assert retry_policy.materialize_due(project, store) == []
    assert retry_policy.status(store, policy['policy_id'])['reserved_requests'] == 2


def test_policy_does_not_touch_another_flow(tmp_path):
    project, store, flow_id = _fixture(tmp_path)
    other, _ = flows.create(project, store, selector=Selector('round-two'), title='Round two')
    _candidate(store, 'one')
    store.append('candidates.jsonl', {'candidate_key': 'two', 'round': 'round-two',
                                      'source_class': 'MET', 'url': 'https://repo.example.org/two.pdf',
                                      'title': 'two', 'channel': 'keyword'})
    store.append('acquisitions.jsonl', {'candidate_key': 'two', 'acquired': False,
                                        'failure_class': net.SERVER_ERROR,
                                        'attempts': [{'failure_class': net.SERVER_ERROR}],
                                        'fetched_at': (dt.datetime.now(dt.timezone.utc) -
                                                       dt.timedelta(hours=10)).isoformat()})
    policy = _plan(project, store, flow_id)
    retry_policy.authorize(store, policy['policy_id'])
    assert retry_policy.materialize_due(project, store, flow_id=other['flow_id']) == []
    made = retry_policy.materialize_due(project, store)
    assert len(made) == 1
    assert operations.status(store, made[0])['plan']['candidate_key'] == 'one'


def test_changed_code_or_protocol_starts_nothing(tmp_path, monkeypatch):
    project, store, flow_id = _fixture(tmp_path)
    _candidate(store, 'one')
    policy = _plan(project, store, flow_id)
    retry_policy.authorize(store, policy['policy_id'])
    original = operations._code_identity
    monkeypatch.setattr(operations, '_code_identity', lambda: 'different')
    assert retry_policy.materialize_due(project, store) == []
    monkeypatch.setattr(operations, '_code_identity', original)
    monkeypatch.setattr(flows, 'protocol_digest', lambda _project: 'different')
    assert retry_policy.materialize_due(project, store) == []
