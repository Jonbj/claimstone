"""Authenticated portal planning and finite scheduler permissions."""

from __future__ import annotations

import datetime as dt
import shutil
import threading
from contextlib import contextmanager

from claimstone import autopilot, control, flows, operators
from claimstone.config import load_project
from claimstone.scope import Selector
from claimstone.store import Store
from tests.test_control import _cookie, _login, _request


def _workspace(tmp_path):
    root = tmp_path / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    project = load_project(root)
    store = Store(project.name, base=tmp_path / 'store')
    flow, _ = flows.create(project, store, selector=Selector('original'), title='original')
    state = tmp_path / 'state'
    operators.add_operator(state, 'op1', 'Op One', 'correct horse')
    now = dt.datetime.now(dt.timezone.utc)
    rounds = [{'round': 'update-one', 'title': 'Update one',
               'not_before': (now + dt.timedelta(days=1)).isoformat(),
               'expires_at': (now + dt.timedelta(days=1, hours=1)).isoformat()}]
    return {'root': tmp_path, 'project': project, 'store': store, 'state': state,
            'source_flow': flow['flow_id'], 'rounds': rounds}


@contextmanager
def _served(ws):
    server = control.make_server(ws['root'], ws['root'] / 'store',
                                 host='127.0.0.1', port=0, state_dir=ws['state'])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, response_headers, session = _login(base)
        assert status == 200
        headers = {'Cookie': _cookie(response_headers), 'Origin': base,
                   'X-CSRF-Token': session['csrf_token']}
        yield base + f"/control/v1/p/{ws['project'].name}", headers
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_portal_can_plan_approve_and_revoke_a_finite_series_without_requests(tmp_path):
    ws = _workspace(tmp_path)
    project = ws['project']
    query_count = sum(len(topic.terms) for topic in project.topics)
    with _served(ws) as (base, headers):
        planned = _request(base + '/periodic-plans', method='POST', headers=headers,
                           payload={'source_flow_id': ws['source_flow'],
                                    'rounds': ws['rounds'], 'apis': ['crossref'],
                                    'allowed_hosts': ['api.crossref.org'],
                                    'max_units_each': query_count,
                                    'max_requests_each': 2, 'per_query': 1})
        assert planned[0] == 201
        schedule_id = planned[2]['schedule_id']
        schedule_url = base + f'/schedules/{schedule_id}'
        shown = _request(schedule_url, headers={'Cookie': headers['Cookie']})[2]
        assert shown['state'] == 'PLANNED'
        wrong = _request(schedule_url + '/authorize', method='POST', headers=headers,
                         payload={'plan_sha256': schedule_id,
                                  'max_total_requests': query_count * 2 + 1})
        assert wrong[0] == 409 and wrong[2]['error']['code'] == 'PLAN_DIFFERS'
        assert not list(ws['store'].read('requests.jsonl'))
        approved = _request(schedule_url + '/authorize', method='POST', headers=headers,
                            payload={'plan_sha256': schedule_id,
                                     'max_total_requests': shown['plan']['max_total_requests']})
        assert approved[0] == 201
        assert approved[2]['events'][0]['identity']['operator'] == 'op1'

        policy = _request(base + '/copy-policies', method='POST', headers=headers,
                          payload={'schedule_id': schedule_id,
                                   'allowed_hosts': ['example.org'],
                                   'source_classes': [project.classes[0].id],
                                   'max_candidates': 2, 'max_requests_each': 1,
                                   'not_before': ws['rounds'][0]['not_before'],
                                   'expires_at': ws['rounds'][0]['expires_at']})
        assert policy[0] == 201
        policy_id = policy[2]['policy_id']
        policy_url = base + f'/copy-policies/{policy_id}'
        mismatch = _request(policy_url + '/authorize', method='POST', headers=headers,
                            payload={'policy_sha256': policy_id, 'max_candidates': 3,
                                     'max_requests_each': 1, 'max_total_requests': 2})
        assert mismatch[0] == 409
        accepted = _request(policy_url + '/authorize', method='POST', headers=headers,
                            payload={'policy_sha256': policy_id, 'max_candidates': 2,
                                     'max_requests_each': 1, 'max_total_requests': 2})
        assert accepted[0] == 201
        assert accepted[2]['events'][0]['identity']['operator'] == 'op1'
        assert list(ws['store'].read('copy_policies.jsonl'))[-1]['identity']['operator'] == 'op1'

        child_ids = [row['flow_id'] for row in planned[2]['rounds']]
        mandate = _request(base + '/local-mandates/series', method='POST', headers=headers,
                           payload={'schedule_id': schedule_id, 'flow_ids': child_ids,
                                    'extract_model': 'reader-a', 'review_model': 'reader-b',
                                    'max_total_local_calls': 3})
        assert mandate[0] == 201
        mandate_id = mandate[2]['mandate_id']
        assert mandate[2]['mandate']['authorized_by']['operator'] == 'op1'
        index = _request(base + '/scheduler', headers={'Cookie': headers['Cookie']})[2]
        assert [row['schedule_id'] for row in index['schedules']] == [schedule_id]
        assert [row['policy_id'] for row in index['copy_policies']] == [policy_id]
        assert [row['mandate_id'] for row in index['local_mandates']] == [mandate_id]
        disabled = _request(base + f'/local-mandates/{mandate_id}/disable',
                            method='POST', headers=headers,
                            payload={'mandate_id': mandate_id})
        assert disabled[0] == 200
        assert autopilot.status(ws['store'], mandate_id)['state'] == 'DISABLED'
        assert _request(policy_url + '/revoke', method='POST', headers=headers,
                        payload={'policy_sha256': policy_id})[2]['state'] == 'REVOKED'
        assert _request(schedule_url + '/revoke', method='POST', headers=headers,
                        payload={'plan_sha256': schedule_id})[2]['state'] == 'REVOKED'
    assert not list(ws['store'].read('requests.jsonl'))
    assert not list(ws['store'].read('acquisitions.jsonl'))


