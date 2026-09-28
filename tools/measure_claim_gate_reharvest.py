#!/usr/bin/env python
"""Measure a complete stored batch under gate v3 and v4 by actually harvesting temporary ledgers.

No fetch, model call or mutation of the real store. Both passes use the same current harvest and
supersession code; only the gate instrument differs. D47 changes that harvester's answer selection
and annotation identity: the D46 table describes its historical execution, not this new instrument.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import types
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from claimstone import claim_records, claimgate, extract, model_call
from claimstone.config import load_project
from claimstone.store import Store


def baseline(ref: str):
    source = subprocess.run(['git', 'show', f'{ref}:claimstone/claimgate.py'], cwd=ROOT,
                            check=True, capture_output=True, text=True).stdout
    module = types.ModuleType('claimstone._measured_gate_v3')
    sys.modules[module.__name__] = module
    exec(compile(source, f'{ref}:claimstone/claimgate.py', 'exec'), module.__dict__)
    if module.CLAIM_GATE_VERSION != 3:
        raise ValueError('the baseline revision must declare claim_gate_version 3')
    return module


def snapshot(store: Store) -> dict[str, str]:
    return {str(path.relative_to(store.root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in store.root.rglob('*.jsonl')}


def measure(project_path: str, batch: str, store_base: str, baseline_ref: str) -> dict:
    project = load_project(project_path)
    real = Store(project.name, base=store_base)
    if not real.path(f'calls/extract/{batch}/requests.jsonl').is_file():
        raise ValueError(f'no stored batch {batch!r} in {real.root}')
    before = snapshot(real)
    old_gate = baseline(baseline_ref)
    gate = extract.claimgate
    with tempfile.TemporaryDirectory(prefix='claimstone-gate-') as directory:
        scratch = Store(project.name, base=directory)
        for relative in before:
            target = scratch.path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(real.path(relative), target)
        try:
            extract.claimgate = old_gate
            old_harvest = extract.harvest(project, scratch, batch=batch)
            old_claims, old_rejections = claim_records.current(scratch)
            extract.claimgate = claimgate
            new_harvest = extract.harvest(project, scratch, batch=batch)
            new_claims, new_rejections = claim_records.current(scratch)
            repeat = extract.harvest(project, scratch, batch=batch)
        finally:
            extract.claimgate = gate
        retired = sorted(old_claims.keys() - new_claims.keys())
        recovered = sorted(new_claims.keys() - old_claims.keys())
        result = {'project': project.name, 'batch': batch, 'baseline_ref': baseline_ref,
                  'old_gate_version': 3, 'new_gate_version': claimgate.CLAIM_GATE_VERSION,
                  'annotation_version': claim_records.ANNOTATION_VERSION,
                  'result_judge_version': model_call.RESULT_JUDGE_VERSION,
                  'old_harvest': old_harvest, 'new_harvest': new_harvest, 'repeat_harvest': repeat,
                  'current_store_before': {'accepted': len(old_claims), 'rejected': len(old_rejections)},
                  'current_store_after': {'accepted': len(new_claims), 'rejected': len(new_rejections)},
                  'retired': len(retired), 'recovered': len(recovered),
                  'retired_by_reason': dict(Counter(new_rejections[key]['failure'] for key in retired)),
                  'retired_ids': retired, 'recovered_ids': recovered}
    if snapshot(real) != before:
        raise RuntimeError('the real ledgers changed during measurement; discard this comparison')
    if repeat['accepted'] or repeat['rejected']:
        raise RuntimeError('repeat harvest appended decisions; the replay is not idempotent')
    result['real_ledgers_unchanged'] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project')
    parser.add_argument('--batch', required=True)
    parser.add_argument('--store', default='store')
    parser.add_argument('--baseline-ref', default='9e402e5')
    args = parser.parse_args()
    print(json.dumps(measure(args.project, args.batch, args.store, args.baseline_ref),
                     indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
