"""Calibration completes its sample, preserves failures and never becomes a corpus verdict."""
import json
import pytest

from claimstone import extract, model_call, review, claim_records
from claimstone.runners.base import RawAnswer
from tests.test_synthesize import _project, _store
from tools import complete_question_round as bounded, run_calibration as run


def setup(tmp_path):
    project = _project(tmp_path); store = _store(tmp_path)
    extract.build(project, store, batch='calibration', kind='effect')
    plan = {'question_ids': ['H02', 'H06'], 'budget_usd': 10., 'round': 'routine',
        'extract': {'batch': 'calibration', 'model': 'extractor', 'context_tokens': 1000,
                    'price_in': 1., 'price_out': 1.},
        'review': {'batch': 'calibration-review', 'model': 'reviewer', 'context_tokens': 1000,
                   'price_in': 1., 'price_out': 1.}}
    return project, store, plan


def fake_runner(monkeypatch, bodies):
    calls = []
    class Fake:
        name = 'ollama-cloud'; max_concurrency = 1; min_interval_s = 0
        def __init__(self, **kwargs): self.model = kwargs['model']
        def harness_version(self): return 'synthetic/1'
        def run(self, unit):
            calls.append((self.model, unit['call_id']))
            return RawAnswer(model=self.model, body=bodies(self.model, unit),
                usage={'input_tokens': 10, 'output_tokens': 10}, cost_usd=.00002)
    monkeypatch.setattr(bounded, 'OllamaCloudRunner', Fake)
    monkeypatch.setenv('OLLAMA_API_KEY', 'synthetic'); monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'test@example.org')
    return calls


RECORD = {'result_id': 'one', 'question_id': 'H02', 'claim': 'News tone has an effect.',
          'evidence_quote': 'news tone has an effect', 'stance': 'SUPPORTS'}


def test_complete_sample_is_reviewed_and_resume_pays_nothing(tmp_path, monkeypatch):
    project, store, plan = setup(tmp_path)
    calls = fake_runner(monkeypatch, lambda model, unit: json.dumps(
        [RECORD] if model == 'extractor' else {'verdict': 'SUPPORTED', 'reason': 'The annotation matches.'}).encode())
    run.execute(project, store, plan)
    measured = run.measure(project, store, plan)
    assert measured['calibration']['accepted_annotations'] == 2
    assert measured['calibration']['reviewed_annotations'] == 2
    assert not measured['profile_built'] and not measured['adjudication_written']
    assert not store.path('profiles.jsonl').exists()
    assert not store.path('adjudications.jsonl').exists()
    before = len(calls)
    run.execute(project, store, plan)
    assert len(calls) == before


def test_failure_preserves_successful_harvest(tmp_path, monkeypatch):
    project, store, plan = setup(tmp_path)
    store.append('chunks.jsonl', {'chunk_id': 'ACA001#c2', 'source_id': 'ACA001', 'kind': 'prose',
        'text': 'A second distinct passage'})
    extract.build(project, store, batch='calibration', kind='effect')
    calls = fake_runner(monkeypatch, lambda model, unit: json.dumps([RECORD]).encode()
        if 'news tone' in unit['user'] else b'[]\nextra prose')
    with pytest.raises(bounded.Stopped, match='NOT_JSON'):
        run.execute(project, store, plan)
    assert len(claim_records.current(store)[0]) == 2
    assert len(calls) == 2
    assert not store.path('profiles.jsonl').exists()


def test_all_questions_in_declared_calibration_can_be_reviewed(tmp_path, monkeypatch):
    project, store, plan = setup(tmp_path)
    queue = model_call.Queue(store, lane='review', batch=plan['review']['batch'])
    unit = model_call.work_unit(lane='review', system='Read', user='passage',
        response_schema=review.SCHEMA, max_output_tokens=100, registry_version=3)
    unit.update(claim_id='another', question_id='H06', extracted_by={'backend': 'ollama-cloud', 'model': 'extractor'})
    queue.write([unit])
    calls = fake_runner(monkeypatch, lambda model, unit: b'{"verdict":"SUPPORTED","reason":"Matches."}')
    queues = {lane: model_call.Queue(store, lane=lane, batch=plan[lane]['batch']) for lane in model_call.LANES}
    bounded.drain('review', queues, plan)
    assert len(calls) == 1


