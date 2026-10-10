from __future__ import annotations

import dataclasses
import datetime as dt
import json
import shutil

import pytest

from claimstone import cli, flows, network_schedule, operations, periodic
from claimstone.config import load_project
from claimstone.scope import Selector
from claimstone.store import Store


def _setup(tmp_path):
    root = tmp_path / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    original = load_project(root)
    project = dataclasses.replace(original, topics=(dataclasses.replace(
        original.topics[0], terms=(original.topics[0].terms[0],)),))
    store = Store(project.name, base=tmp_path / 'store')
    source, _ = flows.create(project, store, selector=Selector('original'), title='original')
    now = dt.datetime.now(dt.timezone.utc)
    rounds = [{'round': f'update-{i}', 'title': f'Update {i}',
               'not_before': (now + dt.timedelta(days=i)).isoformat(),
               'expires_at': (now + dt.timedelta(days=i, hours=1)).isoformat()}
              for i in (1, 2)]
    return project, store, source['flow_id'], rounds


def test_periodic_plan_is_bounded_idempotent_and_requires_authorization(tmp_path):
    project, store, source, rounds = _setup(tmp_path)
    kwargs = {'apis': ['crossref'], 'allowed_hosts': ['api.crossref.org'],
              'max_units_each': 1, 'max_requests_each': 2, 'per_query': 1}
    result = periodic.plan(project, store, source, rounds, **kwargs)
    assert result['max_total_requests'] == 4
    assert result['schedule_state'] == 'PLANNED'
    assert periodic.plan(project, store, source, rounds, **kwargs) == result
    assert len([row for row in store.read('flows.jsonl') if row['event'] == 'created']) == 3
    assert len(list(store.read('operations.jsonl'))) == 2
    assert not list(store.read('requests.jsonl'))
    assert periodic.audit(project, store, result['schedule_id'])['ready_for_evidence_review'] is False
    for row in result['rounds']:
        assert flows.flows(store)[row['flow_id']]['binding']['derived_from'] in {source, result['rounds'][0]['flow_id']}
    network_schedule.authorize(store, result['schedule_id'])
    assert periodic.plan(project, store, source, rounds, **kwargs)['schedule_state'] == 'AUTHORIZED'
    assert not network_schedule.due(store, result['schedule_id'],
                                       list(store.read('operation_batches.jsonl'))[0]['operation_ids'][0])


def test_invalid_round_is_refused_before_writes_and_audit_is_cumulative(tmp_path):
    project, store, source, rounds = _setup(tmp_path)
    kwargs = {'apis': ['crossref'], 'allowed_hosts': ['api.crossref.org'],
              'max_units_each': 1, 'max_requests_each': 2}
    with pytest.raises(operations.OperationError, match='ordered'):
        periodic.plan(project, store, source, list(reversed(rounds)), **kwargs)
    assert len(list(store.read('flows.jsonl'))) == 1
    with pytest.raises(operations.OperationError, match='positive caps'):
        periodic.plan(project, store, source, rounds,
                      **(kwargs | {'max_units_each': 0}))
    with pytest.raises(operations.OperationError, match='cover every'):
        periodic.plan(project, store, source, rounds,
                      **(kwargs | {'apis': ['crossref', 'openalex']}))
    assert len(list(store.read('flows.jsonl'))) == 1
    result = periodic.plan(project, store, source, rounds, **kwargs)
    store.append('candidates.jsonl', {'candidate_key': 'new-paper', 'round': 'update-2',
                                      'source_class': 'MET', 'channel': 'keyword'})
    audit = periodic.audit(project, store, result['schedule_id'])
    assert [row['admission']['found'] for row in audit['rounds']] == [0, 1]
    assert audit['cumulative_admission']['found'] == 1
    assert audit['ready_for_evidence_review'] is False
    assert audit['verdict'] is None


def test_periodic_cli_plans_and_audits_without_transport(tmp_path, capsys):
    project, store, source, rounds = _setup(tmp_path)
    # The CLI loads the complete protocol from disk, so use its matching flow.
    original = load_project(project.root)
    flow, _ = flows.create(original, store, selector=Selector('cli-original'), title='CLI')
    schedule_file = tmp_path / 'rounds.json'
    schedule_file.write_text(json.dumps(rounds), encoding='utf-8')
    code = cli.main(['scheduler', 'periodic-plan', str(project.root), flow['flow_id'],
                     '--store', str(store.root.parent), '--rounds-file', str(schedule_file),
                     '--api', 'crossref', '--allow-host', 'api.crossref.org',
                     '--max-units-each', '100', '--max-requests-each', '2'])
    assert code == 0
    schedule_id = json.loads(capsys.readouterr().out)['schedule_id']
    assert cli.main(['scheduler', 'periodic-audit', str(project.root), schedule_id,
                     '--store', str(store.root.parent)]) == 0
    assert json.loads(capsys.readouterr().out)['verdict'] is None
    assert not list(store.read('requests.jsonl'))
