"""Experimental comparisons preserve production and share the original spending ceiling."""
import copy
import hashlib
import json
import pytest

from claimstone import model_call, review
from claimstone.store import Store
from tests.test_run_calibration import setup, fake_runner, RECORD, validation_fixture
from tools import run_calibration as calibration, run_prompt_comparison as run
from tools import complete_question_round as bounded
from tools.replay_answers import files_snapshot


def comparison(tmp_path, origin, baseline):
    experiment = Store(origin.root.name, base=tmp_path / 'experiments')
    plan = copy.deepcopy(baseline)
    plan.update(baseline=copy.deepcopy(baseline), origin_store=str(origin.root.parent),
                experiment_store=str(experiment.root.parent), diagnostic_batch='diagnostics')
    path = tmp_path / 'baseline.json'; path.write_text(json.dumps(baseline))
    plan.update(baseline_plan=str(path), baseline_plan_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    plan['frozen_ledgers'] = {}
    for name in ('chunks.jsonl', 'documents.jsonl', 'registry.jsonl'):
        if origin.path(name).exists():
            experiment.path(name).parent.mkdir(parents=True, exist_ok=True)
            experiment.path(name).write_bytes(origin.path(name).read_bytes())
            plan['frozen_ledgers'][name] = hashlib.sha256(origin.path(name).read_bytes()).hexdigest()
    for lane in model_call.LANES: plan[lane]['batch'] = 'variant-' + lane
    original = model_call.Queue(origin, lane='extract', batch=baseline['extract']['batch'])
    new = model_call.Queue(experiment, lane='extract', batch=plan['extract']['batch'])
    for unit in original.requests():
        rebuilt = run.clone(unit, unit['system'] + '\n' + run.EXTRACT_APPENDIX)
        for asker in unit.get('asked_by') or [unit]:
            new.write([dict(rebuilt, source_id=asker['source_id'], chunk_id=asker['chunk_id'])])
    original_reviews = model_call.Queue(origin, lane='review', batch=baseline['review']['batch'])
    if not original_reviews.requests():
        unit = model_call.work_unit(lane='review', system='Review exactly', user='a passage',
            response_schema=review.SCHEMA, max_output_tokens=100, registry_version=1)
        unit.update(claim_id='case', question_id=baseline['question_ids'][0],
                    extracted_by={'backend': 'ollama-cloud', 'model': baseline['extract']['model']})
        original_reviews.write([unit])
    source = original_reviews.requests()[0]
    diagnostic = model_call.Queue(experiment, lane='review', batch=plan['diagnostic_batch'])
    cases = []
    for target in source['review_targets']:
        diagnostic.write([run.clone(source, source['system'] + '\n' + run.REVIEW_APPENDIX, target)])
        cases.append({'claim_id': target['claim_id'], 'expected': 'SUPPORTED', 'baseline_verdict': 'SUPPORTED',
                      'rationale': 'The supplied passage supports this synthetic record.', 'control': 'positive'})
    reference = {'status': 'provisional_agent_development_reference', 'cases': cases}
    plan['frozen_requests'] = {q.requests_name: hashlib.sha256(experiment.path(q.requests_name).read_bytes()).hexdigest()
                               for q in (new, diagnostic)}
    return experiment, plan, reference


def test_complete_comparison_preserves_production_and_resume_is_free(tmp_path, monkeypatch):
    project, origin, baseline = setup(tmp_path)
    calls = fake_runner(monkeypatch, lambda model, unit: json.dumps([RECORD] if model == 'extractor'
        else {'verdict': 'SUPPORTED', 'reason': 'Matches the supplied passage.'}).encode())
    calibration.execute(project, origin, baseline)
    experiment, plan, reference = comparison(tmp_path, origin, baseline)
    before = files_snapshot(origin)
    run.execute(project, origin, experiment, plan)
    assert files_snapshot(origin) == before
    measured = run.measure(project, origin, experiment, plan, reference)
    assert measured['diagnostic_unanswered'] == 0
    assert measured['variant_reference_agreement'] == len(reference['cases'])
    assert measured['variant_sample']['accepted_annotations'] == 2
    assert measured['variant_sample']['reviewed_annotations'] == 2
    assert not measured['automatic_adoption'] and not measured['reference_is_held_out']
    assert not experiment.path('profiles.jsonl').exists()
    count = len(calls)
    run.execute(project, origin, experiment, plan)
    assert len(calls) == count
    held, diagnostic, accounting = run.queues_and_accounting(origin, experiment, plan)
    assert measured['priced_usd_at_plan_rates'] == pytest.approx(len(calls) * .00002)


def test_original_unknown_attempt_blocks_new_comparison_spending(tmp_path, monkeypatch):
    project, origin, baseline = setup(tmp_path)
    queue = model_call.Queue(origin, lane='extract', batch=baseline['extract']['batch'])
    queue.store.append(queue.results_name, {'call_id': queue.requests()[0]['call_id'],
        'backend': 'ollama-cloud', 'model': 'extractor', 'ok': False, 'failure_class': 'BACKEND_ERROR'})
    experiment, plan, reference = comparison(tmp_path, origin, baseline)
    plan['budget_usd'] = .003
    calls = fake_runner(monkeypatch, lambda model, unit: b'[]')
    with pytest.raises(bounded.Stopped, match='USD ceiling'):
        run.execute(project, origin, experiment, plan)
    assert not calls
    assert run.measure(project, origin, experiment, plan, reference)['unknown_attempt_reservation_usd'] > .003


def test_altered_generated_review_refuses_before_more_payment(tmp_path, monkeypatch):
    project, origin, baseline = setup(tmp_path)
    calls = fake_runner(monkeypatch, lambda model, unit: json.dumps([RECORD] if model == 'extractor'
        else {'verdict': 'SUPPORTED', 'reason': 'Matches.'}).encode())
    calibration.execute(project, origin, baseline)
    experiment, plan, reference = comparison(tmp_path, origin, baseline)
    run.execute(project, origin, experiment, plan)
    queue = model_call.Queue(experiment, lane='review', batch=plan['review']['batch'])
    original = queue.requests()[0]
    experiment.append(queue.requests_name, dict(original, system='unapproved altered prompt'))
    before = len(calls)
    with pytest.raises(ValueError, match='unexpected experimental full-review request'):
        run.execute(project, origin, experiment, plan)
    assert len(calls) == before


@pytest.mark.parametrize('damage', ['budget', 'source', 'requests', 'nested_store'])
def test_validation_refuses_drift_and_overlapping_stores(tmp_path, damage):
    project, origin, baseline = validation_fixture(tmp_path)
    experiment, plan, reference = comparison(tmp_path, origin, baseline)
    run.validate(project, origin, experiment, plan, reference)
    if damage == 'budget': plan['budget_usd'] += 1
    elif damage == 'source': origin.append('chunks.jsonl', {'text': 'changed'})
    elif damage == 'requests':
        queue = model_call.Queue(experiment, lane='review', batch=plan['diagnostic_batch'])
        experiment.append(queue.requests_name, {'call_id': 'unplanned'})
    else: experiment = Store('nested', base=origin.root)
    with pytest.raises(ValueError): run.validate(project, origin, experiment, plan, reference)


def test_preview_does_not_write_or_contact_a_reader(tmp_path, monkeypatch, capsys):
    project, origin, baseline = validation_fixture(tmp_path)
    experiment, plan, reference = comparison(tmp_path, origin, baseline)
    ref = tmp_path / 'reference.json'; ref.write_text(json.dumps(reference))
    plan.update(reference=str(ref), reference_sha256=hashlib.sha256(ref.read_bytes()).hexdigest())
    path = tmp_path / 'plan.json'; path.write_text(json.dumps(plan))
    monkeypatch.setattr('sys.argv', ['comparison', '--plan', str(path)])
    monkeypatch.setattr(run, 'execute', lambda *a: pytest.fail('preview contacted a reader'))
    before = files_snapshot(origin), files_snapshot(experiment)
    assert run.main() == 0
    assert (files_snapshot(origin), files_snapshot(experiment)) == before
    assert '"status": "PREVIEW"' in capsys.readouterr().out
