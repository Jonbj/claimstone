#!/usr/bin/env python
"""Resume a prepared question round with metered readers and a cumulative USD ceiling.

Default: inspect only. --execute drains prepared extraction, harvests, builds independent
full-result reviews, drains/harvests them and rebuilds profiles. Never adjudicates.
The JSON plan holds reader names, dated rates and context ceilings; none lives in the engine.
An optional extract fallback reads only primary JSON/schema failures, within the same ceiling.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from claimstone import extract, model_call, profile_inputs, review, synthesize
from claimstone.config import check_registry_drift, load_project
from claimstone.runners.ollama_cloud import OllamaCloudRunner
from claimstone.store import Store


class Stopped(RuntimeError):
    pass


class SelectedQueue:
    """Restrict a drain to named calls; all writes still belong to the original queue."""
    def __init__(self, queue, call_ids):
        self.queue, self.call_ids = queue, call_ids

    def __getattr__(self, name):
        return getattr(self.queue, name)

    def pending(self, **kwargs):
        return [unit for unit in self.queue.pending(**kwargs) if unit['call_id'] in self.call_ids]


def readers(config):
    return [config] + ([config['fallback']] if config.get('fallback') else [])


def load_environment(path):
    """Read only API credentials/contact. Do not execute .env or assign its Docker UID."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.removeprefix('export ').partition('=')
        key = key.strip()
        if sep and key in ('OLLAMA_API_KEY', 'OPENALEX_API_KEY', 'CLAIMSTONE_CONTACT_EMAIL') and not os.environ.get(key):
            parts = shlex.split(value, comments=True)
            if len(parts) != 1:
                raise ValueError(f'invalid .env value for {key}')
            os.environ[key] = parts[0]


def reservation(reader, unit):
    # Full context at fresh-input rates, plus the output cap: deliberately conservative.
    return (reader['context_tokens'] * max(reader['price_in'], reader.get('price_cached_in', 0))
            + unit['max_output_tokens'] * reader['price_out']) / 1e6


def expenditure(queues, plan):
    """Every physical attempt counts, including failed and unpriced ones; replay does not."""
    measured = reserved = 0.0
    for lane, queue in queues.items():
        choices = readers(plan[lane])
        units = {u['call_id']: u for u in queue.requests()}
        for row in queue.attempts():
            if 'rejudged_from' in row:
                continue
            reader = next((choice for choice in choices if model_call.result_key(row)
                           == f"{row['call_id']}|ollama-cloud|{choice['model']}"), None)
            if reader is None:
                raise Stopped('an unplanned reader answered this batch')
            usage = row.get('usage') or {}
            if row.get('cost_usd') is None or not all(k in usage for k in ('input_tokens', 'output_tokens')):
                reserved += reservation(reader, units[row['call_id']])
            else:
                cost = float(row['cost_usd'])
                if not math.isfinite(cost) or cost < 0:
                    raise Stopped('invalid recorded cost')
                measured += cost
    return {'priced_usd_at_plan_rates': measured, 'unknown_attempt_reservation_usd': reserved,
            'budget_accounted_usd': measured + reserved}


