"""Three-axis diagnostics preserve scientific stores and retain all cumulative spending."""
import copy
import hashlib
import json
import pytest

from claimstone import claim_records, chunk_sets, model_call, review, jsonshape
from claimstone.store import Store
from tests.test_run_calibration import setup, fake_runner, RECORD
from tests.test_run_prompt_comparison import comparison as prepare_comparison
from tools import run_calibration as calibration, run_prompt_comparison as comparison
from tools import run_review_diagnostics as run, complete_question_round as bounded
from tools.replay_answers import files_snapshot


def answer(applicability='APPLICABLE', fidelity='FAITHFUL', direction='COHERENT'):
    return {key: {'label': value, 'reason': 'Synthetic supplied evidence.'} for key, value in
            [('applicability', applicability), ('fidelity', fidelity), ('direction', direction)]}


def fixture(tmp_path, monkeypatch):
    project, origin, baseline = setup(tmp_path)
    calls = fake_runner(monkeypatch, lambda model, unit: json.dumps([RECORD] if model == 'extractor'
        else {'verdict': 'SUPPORTED', 'reason': 'Matches.'}).encode())
    calibration.execute(project, origin, baseline)
    previous, old_plan, old_reference = prepare_comparison(tmp_path, origin, baseline)
    comparison.execute(project, origin, previous, old_plan)
    experiment = Store(origin.root.name, base=tmp_path / 'axes')
    cases = []
    for cid, a in calibration.selected_claims(origin, baseline['extract']['batch']).items():
        cases.append({'claim_id': cid, 'annotation_store': 'baseline', 'control': 'positive',
            'expected_label': 'SUPPORTED', 'previous_label': 'SUPPORTED', 'rationale': 'Synthetic reference.',
            'expected_axes': {k: answer()[k]['label'] for k in run.AXES},
            'annotation_sha256': hashlib.sha256(model_call.canonical(review.annotation(a)).encode()).hexdigest(),
            'passage_sha256': hashlib.sha256(chunk_sets.current(origin)[a['chunk_id']]['text'].encode()).hexdigest()})
    reference = {'status': 'provisional_agent_development_reference', 'cases': cases}
    plan = {k: copy.deepcopy(old_plan[k]) for k in ('budget_usd', 'question_ids', 'extract', 'review')}
    plan['review']['batch'] = 'axes'; plan['frozen_history'] = {'baseline': {}, 'variant': {}}
    for label, store in [('baseline', origin), ('variant', previous)]:
        plan['frozen_history'][label] = {str(p.relative_to(store.root)): run.digest(p)
                                        for p in store.root.rglob('*.jsonl')}
    queue = model_call.Queue(experiment, lane='review', batch='axes')
    queue.write([run.make_unit(project, origin, c) for c in cases])
    plan['requests_sha256'] = run.digest(experiment.path(queue.requests_name))
    return project, origin, previous, experiment, old_plan, plan, reference, calls


@pytest.mark.parametrize('a,f,d,expected', [
    ('APPLICABLE','FAITHFUL','COHERENT','SUPPORTED'),
    ('NOT_APPLICABLE','FAITHFUL','UNCLEAR','NOT_APPLICABLE'),
    ('NOT_APPLICABLE','UNFAITHFUL','INCOHERENT','NOT_APPLICABLE'),
    ('APPLICABLE','UNFAITHFUL','COHERENT','OVERSTATED'),
    ('APPLICABLE','FAITHFUL','INCOHERENT','OVERSTATED'),
    ('APPLICABLE','UNCLEAR','COHERENT','AMBIGUOUS')])
def test_diagnostic_mapping_keeps_checks_separate(a, f, d, expected):
    assert run.diagnostic_label(answer(a,f,d)) == expected


def test_schema_requires_three_checks_and_no_final_verdict():
    jsonshape.check_schema(run.SCHEMA)
    assert not jsonshape.errors(answer(), run.SCHEMA)
    assert jsonshape.errors({'verdict': 'SUPPORTED', 'reason': 'Missing checks.'}, run.SCHEMA)
    assert jsonshape.errors(dict(answer(), verdict='SUPPORTED'), run.SCHEMA)


