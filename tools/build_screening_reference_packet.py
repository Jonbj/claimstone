#!/usr/bin/env python
"""Build an unlabeled, provenance-bearing human screening packet from frozen metadata.

No model recommendation or development label enters the packet. Missing abstracts remain
pending rather than being inferred from titles. This writes only a private audit artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import fetch_screening_abstracts as metadata


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(metadata_plan, scope_path):
    plan, project, store, selected = metadata.load(metadata_plan)
    scope = json.loads(Path(scope_path).read_bytes())
    if (not scope.get('question_id') or not scope.get('question_text') or
            not scope.get('criteria') or
            scope.get('registry_sha256') != project.registry_sha256 or
            type(scope.get('selection_protocol_version')) is not int):
        raise ValueError('scope and metadata project do not match')
    lookup = {}
    for row in store.read(metadata.LEDGER):
        if row.get('candidate_key') in plan['keys']:
            lookup.setdefault(row['candidate_key'], []).append(row)
    cases = []
    for item in selected:
        candidate = item['candidate']; key = candidate['candidate_key']
        rows = lookup.get(key, [])
        available = next((r for r in reversed(rows) if r.get('status') == 'ABSTRACT_AVAILABLE'), None)
        status = 'ABSTRACT_AVAILABLE' if available else (rows[-1]['status'] if rows else 'NOT_LOOKED_UP')
        cases.append({'candidate_key': key, 'title': candidate['title'],
                      'doi': candidate.get('doi'), 'source_class': candidate.get('source_class'),
                      'screening_level': 'abstract' if available else 'metadata_only',
                      'source_text': available['abstract'] if available else None,
                      'metadata_status': status,
                      'source_raw_sha256': available.get('raw_sha256') if available else None,
                      'source_provider': available.get('provider') if available else None,
                      'human_decision': None, 'human_reason': None,
                      'identity_checked_by_human': None})
    return {'metadata_plan_sha256': digest(metadata_plan), 'scope_sha256': digest(scope_path),
            'registry_sha256': project.registry_sha256,
            'question_id': scope['question_id'], 'question_text': scope['question_text'],
            'criteria': scope['criteria'], 'reference_status': 'unlabeled_human_review_packet',
            'cases': cases, 'available_abstracts': sum(c['source_text'] is not None for c in cases),
            'missing_abstracts': sum(c['source_text'] is None for c in cases),
            'model_calls': 0, 'automatic_adoption': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata-plan', required=True)
    parser.add_argument('--scope', required=True)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    packet = build(args.metadata_plan, args.scope)
    if args.write:
        root = Path(args.metadata_plan).parent / 'human-reference-packets'
        root.mkdir(parents=True, exist_ok=True)
        body = (json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
        path = root / (hashlib.sha256(body).hexdigest() + '.json')
        if not path.exists():
            path.write_bytes(body)
        packet['audit_path'] = str(path)
    print(json.dumps({k: v for k, v in packet.items() if k != 'cases'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
