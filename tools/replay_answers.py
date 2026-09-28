#!/usr/bin/env python
"""Apply stored-answer replay offline, or measure residual readings/review work without requests.

--apply appends authoritative rejudgements and harvests to the existing store, verifies every
old file's prefix, and repeats the whole replay to check idempotence. No runner is constructed.
Review queues are built only in a temporary copy; their cost remains unknown until a reader is chosen.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from claimstone import admissibility, chunk, claim_records, claimgate, extract, model_call, profile_inputs, review, synthesize
from claimstone.config import check_registry_drift, load_project
from claimstone.store import Store


def files_snapshot(store):
    return {str(path.relative_to(store.root)): {
        'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in sorted(store.root.rglob('*')) if path.is_file()}


def validate_history(store, before, allowed):
    after = files_snapshot(store)
    changes = {}
    for name, prior in before.items():
        if name not in after:
            raise RuntimeError(f'original file disappeared: {name}')
        with store.path(name).open('rb') as stream:
            digest = hashlib.sha256(stream.read(prior['bytes'])).hexdigest()
        if digest != prior['sha256']:
            raise RuntimeError(f'original bytes changed: {name}')
        if after[name] != prior:
            if name not in allowed or after[name]['bytes'] < prior['bytes']:
                raise RuntimeError(f'unexpected file change: {name}')
            changes[name] = {'before': prior, 'after': after[name],
                             'appended_bytes': after[name]['bytes'] - prior['bytes']}
    for name in after.keys() - before.keys():
        if name not in allowed:
            raise RuntimeError(f'unexpected new file: {name}')
        changes[name] = {'before': None, 'after': after[name], 'appended_bytes': after[name]['bytes']}
    return changes


def replay_pass(project, store, batches):
    judged, missing = Counter(), 0
    for lane, names in batches.items():
        for batch in names:
            queue = model_call.Queue(store, lane=lane, batch=batch)
            missing += sum(not row.get('raw_path') or not Path(row['raw_path']).is_file()
                           for row in queue.results().values())
            for row in model_call.rejudge(queue):
                judged[row.get('failure_class') or 'OK'] += 1
    harvests = {lane: [] for lane in model_call.LANES}
    for lane, names in batches.items():
        for batch in names:
            result = (extract if lane == 'extract' else review).harvest(project, store, batch=batch)
            harvests[lane].append({'batch': batch, **result})
    return {'rejudged': sum(judged.values()), 'by_outcome': dict(judged),
            'missing_raw_answers': missing, 'harvests': harvests}


def appends(result):
    counts = Counter({'rejudged': result['rejudged']})
    for rows in result['harvests'].values():
        for row in rows:
            for key in ('accepted', 'rejected', 'reviewed'):
                counts[key] += row.get(key, 0)
    return dict(counts)


def apply(project, store):
    check_registry_drift(project, store, record=False)
    for path in sorted(store.root.rglob('*.jsonl')):
        for _ in store.read(str(path.relative_to(store.root))):
            pass
    if store.torn_tail:
        raise RuntimeError(f'replay requires complete ledger tails: {store.torn_tail}')
    before = files_snapshot(store)
    batches = {lane: [p.parent.name for p in sorted(store.path(f'calls/{lane}').glob('*/requests.jsonl'))]
               for lane in model_call.LANES}
    allowed = {'registry.jsonl', 'claims.jsonl', 'rejections.jsonl', 'reviews.jsonl'}
    allowed.update(f'calls/{lane}/{name}/results.jsonl'
                   for lane, names in batches.items() for name in names)
    old_claims = set(store.latest_by('claims.jsonl', 'claim_id'))
    old_reviews = set(store.latest_by('reviews.jsonl', 'claim_id'))
    check_registry_drift(project, store)
    first = replay_pass(project, store, batches)
    repeated_before = files_snapshot(store)
    repeat = replay_pass(project, store, batches)
    if any(appends(repeat).values()) or files_snapshot(store) != repeated_before:
        raise RuntimeError(f'repeated replay appended rows: {appends(repeat)}')
    changes = validate_history(store, before, allowed)
    claims, rejections = claim_records.current(store)
    return {'batches': {lane: len(names) for lane, names in batches.items()},
            'first_pass': first, 'repeat_appends': appends(repeat),
            'accepted': len(claims), 'rejected': len(rejections),
            'retained_original_claim_ids': len(old_claims & claims.keys()),
            'new_claim_ids': len(claims.keys() - old_claims),
            'historical_review_ids_retained': len(old_reviews & store.latest_by('reviews.jsonl', 'claim_id').keys()),
            'usable_reviews': len(review.current(store)),
            'all_original_bytes_preserved': True, 'changed_files': changes}


def residual(project, store, *, round_name=None, manifest_only=False):
    check_registry_drift(project, store, record=False)
    admission = admissibility.admit(project, store, round_name=round_name, manifest_only=manifest_only)
    inputs = profile_inputs.collect(project, store, round_name=round_name, manifest_only=manifest_only)
    pending = {str(row['claim_id']): row for row in inputs['claims']
               if str(row['claim_id']) not in inputs['reviews']}
    batch = 'offline-review-v2-planning'
    with tempfile.TemporaryDirectory(prefix='claimstone-review-plan-') as directory:
        scratch = Store(project.name, base=directory)
        for path in store.root.rglob('*.jsonl'):
            target = scratch.path(str(path.relative_to(store.root)))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        # A fresh planning batch avoids including unrelated requests from a historical batch.
        while scratch.path(f'calls/review/{batch}/requests.jsonl').exists():
            batch += '-new'
        built = review.build(project, scratch, batch=batch)
        units = model_call.Queue(scratch, lane='review', batch=batch).requests()
        by_question, queued, prompt_chars, output_cap = {}, set(), 0, 0
        selected_calls = 0
        for unit in units:
            targets = [t for t in unit.get('review_targets', []) if str(t['claim_id']) in pending]
            if not targets:
                continue
            selected_calls += 1
            prompt_chars += len(unit['system']) + len(unit['user'])
            output_cap += unit['max_output_tokens']
            for question in {str(target['question_id']) for target in targets}:
                bucket = by_question.setdefault(question, {'annotations': 0, 'calls': 0, 'prompt_chars': 0, 'max_output_tokens_total': 0})
                bucket['calls'] += 1
                bucket['prompt_chars'] += len(unit['system']) + len(unit['user'])
                bucket['max_output_tokens_total'] += unit['max_output_tokens']
                bucket['annotations'] += sum(str(target['question_id']) == question for target in targets)
            queued.update(str(t['claim_id']) for t in targets)
        if set(pending) - queued:
            raise RuntimeError(f'{len(set(pending) - queued)} eligible annotations could not be queued')
    return {'round': round_name, 'manifest_only': manifest_only,
            'admission': {key: admission[key] for key in ('status', 'rate', 'floor', 'final', 'found',
                                                        'obtained', 'confirmed', 'blocking')},
            'completion_by_kind': inputs['completion'],
            'unanswered_readings': sum(row['unanswered'] for row in inputs['completion'].values()),
            'accepted_in_scope': len(inputs['claims']), 'rejected_in_scope': len(inputs['rejections']),
            'usable_reviews_in_scope': len(inputs['reviews']),
            'review_annotations': len(pending), 'review_calls': selected_calls,
            'review_calls_by_question': dict(sorted(by_question.items())),
            'extractors_of_pending_annotations': dict(Counter('/'.join(review.reader_of(row)) for row in pending.values())),
            'prompt_chars': prompt_chars, 'max_output_tokens_total': output_cap,
            'unscoped_builder_calls': built['units'], 'skipped_missing_chunk': built['missing_chunk'],
            'skipped_unknown_question': built['unknown_question'],
            'reviewer_chosen': False, 'price_estimate': None,
            'queue_built_in_temporary_copy': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project')
    parser.add_argument('--store', default='store')
    parser.add_argument('--apply', action='store_true', help='append offline replay to the real ledgers')
    parser.add_argument('--round', default=None)
    parser.add_argument('--manifest-only', action='store_true')
    args = parser.parse_args()
    project = load_project(args.project)
    store = Store(project.name, base=args.store)
    if not store.root.is_dir():
        raise ValueError(f'no existing store: {store.root}')
    report = {'project': project.name, 'recorded_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'instruments': {'result_judge_version': model_call.RESULT_JUDGE_VERSION,
                              'annotation_version': claim_records.ANNOTATION_VERSION,
                              'claim_gate_version': claimgate.CLAIM_GATE_VERSION,
                              'review_version': review.REVIEW_VERSION,
                              'chunk_version': chunk.CHUNK_VERSION, 'profile_version': synthesize.PROFILE_VERSION,
                              'admission_version': admissibility.ADMISSION_VERSION}}
    if args.apply:
        report['applied'] = apply(project, store)
    before_plan = files_snapshot(store)
    report['residual'] = residual(project, store, round_name=args.round, manifest_only=args.manifest_only)
    if files_snapshot(store) != before_plan:
        raise RuntimeError('queue measurement changed the real store')
    if args.apply:
        _, path = store.store_bytes_at('audits/offline-replay', json.dumps(report, indent=2, sort_keys=True).encode(), '.json')
        report['audit_path'] = str(path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
