from __future__ import annotations

import shutil

import pytest

from claimstone import flows, operations
from claimstone.config import load_project
from claimstone.scope import Selector
from claimstone.store import Store


def _fixture(tmp_path):
    root = tmp_path / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    project = load_project(root)
    store = Store(project.name, base=tmp_path / 'store')
    flow, _ = flows.create(project, store, selector=Selector('new'), title='new')
    store.append('candidates.jsonl', {'candidate_key': 'doi:10.1/one',
                                      'source_id': 'S01', 'source_class': 'ACA',
                                      'round': 'new'})
    store.append('documents.jsonl', {'source_id': 'S01', 'fulltext_confirmed': True})
    store.append('chunks.jsonl', {'source_id': 'S01', 'chunk_id': 'S01#one',
                                  'text': 'News predicts future returns.'})
    return project, store, flow


def test_offline_operation_requires_exact_authorization_and_is_idempotent(tmp_path):
    project, store, flow = _fixture(tmp_path)
    plan = operations.plan(project, store, flow['flow_id'], 'extract-build', batch='e1')
    operation_id = operations._digest(plan)
    assert operations.status(store, operation_id)['state'] == 'PLANNED'
    with pytest.raises(operations.OperationError, match='authorized'):
        operations.execute(project, store, operation_id)
    operations.authorize(store, operation_id)
    assert operations.execute(project, store, operation_id)['units'] > 0
    assert operations.execute(project, store, operation_id)['units'] > 0
    store.append('chunks.jsonl', {'source_id': 'S01', 'chunk_id': 'S01#later',
                                  'text': 'New evidence after the completed plan.'})
    assert operations.execute(project, store, operation_id)['units'] > 0
    assert [row['event'] for row in store.read(operations.LEDGER)] == [
        'planned', 'authorized', 'started', 'unit_completed', 'completed']


def test_changed_input_refuses_old_authorization(tmp_path):
    project, store, flow = _fixture(tmp_path)
    plan = operations.plan(project, store, flow['flow_id'], 'extract-build', batch='e1')
    operation_id = operations._digest(plan)
    operations.authorize(store, operation_id)
    store.append('chunks.jsonl', {'source_id': 'S01', 'chunk_id': 'S01#two', 'text': 'new'})
    with pytest.raises(operations.OperationError, match='frozen inputs'):
        operations.execute(project, store, operation_id)
    assert operations.status(store, operation_id)['state'] == 'AUTHORIZED'


def test_local_model_plan_limits_calls_and_replays_result_after_crash(tmp_path, monkeypatch):
    from claimstone import extract, runners
    from claimstone.runners.base import RawAnswer

    project, store, flow = _fixture(tmp_path)
    extract.build(project, store, batch='e1', selector=Selector('new'), kind='effect')
    calls = []

    class Local:
        name = 'llamacpp'
        model = 'local'
        max_concurrency = 1
        min_interval_s = 0

        def harness_version(self):
            return 'llamacpp/local-test'

        def run(self, request):
            calls.append(request['call_id'])
            return RawAnswer(body=b'[]', model='local')

    monkeypatch.setattr(runners, 'build', lambda *args, **kwargs: Local())
    plan = operations.plan(project, store, flow['flow_id'], 'extract-drain',
                           batch='e1', model='local', max_calls=1)
    assert len(plan['call_ids']) == 1
    operation_id = operations._digest(plan)
    operations.authorize(store, operation_id)
    assert operations.execute(project, store, operation_id)['calls'] == 1
    assert operations.execute(project, store, operation_id)['calls'] == 1
    assert calls == plan['call_ids']


def test_crash_after_model_result_reconciles_without_second_call(tmp_path, monkeypatch):
    from claimstone import extract, model_call, runners
    from claimstone.runners.base import RawAnswer

    project, store, flow = _fixture(tmp_path)
    extract.build(project, store, batch='e1', selector=Selector('new'), kind='effect')
    calls = []

    class Local:
        name = 'llamacpp'
        model = 'local'
        max_concurrency = 1
        min_interval_s = 0

        def harness_version(self):
            return 'llamacpp/crash-test'

        def run(self, request):
            calls.append(request['call_id'])
            return RawAnswer(body=b'[]', model='local')

    monkeypatch.setattr(runners, 'build', lambda *args, **kwargs: Local())
    plan = operations.plan(project, store, flow['flow_id'], 'extract-drain',
                           batch='e1', model='local', max_calls=1)
    operation_id = operations._digest(plan)
    operations.authorize(store, operation_id)
    operations._append(store, operation_id, flow['flow_id'], 'started', 'worker',
                       worker_pid=123, coordination='PROJECT_WRITER_LOCK')
    queue = model_call.Queue(store, lane='extract', batch='e1')
    list(model_call.drain(queue, Local(), limit=1,
                          call_ids=frozenset(plan['call_ids'])))
    assert len(calls) == 1
    assert operations.execute(project, store, operation_id)['calls'] == 1
    assert len(calls) == 1