def test_portal_rejects_unmatched_child_flows_and_anonymous_scheduler_read(tmp_path):
    ws = _workspace(tmp_path)
    with _served(ws) as (base, headers):
        assert _request(base + '/scheduler')[0] == 401
        assert _request(base + '/periodic-plans', method='POST', headers=headers,
                        payload={})[0] == 422
        assert _request(base + '/local-mandates/series', method='POST', headers=headers,
                        payload={'schedule_id': 'missing', 'flow_ids': [],
                                 'extract_model': 'a', 'review_model': 'b',
                                 'max_total_local_calls': 1})[0] == 404


def test_scheduler_archive_pages_and_refuses_a_stale_cursor(tmp_path):
    from urllib.parse import quote

    ws = _workspace(tmp_path)
    with _served(ws) as (base, headers):
        count = sum(len(topic.terms) for topic in ws['project'].topics)
        planned = _request(base + '/periodic-plans', method='POST', headers=headers,
                           payload={'source_flow_id': ws['source_flow'],
                                    'rounds': ws['rounds'], 'apis': ['crossref'],
                                    'allowed_hosts': ['api.crossref.org'],
                                    'max_units_each': count, 'max_requests_each': 2,
                                    'per_query': 1})[2]
        sid = planned['schedule_id']
        _request(base + f'/schedules/{sid}/authorize', method='POST', headers=headers,
                 payload={'plan_sha256': sid,
                          'max_total_requests': planned['max_total_requests']})
        request = {'schedule_id': sid,
                   'flow_ids': [row['flow_id'] for row in planned['rounds']],
                   'extract_model': 'a', 'review_model': 'b',
                   'max_total_local_calls': 1}
        first = _request(base + '/local-mandates/series', method='POST',
                         headers=headers, payload=request)[2]['mandate_id']
        _request(base + f'/local-mandates/{first}/disable', method='POST',
                 headers=headers, payload={'mandate_id': first})
        second = _request(base + '/local-mandates/series', method='POST',
                          headers=headers, payload=request)[2]['mandate_id']
        page1 = _request(base + '/scheduler?limit=1',
                         headers={'Cookie': headers['Cookie']})[2]
        assert page1['archive']['total']['local_mandates'] == 2
        cursor = page1['archive']['next_cursor']
        assert cursor
        page2 = _request(base + '/scheduler?limit=1&cursor=' + quote(cursor),
                         headers={'Cookie': headers['Cookie']})[2]
        assert {page1['local_mandates'][0]['mandate_id'],
                page2['local_mandates'][0]['mandate_id']} == {first, second}
        _request(base + f'/local-mandates/{second}/disable', method='POST',
                 headers=headers, payload={'mandate_id': second})
        _request(base + '/local-mandates/series', method='POST',
                 headers=headers, payload=request)
        changed = _request(base + '/scheduler?limit=1&cursor=' + quote(cursor),
                           headers={'Cookie': headers['Cookie']})
        assert changed[0] == 409 and changed[2]['error']['code'] == 'ARCHIVE_CHANGED'


def test_portal_packages_and_serves_only_a_current_cumulative_dossier(tmp_path, monkeypatch):
    import urllib.request
    import zipfile
    from io import BytesIO

    from claimstone import periodic_dossier
    from tests.test_periodic_export import _report

    ws = _workspace(tmp_path)
    monkeypatch.setattr(periodic_dossier, 'preview', _report)
    with _served(ws) as (base, headers):
        count = sum(len(topic.terms) for topic in ws['project'].topics)
        planned = _request(base + '/periodic-plans', method='POST', headers=headers,
                           payload={'source_flow_id': ws['source_flow'],
                                    'rounds': ws['rounds'], 'apis': ['crossref'],
                                    'allowed_hosts': ['api.crossref.org'],
                                    'max_units_each': count, 'max_requests_each': 2,
                                    'per_query': 1})[2]
        sid = planned['schedule_id']
        denied = _request(base + f'/schedules/{sid}/export', method='POST',
                          headers=headers, payload={'dossier_id': 'b' * 64})
        assert denied[0] == 409
        created = _request(base + f'/schedules/{sid}/export', method='POST',
                           headers=headers, payload={'dossier_id': 'a' * 64})
        assert created[0] == 201
        export_id = created[2]['export_id']
        assert _request(base + f'/periodic-exports/{export_id}',
                        headers={'Cookie': headers['Cookie']})[0] == 200
        with urllib.request.urlopen(urllib.request.Request(
                base + f'/periodic-exports/{export_id}/download',
                headers={'Cookie': headers['Cookie']})) as response:
            assert response.headers['Content-Type'] == 'application/zip'
            with zipfile.ZipFile(BytesIO(response.read())) as package:
                assert 'dossier.json' in package.namelist()
        checked = _request(base + f'/periodic-exports/{export_id}/verify',
                           method='POST', headers=headers, payload={})
        assert checked[0] == 200 and checked[2]['holds'] is True
