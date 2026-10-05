#!/usr/bin/env python
"""Isolated three-axis reviewer experiment; preview is offline and spending remains cumulative.

Outputs are diagnostics, never production reviews or question verdicts. Reference cases are
post-selected agent assessments, not held-out scientific accuracy.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import claim_records, chunk_sets, model_call, review
from claimstone.config import load_project, check_registry_drift
from claimstone.store import Store
from tools import complete_question_round as bounded, run_prompt_comparison as comparison
from tools.replay_answers import files_snapshot

AXES = {'applicability': ('APPLICABLE', 'NOT_APPLICABLE', 'UNCLEAR'),
        'fidelity': ('FAITHFUL', 'UNFAITHFUL', 'UNCLEAR'),
        'direction': ('COHERENT', 'INCOHERENT', 'UNCLEAR')}
SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': list(AXES),
          'properties': {name: {'type': 'object', 'additionalProperties': False,
              'required': ['label', 'reason'], 'properties': {
                  'label': {'type': 'string', 'enum': list(values)},
                  'reason': {'type': 'string'}}} for name, values in AXES.items()}}
MAX_OUTPUT_TOKENS = 1200
SYSTEM = """Read the supplied question, complete annotation and entire passage. Return three
independent checks with a short, specific reason for each. Do not return a final verdict.

APPLICABILITY: Is the annotation evidence about the EXACT question proposition, including its
required condition, horizon and comparison? Use APPLICABLE, NOT_APPLICABLE or UNCLEAR.
Topic overlap alone is insufficient. For an empirical effect question, a hypothetical mechanism,
a description of section organization or a regression specification is not an observed result.
For a methodological requirement, an explicit author endorsement or demonstrated relevant failure
can be evidence; a design feature alone does not establish that requirement. A result about one
side of a comparison is applicable only if the supplied context actually establishes the required
comparison. Do not invent a magnitude, causal condition or timing requirement absent from the question.

FIDELITY: Independently of applicability, is EVERY asserted field faithful to the quote interpreted
in the WHOLE supplied passage? Use FAITHFUL, UNFAITHFUL or UNCLEAR. Check named entities, sample,
design, estimates, uncertainty, horizon, original/converted values and certainty. Missing optional
fields are not assertions. Context can explicitly establish metadata absent from the short quote;
do not require every field to be repeated inside that quote. Numbers must still be justified.
An inclusive even/also is not exclusive only. A source-specific reported finding is not automatically
a universal assertion: assess what the annotation actually says. A hypothesis accurately described
as conceivable can be FAITHFUL while NOT_APPLICABLE as evidence of an observed effect. Do not penalize
an annotation just because an additional result or qualification elsewhere was not also extracted,
unless its omission changes the assertion's meaning. Name the actual mismatching field, not an
imagined stronger claim. UNFAITHFUL requires a specific unsupported or conflicting assertion.

DIRECTION: Independently check the annotation's stance against the EXACT question.
Use COHERENT, INCOHERENT or UNCLEAR. SUPPORTS points toward that proposition; CONTRADICTS points
against it; QUALIFIES must state a relevant limitation. A null result outside a condition does not
contradict an effect inside it. Missing a design feature does not refute a requirement for it.
If applicability is NOT_APPLICABLE, use UNCLEAR for direction rather than inventing a relation.