def test_local_model_must_report_the_planned_identity(tmp_path, monkeypatch):
    from claimstone import extract, model_call, runners
    from claimstone.runners.base import RawAnswer

    project, store, flow = _fixture(tmp_path)
    extract.build(project, store, batch='e1', selector=Selector('new'), kind='effect')

    class Local:
        name = 'llamacpp'
        model = 'planned'
        max_concurrency = 1
        min_interval_s = 0

        def harness_version(self):
            return 'llamacpp/identity-test'

        def run(self, request):
            return RawAnswer(body=b'[]', model='another-loaded-model')

    monkeypatch.setattr(runners, 'build', lambda *args, **kwargs: Local())
    plan = operations.plan(project, store, flow['flow_id'], 'extract-drain',
                           batch='e1', model='planned', max_calls=1)
    operation_id = operations._digest(plan)
    operations.authorize(store, operation_id)
    operations.execute(project, store, operation_id)
    result = next(iter(model_call.Queue(store, lane='extract', batch='e1').results().values()))
    assert result['ok'] is False
    assert result['failure_class'] == 'MODEL_IDENTITY_MISMATCH'
    assert 'strict-model-report=1' in result['harness_version']


def test_paid_budget_is_cumulative_and_call_is_recorded_before_transport(tmp_path, monkeypatch):
    from claimstone import extract, model_call, runners
    from claimstone.runners.base import RawAnswer

    project, store, flow = _fixture(tmp_path)
    extract.build(project, store, batch='e1', selector=Selector('new'), kind='effect')
    calls = []

    class Remote:
        name = 'ollama-cloud'
        model = 'remote'
        max_concurrency = 1
        min_interval_s = 0

        def harness_version(self):
            return 'ollama-cloud/fake'

        def run(self, request):
            calls.append(request['call_id'])
            return RawAnswer(body=b'[]', model='remote', cost_usd=0.01,
                             usage={'input_tokens': 100, 'output_tokens': 1})

    monkeypatch.setattr(runners, 'build', lambda *args, **kwargs: Remote())
    opts = dict(batch='e1', model='remote', backend='ollama-cloud', max_calls=1,
                budget_id='research-1', budget_cents=15, max_call_cents=10,
                price_in_cents=100, price_out_cents=100)
    first = operations.plan(project, store, flow['flow_id'], 'extract-drain', **opts)
    second = operations.plan(project, store, flow['flow_id'], 'extract-drain',
                             run_label='another', **opts)
    first_id, second_id = operations._digest(first), operations._digest(second)
    operations.authorize(store, first_id)
    with pytest.raises(operations.OperationError, match='cumulative paid reservations'):
        operations.authorize(store, second_id)
    operations.execute(project, store, first_id)
    assert calls == first['call_ids']
    assert operations.execute(project, store, first_id)['calls'] == 1
    assert [row['event'] for row in store.read(operations.LEDGER)
            if row['operation_id'] == first_id] == [
                'planned', 'authorized', 'started', 'call_started',
                'unit_completed', 'completed']
    result = next(iter(model_call.Queue(store, lane='extract', batch='e1').results().values()))
    assert result['cost_usd'] == 0.01


