#!/usr/bin/env python
"""Audit a frozen, manually screened source inventory before admitting a new round.

No classifier, network, production ledger writes, or acquisition-floor recalculation.
Unknown eligibility/identity remains pending. Input paths are relative to the plan.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(plan_path):
    plan_path = Path(plan_path)
    plan = json.loads(plan_path.read_text())
    if type(plan.get('version')) is not int or plan['version'] < 1:
        raise ValueError('selection protocol needs a positive version')
    dt.date.fromisoformat(plan['declared_at'])
    for name in ('question_id', 'question_text', 'registry_sha256', 'round', 'rationale'):
        if not isinstance(plan.get(name), str) or not plan[name].strip():
            raise ValueError(f'missing protocol field: {name}')
    criteria = plan.get('criteria')
    dimensions = {'population', 'topic', 'exposure', 'outcome', 'unit', 'horizon',
                  'design', 'identity', 'duplicate'}
    if not isinstance(criteria, dict) or not criteria or any(
            not isinstance(k, str) or not isinstance(v, dict)
            or v.get('dimension') not in dimensions
            or not isinstance(v.get('description'), str) or not v['description'].strip()
            for k, v in criteria.items()):
        raise ValueError('protocol needs named, project-supplied criteria')
    for item in plan['frozen_inputs']:
        path = plan_path.parent / item['path']
        if digest(path) != item['sha256']:
            raise ValueError(f'frozen input changed: {item["path"]}')
    inventory_path = plan_path.parent / plan['inventory_path']
    decisions_path = plan_path.parent / plan['decisions_path']
    if not any((plan_path.parent / r['path']).resolve() == inventory_path.resolve()
               for r in plan['frozen_inputs']):
        raise ValueError('inventory must be frozen')
    inventory = json.loads(inventory_path.read_text())
    decisions = json.loads(decisions_path.read_text())
    by_key = {}
    for row in inventory:
        key = row['candidate_key']
        if key in by_key:
            raise ValueError('duplicate inventory identity')
        by_key[key] = row
    assessed = {}
    corrections = []
    for row in decisions:
        key = row['candidate_key']
        if key not in by_key or key in assessed:
            raise ValueError('unknown or repeated assessment identity')
        label = row['decision']
        if label not in {'INCLUDE', 'EXCLUDE', 'UNCERTAIN'}:
            raise ValueError('invalid screening decision')
        identity = row['identity_status']
        if identity not in {'VERIFIED', 'CORRECTED', 'CONFLICT', 'UNVERIFIED'}:
            raise ValueError('invalid identity status')
        if not row.get('checked_by') or not row.get('reason'):
            raise ValueError('assessment needs author and reason')
        used = row.get('criterion_ids')
        if not isinstance(used, list) or not used or any(k not in criteria for k in used):
            raise ValueError('assessment must cite declared criteria')
        evidence = row.get('evidence')
        if not isinstance(evidence, list) or not evidence or any(
                not e.get('locator') or not e.get('observation') for e in evidence):
            raise ValueError('assessment needs evidence with provenance')
        if identity == 'CORRECTED':
            correction = row.get('corrected_identity', {})
            if not all(correction.get(k) for k in ('candidate_key', 'title', 'authority')):
                raise ValueError('identity correction needs canonical identity and authority')
            corrections.append({'original_candidate_key': key, **correction})
        assessed[key] = row
    included, excluded, pending = [], [], []
    for key in by_key:
        row = assessed.get(key)
        if row is None or row['identity_status'] in {'CONFLICT', 'UNVERIFIED'} or row['decision'] == 'UNCERTAIN':
            pending.append(key)
        elif row['decision'] == 'EXCLUDE':
            excluded.append(key)
        else:
            included.append(key)
    # No availability fields are read, and pending sources cannot yield a closed cohort.
    ready = bool(included) and not pending
    eligible = []
    for key in included:
        row = dict(by_key[key])
        correction = assessed[key].get('corrected_identity')
        if assessed[key]['identity_status'] == 'CORRECTED':
            row.update({k: v for k, v in correction.items() if k != 'authority'})
            if row['candidate_key'].startswith('doi:'):
                row['doi'] = row['candidate_key'][4:]
        eligible.append(row)
    if len({r['candidate_key'] for r in eligible}) != len(eligible):
        raise ValueError('corrected identities collide; explicit duplicate assessment required')
    return {
        'plan_sha256': digest(plan_path), 'inventory_sha256': digest(inventory_path),
        'decisions_sha256': digest(decisions_path), 'round': plan['round'],
        'question_id': plan['question_id'], 'registry_sha256': plan['registry_sha256'],
        'status': 'READY_FOR_COHORT_PREPARATION' if ready else 'AWAITING_SCREENING',
        'inventory_count': len(by_key), 'assessed_count': len(assessed),
        'included_keys': included, 'excluded_keys': excluded, 'pending_keys': pending,
        'identity_corrections': corrections,
        'eligible_inventory': eligible, 'protocol': plan, 'assessments': decisions,
        'cohort_closed': ready, 'acquisition_rate': None, 'literature_recall': None,
        'screening_precision': None, 'automatic_classification': False,
        'production_ledger_rows_written': 0, 'network_requests': 0, 'model_calls': 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--write', action='store_true', help='write an immutable preparation audit')
    args = parser.parse_args()
    result = audit(args.plan)
    if args.write:
        data = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
        root = Path(args.plan).parent / 'results'
        root.mkdir(parents=True, exist_ok=True)
        path = root / (hashlib.sha256(data).hexdigest() + '.json')
        if not path.exists():
            path.write_bytes(data)
        result['audit_path'] = str(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
