"""Paid continuation must stop within budget and retain failed attempts on resume."""
import json

import pytest

from claimstone import extract, model_call, review
from claimstone.runners.base import RawAnswer
from claimstone.store import Store
from tests.test_synthesize import _project, _store
from tools import complete_question_round as run


def queues(tmp_path):
    store = Store('t', base=tmp_path)
    unit = model_call.work_unit(lane='extract', system='Read', user='passage',
        response_schema={'type': 'array', 'items': {'type': 'string'}}, max_output_tokens=100, registry_version=1)
    held = {lane: model_call.Queue(store, lane=lane, batch=lane) for lane in model_call.LANES}
    held['extract'].write([unit])
    return held, unit


def plan(budget=1):
    return {'question_id': 'H02', 'budget_usd': budget,
            'extract': {'model': 'e', 'batch': 'extract', 'price_in': 1., 'price_out': 1., 'context_tokens': 1000},
            'review': {'model': 'r', 'batch': 'review', 'price_in': 1., 'price_out': 1., 'context_tokens': 1000}}


def test_budget_reserves_whole_next_call_before_contact(tmp_path, monkeypatch):
    held, unit = queues(tmp_path)
    monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'test@example.org')
    monkeypatch.setenv('OLLAMA_API_KEY', 'test')
    contacted = []
    monkeypatch.setattr(run.OllamaCloudRunner, 'run', lambda self, unit: contacted.append(unit))
    with pytest.raises(run.Stopped, match='USD ceiling'):
        run.drain('extract', held, plan(budget=.001))
    assert contacted == []
    assert held['extract'].attempts() == []


def test_one_transport_failure_stops_and_reserves_unknown_cost_on_resume(tmp_path, monkeypatch):
    held, unit = queues(tmp_path)
    monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'test@example.org')
    monkeypatch.setenv('OLLAMA_API_KEY', 'test')
    calls = []
    def fail(self, unit):
        calls.append(unit)
        return RawAnswer(model=self.model, failure_class='BACKEND_ERROR')
    monkeypatch.setattr(run.OllamaCloudRunner, 'run', fail)
    with pytest.raises(run.Stopped, match='BACKEND_ERROR'):
        run.drain('extract', held, plan())
    assert len(calls) == len(held['extract'].attempts()) == 1
    cost = run.expenditure(held, plan())
    assert cost['priced_usd_at_plan_rates'] == 0
    assert cost['unknown_attempt_reservation_usd'] == pytest.approx(.0011)
    with pytest.raises(run.Stopped, match='USD ceiling'):
        run.drain('extract', held, plan(budget=.002))
    assert len(calls) == 1
    held['extract'].store.append(held['extract'].results_name,
        held['extract'].attempts()[0] | {'rejudged_from': ''})
    assert run.expenditure(held, plan()) == cost


def test_own_reader_review_is_refused_before_payment(tmp_path, monkeypatch):
    held, _ = queues(tmp_path)
    unit = model_call.work_unit(lane='review', system='Review', user='annotation',
        response_schema={'type': 'object', 'properties': {}}, max_output_tokens=100, registry_version=1)
    unit.update(claim_id='c1', question_id='H02', extracted_by={'backend': 'ollama-cloud', 'model': 'r'})
    held['review'].write([unit])
    monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'test@example.org')
    monkeypatch.setenv('OLLAMA_API_KEY', 'test')
    contacted = []
    monkeypatch.setattr(run.OllamaCloudRunner, 'run', lambda self, unit: contacted.append(unit))
    with pytest.raises(run.Stopped, match='reviewer is also the extractor'):
        run.drain('review', held, plan())
    assert contacted == []


def test_cached_new_extraction_adds_full_reviews_and_never_adjudicates(tmp_path, monkeypatch):
    project = _project(tmp_path)
    store = _store(tmp_path)
    extract.build(project, store, batch='extract', kind='effect')
    queue = model_call.Queue(store, lane='extract', batch='extract')
    unit = queue.requests()[0]
    record = {'result_id': 'one', 'question_id': 'H02', 'claim': 'News tone has an effect.',
              'evidence_quote': 'news tone has an effect', 'stance': 'SUPPORTS'}
    store.append(queue.results_name, {'call_id': unit['call_id'],
        'backend': 'ollama-cloud', 'model': 'e', 'harness_version': 'test/1',
        'ok': True, 'output': [record], 'usage': {'input_tokens': 10, 'output_tokens': 10},
        'cost_usd': .00002})
    before = {path: path.read_bytes() for path in store.root.rglob('*') if path.is_file()}
    calls = []
    class Fake:
        name = 'ollama-cloud'
        max_concurrency = 1
        min_interval_s = 0
        def __init__(self, **kwargs):
            self.model = kwargs['model']
        def harness_version(self):
            return 'test/1'
        def run(self, unit):
            calls.append(unit)
            return RawAnswer(model=self.model,
                body=json.dumps({'verdict': 'SUPPORTED', 'reason': 'The entire annotation is established.'}).encode(),
                usage={'input_tokens': 10, 'output_tokens': 10}, cost_usd=.00002)
    monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'test@example.org')
    monkeypatch.setattr(run, 'OllamaCloudRunner', Fake)
    selected = run.execute(project, store, plan(), project.questions[0])
    assert not selected['provisional']
    assert len(review.current(store)) == 2
    assert len(calls) == 1  # identical prompts merge the two current annotation targets
    assert all(path.read_bytes().startswith(body) for path, body in before.items())
    assert not store.path('adjudications.jsonl').exists()
    assert not run.execute(project, store, plan(), project.questions[0])['provisional']
    assert len(calls) == 1


def test_env_reads_only_required_keys_without_executing_shell(tmp_path, monkeypatch):
    monkeypatch.delenv('OLLAMA_API_KEY', raising=False)
    monkeypatch.delenv('CLAIMSTONE_CONTACT_EMAIL', raising=False)
    monkeypatch.setenv('UID', 'unchanged')
    path = tmp_path / '.env'
    path.write_text('UID=123\nOLLAMA_API_KEY="literal-$(no-shell)"\n'
                    'export CLAIMSTONE_CONTACT_EMAIL=test@example.org # contact\n')
    run.load_environment(path)
    import os
    assert os.environ['UID'] == 'unchanged'
    assert os.environ['OLLAMA_API_KEY'] == 'literal-$(no-shell)'
    assert os.environ['CLAIMSTONE_CONTACT_EMAIL'] == 'test@example.org'