The exact quote was checked mechanically. You supply semantic checks, not a vote about a question.
Use only the supplied text. Return the requested JSON object, no extra prose.
"""

FORMAT_APPENDIX = """
OUTPUT SHAPE IS MANDATORY. Your response MUST be one JSON object, never an array.
Use exactly these lowercase top-level keys and exactly label/reason inside each:
{
  "applicability": {"label": "<allowed applicability label>", "reason": "<specific reason>"},
  "fidelity": {"label": "<allowed fidelity label>", "reason": "<specific reason>"},
  "direction": {"label": "<allowed direction label>", "reason": "<specific reason>"}
}
Replace the angle-bracket placeholders with your actual checks using the allowed labels above.
Do not output keys named check or verdict. Do not wrap this object in a list or a Markdown fence.
First character {, last character }. Complete all three label/reason objects.
"""


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def diagnostic_label(output):
    """Experimental summary only: not harvested into the production review contract."""
    labels = {k: output[k]['label'] for k in AXES}
    if labels['applicability'] == 'NOT_APPLICABLE': return 'NOT_APPLICABLE'
    if labels['fidelity'] == 'UNFAITHFUL' or labels['direction'] == 'INCOHERENT': return 'OVERSTATED'
    if 'UNCLEAR' in labels.values(): return 'AMBIGUOUS'
    return 'SUPPORTED'


def make_unit(project, store, case, *, format_version=1):
    if format_version not in (1, 2): raise ValueError('unknown diagnostic format version')
    annotation = claim_records.current(store)[0].get(case['claim_id'])
    if annotation is None: raise ValueError('reference annotation no longer accepted')
    if hashlib.sha256(model_call.canonical(review.annotation(annotation)).encode()).hexdigest() != case['annotation_sha256']:
        raise ValueError('reference annotation changed')
    question = next(q for q in project.questions if q.id == annotation['question_id'])
    chunk = chunk_sets.current(store).get(annotation['chunk_id'])
    if chunk is None or chunk['source_id'] != annotation['source_id']:
        raise ValueError('reference passage missing')
    if hashlib.sha256(chunk['text'].encode()).hexdigest() != case['passage_sha256']:
        raise ValueError('reference passage changed')
    unit = model_call.work_unit(lane='review', system=SYSTEM + (FORMAT_APPENDIX if format_version == 2 else ''),
        user=review.review_unit(question, annotation, chunk['text']), response_schema=SCHEMA,
        max_output_tokens=MAX_OUTPUT_TOKENS, registry_version=project.registry_version,
        source_id=annotation['source_id'], chunk_id=annotation['chunk_id'])
    unit.update(claim_id=annotation['claim_id'], question_id=annotation['question_id'],
                annotation_sha256=case['annotation_sha256'], extracted_by={
                    k: annotation.get(k, '') for k in ('backend', 'model', 'harness_version')},
                diagnostic_task='three-axis-development-reference')
    return unit


def accounting_queues(origin, previous, experiment, old_plan, plan):
    held, diagnostic, accounting = comparison.queues_and_accounting(origin, previous, old_plan)
    queue = model_call.Queue(experiment, lane='review', batch=plan['review']['batch'])
    preceding = [model_call.Queue(Store(origin.root.name, base=entry['store']),
                 lane='review', batch=entry['batch']) for entry in plan.get('preceding_diagnostics', [])]
    accounting['review'] = comparison.AccountingGroup([accounting['review'], *preceding, queue])
    return queue, accounting


def validate(project, origin, previous, experiment, old_plan, plan, reference):
    roots = [s.root.resolve() for s in (origin, previous, experiment)]
    if any(a.is_relative_to(b) or b.is_relative_to(a) for i, a in enumerate(roots) for b in roots[i+1:]):
        raise ValueError('diagnostics need nonoverlapping stores')
    if plan['budget_usd'] != old_plan['budget_usd']:
        raise ValueError('retain the original budget')
    if plan['question_ids'] != old_plan['question_ids']:
        raise ValueError('retain the original registry scope')
    for lane in model_call.LANES:
        if {k: v for k, v in plan[lane].items() if k != 'batch'} != {k: v for k, v in old_plan[lane].items() if k != 'batch'}:
            raise ValueError('retain the measured readers, prices and bounds')
    if reference['status'] != 'provisional_agent_development_reference':
        raise ValueError('provisional reference status required')
    cases = reference['cases']
    if not cases or len({c['claim_id'] for c in cases}) != len(cases):
        raise ValueError('unique reference cases required')
    if not any(c['control'] == 'positive' for c in cases):
        raise ValueError('positive controls required')
    stores = {'baseline': origin, 'variant': previous}
    seen = set()
    for entry in plan.get('preceding_diagnostics', []):
        store = Store(origin.root.name, base=entry['store'])
        if store.root.resolve() != experiment.root.resolve() or entry['batch'] == plan['review']['batch']:
            raise ValueError('prior diagnostic queue must be distinct in the same isolated store')
        if entry['batch'] in seen: raise ValueError('duplicate prior accounting queue')
        seen.add(entry['batch'])
        prior_queue = model_call.Queue(store, lane='review', batch=entry['batch'])
        for name, key in ((prior_queue.requests_name, 'requests_sha256'),
                          (prior_queue.results_name, 'results_sha256')):
            if digest(store.path(name)) != entry[key]: raise ValueError('prior diagnostic history changed')
    if plan.get('format_version', 1) == 2 and not seen:
        raise ValueError('format repair must retain prior diagnostic accounting')
    for key, files in plan['frozen_history'].items():
        if key not in stores: raise ValueError('unknown history store')
        for name, sha in files.items():
            if digest(stores[key].path(name)) != sha: raise ValueError('prior history changed')
    queue, accounting = accounting_queues(origin, previous, experiment, old_plan, plan)
    if digest(experiment.path(queue.requests_name)) != plan['requests_sha256']:
        raise ValueError('diagnostic requests changed')
    expected = {}
    for case in cases:
        if case['annotation_store'] not in stores or case['control'] not in ('positive', 'challenge'):
            raise ValueError('invalid reference source/control')
        if case['expected_label'] not in review.VERDICTS or not case['rationale']:
            raise ValueError('expected label and rationale required')
        if set(case['expected_axes']) != set(AXES) or any(v is not None and v not in AXES[k]
                for k, v in case['expected_axes'].items()):
            raise ValueError('invalid expected axes')
        unit = make_unit(project, stores[case['annotation_store']], case,
                         format_version=plan.get('format_version', 1))
        expected.setdefault(unit['call_id'], []).append(unit)
    if {u['call_id'] for u in queue.requests()} != set(expected):
        raise ValueError('unexpected or missing diagnostic calls')
    for unit in queue.requests():
        rebuilt = expected[unit['call_id']][0]
        if any(unit[k] != rebuilt[k] for k in ('system', 'user', 'response_schema',
                'max_output_tokens', 'registry_version', 'prompt_sha256', 'schema_sha256')):
            raise ValueError('unexpected diagnostic task')
        targets = {model_call.canonical(model_call.review_target(u)) for u in expected[unit['call_id']]}
        if {model_call.canonical(t) for t in unit['review_targets']} != targets:
            raise ValueError('diagnostic annotation targets changed')
    for store in (origin, previous, experiment):
        for path in store.root.rglob('*.jsonl'): list(store.read(str(path.relative_to(store.root))))
        if store.torn_tail: raise ValueError('complete ledger tails required')


def measure(origin, previous, experiment, old_plan, plan, reference):
    queue, accounting = accounting_queues(origin, previous, experiment, old_plan, plan)
    answers = {t['claim_id']: r['output'] for u in queue.requests() for t in u['review_targets']
               for r in queue.results(backend='ollama-cloud', model=plan['review']['model']).values()
               if r['call_id'] == u['call_id'] and r.get('ok')}
    pairs = [{'claim_id': c['claim_id'], 'control': c['control'], 'expected': c['expected_label'],
              'previous_label': c['previous_label'], 'axes': answers.get(c['claim_id']),
              'diagnostic_label': diagnostic_label(answers[c['claim_id']]) if c['claim_id'] in answers else None,
              'expected_axes': c['expected_axes']} for c in reference['cases']]
    return {**bounded.expenditure(accounting, plan), 'cases': len(pairs),
        'unanswered': sum(p['axes'] is None for p in pairs),
        'axis_reference_agreement': {axis: {
            'scored': sum(p['expected_axes'][axis] is not None for p in pairs),
            'answered': sum(p['axes'] is not None and p['expected_axes'][axis] is not None for p in pairs),
            'agreed': sum(p['axes'] is not None and p['expected_axes'][axis] is not None
                          and p['axes'][axis]['label'] == p['expected_axes'][axis] for p in pairs)} for axis in AXES},
        'controls': {group: {'cases': len(selected := [p for p in pairs if p['control'] == group]),
            'previous_agreement': sum(p['previous_label'] == p['expected'] for p in selected),
            'diagnostic_agreement': sum(p['diagnostic_label'] == p['expected'] for p in selected)}
            for group in ('positive', 'challenge')},
        'paired_diagnostics': pairs, 'reference_is_held_out': False, 'automatic_adoption': False,
        'production_reviews_written': 0, 'extraction_calls': 0,
        'summary_mapping_is_experimental': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True); parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(); body = Path(args.plan).read_bytes(); plan = json.loads(body)
    if digest(plan['comparison_plan']) != plan['comparison_plan_sha256']:
        raise ValueError('previous comparison plan changed')
    old_plan = json.loads(Path(plan['comparison_plan']).read_bytes())
    if digest(plan['reference']) != plan['reference_sha256']:
        raise ValueError('development reference changed')
    reference = json.loads(Path(plan['reference']).read_bytes())
    project = load_project(old_plan['project'])
    origin = Store(project.name, base=old_plan['origin_store'])
    previous = Store(project.name, base=old_plan['experiment_store'])
    experiment = Store(project.name, base=plan['experiment_store'])
    check_registry_drift(project, origin, record=False)
    old_reference_body = Path(old_plan['reference']).read_bytes()
    if hashlib.sha256(old_reference_body).hexdigest() != old_plan['reference_sha256']:
        raise ValueError('previous development reference changed')
    comparison.validate(project, origin, previous, old_plan, json.loads(old_reference_body))
    validate(project, origin, previous, experiment, old_plan, plan, reference)
    report = {'plan_sha256': hashlib.sha256(body).hexdigest(), 'execute': args.execute,
              'budget_usd': plan['budget_usd'], 'status': 'PREVIEW'}; code = 0
    if args.execute:
        bounded.load_environment(Path('.env'))
        if not all(os.environ.get(k) for k in ('OLLAMA_API_KEY', 'CLAIMSTONE_CONTACT_EMAIL')):
            raise ValueError('required environment values absent')
        prior = files_snapshot(origin), files_snapshot(previous)
        before = files_snapshot(experiment)
        queue, accounting = accounting_queues(origin, previous, experiment, old_plan, plan)
        try:
            bounded.drain('review', {'review': queue}, plan, accounting_queues=accounting)
            valid = {r['call_id'] for r in queue.results(backend='ollama-cloud',
                     model=plan['review']['model']).values() if r.get('ok')}
            if valid != {u['call_id'] for u in queue.requests()}:
                raise bounded.Stopped('diagnostic answers remain invalid or missing')
            report['status'] = 'DIAGNOSTICS_COMPLETE'
        except bounded.Stopped as exc:
            report.update(status='STOPPED', reason=str(exc)); code = 1
        finally:
            if (files_snapshot(origin), files_snapshot(previous)) != prior:
                raise RuntimeError('previous stores changed')
            for name, old in before.items():
                with experiment.path(name).open('rb') as stream: prefix = stream.read(old['bytes'])
                if hashlib.sha256(prefix).hexdigest() != old['sha256']:
                    raise RuntimeError('original diagnostic bytes changed')
                if not name.endswith('.jsonl') and experiment.path(name).stat().st_size != old['bytes']:
                    raise RuntimeError('original diagnostic file grew')
            report.update(previous_stores_unchanged=True, all_original_bytes_preserved=True)
    report.update(measure(origin, previous, experiment, old_plan, plan, reference),
                  measured_at=dt.datetime.now(dt.timezone.utc).isoformat())
    if args.execute:
        data = json.dumps(report, indent=2, sort_keys=True)+'\n'
        path = experiment.path('audits/diagnostics/'+hashlib.sha256(data.encode()).hexdigest()+'.json')
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(data); report['audit_path'] = str(path)
    print(json.dumps(report, indent=2)); return code


if __name__ == '__main__': raise SystemExit(main())
