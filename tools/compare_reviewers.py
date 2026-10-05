#!/usr/bin/env python
"""Compare independent readers on identical diagnostic requests, within one cumulative budget.

Preview is offline. This experiment neither harvests production reviews nor signs verdicts.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import model_call
from claimstone.config import load_project, check_registry_drift
from claimstone.store import Store
from tools import complete_question_round as bounded, run_prompt_comparison as comparison
from tools import run_review_diagnostics as diagnostics
from tools.replay_answers import files_snapshot, validate_history


def accounting_queues(origin, previous, baseline, experiment, old_plan, baseline_plan, plan):
    _, accounting = diagnostics.accounting_queues(origin, previous, baseline, old_plan, baseline_plan)
    queue = model_call.Queue(experiment, lane='review', batch=plan['review']['batch'])
    # This key is an accounting bucket, not a new model-call lane. Historical readers retain
    # their own prices/context bounds; an unknown old attempt cannot be repriced as the new reader.
    accounting['comparison_review'] = queue
    rates = {k: baseline_plan[k] for k in ('extract', 'review', 'question_ids')}
    rates.update(budget_usd=plan['budget_usd'], comparison_review=plan['review'])
    return queue, accounting, rates


def answers(queue, model):
    results = {r['call_id']: r['output'] for r in
               queue.results(backend='ollama-cloud', model=model).values() if r.get('ok')}
    return {t['claim_id']: results[u['call_id']] for u in queue.requests()
            if u['call_id'] in results for t in u['review_targets']}


def validate(origin, previous, baseline, experiment, old_plan, baseline_plan, plan, reference):
    roots = [s.root.resolve() for s in (origin, previous, baseline, experiment)]
    if any(a.is_relative_to(b) or b.is_relative_to(a)
           for i, a in enumerate(roots) for b in roots[i+1:]):
        raise ValueError('comparison needs nonoverlapping stores')
    if plan['budget_usd'] != baseline_plan['budget_usd']:
        raise ValueError('retain the original cumulative budget')
    if files_snapshot(baseline) != plan['frozen_diagnostics']:
        raise ValueError('baseline diagnostic history changed')
    reader = plan['review']
    if reader.get('fallback') or reader.get('think') not in (None, True, False):
        raise ValueError('one explicitly configured comparison reader required')
    if not reader['model'] or reader['model'] == baseline_plan['review']['model']:
        raise ValueError('comparison reader must differ from baseline reviewer')
    for key in ('price_in', 'price_out', 'price_cached_in'):
        if key in reader and (not math.isfinite(reader[key]) or reader[key] < 0):
            raise ValueError('invalid comparison reader rate')
    if type(reader['context_tokens']) is not int or reader['context_tokens'] <= 0:
        raise ValueError('context ceiling must be a positive integer')
    baseline_queue = model_call.Queue(baseline, lane='review', batch=baseline_plan['review']['batch'])
    queue, accounting, rates = accounting_queues(
        origin, previous, baseline, experiment, old_plan, baseline_plan, plan)
    request_hash = diagnostics.digest(experiment.path(queue.requests_name))
    if request_hash != plan['requests_sha256'] or request_hash != baseline_plan['requests_sha256']:
        raise ValueError('comparison requests must be byte-identical to baseline')
    baseline_answers = answers(baseline_queue, baseline_plan['review']['model'])
    if set(baseline_answers) != {c['claim_id'] for c in reference['cases']}:
        raise ValueError('baseline diagnostics must be complete')
    for unit in queue.requests():
        for target in unit['review_targets']:
            if (target.get('extracted_by') or {}).get('model') == reader['model'] and (
                    target.get('extracted_by') or {}).get('backend') == 'ollama-cloud':
                raise ValueError('comparison reviewer is also the extractor')
    for path in experiment.root.rglob('*.jsonl'):
        list(experiment.read(str(path.relative_to(experiment.root))))
    if experiment.torn_tail:
        raise ValueError('complete ledger tails required')
    bounded.expenditure(accounting, rates)  # Reject unplanned reader attempts before contact.


def measure(origin, previous, baseline, experiment, old_plan, baseline_plan, plan, reference):
    queue, accounting, rates = accounting_queues(
        origin, previous, baseline, experiment, old_plan, baseline_plan, plan)
    base_queue = model_call.Queue(baseline, lane='review', batch=baseline_plan['review']['batch'])
    base_answers = answers(base_queue, baseline_plan['review']['model'])
    new_answers = answers(queue, plan['review']['model'])
    pairs = [{**{k: c[k] for k in ('claim_id', 'control', 'expected_axes')},
              'expected': c['expected_label'], 'baseline_axes': base_answers[c['claim_id']],
              'baseline_label': diagnostics.diagnostic_label(base_answers[c['claim_id']]),
              'comparison_axes': new_answers.get(c['claim_id']),
              'comparison_label': diagnostics.diagnostic_label(new_answers[c['claim_id']])
                  if c['claim_id'] in new_answers else None} for c in reference['cases']]
    pending = queue.pending(backend='ollama-cloud', model=plan['review']['model'])
    spent = bounded.expenditure(accounting, rates)
    return {**spent, 'cases': len(pairs),
        'unanswered': sum(p['comparison_axes'] is None for p in pairs),
        'baseline_model': baseline_plan['review']['model'], 'comparison_model': plan['review']['model'],
        'baseline_reference_agreement': sum(p['baseline_label'] == p['expected'] for p in pairs),
        'comparison_reference_agreement': sum(p['comparison_label'] == p['expected'] for p in pairs),
        'reader_label_agreement': sum(p['comparison_label'] == p['baseline_label'] for p in pairs),
        'axis_reference_agreement': {axis: {
            'scored': sum(p['expected_axes'][axis] is not None for p in pairs),
            'answered': sum(p['comparison_axes'] is not None and p['expected_axes'][axis] is not None for p in pairs),
            'baseline_agreed': sum(p['expected_axes'][axis] is not None and
                                  p['baseline_axes'][axis]['label'] == p['expected_axes'][axis] for p in pairs),
            'comparison_agreed': sum(p['comparison_axes'] is not None and p['expected_axes'][axis] is not None
                                    and p['comparison_axes'][axis]['label'] == p['expected_axes'][axis] for p in pairs)}
            for axis in diagnostics.AXES},
        'controls': {group: {
            'cases': len(selected := [p for p in pairs if p['control'] == group]),
            'baseline_agreement': sum(p['baseline_label'] == p['expected'] for p in selected),
            'comparison_agreement': sum(p['comparison_label'] == p['expected'] for p in selected)}
            for group in ('positive', 'challenge')},
        'pending_physical_calls': len(pending),
        'remaining_attempt_reservation_usd': sum(bounded.reservation(plan['review'], u) for u in pending),
        'paired_diagnostics': pairs, 'reference_is_held_out': False, 'automatic_adoption': False,
        'production_reviews_written': 0, 'extraction_calls': 0, 'summary_mapping_is_experimental': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    body = Path(args.plan).read_bytes(); plan = json.loads(body)
    if diagnostics.digest(plan['baseline_plan']) != plan['baseline_plan_sha256']:
        raise ValueError('baseline diagnostic plan changed')
    base_plan = json.loads(Path(plan['baseline_plan']).read_bytes())
    if diagnostics.digest(base_plan['comparison_plan']) != base_plan['comparison_plan_sha256']:
        raise ValueError('previous comparison plan changed')
    old_plan = json.loads(Path(base_plan['comparison_plan']).read_bytes())
    if diagnostics.digest(base_plan['reference']) != base_plan['reference_sha256']:
        raise ValueError('diagnostic reference changed')
    reference = json.loads(Path(base_plan['reference']).read_bytes())
    if diagnostics.digest(old_plan['reference']) != old_plan['reference_sha256']:
        raise ValueError('previous development reference changed')
    project = load_project(old_plan['project'])
    origin = Store(project.name, base=old_plan['origin_store'])
    previous = Store(project.name, base=old_plan['experiment_store'])
    baseline = Store(project.name, base=base_plan['experiment_store'])
    experiment = Store(project.name, base=plan['experiment_store'])
    check_registry_drift(project, origin, record=False)
    comparison.validate(project, origin, previous, old_plan, json.loads(Path(old_plan['reference']).read_bytes()))
    diagnostics.validate(project, origin, previous, baseline, old_plan, base_plan, reference)
    validate(origin, previous, baseline, experiment, old_plan, base_plan, plan, reference)
    report = {'plan_sha256': hashlib.sha256(body).hexdigest(), 'execute': args.execute,
              'budget_usd': plan['budget_usd'], 'status': 'PREVIEW'}
    code = 0
    if args.execute:
        bounded.load_environment(Path('.env'))
        if not all(os.environ.get(k) for k in ('OLLAMA_API_KEY', 'CLAIMSTONE_CONTACT_EMAIL')):
            raise ValueError('required environment values absent')
        prior = [files_snapshot(s) for s in (origin, previous, baseline)]
        before = files_snapshot(experiment)
        queue, accounting, rates = accounting_queues(origin, previous, baseline, experiment, old_plan, base_plan, plan)
        try:
            bounded.drain('review', {'review': queue}, rates, reader=plan['review'], accounting_queues=accounting)
            if set(answers(queue, plan['review']['model'])) != {c['claim_id'] for c in reference['cases']}:
                raise bounded.Stopped('comparison answers remain invalid or missing')
            report['status'] = 'REVIEWER_COMPARISON_COMPLETE'
        except bounded.Stopped as exc:
            report.update(status='STOPPED', reason=str(exc)); code = 1
        finally:
            if [files_snapshot(s) for s in (origin, previous, baseline)] != prior:
                raise RuntimeError('previous stores changed')
            allowed = {queue.results_name} | {str(p.relative_to(experiment.root))
                for p in experiment.path(queue.results_name).parent.joinpath('raw').glob('*.txt')}
            validate_history(experiment, before, allowed)
            if any(not name.endswith('.jsonl') and experiment.path(name).stat().st_size != old['bytes']
                   for name, old in before.items()):
                raise RuntimeError('original comparison file grew')
            report.update(previous_stores_unchanged=True, all_original_bytes_preserved=True)
    report.update(measure(origin, previous, baseline, experiment, old_plan, base_plan, plan, reference),
                  measured_at=dt.datetime.now(dt.timezone.utc).isoformat())
    if args.execute:
        data = json.dumps(report, indent=2, sort_keys=True)+'\n'
        path = experiment.path('audits/reviewer-comparison/'+hashlib.sha256(data.encode()).hexdigest()+'.json')
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(data)
        report['audit_path'] = str(path)
    print(json.dumps(report, indent=2)); return code


if __name__ == '__main__': raise SystemExit(main())
