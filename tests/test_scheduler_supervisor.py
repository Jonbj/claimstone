"""A new mandate is found without passing its ID to the worker."""

import shutil

import pytest

from claimstone import autopilot, flows, operations, scheduler_supervisor, worker_runtime
from claimstone.config import load_project
from claimstone.scope import Selector
from claimstone.store import Store


def test_supervisor_discovers_enabled_mandates_and_observes_revocation(tmp_path):
    projects = tmp_path / 'projects'
    root = projects / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    project = load_project(root)
    store_dir = tmp_path / 'store'
    store = Store(project.name, base=store_dir)
    flow, _ = flows.create(project, store, selector=Selector('new'), title='new')
    mandate_id = autopilot.enable(project, store, flow['flow_id'],
                                  extract_model='reader-a', review_model='reader-b',
                                  max_total_local_calls=0)['mandate_id']

    with worker_runtime.Beacon(scheduler_supervisor.installation_store(store_dir),
                               'supervisor') as beacon:
        assert scheduler_supervisor.status(store_dir)['state'] == 'ALIVE'
        report = scheduler_supervisor.scan_once(projects, store_dir, beacon=beacon)
        assert report['scanned_projects'] == 1
        assert report['active_mandates'] == report['attempted'] == 1
        assert report['errors'] == []
        assert report['results'][0]['result']['stopped_reason'] == 'NEEDS_AUTHORIZED_DISCOVERY'
        assert worker_runtime.status(store, mandate_id)['state'] == 'STOPPED'
        assert beacon.phase == 'IDLE'
        with worker_runtime.Beacon(store, mandate_id):
            occupied = scheduler_supervisor.scan_once(projects, store_dir,
                                                      beacon=beacon)
            assert occupied['attempted'] == 0
            assert occupied['errors'][0]['mandate_id'] == mandate_id
        autopilot.disable(store, mandate_id)
        stopped = scheduler_supervisor.scan_once(projects, store_dir, beacon=beacon)
        assert stopped['active_mandates'] == stopped['attempted'] == 0
    assert scheduler_supervisor.status(store_dir)['state'] == 'STOPPED'


def test_supervisor_reports_bad_project_and_continues(tmp_path):
    projects = tmp_path / 'projects'
    good = projects / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', good)
    bad = projects / 'zz-broken'
    bad.mkdir()
    (bad / 'questions.yaml').write_text('bad: [', encoding='utf-8')
    project = load_project(good)
    store_dir = tmp_path / 'store'
    store = Store(project.name, base=store_dir)
    flow, _ = flows.create(project, store, selector=Selector('new'), title='new')
    mandate_id = autopilot.enable(project, store, flow['flow_id'],
                                  extract_model='reader-a', review_model='reader-b',
                                  max_total_local_calls=0)['mandate_id']
    Store(bad.name, base=store_dir).append(autopilot.LEDGER, {'invalid': True})

    report = scheduler_supervisor.scan_once(projects, store_dir)
    assert report['attempted'] == 1
    assert report['results'][0]['mandate_id'] == mandate_id
    assert len(report['errors']) == 1
    assert report['errors'][0]['project'] == bad.name


def test_installation_lock_prevents_duplicate_supervisors(tmp_path):
    install = scheduler_supervisor.installation_store(tmp_path / 'store')
    with worker_runtime.Beacon(install, 'supervisor'):
        with pytest.raises(operations.OperationError, match='already running'):
            with worker_runtime.Beacon(install, 'supervisor'):
                pass


def test_supervisor_runs_an_authorized_operation_without_any_mandate(tmp_path):
    projects = tmp_path / 'projects'
    root = projects / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    project = load_project(root)
    store_dir = tmp_path / 'store'
    store = Store(project.name, base=store_dir)
    flow, _ = flows.create(project, store, selector=Selector('new'), title='new')
    store.append('candidates.jsonl', {'candidate_key': 'doi:10.1/one', 'source_id': 'S01',
                                      'source_class': 'ACA', 'round': 'new'})
    store.append('documents.jsonl', {'source_id': 'S01', 'fulltext_confirmed': True})
    store.append('chunks.jsonl', {'source_id': 'S01', 'chunk_id': 'S01#one',
                                  'text': 'News predicts future returns.'})
    plan = operations.plan(project, store, flow['flow_id'], 'extract-build', batch='e1')
    operation_id = operations._digest(plan)

    # Planned only: a plan nobody authorized is not started.
    idle = scheduler_supervisor.scan_once(projects, store_dir)
    assert idle['operations_run'] == 0 and idle['errors'] == []
    assert operations.status(store, operation_id)['state'] == 'PLANNED'

    operations.authorize(store, operation_id)
    report = scheduler_supervisor.scan_once(projects, store_dir)
    assert report['errors'] == [] and report['active_mandates'] == 0
    assert report['operations_run'] == 1
    assert operations.status(store, operation_id)['state'] == 'COMPLETED'
    # Nothing left to run on the next pass, and no second execution.
    again = scheduler_supervisor.scan_once(projects, store_dir)
    assert again['operations_run'] == 0


def test_an_occupied_operations_worker_is_reported_and_nothing_runs_twice(tmp_path):
    projects = tmp_path / 'projects'
    root = projects / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    project = load_project(root)
    store_dir = tmp_path / 'store'
    store = Store(project.name, base=store_dir)
    flow, _ = flows.create(project, store, selector=Selector('new'), title='new')
    store.append('candidates.jsonl', {'candidate_key': 'doi:10.1/one', 'source_id': 'S01',
                                      'source_class': 'ACA', 'round': 'new'})
    store.append('documents.jsonl', {'source_id': 'S01', 'fulltext_confirmed': True})
    store.append('chunks.jsonl', {'source_id': 'S01', 'chunk_id': 'S01#one',
                                  'text': 'News predicts future returns.'})
    plan = operations.plan(project, store, flow['flow_id'], 'extract-build', batch='e1')
    operations.authorize(store, operations._digest(plan))
    with worker_runtime.Beacon(store, 'operations'):
        report = scheduler_supervisor.scan_once(projects, store_dir)
    assert report['operations_run'] == 0
    assert 'already running' in report['errors'][0]['error']
