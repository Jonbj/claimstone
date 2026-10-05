#!/usr/bin/env python
"""Bounded, recorded Europe PMC JATS pilot; never edits production stage ledgers.

Default is an offline preview. Execute only after the operator approves the fixed sweep.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import acquire, fulltext, jats, net, resolve
from claimstone.config import load_project, resolve_gate_policy
from claimstone.request_log import RecordingFetcher
from claimstone.store import Store
from tools.complete_question_round import load_environment


def prepare(plan_path: Path):
    plan = json.loads(plan_path.read_text())
    project = load_project(plan['project'])
    manifest_path = project.root / 'manifest.tsv'
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != plan['manifest_sha256']:
        raise ValueError('pilot manifest changed')
    if hashlib.sha256((project.root / 'sources.yaml').read_bytes()).hexdigest() != plan['sources_sha256']:
        raise ValueError('pilot source policy changed')
    rows = list(csv.DictReader(manifest_path.open(), delimiter='\t'))
    selected = rows[:plan['max_articles']]
    if not selected or len(selected) != plan['max_articles'] or \
            [r['source_id'] for r in selected] != plan['source_ids']:
        raise ValueError('pilot selection differs from frozen manifest prefix')
    targets = []
    for row in selected:
        url = resolve.europe_pmc_route(row['url'])
        if not url:
            raise ValueError(f'no PMC article identity for {row["source_id"]}')
        targets.append({**row, 'xml_url': url})
    if not plan.get('campaign') or plan['campaign'] == 'routine':
        raise ValueError('pilot requires a named campaign')
    return plan, project, targets


def run(plan_path: Path, *, execute: bool = False, fetcher=None, store_base='store') -> dict:
    plan, project, targets = prepare(plan_path)
    store = Store(project.name, base=store_base)
    ledger = 'audits/europe-pmc/jats-pilot-v1/outcomes.jsonl'
    prior = store.latest_by(ledger, 'source_id')
    pending = [r for r in targets if r['source_id'] not in prior]
    summary = {'campaign': plan['campaign'], 'selected': len(targets),
               'attempted': len(prior), 'pending': len(pending),
               'targets': [{'source_id': r['source_id'], 'url': r['xml_url']} for r in pending]}
    if not execute or not pending:
        return summary
    if any(r.get('http_status') in (403, 429) or r.get('failure_class') in
           {'ROBOTS_DISALLOWED', 'DOMAIN_BUDGET_EXHAUSTED'} for r in prior.values()):
        raise ValueError('prior host refusal stops this campaign; do not reset its failure budget')
    fetcher = fetcher or net.Fetcher(excluded_hosts=frozenset(project.excluded_hosts))
    for row in pending:
        recorded = RecordingFetcher(fetcher, store, purpose='jats_pilot',
                                    campaign=plan['campaign'], candidate_key=row['source_id'],
                                    source_class=row['class'])
        outcome = recorded.get(row['xml_url'], expect=acquire.JATS_TYPES)
        verdict = None
        parsed = None
        parse_status = 'NO_XML'
        if outcome.ok and outcome.body:
            policy = resolve_gate_policy(project.gate_policy, project.classes, row['class'])
            verdict = fulltext.classify(outcome.body, outcome.content_type, outcome.url,
                                        project.gate_thresholds, policy)
            if verdict.accepted:
                try:
                    doc = jats.parse(outcome.body)
                    parsed = {'title': doc.title, 'body_chars': doc.body_chars,
                              'references': len(doc.references), 'tables': len(doc.tables)}
                    parse_status = 'PARSED'
                except jats.UnsupportedJats:
                    parse_status = 'JATS_UNSUPPORTED'
                except jats.JatsError:
                    parse_status = 'JATS_UNREADABLE'
            else:
                parse_status = 'GATE_REJECTED'
        result = {
            'source_id': row['source_id'], 'source_class': row['class'],
            'campaign': plan['campaign'], 'url': row['xml_url'],
            'http_status': outcome.status, 'failure_class': outcome.failure_class,
            'raw_sha256': hashlib.sha256(outcome.body).hexdigest() if outcome.body else None,
            'gate': verdict.as_row({**fulltext.DEFAULT_THRESHOLDS, **project.gate_thresholds},
                                   policy) if verdict else None,
            'licence': acquire._jats_licence(outcome.body) if verdict and verdict.accepted else None,
            'parse_status': parse_status, 'parsed': parsed,
            'identity_status': 'NEEDS_MANUAL_CHECK',
        }
        store.append(ledger, result)
        summary['attempted'] += 1
        summary['pending'] -= 1
        if outcome.status in (403, 429) or outcome.failure_class in \
                {'ROBOTS_DISALLOWED', 'DOMAIN_BUDGET_EXHAUSTED'}:
            summary['stopped_on_host_refusal'] = row['source_id']
            break
    summary.pop('targets')
    return summary


def rejudge(plan_path: Path, *, store_base='store') -> dict:
    """Re-evaluate recorded XML bytes with current instruments; perform no requests or writes."""
    plan, project, targets = prepare(plan_path)
    store = Store(project.name, base=store_base)
    outcomes = store.latest_by('audits/europe-pmc/jats-pilot-v1/outcomes.jsonl', 'source_id')
    html_documents = store.latest_by('documents.jsonl', 'source_id')
    results = []
    for row in targets:
        previous = outcomes.get(row['source_id'])
        if previous is None:
            raise ValueError(f'pilot has no outcome for {row["source_id"]}')
        result = {'source_id': row['source_id'], 'http_status': previous['http_status'],
                  'original_parse_status': previous['parse_status'],
                  'original_gate_version': previous['gate']['gate_version'] if previous['gate'] else None}
        digest = previous['raw_sha256']
        if digest:
            raw = store.path(f'requests/raw/{digest}.bin').read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError(f'pilot XML hash mismatch for {row["source_id"]}')
            policy = resolve_gate_policy(project.gate_policy, project.classes, row['class'])
            verdict = fulltext.classify(raw, 'application/xml', row['xml_url'],
                                        project.gate_thresholds, policy)
            result.update(gate_version=verdict.gate_version, gate_kind=verdict.kind,
                          licence=acquire._jats_licence(raw) if verdict.accepted else None)
            if verdict.accepted:
                root = ET.fromstring(raw)
                front = next((node for node in root if node.tag.rsplit('}', 1)[-1] == 'front'), None)
                declared = [((node.text or '').strip().upper()) for node in front.iter()
                            if node.tag.rsplit('}', 1)[-1] == 'article-id'
                            and node.get('pub-id-type') == 'pmcid'] if front is not None else []
                expected = row['xml_url'].split('/')[-2].upper()
                result['identity_status'] = ('MATCHED_PMCID' if declared == [expected]
                                             else 'PMCID_MISMATCH_OR_MISSING')
                result['declared_pmcids'] = declared
                try:
                    doc = jats.parse(raw)
                    result.update(parse_status='PARSED', jats_parser_version=jats.JATS_PARSER_VERSION,
                                  body_chars=doc.body_chars, references=len(doc.references),
                                  tables=len(doc.tables), title=doc.title)
                except jats.UnsupportedJats:
                    result['parse_status'] = 'JATS_UNSUPPORTED'
                except jats.JatsError:
                    result['parse_status'] = 'JATS_UNREADABLE'
            else:
                result['parse_status'] = 'GATE_REJECTED'
        else:
            result['parse_status'] = 'NO_XML'
        html = html_documents.get(row['source_id'])
        if html:
            result['stored_html'] = {key: html.get(key) for key in
                                     ('fulltext_confirmed', 'body_chars', 'references', 'tables')}
        results.append(result)
    return {'campaign': plan['campaign'], 'requests_made': 0, 'results': results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--rejudge', action='store_true', help='offline re-evaluation of saved XML')
    args = parser.parse_args()
    if args.execute and args.rejudge:
        parser.error('--execute and --rejudge are mutually exclusive')
    if args.execute:
        load_environment(Path('.env'))
    result = rejudge(Path(args.plan)) if args.rejudge else run(Path(args.plan), execute=args.execute)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