def test_unsettled_paid_call_cannot_be_repeated_after_crash(tmp_path, monkeypatch):
    from claimstone import extract, runners
    from claimstone.runners.base import RawAnswer

    project, store, flow = _fixture(tmp_path)
    extract.build(project, store, batch='e1', selector=Selector('new'), kind='effect')

    class Remote:
        name = 'ollama-cloud'
        model = 'remote'
        max_concurrency = 1
        min_interval_s = 0

        def harness_version(self):
            return 'ollama-cloud/fake'

        def run(self, request):
            pytest.fail('an unsettled paid call must never be sent again')

    monkeypatch.setattr(runners, 'build', lambda *args, **kwargs: Remote())
    plan = operations.plan(project, store, flow['flow_id'], 'extract-drain',
                           batch='e1', model='remote', backend='ollama-cloud',
                           max_calls=1, budget_id='research-1', budget_cents=10,
                           max_call_cents=10, price_in_cents=100,
                           price_out_cents=100)
    operation_id = operations._digest(plan)
    operations.authorize(store, operation_id)
    operations._append(store, operation_id, flow['flow_id'], 'started', 'worker',
                       worker_pid=123, coordination='PROJECT_WRITER_LOCK')
    operations._append(store, operation_id, flow['flow_id'], 'call_started',
                       'worker', call_id=plan['call_ids'][0], reserved_cents=10)
    with pytest.raises(operations.OperationError, match='inspect provider billing'):
        operations.execute(project, store, operation_id)
    assert operations.status(store, operation_id)['state'] == 'FAILED'


def test_paid_result_over_reservation_stops_operation(tmp_path, monkeypatch):
    from claimstone import extract, runners
    from claimstone.runners.base import RawAnswer

    project, store, flow = _fixture(tmp_path)
    extract.build(project, store, batch='e1', selector=Selector('new'), kind='effect')

    class Remote:
        name = 'ollama-cloud'
        model = 'remote'
        max_concurrency = 1
        min_interval_s = 0

        def harness_version(self):
            return 'ollama-cloud/fake'

        def run(self, request):
            return RawAnswer(body=b'[]', model='remote', cost_usd=0.20)

    monkeypatch.setattr(runners, 'build', lambda *args, **kwargs: Remote())
    plan = operations.plan(project, store, flow['flow_id'], 'extract-drain',
                           batch='e1', model='remote', backend='ollama-cloud',
                           max_calls=1, budget_id='research-1', budget_cents=10,
                           max_call_cents=10, price_in_cents=100,
                           price_out_cents=100)
    operation_id = operations._digest(plan)
    operations.authorize(store, operation_id)
    with pytest.raises(operations.OperationError, match='exceeds its per-call reservation'):
        operations.execute(project, store, operation_id)
    assert operations.status(store, operation_id)['state'] == 'FAILED'


def test_review_drain_refuses_the_extractor_as_reader(tmp_path):
    from claimstone import review

    project, store, flow = _fixture(tmp_path)
    store.append('claims.jsonl', {'claim_id': 'c1', 'source_id': 'S01',
                                  'chunk_id': 'S01#one',
                                  'question_id': project.questions[0].id,
                                  'claim': 'News predicts returns.',
                                  'evidence_quote': 'News predicts future returns.',
                                  'backend': 'llamacpp', 'model': 'same',
                                  'harness_version': 'llamacpp/test'})
    review.build(project, store, batch='r1')
    with pytest.raises(operations.OperationError, match='is the extractor'):
        operations.plan(project, store, flow['flow_id'], 'review-drain',
                        batch='r1', model='same', max_calls=1)


def test_existing_batch_with_other_round_request_is_refused(tmp_path):
    from claimstone import extract

    project, store, flow = _fixture(tmp_path)
    store.append('candidates.jsonl', {'candidate_key': 'doi:10.1/two',
                                      'source_id': 'S02', 'round': 'other'})
    store.append('documents.jsonl', {'source_id': 'S02', 'fulltext_confirmed': True})
    store.append('chunks.jsonl', {'source_id': 'S02', 'chunk_id': 'S02#one',
                                  'text': 'News predicts future returns.'})
    extract.build(project, store, batch='mixed')
    with pytest.raises(operations.OperationError, match='outside this flow'):
        operations.plan(project, store, flow['flow_id'], 'extract-drain', batch='mixed',
                        model='local', max_calls=1)


def test_tick_runs_only_authorized_operations(tmp_path):
    project, store, flow = _fixture(tmp_path)
    plan = operations.plan(project, store, flow['flow_id'], 'extract-build', batch='e1')
    operation_id = operations._digest(plan)
    assert operations.tick(project, store)['processed'] == 0
    operations.authorize(store, operation_id)
    run = operations.tick(project, store)
    assert run['processed'] == 1
    assert run['operations'][0]['state'] == 'COMPLETED'
    assert operations.tick(project, store)['processed'] == 0


