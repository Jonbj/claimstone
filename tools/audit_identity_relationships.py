#!/usr/bin/env python
"""List bibliographic relationships needing review in a frozen selection inventory.

This offline audit never merges identities or changes production ledgers. A matching title
is a lead for inspection, not evidence that two records describe the same study.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

if __package__:
    from .audit_source_selection import audit, digest
else:
    from audit_source_selection import audit, digest


def normalized_title(value: str) -> str:
    value = unicodedata.normalize('NFKC', value).casefold()
    return ' '.join(re.findall(r'\w+', value))


def relationship_audit(plan_path: str | Path, acquisitions_path: str | Path | None = None,
                       relationships_path: str | Path | None = None) -> dict:
    plan_path = Path(plan_path)
    selection = audit(plan_path)  # verifies frozen inventory and assessments first
    plan = selection['protocol']
    inventory_path = plan_path.parent / plan['inventory_path']
    inventory = json.loads(inventory_path.read_text())
    by_title: dict[str, list[dict]] = defaultdict(list)
    by_key = {row['candidate_key']: row for row in inventory}
    for row in inventory:
        title = normalized_title(row.get('title') or '')
        if title:
            by_title[title].append(row)

    groups = []
    for title, rows in sorted(by_title.items()):
        if len(rows) > 1:
            groups.append({
                'normalized_title': title,
                'candidate_keys': sorted(row['candidate_key'] for row in rows),
                'status': 'REVIEW_REQUIRED',
                'possible_relations': ['same_work_different_version', 'same_copy',
                                       'distinct_works_same_title'],
            })

    supplements = []
    for row in inventory:
        title = row.get('title') or ''
        match = re.fullmatch(r'\s*(?:online\s+)?(?:appendix|supplement(?:ary|al)?)\s+'
                             r'(?:for|to)\s+["“]?(.+?)["”]?\s*', title, re.I)
        if not match:
            continue
        base = normalized_title(match.group(1))
        supplements.append({
            'candidate_key': row['candidate_key'],
            'possible_parent_keys': sorted(x['candidate_key'] for x in by_title.get(base, [])),
            'status': 'REVIEW_REQUIRED',
            'reason': 'title names a possible parent; contents and authorship require checking',
        })

    acquisitions = []
    if acquisitions_path is not None:
        acquisitions_path = Path(acquisitions_path)
        for line in acquisitions_path.read_text().splitlines():
            if line.strip():
                acquisitions.append(json.loads(line))
    affected = []
    by_bytes: dict[str, set[str]] = defaultdict(set)
    for row in acquisitions:
        if row.get('acquired') and row.get('sha256') and row.get('candidate_key'):
            by_bytes[row['sha256']].add(row['candidate_key'])
    for correction in selection['identity_corrections']:
        key = correction['original_candidate_key']
        for row in acquisitions:
            if row.get('candidate_key') == key:
                affected.append({
                    'original_candidate_key': key,
                    'canonical_candidate_key': correction['candidate_key'],
                    'acquisition_sha256': row.get('sha256'),
                    'stored_path': row.get('stored_path'),
                    'acquisition_round': row.get('round'),
                    'status': 'ORIGINAL_KEY_RETAINED',
                })

    reviewed = []
    if relationships_path is not None:
        relationships_path = Path(relationships_path)
        seen = set()
        for row in json.loads(relationships_path.read_text()):
            keys = row.get('candidate_keys')
            if not isinstance(keys, list) or len(keys) != 2 or len(set(keys)) != 2 \
                    or any(key not in by_key for key in keys):
                raise ValueError('relationship needs two distinct inventory keys')
            pair = tuple(sorted(keys))
            if pair in seen:
                raise ValueError('duplicate relationship pair')
            seen.add(pair)
            relation = row.get('relation')
            status = row.get('status')
            if relation not in {'SAME_WORK', 'POSSIBLE_VERSION', 'POSSIBLE_SUPPLEMENT',
                                'DISTINCT_WORKS'} or status not in {'VERIFIED', 'PENDING'}:
                raise ValueError('invalid relationship or status')
            if (relation.startswith('POSSIBLE_') and status != 'PENDING') or \
                    (relation in {'SAME_WORK', 'DISTINCT_WORKS'} and status != 'VERIFIED'):
                raise ValueError('relationship certainty is inconsistent')
            evidence = row.get('evidence')
            if not row.get('reason') or not isinstance(evidence, list) or not evidence \
                    or any(not isinstance(e, dict) or not e.get('locator') or not e.get('observation')
                           for e in evidence):
                raise ValueError('relationship needs reason and located evidence')
            if status == 'VERIFIED' and len(evidence) < 2:
                raise ValueError('verified relationship needs independent observations')
            reviewed.append(row)

    return {
        'audit_version': 1,
        'plan_sha256': digest(plan_path),
        'inventory_sha256': digest(inventory_path),
        'decisions_sha256': selection['decisions_sha256'],
        'acquisitions_sha256': digest(acquisitions_path) if acquisitions_path else None,
        'relationships_sha256': digest(relationships_path) if relationships_path else None,
        'inventory_count': len(by_key),
        'assessed_corrections': selection['identity_corrections'],
        'affected_acquisitions': affected,
        'same_bytes_groups': [
            {'sha256': sha, 'candidate_keys': sorted(keys), 'status': 'SAME_COPY_BYTES'}
            for sha, keys in sorted(by_bytes.items()) if len(keys) > 1
        ],
        'same_title_groups': groups,
        'possible_supplements': supplements,
        'reviewed_relationships': reviewed,
        'automatic_merges': 0,
        'production_ledger_rows_written': 0,
        'network_requests': 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--acquisitions', help='existing acquisition ledger to flag affected bytes')
    parser.add_argument('--relationships', help='evidence-backed manual relationship assessments')
    parser.add_argument('--write', action='store_true', help='write immutable content-addressed audit')
    args = parser.parse_args()
    result = relationship_audit(args.plan, args.acquisitions, args.relationships)
    if args.write:
        data = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
        root = Path(args.plan).parent / 'identity-audits'
        root.mkdir(parents=True, exist_ok=True)
        path = root / (hashlib.sha256(data).hexdigest() + '.json')
        if not path.exists():
            path.write_bytes(data)
        result['audit_path'] = str(path)
    print(json.dumps({
        'inventory_count': result['inventory_count'],
        'assessed_corrections': len(result['assessed_corrections']),
        'affected_acquisitions': len(result['affected_acquisitions']),
        'same_bytes_groups': len(result['same_bytes_groups']),
        'same_title_groups': len(result['same_title_groups']),
        'possible_supplements': len(result['possible_supplements']),
        'reviewed_relationships': len(result['reviewed_relationships']),
        'audit_path': result.get('audit_path'),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
