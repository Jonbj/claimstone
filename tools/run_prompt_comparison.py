#!/usr/bin/env python
"""Compare experimental prompts in an isolated store under the ORIGINAL calibration budget.

Default is read-only. No production prompt, annotation, review or profile is modified.
The small, agent-authored development reference is diagnostic, not held-out accuracy.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import extract, model_call, review
from claimstone.config import load_project, check_registry_drift
from claimstone.store import Store
from tools import complete_question_round as bounded, run_calibration as calibration
from tools.replay_answers import files_snapshot

EXTRACT_APPENDIX = """
Before returning each record, check the EXACT question proposition, not merely its topic.
A description of study organization, a regression specification or an experimental split is not
an empirical result on a different proposition. A methodological record requires an explicit
endorsement of the stated requirement or a demonstrated failure relevant to that requirement;
a design feature alone does not endorse or contradict a methodological requirement.
Check each clause, condition, comparison and horizon in the question. Omit records that do not
bear on them. Where the schema permits QUALIFIES, use it for explicitly limited evidence rather
than pretending to establish the full proposition. Never invent a new stance value.
Check stance separately: SUPPORTS means evidence in the direction of the exact proposition;
CONTRADICTS means evidence against it. A null result outside the condition in the question is
not automatically a contradiction of an effect inside that condition. An absence of a design
feature is not by itself evidence against a requirement for that feature.
Keep named entities, conditions and uncertainty faithful: may is not does, an illustration is
not proof, and one entity's result is not another entity's result. Do not infer facts from missing
statements. Use the complete passage to interpret the quote, but every number in the claim must
still be inside the exact quote. Include enough consecutive quoted text to carry the assertion.
If these checks fail, omit that record. Returning [] is correct; making a plausible story is not.
"""

REVIEW_APPENDIX = """
Apply the following checks explicitly before selecting a verdict.
1. Applicability: does this annotation actually bear on the EXACT question, including its
conditions, comparisons and horizons? Topic overlap, section organization and a regression
specification do not themselves establish an empirical result. Return NOT_APPLICABLE for an
annotation that does not address the proposition, even if its sentence is literally true.
2. Fidelity: check EVERY asserted field and named entity against the quote IN THE WHOLE PASSAGE.
Context may identify a table column, sample, horizon, antecedent or design without being repeated
inside the short quote. Do not reject solely because such context is absent from the short quote
when it is explicitly present in the supplied passage. This does not permit outside knowledge,
invented results or unchecked numbers. Inclusive even/also is not exclusive only.
3. Direction: judge stance against the EXACT question, separately from sentence fidelity.
An observation outside a condition is not automatically a contradiction of a result inside it.
An absence of a feature does not refute a requirement for that feature. A wrong stance, invented
condition, entity substitution or strengthened certainty prevents SUPPORTED for the whole record.
Preserve may, suggests, consistent with and study-specific scope; they do not establish causality
or a universal claim. A hypothetical premise is not an observed finding.
Do not invent stronger claims to reject: criticize what the annotation actually asserts.
Give a concise reason identifying the applicable check and the specific evidence or mismatch.
Use the existing four verdicts and the existing JSON schema. These checks do not change the gate.
"""


class AccountingGroup:
    """Only accounting is combined. Actual drains write to their own original queues."""
    def __init__(self, queues): self.queues = queues
    def requests(self): return [u for q in self.queues for u in q.requests()]
    def attempts(self): return [r for q in self.queues for r in q.attempts()]


def clone(unit, system, target=None):
    new = model_call.work_unit(lane=unit['lane'], system=system, user=unit['user'],
        response_schema=unit['response_schema'], max_output_tokens=unit['max_output_tokens'],
        registry_version=unit['registry_version'], source_id=unit.get('source_id'), chunk_id=unit.get('chunk_id'))
    for key in ('kind', 'review_version', 'claim_id', 'question_id', 'extracted_by', 'annotation_sha256'):
        if key in unit: new[key] = unit[key]
    if target:
        for key in ('claim_id', 'question_id', 'extracted_by', 'annotation_sha256'):
            new[key] = target[key]
    new['comparison_from_call_id'] = unit['call_id']
    return new


def queues_and_accounting(origin, experiment, plan):
    held = {lane: model_call.Queue(experiment, lane=lane, batch=plan[lane]['batch']) for lane in model_call.LANES}
    diagnostic = model_call.Queue(experiment, lane='review', batch=plan['diagnostic_batch'])
    accounting = {lane: AccountingGroup([
        model_call.Queue(origin, lane=lane, batch=plan['baseline'][lane]['batch']), held[lane]
    ] + ([diagnostic] if lane == 'review' else [])) for lane in model_call.LANES}
    return held, diagnostic, accounting


def validate(project, origin, experiment, plan, reference):
    original_root, experimental_root = origin.root.resolve(), experiment.root.resolve()
    if original_root.is_relative_to(experimental_root) or experimental_root.is_relative_to(original_root):
        raise ValueError('experiment must be isolated without overlapping roots')
    baseline_body = Path(plan['baseline_plan']).read_bytes()
    if hashlib.sha256(baseline_body).hexdigest() != plan['baseline_plan_sha256']:
        raise ValueError('baseline plan changed')
    baseline = json.loads(baseline_body)
    if baseline != plan['baseline'] or plan['budget_usd'] != baseline['budget_usd']:
        raise ValueError('original shared budget/plan must be retained')
    for lane in model_call.LANES:
        if {k: v for k, v in plan[lane].items() if k != 'batch'} != {k: v for k, v in baseline[lane].items() if k != 'batch'}:
            raise ValueError('keep original reader identities, rates and reservation bounds')
    calibration.validate(baseline, project, origin)
    if reference['status'] != 'provisional_agent_development_reference':
        raise ValueError('reference status must be explicit')
    if not reference['cases'] or len({c['claim_id'] for c in reference['cases']}) != len(reference['cases']):
        raise ValueError('reference needs unique cases')
    for name, digest in plan['frozen_ledgers'].items():
        if name not in {'chunks.jsonl', 'documents.jsonl', 'registry.jsonl'}:
            raise ValueError('unexpected copied ledger')
        if any(hashlib.sha256(s.path(name).read_bytes()).hexdigest() != digest for s in [origin, experiment]):
            raise ValueError('source/copy ledger changed')
    held, diagnostic, accounting = queues_and_accounting(origin, experiment, plan)
    for name, digest in plan['frozen_requests'].items():
        if hashlib.sha256(experiment.path(name).read_bytes()).hexdigest() != digest:
            raise ValueError('prepared experimental request changed')
    original = {u['call_id']: u for u in model_call.Queue(origin, lane='extract', batch=baseline['extract']['batch']).requests()}
    expected = set()
    for unit in held['extract'].requests():
        source = original.get(unit.get('comparison_from_call_id'))
        if source is None: raise ValueError('experimental passage was not in original calibration')
        rebuilt = clone(source, source['system'] + '\n' + EXTRACT_APPENDIX)
        if any(unit[k] != rebuilt[k] for k in ('call_id', 'system', 'user', 'response_schema', 'max_output_tokens', 'kind')):
            raise ValueError('unexpected extraction variant')
        if unit.get('asked_by') != source.get('asked_by'):
            raise ValueError('calibration askers changed')
        expected.add(source['call_id'])
    if expected != set(original): raise ValueError('variant must read the same full document set')
    originals = {u['call_id']: u for u in model_call.Queue(origin, lane='review', batch=baseline['review']['batch']).requests()}
    cases = {c['claim_id']: c for c in reference['cases']}
    covered = set()
    for unit in diagnostic.requests():
        source = originals.get(unit.get('comparison_from_call_id'))
        if source is None: raise ValueError('missing original review task')
        rebuilt = clone(source, source['system'] + '\n' + REVIEW_APPENDIX)
        if any(unit[k] != rebuilt[k] for k in ('call_id', 'system', 'user', 'response_schema', 'max_output_tokens')):
            raise ValueError('unexpected review variant')
        for target in unit['review_targets']:
            case = cases.get(target['claim_id'])
            if case is None or target not in source['review_targets']:
                raise ValueError('unexpected diagnostic annotation')
            if case['expected'] not in ('SUPPORTED', 'OVERSTATED', 'NOT_APPLICABLE', 'AMBIGUOUS') or not case['rationale']:
                raise ValueError('reference label/rationale incomplete')
            covered.add(target['claim_id'])
    if covered != set(cases): raise ValueError('every reference case must be queued')


def build_variant_reviews(project, experiment, plan):
    staging = plan['review']['batch'] + '-build'
    review.build(project, experiment, batch=staging, reviewer=('ollama-cloud', plan['review']['model']))
    units = []
    eligible = calibration.selected_claims(experiment, plan['extract']['batch'])
    for unit in model_call.Queue(experiment, lane='review', batch=staging).requests():
        for target in unit.get('review_targets') or [unit]:
            new = clone(unit, unit['system'] + '\n' + REVIEW_APPENDIX, target)
            new.update(source_id=eligible[target['claim_id']]['source_id'],
                       chunk_id=eligible[target['claim_id']]['chunk_id'])
            units.append(new)
    queue = model_call.Queue(experiment, lane='review', batch=plan['review']['batch'])
    queue.write(units)
    expected = {u['call_id']: u for u in units}
    for unit in queue.requests():
        rebuilt = expected.get(unit['call_id'])
        if rebuilt is None or any(unit[k] != rebuilt[k] for k in
                ('system', 'user', 'response_schema', 'max_output_tokens', 'registry_version')):
            raise ValueError('unexpected experimental full-review request')
        allowed = [u for u in units if u['call_id'] == unit['call_id']]
        if any(not any(all(target.get(k) == u.get(k) for k in
                ('claim_id', 'question_id', 'extracted_by', 'annotation_sha256')) for u in allowed)
                for target in unit['review_targets']):
            raise ValueError('unexpected experimental full-review target')


def execute(project, origin, experiment, plan):
    held, diagnostic, accounting = queues_and_accounting(origin, experiment, plan)
    diagnostic_queues = {**held, 'review': diagnostic}
    bounded.drain('review', diagnostic_queues, plan, accounting_queues=accounting)
    try:
        bounded.drain('extract', held, plan, accounting_queues=accounting)
    finally:
        extract.harvest(project, experiment, batch=plan['extract']['batch'])
    valid = {r['call_id'] for r in held['extract'].results().values() if r.get('ok')}
    failed = {r['call_id'] for r in held['extract'].results(backend='ollama-cloud', model=plan['extract']['model']).values()
              if r.get('failure_class') in ('NOT_JSON', 'SCHEMA_INVALID') and r['call_id'] not in valid}
    if failed and (alternate := plan['extract'].get('fallback')):
        try: bounded.drain('extract', held, plan, reader=alternate, call_ids=failed, accounting_queues=accounting)
        finally: extract.harvest(project, experiment, batch=plan['extract']['batch'])
    valid = {r['call_id'] for r in held['extract'].results().values() if r.get('ok')}
    if len(valid) != len(held['extract'].requests()): raise bounded.Stopped('variant extraction incomplete')
    review.harvest(project, experiment, batch=plan['review']['batch'])
    build_variant_reviews(project, experiment, plan)
    try: bounded.drain('review', held, plan, accounting_queues=accounting)
    finally: review.harvest(project, experiment, batch=plan['review']['batch'])
    if any(cid not in review.current(experiment) for cid in calibration.selected_claims(experiment, plan['extract']['batch'])):
        raise bounded.Stopped('variant full-result review incomplete')


def measure(project, origin, experiment, plan, reference):
    held, diagnostic, accounting = queues_and_accounting(origin, experiment, plan)
    current = {t['claim_id']: r for u in diagnostic.requests() for t in u['review_targets']
               for r in diagnostic.results(backend='ollama-cloud', model=plan['review']['model']).values()
               if r['call_id'] == u['call_id'] and r.get('ok')}
    pairs = [{'claim_id': c['claim_id'], 'expected': c['expected'], 'baseline': c['baseline_verdict'],
              'variant': (current.get(c['claim_id'], {}).get('output') or {}).get('verdict'),
              'reason': (current.get(c['claim_id'], {}).get('output') or {}).get('reason'),
              'control': c['control']} for c in reference['cases']]
    return {**bounded.expenditure(accounting, plan), 'reference_status': reference['status'],
            'diagnostic_cases': len(pairs), 'baseline_reference_agreement': sum(p['baseline'] == p['expected'] for p in pairs),
            'variant_reference_agreement': sum(p['variant'] == p['expected'] for p in pairs),
            'diagnostic_unanswered': sum(p['variant'] is None for p in pairs), 'paired_diagnostics': pairs,
            'variant_sample': calibration.measure(project, experiment, plan)['calibration'],
            'production_prompts_changed': False, 'reference_is_held_out': False, 'automatic_adoption': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True); parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(); body = Path(args.plan).read_bytes(); plan = json.loads(body)
    ref_body = Path(plan['reference']).read_bytes()
    if hashlib.sha256(ref_body).hexdigest() != plan['reference_sha256']: raise ValueError('reference changed')
    reference = json.loads(ref_body); project = load_project(plan['project'])
    origin = Store(project.name, base=plan.get('origin_store', 'store'))
    experiment = Store(project.name, base=plan['experiment_store'])
    check_registry_drift(project, origin, record=False)
    validate(project, origin, experiment, plan, reference)
    for store in (origin, experiment):
        for path in store.root.rglob('*.jsonl'): list(store.read(str(path.relative_to(store.root))))
        if store.torn_tail: raise ValueError('complete ledger tails required')
    report = {'plan_sha256': hashlib.sha256(body).hexdigest(), 'execute': args.execute,
              'budget_usd': plan['budget_usd'], 'status': 'PREVIEW'}; code = 0
    if args.execute:
        bounded.load_environment(Path('.env'))
        import os
        if not all(os.environ.get(key) for key in ('OLLAMA_API_KEY', 'CLAIMSTONE_CONTACT_EMAIL')):
            raise ValueError('required environment values absent')
        before = files_snapshot(origin); scratch_before = files_snapshot(experiment)
        try:
            execute(project, origin, experiment, plan); report['status'] = 'COMPARISON_COMPLETE'
        except bounded.Stopped as exc:
            report.update(status='STOPPED', reason=str(exc)); code = 1
        finally:
            if files_snapshot(origin) != before: raise RuntimeError('production store changed')
            for name, prior in scratch_before.items():
                with experiment.path(name).open('rb') as stream: prefix = stream.read(prior['bytes'])
                if hashlib.sha256(prefix).hexdigest() != prior['sha256']: raise RuntimeError('experimental original bytes changed')
                if not name.endswith('.jsonl') and experiment.path(name).stat().st_size != prior['bytes']:
                    raise RuntimeError('experimental original file grew')
            report.update(production_store_unchanged=True, all_original_bytes_preserved=True)
    report.update(measure(project, origin, experiment, plan, reference), measured_at=dt.datetime.now(dt.timezone.utc).isoformat())
    if args.execute:
        data = json.dumps(report, sort_keys=True, indent=2) + '\n'
        path = experiment.path('audits/comparison/' + hashlib.sha256(data.encode()).hexdigest() + '.json')
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(data); report['audit_path'] = str(path)
    print(json.dumps(report, indent=2)); return code


if __name__ == '__main__': raise SystemExit(main())