def test_discovery_pretransport_failure_needs_a_named_retry(tmp_path, monkeypatch):
    from claimstone import discover, net
    from claimstone.store import sha256_text

    project, store, flow = _fixture(tmp_path)
    term = project.topics[0].terms[0]
    query_id = sha256_text(f'new|openalex|{project.topics[0].id}|{term}')
    store.append('queries.jsonl', {
        'query_id': query_id, 'round': 'new', 'source_api': 'openalex',
        'topic_id': project.topics[0].id, 'query': term, 'campaign': 'old',
        'ok': False, 'failure_class': 'NON_GLOBAL_ADDRESS', 'returned': 0})
    opts = dict(api='openalex', topic_id=project.topics[0].id, term=term,
                per_query=10, allowed_hosts=['api.openalex.org'], max_requests=3)
    with pytest.raises(operations.OperationError, match='pre-transport'):
        operations.plan(project, store, flow['flow_id'], 'discover', **opts)
    plan = operations.plan(project, store, flow['flow_id'], 'discover',
                           run_label='dns-retry', retry_reason='sandbox DNS blocked before HTTP',
                           **opts)
    assert plan['prior_query_sha256']
    operation_id = operations._digest(plan)
    monkeypatch.setattr(net, 'Fetcher', lambda **kwargs: object())

    def fake_run(project, store, fetcher, **kwargs):
        store.append('queries.jsonl', {
            'query_id': query_id, 'round': 'new', 'source_api': 'openalex',
            'topic_id': project.topics[0].id, 'query': term,
            'campaign': operation_id, 'ok': True, 'returned': 2})
        return {'queries': 1}

    monkeypatch.setattr(discover, 'run', fake_run)
    operations.authorize(store, operation_id)
    assert operations.execute(project, store, operation_id) == {
        'query_id': query_id, 'ok': True, 'returned': 2, 'reconciled': False}


def test_discovery_retry_refuses_an_old_physical_request(tmp_path):
    from claimstone.store import sha256_text

    project, store, flow = _fixture(tmp_path)
    term = project.topics[0].terms[0]
    store.append('queries.jsonl', {
        'query_id': sha256_text(f'new|openalex|{project.topics[0].id}|{term}'),
        'round': 'new', 'source_api': 'openalex', 'topic_id': project.topics[0].id,
        'query': term, 'campaign': 'old', 'ok': False,
        'failure_class': 'NON_GLOBAL_ADDRESS', 'returned': 0})
    store.append('requests.jsonl', {
        'event': 'request_started', 'round': 'new', 'source_api': 'openalex',
        'topic_id': project.topics[0].id, 'query': term, 'campaign': 'old'})
    with pytest.raises(operations.OperationError, match='physical query request'):
        operations.plan(project, store, flow['flow_id'], 'discover',
                        api='openalex', topic_id=project.topics[0].id, term=term,
                        per_query=10, allowed_hosts=['api.openalex.org'],
                        max_requests=3, run_label='retry', retry_reason='DNS')


def test_acquisition_plan_counts_robots_and_copy_without_real_network(tmp_path, monkeypatch):
    import socket
    import requests

    project, store, flow = _fixture(tmp_path)
    store.append('candidates.jsonl', {'candidate_key': 'doi:10.1/one',
                                      'source_id': 'S01', 'source_class': 'ACA',
                                      'round': 'new', 'url': 'https://example.org/paper.pdf'})
    monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'test@example.org')
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.215.14', 0))])
    visited = []

    class Response:
        def __init__(self, url):
            self.url = url
            self.status_code = 404 if url.endswith('/robots.txt') else 200
            self.headers = {'Content-Type': 'text/plain' if self.status_code == 404
                            else 'application/pdf'}
            self.content = b'' if self.status_code == 404 else b'not-a-real-pdf'

    def fake_get(self, url, **kwargs):
        visited.append(url)
        return Response(url)

    monkeypatch.setattr(requests.Session, 'get', fake_get)
    plan = operations.plan(project, store, flow['flow_id'], 'acquire',
                           candidate_key='doi:10.1/one',
                           allowed_hosts=['example.org'], max_requests=2)
    operation_id = operations._digest(plan)
    operations.authorize(store, operation_id)
    result = operations.execute(project, store, operation_id)
    assert result['candidate_key'] == 'doi:10.1/one'
    assert visited == ['https://example.org/robots.txt', 'https://example.org/paper.pdf']
    assert sum(row.get('event') == 'request_started' and
               row.get('campaign') == operation_id
               for row in store.read('requests.jsonl')) == 2
    assert operations.execute(project, store, operation_id) == result
    assert len(visited) == 2