def validate_plan(plan, project, store):
    if plan['registry_sha256'] != project.registry_sha256:
        raise ValueError('plan registry no longer matches the project')
    if not math.isfinite(plan['budget_usd']) or plan['budget_usd'] <= 0:
        raise ValueError('budget must be finite and positive')
    if plan['review']['model'] in {r['model'] for r in readers(plan['extract'])}:
        raise ValueError('extractor and reviewer must differ')
    for lane in model_call.LANES:
        choices = readers(plan[lane])
        if len({r['model'] for r in choices}) != len(choices):
            raise ValueError('fallback must be a different reader')
        for reader in choices:
            for key in ('price_in', 'price_out', 'price_cached_in'):
                if key in reader and (not math.isfinite(reader[key]) or reader[key] < 0):
                    raise ValueError(f'invalid {lane} rate: {key}')
            if not isinstance(reader['context_tokens'], int) or reader['context_tokens'] <= 0:
                raise ValueError('context ceiling must be a positive integer')
    queue = model_call.Queue(store, lane='extract', batch=plan['extract']['batch'])
    path = store.path(queue.requests_name)
    if hashlib.sha256(path.read_bytes()).hexdigest() != plan['extract_requests_sha256']:
        raise ValueError('prepared extraction requests changed')
    question = next(q for q in project.questions if q.id == plan['question_id'])
    questions = [q for q in project.questions if q.kind == question.kind]
    inputs = profile_inputs.collect(project, store, round_name=None, manifest_only=False)
    for unit in queue.requests():
        if (unit.get('registry_version') != project.registry_version
                or unit.get('kind') != question.kind
                or unit['system'] != extract.system_prompt(question.kind, questions)
                or unit['response_schema'] != extract.response_schema(question.kind, questions)):
            raise ValueError('prepared extraction is not the current reading task')
        for asker in unit.get('asked_by') or [unit]:
            chunk = inputs['chunks'].get(str(asker.get('chunk_id')))
            if chunk is None or unit['user'] != chunk['text']:
                raise ValueError('prepared extraction passage is no longer current')
    return question


def drain(lane, queues, plan, *, reader=None, call_ids=None, accounting_queues=None):
    import requests
    primary = reader is None
    reader = plan[lane] if primary else reader
    session = requests.Session()
    session.headers['User-Agent'] = f"Claimstone/question-round (contact: {os.environ['CLAIMSTONE_CONTACT_EMAIL']})"
    runner = OllamaCloudRunner(model=reader['model'], price_in=reader['price_in'],
        price_out=reader['price_out'], price_cached_in=reader.get('price_cached_in'),
        think=reader.get('think'), enforce_schema=True, max_concurrency=1,
        timeout_s=90, post=session.post)
    queue = queues[lane] if call_ids is None else SelectedQueue(queues[lane], call_ids)
    try:
        while pending := queue.pending(backend=runner.name, model=runner.model):
            unit = pending[0]
            if lane == 'review':
                for target in unit.get('review_targets') or [unit]:
                    if target.get('question_id') not in plan.get('question_ids', [plan.get('question_id')]):
                        raise Stopped('review batch includes another question')
                    if review.reader_of(target.get('extracted_by') or {}) == (runner.name, runner.model):
                        raise Stopped('reviewer is also the extractor')
            spent = expenditure(accounting_queues or queues, plan)['budget_accounted_usd']
            if spent + reservation(reader, unit) > plan['budget_usd']:
                raise Stopped('USD ceiling: insufficient room to reserve the next whole call')
            row = next(model_call.drain(queue, runner, limit=1))
            print(json.dumps({'lane': lane, **{k: row.get(k) for k in
                ('call_id', 'model', 'ok', 'failure_class', 'usage', 'cost_usd', 'latency_s')}}), flush=True)
            usage = row.get('usage') or {}
            if (usage.get('input_tokens', 0) > reader['context_tokens']
                    or usage.get('output_tokens', 0) > unit['max_output_tokens']):
                raise Stopped('reported usage exceeded the declared reservation bound')
            if not row.get('ok'):
                if (lane == 'extract' and primary and reader.get('fallback')
                        and row.get('failure_class') in ('NOT_JSON', 'SCHEMA_INVALID')
                        and all(k in usage for k in ('input_tokens', 'output_tokens'))):
                    continue  # terminal for this reader; the bounded alternate reader comes next
                raise Stopped(f"{lane}: {row.get('failure_class')}; stopped after this attempt")
            if not all(k in usage for k in ('input_tokens', 'output_tokens')):
                raise Stopped('missing usage: retained full reservation, stopping')
    finally:
        session.close()