def test_fixed_annotations_resume_free_and_all_prior_costs_count(tmp_path, monkeypatch):
    project, origin, previous, experiment, old, plan, reference, paid = fixture(tmp_path, monkeypatch)
    run.validate(project, origin, previous, experiment, old, plan, reference)
    snapshots = files_snapshot(origin), files_snapshot(previous)
    calls = fake_runner(monkeypatch, lambda model, unit: json.dumps(answer()).encode())
    queue, accounting = run.accounting_queues(origin, previous, experiment, old, plan)
    bounded.drain('review', {'review': queue}, plan, accounting_queues=accounting)
    result = run.measure(origin, previous, experiment, old, plan, reference)
    assert result['unanswered'] == 0
    assert result['controls']['positive']['diagnostic_agreement'] == 2
    assert result['axis_reference_agreement']['fidelity']['agreed'] == 2
    assert result['priced_usd_at_plan_rates'] == pytest.approx((len(paid)+len(calls))*.00002)
    assert (files_snapshot(origin), files_snapshot(previous)) == snapshots
    assert not experiment.path('reviews.jsonl').exists()
    assert result['production_reviews_written'] == result['extraction_calls'] == 0
    bounded.drain('review', {'review': queue}, plan, accounting_queues=accounting)
    assert len(calls) == 1  # identical passages share a call, retaining both annotation targets


@pytest.mark.parametrize('damage', ['budget', 'history', 'annotation', 'request', 'nested', 'no_positive'])
def test_drift_refuses_before_contact(tmp_path, monkeypatch, damage):
    project, origin, previous, experiment, old, plan, reference, paid = fixture(tmp_path, monkeypatch)
    if damage == 'budget': plan['budget_usd'] += 1
    elif damage == 'history': origin.append('claims.jsonl', {'claim_id': 'changed'})
    elif damage == 'annotation': reference['cases'][0]['annotation_sha256'] = 'changed'
    elif damage == 'request':
        queue = model_call.Queue(experiment, lane='review', batch='axes')
        experiment.append(queue.requests_name, {'call_id': 'unexpected'})
    elif damage == 'nested': experiment = Store('nested', base=previous.root)
    else:
        for case in reference['cases']: case['control'] = 'challenge'
    with pytest.raises(ValueError): run.validate(project, origin, previous, experiment, old, plan, reference)


def test_previous_unknown_attempt_prevents_new_spending(tmp_path, monkeypatch):
    project, origin, previous, experiment, old, plan, reference, paid = fixture(tmp_path, monkeypatch)
    old_queue = model_call.Queue(origin, lane='extract', batch=old['baseline']['extract']['batch'])
    origin.append(old_queue.results_name, {'call_id': old_queue.requests()[0]['call_id'],
        'backend':'ollama-cloud','model':'extractor','ok':False,'failure_class':'BACKEND_ERROR'})
    plan['budget_usd'] = .003
    calls = fake_runner(monkeypatch, lambda model, unit: json.dumps(answer()).encode())
    queue, accounting = run.accounting_queues(origin, previous, experiment, old, plan)
    with pytest.raises(bounded.Stopped, match='USD ceiling'):
        bounded.drain('review', {'review': queue}, plan, accounting_queues=accounting)
    assert not calls


def test_unscored_axis_and_unanswered_cases_are_not_agreement(tmp_path, monkeypatch):
    project, origin, previous, experiment, old, plan, reference, paid = fixture(tmp_path, monkeypatch)
    reference['cases'][0]['expected_axes']['direction'] = None
    result = run.measure(origin, previous, experiment, old, plan, reference)
    assert result['unanswered'] == 2
    assert result['axis_reference_agreement']['direction'] == {'scored':1, 'answered':0, 'agreed':0}
    assert result['controls']['positive']['diagnostic_agreement'] == 0


@pytest.mark.parametrize('mode', ['preview', 'complete', 'invalid'])
def test_driver_preview_preservation_and_invalid_resume(tmp_path, monkeypatch, capsys, mode):
    project, origin, previous, experiment, old, plan, reference, paid = fixture(tmp_path, monkeypatch)
    old_ref = tmp_path / 'old-reference.json'
    old_ref.write_text(json.dumps({'status':'provisional_agent_development_reference'}))
    old.update(project=str(project.root), origin_store=str(origin.root.parent),
               experiment_store=str(previous.root.parent), reference=str(old_ref),
               reference_sha256=run.digest(old_ref))
    old_path = tmp_path / 'comparison.json'; old_path.write_text(json.dumps(old))
    ref_path = tmp_path / 'reference.json'; ref_path.write_text(json.dumps(reference))
    plan.update(comparison_plan=str(old_path), comparison_plan_sha256=run.digest(old_path),
                reference=str(ref_path), reference_sha256=run.digest(ref_path),
                experiment_store=str(experiment.root.parent))
    path = tmp_path / 'axes-plan.json'; path.write_text(json.dumps(plan))
    monkeypatch.setattr(run, 'load_project', lambda *args: project)
    monkeypatch.setattr(run, 'check_registry_drift', lambda *args, **kwargs: None)
    # The real previous-plan validator is exercised by comparison tests; this synthetic project
    # intentionally has no filesystem config. The new task and all frozen histories are validated.
    monkeypatch.setattr(comparison, 'validate', lambda *args: None)
    calls = fake_runner(monkeypatch, lambda model, unit: b'{}' if mode=='invalid'
                        else json.dumps(answer()).encode())
    monkeypatch.setattr('sys.argv', ['diagnostics', '--plan', str(path)] +
                        ([] if mode=='preview' else ['--execute']))
    prior = files_snapshot(origin), files_snapshot(previous)
    before = files_snapshot(experiment)
    expected_status = {'preview':'PREVIEW','complete':'DIAGNOSTICS_COMPLETE','invalid':'STOPPED'}[mode]
    capsys.readouterr()
    assert run.main() == (1 if mode=='invalid' else 0)
    output = capsys.readouterr().out
    assert json.loads(output[output.index('{\n'):])['status'] == expected_status
    assert (files_snapshot(origin), files_snapshot(previous)) == prior
    if mode=='preview':
        assert not calls and files_snapshot(experiment) == before
    else:
        count = len(calls)
        assert run.main() == (1 if mode=='invalid' else 0)
        assert len(calls) == count
        assert not experiment.path('reviews.jsonl').exists()