def test_interrupted_physical_request_is_never_reissued_automatically(tmp_path):
    project, store, flow = _fixture(tmp_path)
    store.append('candidates.jsonl', {'candidate_key': 'doi:10.1/one',
                                      'source_id': 'S01', 'source_class': 'ACA',
                                      'round': 'new', 'url': 'https://example.org/paper.pdf'})
    plan = operations.plan(project, store, flow['flow_id'], 'acquire',
                           candidate_key='doi:10.1/one',
                           allowed_hosts=['example.org'], max_requests=2)
    operation_id = operations._digest(plan)
    operations.authorize(store, operation_id)
    store.append('requests.jsonl', {'event': 'request_started',
                                   'campaign': operation_id,
                                   'candidate_key': 'doi:10.1/one',
                                   'url': 'https://example.org/paper.pdf'})
    with pytest.raises(operations.OperationError, match='inspect before retry'):
        operations.execute(project, store, operation_id)
    assert operations.status(store, operation_id)['state'] == 'FAILED'
    with pytest.raises(operations.OperationError, match='earlier physical acquisition request'):
        operations.plan(project, store, flow['flow_id'], 'acquire',
                        candidate_key='doi:10.1/one', allowed_hosts=['example.org'],
                        max_requests=2, run_label='retry')


def test_one_query_discovery_plan_is_bounded_and_replay_safe(tmp_path, monkeypatch):
    import socket
    import requests
    from claimstone import discover

    root = tmp_path / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    project = load_project(root)
    store = Store(project.name, base=tmp_path / 'store')
    flow, _ = flows.create(project, store, selector=Selector('new'), title='new')
    topic = project.topics[0]
    term = topic.terms[0]
    monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'test@example.org')
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.215.14', 0))])
    visited = []

    class Response:
        def __init__(self, url):
            self.url = url
            self.status_code = 404 if url.endswith('/robots.txt') else 200
            self.headers = {'Content-Type': 'text/plain' if self.status_code == 404
                            else 'application/json'}
            self.content = b'' if self.status_code == 404 else b'{"results": []}'

    def fake_get(self, url, **kwargs):
        visited.append(url)
        return Response(url)

    def fake_search(logged, term, topic_id, **kwargs):
        payload, outcome = logged.get_json('https://api.openalex.org/works?search=test')
        assert outcome.ok and payload == {'results': []}
        return []

    monkeypatch.setattr(requests.Session, 'get', fake_get)
    monkeypatch.setattr(discover, 'SEARCHERS', {**discover.SEARCHERS, 'openalex': fake_search})
    plan = operations.plan(project, store, flow['flow_id'], 'discover',
                           api='openalex', topic_id=topic.id, term=term,
                           per_query=5, allowed_hosts=['api.openalex.org'], max_requests=2)
    operation_id = operations._digest(plan)
    operations.authorize(store, operation_id)
    assert operations.execute(project, store, operation_id)['ok'] is True
    assert len(visited) == 2
    assert operations.execute(project, store, operation_id)['ok'] is True
    assert len(visited) == 2


def test_tick_marks_stale_authorization_failed_once(tmp_path):
    project, store, flow = _fixture(tmp_path)
    plan = operations.plan(project, store, flow['flow_id'], 'extract-build', batch='e1')
    operation_id = operations._digest(plan)
    operations.authorize(store, operation_id)
    store.append('chunks.jsonl', {'source_id': 'S01', 'chunk_id': 'S01#late',
                                  'text': 'Changed after approval.'})
    result = operations.tick(project, store)
    assert result['processed'] == 1
    assert result['operations'][0]['state'] == 'FAILED'
    assert operations.status(store, operation_id)['state'] == 'FAILED'
    assert operations.tick(project, store)['processed'] == 0