def execute(project, store, plan, question):
    queues = {lane: model_call.Queue(store, lane=lane, batch=plan[lane]['batch'])
              for lane in model_call.LANES}
    extract.harvest(project, store, batch=plan['extract']['batch'])
    inputs = profile_inputs.collect(project, store, round_name=None, manifest_only=False)
    if inputs['completion'][question.kind]['unanswered']:
        try:
            drain('extract', queues, plan)
        finally:
            extract.harvest(project, store, batch=plan['extract']['batch'])
        if fallback := plan['extract'].get('fallback'):
            queue = queues['extract']
            valid = {row['call_id'] for row in queue.results().values() if row.get('ok')}
            failed = {row['call_id'] for row in queue.results(
                backend='ollama-cloud', model=plan['extract']['model']).values()
                if row.get('failure_class') in ('NOT_JSON', 'SCHEMA_INVALID') and row['call_id'] not in valid}
            try:
                drain('extract', queues, plan, reader=fallback, call_ids=failed)
            finally:
                extract.harvest(project, store, batch=plan['extract']['batch'])
    inputs = profile_inputs.collect(project, store, round_name=None, manifest_only=False)
    if any(inputs['completion'][question.kind][k] for k in
           ('unanswered', 'unharvested', 'unregated', 'unchunked_sources')):
        raise Stopped('extraction remains incomplete; no complete profile can be built')
    review.harvest(project, store, batch=plan['review']['batch'])
    review.build(project, store, batch=plan['review']['batch'], question_id=question.id,
                 reviewer=('ollama-cloud', plan['review']['model']))
    try:
        drain('review', queues, plan)
    finally:
        review.harvest(project, store, batch=plan['review']['batch'])
    profiles, _ = synthesize.preview(project, store)
    selected = next(row for row in profiles if row['question_id'] == question.id)
    if selected['provisional']:
        raise Stopped(f"profile remains provisional: {selected['blocking']}")
    synthesize.build(project, store)
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    body = Path(args.plan).read_bytes()
    plan = json.loads(body)
    project = load_project(plan['project'])
    store = Store(project.name, base=plan.get('store', 'store'))
    check_registry_drift(project, store, record=False)
    question = validate_plan(plan, project, store)
    for path in store.root.rglob('*.jsonl'):
        list(store.read(str(path.relative_to(store.root))))
    if store.torn_tail:
        raise ValueError(f'complete ledger tails required: {store.torn_tail}')
    queues = {lane: model_call.Queue(store, lane=lane, batch=plan[lane]['batch'])
              for lane in model_call.LANES}
    profiles, _ = synthesize.preview(project, store)
    selected = next(row for row in profiles if row['question_id'] == question.id)
    report = {'plan_sha256': hashlib.sha256(body).hexdigest(), 'execute': args.execute,
              'question_id': question.id, 'budget_usd': plan['budget_usd'], 'status': 'PREVIEW'}
    code = 0
    if args.execute:
        load_environment(Path('.env'))
        if not all(os.environ.get(k) for k in ('OLLAMA_API_KEY', 'CLAIMSTONE_CONTACT_EMAIL')):
            raise ValueError('OLLAMA_API_KEY and CLAIMSTONE_CONTACT_EMAIL are required')
        from tools.replay_answers import files_snapshot
        before = files_snapshot(store)
        try:
            selected = execute(project, store, plan, question)
            report['status'] = 'READY_FOR_HUMAN_READING'
        except Stopped as exc:
            report.update(status='STOPPED', reason=str(exc))
            code = 1
        finally:
            for name, prior in before.items():
                data = store.path(name).read_bytes()
                if hashlib.sha256(data[:prior['bytes']]).hexdigest() != prior['sha256']:
                    raise RuntimeError(f'original bytes changed: {name}')
                if not name.endswith('.jsonl') and len(data) != prior['bytes']:
                    raise RuntimeError(f'original artifact changed: {name}')
            report['all_original_bytes_preserved'] = True
        profiles, _ = synthesize.preview(project, store)
        selected = next(row for row in profiles if row['question_id'] == question.id)
    report.update(expenditure(queues, plan))
    report.update(profile=selected, measured_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'))
    if args.execute:
        data = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
        path = store.path(f"audits/question-round/{hashlib.sha256(data).hexdigest()}.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        report['audit_path'] = str(path)
    print(json.dumps({k: v for k, v in report.items() if k != 'profile'}, indent=2))
    print(json.dumps({'profile_sha256': selected['profile_sha256'],
                      'provisional': selected['provisional'], 'blocking': selected['blocking']}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