def repaired_fixture(tmp_path, monkeypatch):
    project, origin, previous, experiment, old, plan, reference, paid = fixture(tmp_path, monkeypatch)
    queue, accounting = run.accounting_queues(origin, previous, experiment, old, plan)
    bad_calls = fake_runner(monkeypatch, lambda model, unit: json.dumps([
        {'check': 'APPLICABILITY', 'verdict': 'APPLICABLE', 'reason': 'Wrong shape.'}]).encode())
    with pytest.raises(bounded.Stopped, match='SCHEMA_INVALID'):
        bounded.drain('review', {'review':queue}, plan, accounting_queues=accounting)
    repaired = copy.deepcopy(plan)
    repaired.update(format_version=2, preceding_diagnostics=[{'store':str(experiment.root.parent),
        'batch':plan['review']['batch'], 'requests_sha256':run.digest(experiment.path(queue.requests_name)),
        'results_sha256':run.digest(experiment.path(queue.results_name))}])
    repaired['review']['batch'] = 'explicit-format'
    new_queue = model_call.Queue(experiment, lane='review', batch=repaired['review']['batch'])
    new_queue.write([run.make_unit(project, origin, c, format_version=2) for c in reference['cases']])
    repaired['requests_sha256'] = run.digest(experiment.path(new_queue.requests_name))
    return project, origin, previous, experiment, old, repaired, reference, paid, bad_calls, queue


def test_format_repair_preserves_failed_answer_and_includes_its_cost(tmp_path, monkeypatch):
    project, origin, previous, experiment, old, plan, reference, paid, bad_calls, prior = repaired_fixture(tmp_path, monkeypatch)
    run.validate(project, origin, previous, experiment, old, plan, reference)
    before = experiment.path(prior.results_name).read_bytes()
    prior_units = prior.requests()
    assert all(u['system'] == run.SYSTEM for u in prior_units)
    queue, accounting = run.accounting_queues(origin, previous, experiment, old, plan)
    assert all(u['system'] == run.SYSTEM + run.FORMAT_APPENDIX for u in queue.requests())
    assert {u['call_id'] for u in queue.requests()}.isdisjoint({u['call_id'] for u in prior_units})
    assert all(u['response_schema'] == run.SCHEMA for u in queue.requests())
    calls = fake_runner(monkeypatch, lambda model, unit: json.dumps(answer()).encode())
    bounded.drain('review', {'review':queue}, plan, accounting_queues=accounting)
    result = run.measure(origin, previous, experiment, old, plan, reference)
    assert result['unanswered'] == 0
    assert result['priced_usd_at_plan_rates'] == pytest.approx((len(paid)+len(bad_calls)+len(calls))*.00002)
    assert experiment.path(prior.results_name).read_bytes() == before
    assert all(not r['ok'] for r in prior.results().values())
    assert not experiment.path('reviews.jsonl').exists()


@pytest.mark.parametrize('damage', ['missing', 'duplicate', 'hash', 'current_batch', 'store'])
def test_format_repair_refuses_incomplete_or_duplicated_prior_accounting(tmp_path, monkeypatch, damage):
    project, origin, previous, experiment, old, plan, reference, paid, bad_calls, prior = repaired_fixture(tmp_path, monkeypatch)
    entry = plan['preceding_diagnostics'][0]
    if damage == 'missing': plan['preceding_diagnostics'] = []
    elif damage == 'duplicate': plan['preceding_diagnostics'].append(dict(entry))
    elif damage == 'hash': entry['results_sha256'] = 'wrong'
    elif damage == 'current_batch': entry['batch'] = plan['review']['batch']
    else: entry['store'] = str(previous.root.parent)
    with pytest.raises(ValueError): run.validate(project, origin, previous, experiment, old, plan, reference)