def test_failed_offline_operation_needs_new_named_attempt(tmp_path):
    project, store, flow = _fixture(tmp_path)
    plan = operations.plan(project, store, flow['flow_id'], 'extract-build', batch='e1')
    operation_id = operations._digest(plan)
    operations.authorize(store, operation_id)
    operations._append(store, operation_id, flow['flow_id'], 'failed', 'worker',
                       failure_class='BackendUnavailable')
    with pytest.raises(operations.OperationError, match='new --run-label'):
        operations.plan(project, store, flow['flow_id'], 'extract-build', batch='e1')
    replacement = operations.plan(project, store, flow['flow_id'], 'extract-build',
                                  batch='e1', run_label='after-repair')
    assert operations._digest(replacement) != operation_id


def test_batch_plan_and_one_operator_authorization_freeze_total_ceiling(tmp_path):
    root = tmp_path / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    project = load_project(root)
    store = Store(project.name, base=tmp_path / 'store')
    flow, _ = flows.create(project, store, selector=Selector('new'), title='new')
    batch = operations.plan_batch(project, store, flow['flow_id'], 'discover',
                                  apis=['openalex'], allowed_hosts=['api.openalex.org'],
                                  max_units=2, max_requests_each=3, per_query=5)
    assert len(batch['operation_ids']) == 2
    assert batch['max_total_requests'] == 6
    assert len(batch['units']) == 2
    assert batch['units'][0]['subject']['api'] == 'openalex'
    assert all(operations.status(store, op)['state'] == 'PLANNED'
               for op in batch['operation_ids'])
    authorized = operations.authorize_batch(store, batch['batch_id'])
    assert authorized['authorized_now'] == 2
    assert operations.authorize_batch(store, batch['batch_id'])['authorized_now'] == 0
    assert all(operations.status(store, op)['state'] == 'AUTHORIZED'
               for op in batch['operation_ids'])


def test_batch_plan_advances_past_completed_queries(tmp_path):
    from claimstone.store import sha256_text

    root = tmp_path / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    project = load_project(root)
    store = Store(project.name, base=tmp_path / 'store')
    flow, _ = flows.create(project, store, selector=Selector('new'), title='new')
    first_two = [(topic.id, term) for topic in project.topics
                 for term in topic.terms][:2]
    for topic_id, term in first_two:
        store.append('queries.jsonl', {
            'query_id': sha256_text(f'new|openalex|{topic_id}|{term}'),
            'round': 'new', 'source_api': 'openalex', 'topic_id': topic_id,
            'query': term, 'campaign': 'previous', 'ok': True, 'returned': 0})
    batch = operations.plan_batch(project, store, flow['flow_id'], 'discover',
                                  apis=['openalex'], allowed_hosts=['api.openalex.org'],
                                  max_units=2, max_requests_each=3, per_query=5)
    assert len(batch['operation_ids']) == 2
    assert batch['selected'] == 4
    assert len(batch['skipped']) == 2
    assert all((unit['subject']['topic_id'], unit['subject']['term']) not in first_two
               for unit in batch['units'])


def test_later_query_plan_survives_candidates_found_by_earlier_query(tmp_path, monkeypatch):
    from claimstone import discover

    root = tmp_path / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    project = load_project(root)
    store = Store(project.name, base=tmp_path / 'store')
    flow, _ = flows.create(project, store, selector=Selector('new'), title='new')
    batch = operations.plan_batch(project, store, flow['flow_id'], 'discover',
                                  apis=['openalex'], allowed_hosts=['api.openalex.org'],
                                  max_units=2, max_requests_each=2, per_query=5)
    operations.authorize_batch(store, batch['batch_id'])
    second_id = batch['operation_ids'][1]
    store.append('candidates.jsonl', {'candidate_key': 'doi:10.1/from-first-query',
                                      'round': 'new', 'source_class': 'ACA'})
    monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'test@example.org')

    def fake_run(project, store, fetcher, *, apis, topics, terms,
                 per_query, round_name, campaign):
        plan = operations.status(store, campaign)['plan']
        store.append('queries.jsonl', {'query_id': plan['query']['query_id'],
                                      'campaign': campaign, 'ok': True, 'returned': 0})
        return {'queries': 1}

    monkeypatch.setattr(discover, 'run', fake_run)
    assert operations.execute(project, store, second_id)['ok'] is True


