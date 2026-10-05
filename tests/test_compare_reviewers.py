"""An independent reader keeps fixed cases, prior attempts and scientific stores intact."""
import json
import pytest

from claimstone import model_call
from claimstone.store import Store
from tests.test_run_calibration import fake_runner
from tests.test_run_review_diagnostics import repaired_fixture, answer
from tools import compare_reviewers as run, run_review_diagnostics as diagnostics
from tools import run_prompt_comparison as comparison, complete_question_round as bounded
from tools.replay_answers import files_snapshot


def fixture(tmp_path, monkeypatch):
    project, origin, previous, baseline, old, base_plan, reference, paid, bad, _ = repaired_fixture(tmp_path, monkeypatch)
    queue, accounting = diagnostics.accounting_queues(origin, previous, baseline, old, base_plan)
    baseline_calls = fake_runner(monkeypatch, lambda model, unit: json.dumps(answer()).encode())
    bounded.drain('review', {'review': queue}, base_plan, accounting_queues=accounting)
    experiment = Store(origin.root.name, base=tmp_path / 'independent')
    plan = {'budget_usd': base_plan['budget_usd'], 'review': {
        'model': 'independent', 'batch': 'same-requests', 'context_tokens': 10000,
        'price_in': .95, 'price_out': 4., 'price_cached_in': .16, 'think': False},
        'frozen_diagnostics': files_snapshot(baseline), 'requests_sha256': base_plan['requests_sha256']}
    new_queue = model_call.Queue(experiment, lane='review', batch=plan['review']['batch'])
    new_queue_path = experiment.path(new_queue.requests_name)
    new_queue_path.parent.mkdir(parents=True)
    new_queue_path.write_bytes(baseline.path(queue.requests_name).read_bytes())
    return project, origin, previous, baseline, experiment, old, base_plan, plan, reference, paid+bad+baseline_calls


def test_fixed_cases_and_all_paid_history_resume_without_writing_science(tmp_path, monkeypatch):
    _, origin, previous, baseline, experiment, old, base_plan, plan, reference, paid = fixture(tmp_path, monkeypatch)
    run.validate(origin, previous, baseline, experiment, old, base_plan, plan, reference)
    before = [files_snapshot(s) for s in (origin, previous, baseline)]
    calls = fake_runner(monkeypatch, lambda model, unit: json.dumps(answer()).encode())
    queue, accounting, rates = run.accounting_queues(origin, previous, baseline, experiment, old, base_plan, plan)
    bounded.drain('review', {'review': queue}, rates, reader=plan['review'], accounting_queues=accounting)
    result = run.measure(origin, previous, baseline, experiment, old, base_plan, plan, reference)
    assert result['cases'] == result['baseline_reference_agreement'] == result['comparison_reference_agreement'] == 2
    assert result['unanswered'] == result['pending_physical_calls'] == 0
    assert result['priced_usd_at_plan_rates'] == pytest.approx((len(paid)+len(calls))*.00002)
    assert len(calls) == 1  # Two annotation targets share one identical prompt.
    assert [files_snapshot(s) for s in (origin, previous, baseline)] == before
    assert not experiment.path('reviews.jsonl').exists()
    bounded.drain('review', {'review': queue}, rates, reader=plan['review'], accounting_queues=accounting)
    assert len(calls) == 1


def test_unknown_cost_reserves_use_each_readers_original_rates(tmp_path, monkeypatch):
    _, origin, previous, baseline, experiment, old, base_plan, plan, reference, _ = fixture(tmp_path, monkeypatch)
    old_queue = model_call.Queue(baseline, lane='review', batch=base_plan['preceding_diagnostics'][0]['batch'])
    queue, _, _ = run.accounting_queues(origin, previous, baseline, experiment, old, base_plan, plan)
    for store, q, config in ((baseline, old_queue, base_plan['review']), (experiment, queue, plan['review'])):
        store.append(q.results_name, {'call_id': q.requests()[0]['call_id'], 'backend': 'ollama-cloud',
            'model': config['model'], 'ok': False, 'failure_class': 'BACKEND_ERROR', 'usage': None, 'cost_usd': None})
    result = run.measure(origin, previous, baseline, experiment, old, base_plan, plan, reference)
    expected = bounded.reservation(base_plan['review'], old_queue.requests()[0]) + bounded.reservation(plan['review'], queue.requests()[0])
    assert result['unknown_attempt_reservation_usd'] == pytest.approx(expected)
    assert result['unanswered'] == 2  # Baseline model answers do not fill new-reader cases.


