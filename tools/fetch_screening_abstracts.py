#!/usr/bin/env python
"""Fetch a frozen, bounded OpenAlex metadata batch for source-screening calibration.

Preview is offline and read-only. Execution records every request through RecordingFetcher,
keeps original payload bytes, and appends identity-checked abstract outcomes. An attempt is
never silently repeated within the same named campaign. No candidate or decision is changed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import quote, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import ids, net
from claimstone.config import load_project
from claimstone.request_log import RecordingFetcher
from claimstone.store import Store
from tools.complete_question_round import load_environment

LEDGER = 'screening_metadata.jsonl'
WORK_ID = re.compile(r'^https://openalex\.org/(W[0-9]+)$')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reconstruct_abstract(index):
    """OpenAlex's positional inverted index, without guessing through malformed payloads."""
    if index is None:
        return None
    if not isinstance(index, dict):
        raise ValueError('invalid abstract index')
    positions = {}
    for word, locs in index.items():
        if not isinstance(word, str) or not isinstance(locs, list):
            raise ValueError('invalid abstract index')
        for loc in locs:
            if type(loc) is not int or loc < 0 or loc > 10000 or loc in positions:
                raise ValueError('invalid abstract positions')
            positions[loc] = word
    if not positions:
        return None
    if set(positions) != set(range(len(positions))):
        raise ValueError('incomplete abstract positions')
    return ' '.join(positions[n] for n in range(len(positions)))