def test_terminal_acquisition_retry_needs_named_class_and_reason(tmp_path):
    project, store, flow = _fixture(tmp_path)
    store.append('candidates.jsonl', {'candidate_key': 'doi:10.1/one',
                                      'source_id': 'S01', 'source_class': 'ACA',
                                      'round': 'new', 'url': 'https://example.org/paper.pdf'})
    store.append('acquisitions.jsonl', {'candidate_key': 'doi:10.1/one',
                                        'source_id': 'S01', 'acquired': False,
                                        'failure_class': 'PAYWALL_403',
                                        'campaign': 'earlier', 'attempt_no': 1})
    with pytest.raises(operations.OperationError, match='not eligible'):
        operations.plan(project, store, flow['flow_id'], 'acquire',
                        candidate_key='doi:10.1/one', allowed_hosts=['example.org'],
                        max_requests=2)
    with pytest.raises(operations.OperationError, match='stated reason'):
        operations.plan(project, store, flow['flow_id'], 'acquire',
                        candidate_key='doi:10.1/one', allowed_hosts=['example.org'],
                        max_requests=2, retry_classes=['PAYWALL_403'])
    plan = operations.plan(project, store, flow['flow_id'], 'acquire',
                           candidate_key='doi:10.1/one', allowed_hosts=['example.org'],
                           max_requests=2, retry_classes=['PAYWALL_403'],
                           retry_reason='new repository route verified')
    assert plan['retry_classes'] == ['PAYWALL_403']


def test_local_drive_stops_at_network_gate_and_respects_call_cap(tmp_path, monkeypatch):
    from claimstone import runners
    from claimstone.runners.base import RawAnswer

    root = tmp_path / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    project = load_project(root)
    store = Store(project.name, base=tmp_path / 'store')
    flow, _ = flows.create(project, store, selector=Selector('new'), title='new')
    empty = operations.drive_local(project, store, flow['flow_id'],
                                   extract_model='reader-a', review_model='reader-b',
                                   max_local_calls=1)
    assert empty['stopped_reason'] == 'NEEDS_AUTHORIZED_DISCOVERY'

    store.append('candidates.jsonl', {'candidate_key': 'doi:10.1/one',
                                      'source_id': 'S01', 'source_class': 'ACA',
                                      'round': 'new'})
    store.append('documents.jsonl', {'source_id': 'S01', 'fulltext_confirmed': True})
    store.append('chunks.jsonl', {'source_id': 'S01', 'chunk_id': 'S01#one',
                                  'text': 'News predicts next month returns.'})
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
    result = operations.drive_local(project, store, flow['flow_id'],
                                    extract_model='reader-a', review_model='reader-b',
                                    max_local_calls=1)
    assert result['local_calls'] == len(calls) == 1
    assert result['stopped_reason'] == 'NEEDS_ACQUISITION_FLOOR'


def test_drive_runs_preapproved_network_query_before_local_pass(tmp_path, monkeypatch):
    from claimstone import discover

    root = tmp_path / 'example-news-and-returns'
    shutil.copytree('projects/example-news-and-returns', root)
    project = load_project(root)
    store = Store(project.name, base=tmp_path / 'store')
    flow, _ = flows.create(project, store, selector=Selector('new'), title='new')
    topic = project.topics[0]
    frozen = operations.plan(project, store, flow['flow_id'], 'discover',
                             api='openalex', topic_id=topic.id, term=topic.terms[0],
                             per_query=1, allowed_hosts=['api.openalex.org'],
                             max_requests=1)
    operation_id = operations._digest(frozen)
    operations.authorize(store, operation_id)
    monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'test@example.org')

    def fake_run(project, store, fetcher, *, apis, topics, terms,
                 per_query, round_name, campaign):
        store.append('candidates.jsonl', {'candidate_key': 'doi:10.1/found',
                                          'source_id': 'S01', 'source_class': 'ACA',
                                          'round': round_name})
        store.append('queries.jsonl', {'query_id': frozen['query']['query_id'],
                                      'campaign': campaign, 'ok': True, 'returned': 1})
        return {'queries': 1}

    monkeypatch.setattr(discover, 'run', fake_run)
    result = operations.drive_local(project, store, flow['flow_id'],
                                    extract_model='reader-a', review_model='reader-b',
                                    max_local_calls=0)
    assert result['network']['processed'] == 1
    assert result['network']['operations'][0]['state'] == 'COMPLETED'
    assert result['local_calls'] == 0