@pytest.mark.parametrize('damage', ['budget', 'history', 'requests', 'same_reader', 'own_reader', 'rate', 'context', 'nested'])
def test_invalid_comparison_refuses_before_contact(tmp_path, monkeypatch, damage):
    _, origin, previous, baseline, experiment, old, base_plan, plan, reference, _ = fixture(tmp_path, monkeypatch)
    if damage == 'budget': plan['budget_usd'] += 1
    elif damage == 'history': baseline.append('extra.jsonl', {'change': True})
    elif damage == 'requests':
        q = model_call.Queue(experiment, lane='review', batch=plan['review']['batch'])
        experiment.append(q.requests_name, {'call_id': 'changed'})
    elif damage == 'same_reader': plan['review']['model'] = base_plan['review']['model']
    elif damage == 'own_reader': plan['review']['model'] = base_plan['extract']['model']
    elif damage == 'rate': plan['review']['price_in'] = float('nan')
    elif damage == 'context': plan['review']['context_tokens'] = 0
    else: experiment = Store('nested', base=baseline.root)
    with pytest.raises(ValueError): run.validate(origin, previous, baseline, experiment, old, base_plan, plan, reference)


def test_prior_spending_can_stop_new_reader_before_contact(tmp_path, monkeypatch):
    _, origin, previous, baseline, experiment, old, base_plan, plan, reference, _ = fixture(tmp_path, monkeypatch)
    queue, accounting, rates = run.accounting_queues(origin, previous, baseline, experiment, old, base_plan, plan)
    rates['budget_usd'] = bounded.expenditure(accounting, rates)['budget_accounted_usd']
    calls = fake_runner(monkeypatch, lambda model, unit: json.dumps(answer()).encode())
    with pytest.raises(bounded.Stopped, match='USD ceiling'):
        bounded.drain('review', {'review': queue}, rates, reader=plan['review'], accounting_queues=accounting)
    assert not calls


@pytest.mark.parametrize('mode', ['preview', 'complete', 'invalid'])
def test_driver_offline_preview_preservation_and_terminal_failure(tmp_path, monkeypatch, capsys, mode):
    project, origin, previous, baseline, experiment, old, base_plan, plan, reference, _ = fixture(tmp_path, monkeypatch)
    old_ref = tmp_path / 'old-reference.json'; old_ref.write_text(json.dumps({}))
    old.update(project=str(project.root), origin_store=str(origin.root.parent),
        experiment_store=str(previous.root.parent), reference=str(old_ref), reference_sha256=diagnostics.digest(old_ref))
    old_path = tmp_path / 'old-plan.json'; old_path.write_text(json.dumps(old))
    ref_path = tmp_path / 'reference.json'; ref_path.write_text(json.dumps(reference))
    base_plan.update(comparison_plan=str(old_path), comparison_plan_sha256=diagnostics.digest(old_path),
        reference=str(ref_path), reference_sha256=diagnostics.digest(ref_path), experiment_store=str(baseline.root.parent))
    base_path = tmp_path / 'baseline-plan.json'; base_path.write_text(json.dumps(base_plan))
    plan.update(baseline_plan=str(base_path), baseline_plan_sha256=diagnostics.digest(base_path),
        experiment_store=str(experiment.root.parent))
    path = tmp_path / 'new-plan.json'; path.write_text(json.dumps(plan))
    monkeypatch.setattr(run, 'load_project', lambda *args: project)
    monkeypatch.setattr(run, 'check_registry_drift', lambda *args, **kwargs: None)
    monkeypatch.setattr(comparison, 'validate', lambda *args: None)
    calls = fake_runner(monkeypatch, lambda model, unit: b'{}' if mode == 'invalid' else json.dumps(answer()).encode())
    monkeypatch.setattr('sys.argv', ['compare', '--plan', str(path)] + ([] if mode == 'preview' else ['--execute']))
    before = files_snapshot(experiment)
    capsys.readouterr()
    assert run.main() == (1 if mode == 'invalid' else 0)
    output = capsys.readouterr().out
    result = json.loads(output[output.index('{\n'):])
    assert result['status'] == {'preview': 'PREVIEW', 'complete': 'REVIEWER_COMPARISON_COMPLETE', 'invalid': 'STOPPED'}[mode]
    if mode == 'preview':
        assert not calls and files_snapshot(experiment) == before
    else:
        count = len(calls)
        assert result['previous_stores_unchanged'] and result['all_original_bytes_preserved']
        assert run.main() == (1 if mode == 'invalid' else 0)
        assert len(calls) == count
        assert not experiment.path('reviews.jsonl').exists()