def crossref_abstract(markup):
    if markup is None:
        return None
    if not isinstance(markup, str) or len(markup) > 200000:
        raise ValueError('invalid Crossref abstract')
    class Text(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts = []
        def handle_data(self, data):
            self.parts.append(data)
    parser = Text()
    parser.feed(markup)
    value = ' '.join(' '.join(parser.parts).split())
    return value or None


def target(record, provider='openalex'):
    candidate = record['candidate']
    doi = candidate.get('doi')
    if provider == 'crossref':
        return 'https://api.crossref.org/works/' + quote(doi, safe='/') if doi else None
    if doi:
        return 'https://api.openalex.org/works/doi:' + quote(doi, safe='/.')
    found = {match.group(1) for meta in record.get('cached_metadata', [])
             if (match := WORK_ID.fullmatch(meta.get('api_work_id') or ''))}
    return 'https://api.openalex.org/works/' + next(iter(found)) if len(found) == 1 else None


def load(plan_path):
    plan = json.loads(Path(plan_path).read_bytes())
    if plan.get('version') != 1 or not plan.get('campaign') or not plan.get('keys'):
        raise ValueError('positive version, named campaign and frozen keys required')
    if plan.get('provider', 'openalex') not in ('openalex', 'crossref'):
        raise ValueError('unsupported metadata provider')
    project = load_project(plan['project'])
    queue_path = Path(plan['queue_path'])
    if digest(queue_path) != plan['queue_sha256']:
        raise ValueError('frozen screening queue changed')
    queue = json.loads(queue_path.read_bytes())
    by_key = {r['candidate']['candidate_key']: r for r in queue['records']}
    if len(by_key) != len(queue['records']) or len(plan['keys']) != len(set(plan['keys'])):
        raise ValueError('duplicate queue or plan identity')
    if any(key not in by_key for key in plan['keys']):
        raise ValueError('planned identity absent from queue')
    if (type(plan.get('max_requests')) is not int or plan['max_requests'] < 1 or
            len(plan['keys']) > plan['max_requests']):
        raise ValueError('request ceiling exceeded')
    if project.registry_sha256 != plan['registry_sha256']:
        raise ValueError('project registry changed')
    for name, expected in plan['project_inputs'].items():
        if digest(project.root / name) != expected:
            raise ValueError('project input changed: ' + name)
    store = Store(project.name, base=plan.get('store_base', 'store'))
    selected = [by_key[key] for key in plan['keys']]
    if required_campaign := plan.get('requires_campaign'):
        prior = {r['candidate_key']: r for r in store.read(LEDGER)
                 if r.get('campaign') == required_campaign}
        if any(prior.get(key, {}).get('status') != plan.get('requires_status')
               for key in plan['keys']):
            raise ValueError('required prior metadata outcome changed or absent')
    return plan, project, store, selected


def pending(plan, store, selected):
    attempted = {(r.get('campaign'), r.get('candidate_key')) for r in store.read(LEDGER)}
    return [r for r in selected if (plan['campaign'], r['candidate']['candidate_key']) not in attempted]


def assess(record, payload, outcome, provider='openalex'):
    candidate = record['candidate']
    if not outcome.ok or payload is None:
        return 'LOOKUP_FAILED', None, None
    work = payload.get('message') if provider == 'crossref' else payload
    if not isinstance(work, dict):
        return 'INVALID_METADATA', None, None
    actual_doi = ids.normalize_doi(work.get('DOI') if provider == 'crossref' else work.get('doi'))
    expected_doi = ids.normalize_doi(candidate.get('doi'))
    if provider == 'crossref':
        titles = work.get('title') or []
        actual_title = str(titles[0]) if isinstance(titles, list) and titles else ''
    else:
        actual_title = str(work.get('title') or work.get('display_name') or '')
    requested = target(record, provider)
    expected_work_id = requested.rsplit('/', 1)[-1] if requested and not expected_doi else None
    if ((expected_doi and actual_doi != expected_doi) or
            (provider == 'openalex' and expected_work_id and
             work.get('id') != 'https://openalex.org/' + expected_work_id) or
            ids.normalize_title(actual_title) != ids.normalize_title(candidate['title'])):
        return 'IDENTITY_CONFLICT', None, actual_title
    try:
        abstract = (crossref_abstract(work.get('abstract')) if provider == 'crossref'
                    else reconstruct_abstract(work.get('abstract_inverted_index')))
    except ValueError:
        return 'INVALID_ABSTRACT', None, actual_title
    return ('ABSTRACT_AVAILABLE' if abstract else 'NO_ABSTRACT'), abstract, actual_title


def run(plan_path, *, execute=False, fetcher=None):
    plan, project, store, selected = load(plan_path)
    provider = plan.get('provider', 'openalex')
    outstanding = pending(plan, store, selected)
    report = {'execute': execute, 'campaign': plan['campaign'], 'planned': len(selected),
              'pending': len(outstanding), 'network_requests': 0, 'model_calls': 0,
              'status': 'PREVIEW', 'outcomes': []}
    if not execute:
        report['unresolvable'] = [r['candidate']['candidate_key'] for r in outstanding
                                  if not target(r, provider)]
        return report
    load_environment(Path('.env'))
    if provider == 'openalex' and not os.environ.get('OPENALEX_API_KEY', '').strip():
        raise ValueError('OPENALEX_API_KEY required for recorded metadata requests')
    owned_fetcher = fetcher is None
    fetcher = fetcher or net.Fetcher(excluded_hosts=frozenset(project.excluded_hosts))
    recorder = RecordingFetcher(fetcher, store, purpose='screening_abstract', campaign=plan['campaign'])
    try:
        for record in outstanding:
            candidate = record['candidate']; key = candidate['candidate_key']
            endpoint = target(record, provider)
            if endpoint:
                url = endpoint + '?' + urlencode({'mailto': net.contact_email()})
                payload, outcome = recorder.get_json(url)
                report['network_requests'] += 1
                status, abstract, actual_title = assess(record, payload, outcome, provider)
                raw_sha = hashlib.sha256(outcome.body).hexdigest() if outcome.body else None
                row = {'campaign': plan['campaign'], 'candidate_key': key,
                       'provider': provider,
                       'source_class': candidate.get('source_class'), 'status': status,
                       'failure_class': outcome.failure_class, 'http_status': outcome.status,
                       'request_url': url, 'raw_sha256': raw_sha,
                       'openalex_work_id': payload.get('id') if isinstance(payload, dict) else None,
                       'candidate_doi': candidate.get('doi'), 'candidate_title': candidate['title'],
                       'response_title': actual_title, 'abstract': abstract,
                       'recorded_at': dt.datetime.now(dt.timezone.utc).isoformat()}
            else:
                row = {'campaign': plan['campaign'], 'candidate_key': key,
                       'provider': provider,
                       'source_class': candidate.get('source_class'), 'status': 'NO_LOOKUP_ID',
                       'failure_class': None, 'http_status': None, 'request_url': None,
                       'raw_sha256': None, 'openalex_work_id': None,
                       'candidate_doi': candidate.get('doi'), 'candidate_title': candidate['title'],
                       'response_title': None, 'abstract': None,
                       'recorded_at': dt.datetime.now(dt.timezone.utc).isoformat()}
            store.append(LEDGER, row)
            report['outcomes'].append({'candidate_key': key, 'status': row['status']})
            if row['status'] == 'LOOKUP_FAILED':
                report['status'] = 'STOPPED_ON_LOOKUP_FAILURE'
                break
        else:
            report['status'] = 'SELECTED_METADATA_COMPLETE'
    finally:
        if owned_fetcher and getattr(fetcher, '_session', None):
            fetcher._session.close()
    report['pending'] = len(pending(plan, store, selected))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    report = run(args.plan, execute=args.execute)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(report['status'] == 'STOPPED_ON_LOOKUP_FAILURE')


if __name__ == '__main__':
    raise SystemExit(main())
