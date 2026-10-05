#!/usr/bin/env python
"""Run a hash-frozen calibration sample with a shared budget and independent full review.

Default is offline preview. --execute preserves raw responses and harvests partial successes;
it never builds a corpus profile, changes a registry or signs a verdict.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import admissibility, chunk_sets, claim_records, extract, model_call, review
from claimstone.config import check_registry_drift, load_project
from claimstone.store import Store
from tools import complete_question_round as bounded
from tools.replay_answers import files_snapshot


def validate(plan, project, store):
    if plan['registry_sha256'] != project.registry_sha256:
        raise ValueError('question registry changed')
    if not math.isfinite(plan['budget_usd']) or plan['budget_usd'] <= 0:
        raise ValueError('positive finite budget required')
    names = {'topics.yaml', 'questions.yaml', 'sources.yaml', 'manifest.tsv'}
    if set(plan['input_sha256']) != names:
        raise ValueError('all four project inputs must be frozen')
    for name, digest in plan['input_sha256'].items():
        if hashlib.sha256((project.root / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'project input changed: {name}')
    choices = bounded.readers(plan['extract'])
    if plan['review']['model'] in {r['model'] for r in choices}:
        raise ValueError('reviewer must differ from every extractor')
    if len({r['model'] for r in choices}) != len(choices):
        raise ValueError('fallback must differ from primary')
    for reader in choices + bounded.readers(plan['review']):
        if type(reader['context_tokens']) is not int or reader['context_tokens'] <= 0:
            raise ValueError('positive integer context bound required')
        for key in ('price_in', 'price_out', 'price_cached_in'):
            if key in reader and (not math.isfinite(reader[key]) or reader[key] < 0):
                raise ValueError('invalid reader price')
    if set(plan['question_ids']) != {q.id for q in project.questions if q.kind != 'operational'}:
        raise ValueError('review must cover the frozen registry')
    queue = model_call.Queue(store, lane='extract', batch=plan['extract']['batch'])
    if hashlib.sha256(store.path(queue.requests_name).read_bytes()).hexdigest() != plan['extract_requests_sha256']:
        raise ValueError('calibration requests changed')
    chunks = chunk_sets.current(store)
    expected = Counter()
    for selection in plan['selection']:
        expected.update((str(c['chunk_id']), selection['kind']) for c in chunks.values()
                        if c['source_id'] == selection['source_id'])
    actual = Counter()
    confirmed = extract._confirmed_sources(store)
    for unit in queue.requests():
        kind = unit['kind']
        questions = [q for q in project.questions if q.kind == kind]
        if (unit['registry_version'] != project.registry_version
                or unit['system'] != extract.system_prompt(kind, questions)
                or unit['response_schema'] != extract.response_schema(kind, questions)):
            raise ValueError('calibration is not the current reading task')
        rebuilt = model_call.work_unit(lane='extract', system=unit['system'], user=unit['user'],
            response_schema=unit['response_schema'], max_output_tokens=unit['max_output_tokens'],
            registry_version=unit['registry_version'])
        if any(unit[key] != rebuilt[key] for key in ('call_id', 'prompt_sha256', 'schema_sha256')):
            raise ValueError('calibration call identity changed')
        for asker in unit.get('asked_by') or [unit]:
            chunk = chunks.get(asker['chunk_id'])
            if (chunk is None or chunk['source_id'] != asker['source_id']
                    or chunk['source_id'] not in confirmed or chunk['text'] != unit['user']):
                raise ValueError('calibration passage changed or source is not confirmed')
            actual.update([(str(chunk['chunk_id']), kind)])
    if actual != expected or not actual:
        raise ValueError('calibration must read every current chunk of the declared documents/kinds')


def selected_claims(store, batch):
    return {cid: row for cid, row in claim_records.current(store)[0].items()
            if batch in (row.get('answer_batches') or [row.get('batch')])}


def build_reviews(project, store, plan):
    eligible = selected_claims(store, plan['extract']['batch'])
    batch = plan['review']['batch']
    # Stage 5 owns the request shape. The staging queue may contain other work, but only the
    # calibration's immutable annotation ids enter the queue that is actually paid for.
    staging = batch + '-build'
    review.build(project, store, batch=staging, reviewer=('ollama-cloud', plan['review']['model']))
    units = []
    for unit in model_call.Queue(store, lane='review', batch=staging).requests():
        targets = [t for t in unit.get('review_targets') or [unit] if t['claim_id'] in eligible]
        if not targets:
            continue
        for target in targets:
            scoped = dict(unit)
            for key in ('claim_id', 'question_id', 'extracted_by', 'annotation_sha256'):
                scoped[key] = target[key]
            claim = eligible[target['claim_id']]
            scoped.update(source_id=claim['source_id'], chunk_id=claim['chunk_id'])
            units.append(scoped)
    queue = model_call.Queue(store, lane='review', batch=batch)
    queue.write(units)
    for unit in queue.requests():
        if any(t['claim_id'] not in eligible for t in unit.get('review_targets') or [unit]):
            raise bounded.Stopped('review queue includes an annotation outside calibration')


def execute(project, store, plan):
    queues = {lane: model_call.Queue(store, lane=lane, batch=plan[lane]['batch'])
              for lane in model_call.LANES}
    extract.harvest(project, store, batch=plan['extract']['batch'])
    try:
        bounded.drain('extract', queues, plan)
    finally:
        extract.harvest(project, store, batch=plan['extract']['batch'])
    queue = queues['extract']
    valid = {r['call_id'] for r in queue.results().values() if r.get('ok')}
    failed = {r['call_id'] for r in queue.results(backend='ollama-cloud', model=plan['extract']['model']).values()
              if r.get('failure_class') in ('NOT_JSON', 'SCHEMA_INVALID') and r['call_id'] not in valid}
    if failed and (fallback := plan['extract'].get('fallback')):
        try:
            bounded.drain('extract', queues, plan, reader=fallback, call_ids=failed)
        finally:
            extract.harvest(project, store, batch=plan['extract']['batch'])
    valid = {r['call_id'] for r in queue.results().values() if r.get('ok')}
    if any(u['call_id'] not in valid for u in queue.requests()):
        raise bounded.Stopped('calibration extraction is incomplete')
    review.harvest(project, store, batch=plan['review']['batch'])
    build_reviews(project, store, plan)
    try:
        bounded.drain('review', queues, plan)
    finally:
        review.harvest(project, store, batch=plan['review']['batch'])
    eligible = selected_claims(store, plan['extract']['batch'])
    if any(cid not in review.current(store) for cid in eligible):
        raise bounded.Stopped('calibration review is incomplete')


def measure(project, store, plan):
    queues = {lane: model_call.Queue(store, lane=lane, batch=plan[lane]['batch'])
              for lane in model_call.LANES}
    eligible = selected_claims(store, plan['extract']['batch'])
    rejected = {cid: r for cid, r in claim_records.current(store)[1].items()
                if plan['extract']['batch'] in (r.get('answer_batches') or [r.get('batch')])}
    reviewed = {cid: r for cid, r in review.current(store).items() if cid in eligible}
    valid = {r['call_id'] for r in queues['extract'].results().values() if r.get('ok')}
    return {**bounded.expenditure(queues, plan), 'calibration': {
        'extraction_calls': len(queues['extract'].requests()), 'valid_readings': len(valid),
        'accepted_annotations': len(eligible), 'rejected_annotations': len(rejected),
        'rejection_reasons': dict(Counter(r['failure'] for r in rejected.values())),
        'reviewed_annotations': len(reviewed), 'review_verdicts': dict(Counter(r['verdict'] for r in reviewed.values())),
        'awaiting_review': len(eligible) - len(reviewed)},
        'admission': admissibility.admit(project, store, round_name=plan['round']),
        'profile_built': False, 'adjudication_written': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    body = Path(args.plan).read_bytes(); plan = json.loads(body)
    project = load_project(plan['project']); store = Store(project.name, base=plan.get('store', 'store'))
    check_registry_drift(project, store, record=False)
    validate(plan, project, store)
    for path in store.root.rglob('*.jsonl'):
        list(store.read(str(path.relative_to(store.root))))
    if store.torn_tail:
        raise ValueError('complete ledger tails required')
    report = {'plan_sha256': hashlib.sha256(body).hexdigest(), 'execute': args.execute,
              'budget_usd': plan['budget_usd'], 'status': 'PREVIEW'}
    code = 0
    if args.execute:
        bounded.load_environment(Path('.env'))
        if not all(os.environ.get(key) for key in ('OLLAMA_API_KEY', 'CLAIMSTONE_CONTACT_EMAIL')):
            raise ValueError('required environment values absent')
        before = files_snapshot(store)
        try:
            execute(project, store, plan)
            report['status'] = 'CALIBRATION_COMPLETE'
        except bounded.Stopped as exc:
            report.update(status='STOPPED', reason=str(exc)); code = 1
        finally:
            for name, prior in before.items():
                path = store.path(name)
                with path.open('rb') as stream:
                    prefix = stream.read(prior['bytes'])
                if hashlib.sha256(prefix).hexdigest() != prior['sha256']:
                    raise RuntimeError(f'original bytes changed: {name}')
                if not name.endswith('.jsonl') and path.stat().st_size != prior['bytes']:
                    raise RuntimeError(f'original artifact changed: {name}')
            report['all_original_bytes_preserved'] = True
    report.update(measure(project, store, plan), measured_at=dt.datetime.now(dt.timezone.utc).isoformat())
    if args.execute:
        data = json.dumps(report, sort_keys=True, indent=2) + '\n'
        path = store.path('audits/calibration/' + hashlib.sha256(data.encode()).hexdigest() + '.json')
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(data)
        report['audit_path'] = str(path)
    print(json.dumps(report, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
