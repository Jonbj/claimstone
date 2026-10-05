#!/usr/bin/env python
"""Bounded legal-copy check for the five AI-uncertain L02 abstracts.

Default is an offline preview. Execution writes only request and isolated audit ledgers;
it does not assign source classes, select studies, or modify production acquisitions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import acquire, fulltext, net
from claimstone.config import load_project
from claimstone.request_log import RecordingFetcher
from claimstone.store import Store
from tools.complete_question_round import load_environment

ROOT = Path('store/alembic-s4-lungo/audits/source-selection/l02-v2')
PACKET = ROOT / 'human-reference-packets/b991c6a06218e1778ab93e8550c3e2ee095ac3f7933a2dc55b85fe8182517904.json'
AI = ROOT / 'ai-screening-claude-2026-10-05/l02-ai-screening.json'
LEDGER = 'audits/source-selection/l02-v2/uncertain-fulltext-2026-10-05/outcomes.jsonl'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(plan_path: Path):
    plan = json.loads(plan_path.read_bytes())
    if plan.get('version') != 1 or not plan.get('campaign') or len(plan.get('targets', [])) != 5:
        raise ValueError('expected a versioned, named five-work plan')
    project = load_project(plan['project'])
    if sha(PACKET) != plan['packet_sha256'] or sha(AI) != plan['ai_screening_sha256']:
        raise ValueError('frozen screening inputs changed')
    if sha(project.root / 'sources.yaml') != plan['sources_sha256']:
        raise ValueError('project source policy changed')
    packet = json.loads(PACKET.read_bytes())
    screening = json.loads(AI.read_bytes())
    uncertain = {r['candidate_key'] for r in screening['cases'] if r['decision'] == 'UNCERTAIN'}
    targets = plan['targets']
    if len(uncertain) != 5 or {r['candidate_key'] for r in targets} != uncertain:
        raise ValueError('plan does not equal the five AI-uncertain identities')
    by_key = {r['candidate_key']: r for r in packet['cases']}
    if len(by_key) != len(packet['cases']):
        raise ValueError('duplicate packet identity')
    metadata = sum(r['route'] == 'unpaywall' for r in targets)
    if metadata != plan['max_metadata_requests'] or plan['max_copy_requests'] != len(targets):
        raise ValueError('request ceiling differs from planned routes')
    for target in targets:
        key = target['candidate_key']
        if not key.startswith('doi:') or by_key[key]['doi'] != key[4:]:
            raise ValueError('target DOI differs from packet identity')
        if target['route'] == 'cached_openalex_pdf':
            raw_sha = target['cached_openalex_sha256']
            raw_path = Path('store/alembic-s4-lungo/requests/raw') / f'{raw_sha}.bin'
            if sha(raw_path) != raw_sha:
                raise ValueError('cached OpenAlex payload changed')
            record = json.loads(raw_path.read_bytes())
            urls = [loc.get('pdf_url') for loc in record.get('locations', [])
                    if loc.get('is_oa')]
            # The UK provider recorded a path containing ../ components; HTTP normalizes it.
            planned = urlsplit(target['url'])
            from posixpath import normpath
            if not any(url and urlsplit(url).hostname == planned.hostname and
                       normpath(urlsplit(url).path) == normpath(planned.path) for url in urls):
                raise ValueError('direct URL absent from cached OA metadata')
        elif target['route'] != 'unpaywall':
            raise ValueError('unsupported copy route')
    return plan, project, targets


def _oa_location(payload: dict, excluded: frozenset[str]):
    records = payload.get('oa_locations') or []
    best = payload.get('best_oa_location')
    if isinstance(best, dict) and best not in records:
        records = [best, *records]
    candidates = []
    for entry in records:
        if not isinstance(entry, dict):
            continue
        for field in ('url_for_pdf', 'url'):
            url = entry.get(field)
            if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
                continue
            host = net.host_of(url)
            if host in excluded or host in {'doi.org', 'dx.doi.org', 'papers.ssrn.com'}:
                continue
            candidates.append((0 if field == 'url_for_pdf' or url.lower().endswith('.pdf') else 1,
                               url, entry))
    if not candidates:
        return None
    _, url, entry = min(candidates, key=lambda row: row[0])
    return url, entry


def run(plan_path: Path, *, execute=False, fetcher=None, store_base='store') -> dict:
    plan, project, targets = prepare(plan_path)
    store = Store(project.name, base=store_base)
    prior = {r['candidate_key']: r for r in store.read(LEDGER)
             if r.get('campaign') == plan['campaign']}
    pending = [r for r in targets if r['candidate_key'] not in prior]
    summary = {'campaign': plan['campaign'], 'selected': len(targets),
               'attempted': len(prior), 'pending': len(pending),
               'max_metadata_requests': plan['max_metadata_requests'],
               'max_copy_requests': plan['max_copy_requests'],
               'targets': [{'candidate_key': r['candidate_key'], 'route': r['route']}
                           for r in pending]}
    if not execute or not pending:
        return summary
    fetcher = fetcher or net.Fetcher(excluded_hosts=frozenset(project.excluded_hosts))
    for target in pending:
        key = target['candidate_key']
        recorded = RecordingFetcher(fetcher, store, purpose='l02_uncertain_fulltext',
                                    campaign=plan['campaign'], candidate_key=key,
                                    source_class='UNCLASSIFIED')
        result = {'campaign': plan['campaign'], 'candidate_key': key,
                  'source_class': 'UNCLASSIFIED', 'route': target['route'],
                  'identity_status': 'UNVERIFIED_FULLTEXT', 'adopted': False,
                  'copy_url': None, 'licence': None, 'oa_status': None,
                  'http_status': None, 'failure_class': None, 'gate': None,
                  'raw_sha256': None, 'status': 'NO_OA_COPY'}
        location = None
        if target['route'] == 'cached_openalex_pdf':
            location = (target['url'], None)
            result['oa_status'] = 'openalex-declared-oa'
        else:
            doi = key[4:]
            metadata_url = f'https://api.unpaywall.org/v2/{doi}?email={net.contact_email()}'
            payload, metadata_outcome = recorded.get_json(metadata_url)
            result['metadata_http_status'] = metadata_outcome.status
            result['metadata_failure_class'] = metadata_outcome.failure_class
            if payload:
                result['oa_status'] = payload.get('oa_status')
                location = _oa_location(payload, frozenset(project.excluded_hosts))
            if not location and metadata_outcome.failure_class:
                result['status'] = 'METADATA_FAILED'
                result['failure_class'] = metadata_outcome.failure_class
        if location:
            url, entry = location
            result['copy_url'] = url
            result['licence'] = entry.get('license') if entry else None
            copy_fetcher = RecordingFetcher(fetcher, store, purpose='l02_uncertain_fulltext',
                                            campaign=plan['campaign'], candidate_key=key,
                                            source_class='UNCLASSIFIED', licence=result['licence'],
                                            oa_status=result['oa_status'],
                                            provenance=target['route'])
            outcome = copy_fetcher.get(url, expect=acquire.PDF_TYPES + acquire.HTML_TYPES + acquire.JATS_TYPES)
            result['http_status'] = outcome.status
            result['failure_class'] = outcome.failure_class
            if outcome.ok and outcome.body:
                digest = hashlib.sha256(outcome.body).hexdigest()
                result['raw_sha256'] = digest
                verdict = fulltext.classify(outcome.body, outcome.content_type, outcome.url)
                result['gate'] = verdict.as_row(fulltext.DEFAULT_THRESHOLDS)
                result['status'] = 'FULLTEXT_BYTES' if verdict.accepted else 'COPY_NOT_CONFIRMED'
            else:
                result['status'] = 'COPY_FAILED'
        store.append(LEDGER, result)
        summary['attempted'] += 1
        summary['pending'] -= 1
    summary.pop('targets')
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute:
        load_environment(Path('.env'))
    print(json.dumps(run(Path(args.plan), execute=args.execute), indent=2))


if __name__ == '__main__':
    main()
