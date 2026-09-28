#!/usr/bin/env python
"""Replay every stored model answer and harvest in a temporary store, without requests.

The original JSONL files are hashed before and after. Raw answer paths are read in place and their
recorded hashes are checked by rejudge. Both rejudge and harvest must append nothing on repetition.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from claimstone import chunk, claim_records, extract, model_call, review, synthesize
from claimstone.config import load_project
from claimstone.store import Store
from measure_claim_gate_reharvest import snapshot


def measure(project_path: str, store_base: str) -> dict:
    project = load_project(project_path)
    real = Store(project.name, base=store_base)
    before = snapshot(real)
    with tempfile.TemporaryDirectory(prefix='claimstone-answer-') as directory:
        scratch = Store(project.name, base=directory)
        for relative in before:
            target = scratch.path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(real.path(relative), target)
        batches = {lane: [p.parent.name for p in sorted(scratch.path(f'calls/{lane}').glob('*/requests.jsonl'))]
                   for lane in model_call.LANES}
        original_claims = scratch.latest_by('claims.jsonl', 'claim_id')
        original_reviews = scratch.latest_by('reviews.jsonl', 'claim_id')
        active_before = claim_records.current(scratch)
        judged = Counter()
        missing_raw = 0
        for lane, names in batches.items():
            for batch in names:
                queue = model_call.Queue(scratch, lane=lane, batch=batch)
                missing_raw += sum(not row.get('raw_path') or not pathlib.Path(row['raw_path']).is_file()
                                   for row in queue.results().values())
                for row in model_call.rejudge(queue):
                    judged[row.get('failure_class') or 'OK'] += 1
        harvests = {lane: [] for lane in model_call.LANES}
        for batch in batches['extract']:
            harvests['extract'].append(extract.harvest(project, scratch, batch=batch))
        for batch in batches['review']:
            harvests['review'].append(review.harvest(project, scratch, batch=batch))
        active_after = claim_records.current(scratch)
        valid_reviews = review.current(scratch)
        repeat = Counter()
        for lane, names in batches.items():
            for batch in names:
                repeat['rejudged'] += len(list(model_call.rejudge(model_call.Queue(scratch, lane=lane, batch=batch))))
                counts = (extract if lane == 'extract' else review).harvest(project, scratch, batch=batch)
                repeat['accepted'] += counts.get('accepted', 0)
                repeat['rejected'] += counts.get('rejected', 0)
                repeat['reviewed'] += counts.get('reviewed', 0)
        retained = original_claims.keys() & active_after[0].keys()
        result = {
            'project': project.name, 'batches': {lane: len(names) for lane, names in batches.items()},
            'instruments': {'result_judge_version': model_call.RESULT_JUDGE_VERSION,
                            'annotation_version': claim_records.ANNOTATION_VERSION,
                            'chunk_version': chunk.CHUNK_VERSION, 'review_version': review.REVIEW_VERSION,
                            'profile_version': synthesize.PROFILE_VERSION},
            'original_claim_ids': len(original_claims), 'original_reviews': len(original_reviews),
            'historical_review_ids_retained': len(original_reviews.keys() & scratch.latest_by('reviews.jsonl', 'claim_id').keys()),
            'active_before': {'accepted': len(active_before[0]), 'rejected': len(active_before[1])},
            'active_after': {'accepted': len(active_after[0]), 'rejected': len(active_after[1])},
            'retained_original_claim_ids': len(retained),
            'new_claim_ids': len(active_after[0].keys() - original_claims.keys()),
            'valid_reviews_after': len(valid_reviews),
            'retained_original_reviews': len(original_reviews.keys() & valid_reviews.keys()),
            'rejudged_by_outcome': dict(judged), 'missing_raw_answers': missing_raw,
            'harvest_totals': {lane: {key: sum(row.get(key, 0) for row in rows)
                                     for key in ('proposed', 'accepted', 'rejected', 'reviewed', 'calls_without_an_answer')}
                               for lane, rows in harvests.items()},
            'repeat_appends': dict(repeat),
        }
        if any(repeat.values()):
            raise RuntimeError(f'repeated replay appended rows: {dict(repeat)}')
    if snapshot(real) != before:
        raise RuntimeError('real ledgers changed during measurement; discard this comparison')
    result['real_ledgers_unchanged'] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project')
    parser.add_argument('--store', default='store')
    args = parser.parse_args()
    print(json.dumps(measure(args.project, args.store), indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