def test_reviews_of_other_batches_never_enter_paid_sample(tmp_path, monkeypatch):
    project, store, plan = setup(tmp_path)
    fake_runner(monkeypatch, lambda model, unit: json.dumps([RECORD]).encode())
    queues = {lane: model_call.Queue(store, lane=lane, batch=plan[lane]['batch']) for lane in model_call.LANES}
    bounded.drain('extract', queues, plan); extract.harvest(project, store, batch='calibration')
    claim = dict(next(iter(claim_records.current(store)[0].values())))
    claim.update(claim_id='unrelated', batch='different-batch', answer_batches=['different-batch'])
    # No result key: represents a legacy unrelated annotation, which stage 5 can read.
    for key in ['call_id', 'result_key', 'raw_record']:
        claim.pop(key, None)
    store.append('claims.jsonl', claim)
    run.build_reviews(project, store, plan)
    queue = queues['review']
    assert all(t['claim_id'] != 'unrelated' for u in queue.requests() for t in u['review_targets'])


def test_shared_budget_applies_across_extract_and_review(tmp_path, monkeypatch):
    project, store, plan = setup(tmp_path)
    plan['budget_usd'] = .001
    calls = fake_runner(monkeypatch, lambda model, unit: b'[]')
    with pytest.raises(bounded.Stopped, match='USD ceiling'):
        run.execute(project, store, plan)
    assert not calls


def validation_fixture(tmp_path):
    import hashlib
    from tests.test_prepare_research_round import fixture
    from tools.prepare_research_round import prepare
    from claimstone.config import load_project
    initial, old, store = fixture(tmp_path)
    prepare(initial, apply=True)
    project = load_project(initial['project'])
    plan = {'project': str(project.root), 'store': initial['store_base'], 'round': initial['round'],
        'registry_sha256': project.registry_sha256, 'budget_usd': 10.,
        'input_sha256': initial['input_sha256'],
        'question_ids': [q.id for q in project.questions if q.kind != 'operational'],
        'selection': [{'source_id': 'S1', 'kind': k} for k in ('effect', 'method')],
        'extract': {'batch': initial['batch'], 'model': 'extractor', 'context_tokens': 1000,
            'price_in': 1., 'price_out': 1.},
        'review': {'batch': 'review', 'model': 'reviewer', 'context_tokens': 1000,
            'price_in': 1., 'price_out': 1.}}
    queue = model_call.Queue(store, lane='extract', batch=initial['batch'])
    plan['extract_requests_sha256'] = hashlib.sha256(store.path(queue.requests_name).read_bytes()).hexdigest()
    return project, store, plan


def test_preview_is_offline_and_writes_nothing(tmp_path, monkeypatch, capsys):
    from tools.replay_answers import files_snapshot
    project, store, plan = validation_fixture(tmp_path)
    path = tmp_path / 'plan.json'; path.write_text(json.dumps(plan))
    monkeypatch.setattr('sys.argv', ['run_calibration', '--plan', str(path)])
    before = files_snapshot(store)
    assert run.main() == 0
    assert files_snapshot(store) == before
    assert '"status": "PREVIEW"' in capsys.readouterr().out


@pytest.mark.parametrize('damage', ['input', 'passage'])
def test_input_or_passage_drift_refuses_before_contact(tmp_path, damage):
    project, store, plan = validation_fixture(tmp_path)
    run.validate(plan, project, store)
    if damage == 'input':
        path = project.root / 'questions.yaml'
        path.write_text(path.read_text() + '\n# changed input\n')
    else:
        chunk = next(iter(store.read('chunks.jsonl')))
        store.append('chunks.jsonl', dict(chunk, text='changed passage'))
    with pytest.raises(ValueError, match='input changed|hash mismatch|passage changed'):
        run.validate(plan, project, store)
