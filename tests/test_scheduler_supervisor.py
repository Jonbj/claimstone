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
