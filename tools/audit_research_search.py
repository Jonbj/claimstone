#!/usr/bin/env python
"""Audit a frozen search protocol offline; unknown literature recall stays unknown.

--write creates a content-addressed audit, never a candidate, reading or verdict.
--previous compares inventories, including changed document generations.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import admissibility, discover_report, population, profile_inputs
from claimstone.config import check_registry_drift, load_project
from claimstone.store import Store


def digest(data):
    return hashlib.sha256(data).hexdigest()


def query_status(planned, recorded):
    """A smaller result cap is not completion of the declared search depth."""
    held = {(r['topic_id'], r['query'], r['source_api']): r for r in recorded}
    result = []
    for item in planned:
        row = held.get((item['topic_id'], item['query'], item['source_api']))
        state = ('NOT_RUN' if row is None else
                 'FAILED' if not row.get('ok') else
                 'SHALLOWER_THAN_PLANNED' if row.get('per_query', 0) < item['per_query'] else
                 'COMPLETED')
        result.append({**item, 'status': state,
                       'failure_class': row.get('failure_class') if row else None,
                       'result_cap_reached': (row.get('returned', 0) >= item['per_query'])
                           if row and row.get('ok') else None})
    return result


def inventory_delta(current, previous):
    """Identity is the recorded key; possible duplicate papers still need inspection."""
    old = {r['candidate_key']: r for r in previous}
    new = {r['candidate_key']: r for r in current}
    return {
        'new_candidate_keys': sorted(new.keys() - old.keys()),
        'absent_candidate_keys': sorted(old.keys() - new.keys()),
        'changed_document_keys': sorted(k for k in old.keys() & new.keys()
            if (old[k].get('document_sha256'), old[k].get('generation_sha256')) !=
               (new[k].get('document_sha256'), new[k].get('generation_sha256'))),
        'basis': 'recorded candidate identities, not independently deduplicated studies',
    }


def build(project, store, plan, previous=None):
    check_registry_drift(project, store, record=False)
    question = next(q for q in project.questions if q.id == plan['question_id'])
    if project.registry_sha256 != plan['registry_sha256']:
        raise ValueError('question registry changed')
    if set(plan['input_sha256']) != {'topics.yaml', 'questions.yaml', 'sources.yaml', 'manifest.tsv'}:
        raise ValueError('freeze all four project inputs')
    for name, sha in plan['input_sha256'].items():
        if digest((project.root / name).read_bytes()) != sha:
            raise ValueError(f'project input changed: {name}')
    population.check_round(store, project.population, plan['search_round'], record=False)
    expected = [{'topic_id': t.id, 'query': term, 'source_api': api, 'per_query': plan['per_query']}
                for t in project.topics if t.id in plan['topic_ids']
                for term in t.terms for api in plan['apis']]
    if expected != plan['queries'] or not expected:
        raise ValueError('search matrix differs from the frozen topics/protocol')
    rows = [r for r in store.latest_by('queries.jsonl', 'query_id').values()
            if r.get('round') == plan['search_round']]
    queries = query_status(expected, rows)
    candidates = store.latest_by('candidates.jsonl', 'candidate_key')
    documents = store.latest_by('documents.jsonl', 'source_id')
    inventory = []
    for key, candidate in sorted(candidates.items()):
        sid = str(candidate.get('source_id') or key)
        document = documents.get(sid, {})
        inventory.append({k: candidate.get(k) for k in
            ('candidate_key', 'title', 'doi', 'url', 'source_class', 'round', 'possible_duplicate_of')} |
            {'source_id': sid, 'document_sha256': document.get('sha256'),
             'generation_sha256': document.get('generation_sha256'),
             'confirmed': bool(document.get('fulltext_confirmed')),
             'chunks': document.get('chunks'), 'l02_relevance': None})
    inputs = profile_inputs.collect(project, store, round_name=None, manifest_only=False)
    annotations = [r for r in inputs['claims'] if r['question_id'] == question.id]
    reviews = [inputs['reviews'][r['claim_id']] for r in annotations
               if r['claim_id'] in inputs['reviews']]
    references = list(store.latest_by('references.jsonl', 'key').values())
    report = {
        'audit_format_version': 1, 'project': project.name, 'question_id': question.id,
        'question': question.text, 'registry_sha256': project.registry_sha256,
        'input_sha256': plan['input_sha256'], 'population_sha256': population.digest(project.population),
        'plan_sha256': digest(json.dumps(plan, sort_keys=True).encode()),
        'measured_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'search_round': plan['search_round'], 'reading_scope': 'whole current project corpus',
        'query_status_counts': dict(Counter(q['status'] for q in queries)), 'queries': queries,
        'queries_at_result_cap': sum(q['result_cap_reached'] is True for q in queries),
        'discovery': discover_report.summarise(store, round_name=plan['search_round']),
        'admission': admissibility.admit(project, store),
        'inventory': inventory, 'references_to_screen': references,
        'reading_completion': inputs['completion'][question.kind],
        'question_annotations': len(annotations), 'question_reviewed_annotations': len(reviews),
        'question_review_labels': dict(Counter(r['verdict'] for r in reviews)),
        'literature_recall': None, 'screening_precision': None,
        'screening_status': 'not measured by this audit; requires recorded relevance decisions',
        'limitation': 'Completing this protocol does not certify completeness of the literature. '
                      'Search caps, indexing gaps, population exclusions and citation bias remain. '
                      'Channel overlap is diagnostic, not a capture-recapture percentage.',
        'model_calls': 0, 'production_ledger_rows_written': 0,
    }
    if previous is not None:
        if (previous['project'], previous['registry_sha256'], previous['question_id']) != (
                project.name, project.registry_sha256, question.id):
            raise ValueError('previous audit concerns another project, registry or question')
        report['delta'] = inventory_delta(inventory, previous['inventory'])
        report['delta']['same_population_policy'] = (
            previous.get('population_sha256') == report['population_sha256'])
    if store.torn_tail:
        raise ValueError('complete ledger tails required')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--previous')
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text())
    project = load_project(plan['project'])
    store = Store(project.name, base=plan.get('store', 'store'))
    previous = json.loads(Path(args.previous).read_text()) if args.previous else None
    report = build(project, store, plan, previous)
    if args.write:
        data = (json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2) + '\n').encode()
        path = store.path(f'audits/research-search/{digest(data)}.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != data:
            raise ValueError('content-addressed audit conflict')
        if not path.exists():
            path.write_bytes(data)
        report['audit_path'] = str(path)
    print(json.dumps({k: v for k, v in report.items() if k not in
        ('queries', 'inventory', 'references_to_screen')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
