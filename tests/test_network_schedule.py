from __future__ import annotations

import datetime as dt
import shutil

import pytest

from claimstone import flows, network_schedule, operations
from claimstone.config import load_project
from claimstone.scope import Selector
from claimstone.store import Store


def _window(*, hours_from_now: int) -> tuple[str, str]:
    now = dt.datetime.now(dt.timezone.utc)
    return ((now + dt.timedelta(hours=hours_from_now)).isoformat(),
            (now + dt.timedelta(hours=hours_from_now + 1)).isoformat())


def _batch(tmp_path):
    root = tmp_path / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    project = load_project(root)
    store = Store(project.name, base=tmp_path / 'store')
    flow, _ = flows.create(project, store, selector=Selector('scheduled'), title='scheduled')
    batch = operations.plan_batch(project, store, flow['flow_id'], 'discover',
                                  apis=['crossref'], allowed_hosts=['api.crossref.org'],
                                  max_units=1, max_requests_each=3, per_query=1)
    assert len(batch['operation_ids']) == 1
    return project, store, batch


def test_future_schedule_waits_then_revocation_stops_execution(tmp_path):
    project, store, batch = _batch(tmp_path)
    start, end = _window(hours_from_now=2)
    frozen = network_schedule.plan(store, project.name,
                                   [{'batch_id': batch['batch_id'], 'not_before': start,
                                     'expires_at': end}], max_total_requests=3)
    operation_id = batch['operation_ids'][0]
    assert operations.status(store, operation_id)['state'] == 'PLANNED'
    approved = network_schedule.authorize(store, frozen['schedule_id'])
    assert approved['state'] == 'AUTHORIZED'
    assert network_schedule.authorize(store, frozen['schedule_id'])['state'] == 'AUTHORIZED'
    assert operations.tick(project, store)['processed'] == 0
    with pytest.raises(operations.OperationError, match='not currently active'):
        operations.execute(project, store, operation_id)
    assert list(store.read('requests.jsonl')) == []
    assert network_schedule.revoke(store, frozen['schedule_id'])['state'] == 'REVOKED'
    assert network_schedule.revoke(store, frozen['schedule_id'])['state'] == 'REVOKED'
    assert operations.tick(project, store)['processed'] == 0
    assert list(store.read('requests.jsonl')) == []


def test_due_schedule_is_eligible_but_ceiling_and_double_approval_are_refused(tmp_path):
    project, store, batch = _batch(tmp_path)
    start = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat()
    end = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()
    entry = {'batch_id': batch['batch_id'], 'not_before': start,
             'expires_at': end}
    with pytest.raises(operations.OperationError, match='ceiling differs'):
        network_schedule.plan(store, project.name, [entry], max_total_requests=4)
    frozen = network_schedule.plan(store, project.name, [entry], max_total_requests=3)
    assert network_schedule.plan(store, project.name, [entry], max_total_requests=3) == frozen
    network_schedule.authorize(store, frozen['schedule_id'])
    operation_id = batch['operation_ids'][0]
    assert network_schedule.due(store, frozen['schedule_id'], operation_id)
    assert operations.status(store, operation_id)['events'][1]['schedule_id'] == frozen['schedule_id']
    assert network_schedule.plan(store, project.name, [entry], max_total_requests=3) == frozen
