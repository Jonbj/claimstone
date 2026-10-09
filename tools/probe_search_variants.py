#!/usr/bin/env python
"""Bounded, isolated comparison of scholarly search modes against a frozen project.

Preview is offline. Execution writes only request evidence and a separate probe ledger;
it never appends candidates or queries to a production round.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
import urllib.parse
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import ids, net, searchers
from claimstone.config import load_project
from claimstone.request_log import RecordingFetcher
from claimstone.store import Store
from tools.complete_question_round import load_environment

LEDGER = 'audits/research-search/variant-probe/outcomes.jsonl'
MODES = {'openalex': 'title_abstract_keywords', 'crossref': 'title',
         'arxiv': 'title_abstract'}
HOSTS = {'openalex': 'api.openalex.org', 'crossref': 'api.crossref.org',
         'arxiv': 'export.arxiv.org'}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def query_url(query: dict) -> str:
    api, term, limit = query['api'], query['term'], query['limit']
    if api == 'openalex':
        return searchers.openalex_query_url(term, per_page=limit,
                                           mode='search.title_abstract_keywords')
    if api == 'crossref':
        params = {'query.title': term, 'rows': limit, 'mailto': net.contact_email(),
                  'select': 'DOI,title,issued,container-title,URL,type,is-referenced-by-count'}
        return 'https://api.crossref.org/works?' + urllib.parse.urlencode(params)
    # Fielded arXiv syntax is intentionally explicit; the original round used all:"...".
    params = {'search_query': 'ti:"news sentiment" AND abs:returns',
              'start': 0, 'max_results': limit}
    return 'https://export.arxiv.org/api/query?' + urllib.parse.urlencode(params)


def prepare(plan_path: Path, store_base: str):
    raw = plan_path.read_bytes()
    plan = json.loads(raw)
    if plan.get('version') != 1 or plan.get('max_physical_requests') != 6:
        raise ValueError('expected a version 1 six-request plan')
    if not isinstance(plan.get('campaign'), str) or not plan['campaign']:
        raise ValueError('named campaign required')
    queries = plan.get('queries')
    if not isinstance(queries, list) or len(queries) != 3:
        raise ValueError('expected three planned queries')
    if [q.get('api') for q in queries] != ['openalex', 'crossref', 'arxiv']:
        raise ValueError('expected one query per declared API')
    for q in queries:
        if set(q) != {'api', 'mode', 'term', 'limit'} or q['mode'] != MODES[q['api']]:
            raise ValueError('unexpected query mode')
        if not isinstance(q['term'], str) or not q['term'].strip() or not isinstance(q['limit'], int) or not 1 <= q['limit'] <= 100:
            raise ValueError('invalid query term or limit')
    if queries[2]['term'] != 'news sentiment returns':
        raise ValueError('arXiv fielded expression differs from frozen plan')
    project = load_project(plan['project'])
    expected_inputs = {'topics.yaml', 'questions.yaml', 'sources.yaml'}
    if (project.root / 'manifest.tsv').exists():
        expected_inputs.add('manifest.tsv')
    if set(plan['input_sha256']) != expected_inputs:
        raise ValueError('all existing project inputs must be frozen')
    for name, expected in plan['input_sha256'].items():
        if digest((project.root / name).read_bytes()) != expected:
            raise ValueError(f'project input changed: {name}')
    store = Store(project.name, base=store_base)
    urls = [query_url(q) for q in queries]
    if len(set(urls)) != 3:
        raise ValueError('duplicate planned URL')
    return plan, project, store, digest(raw), urls


def _records(api: str, payload: bytes) -> list[dict]:
    if api in {'openalex', 'crossref'}:
        data = json.loads(payload)
        items = data.get('results') if api == 'openalex' else (data.get('message') or {}).get('items')
        if not isinstance(items, list):
            raise ValueError('provider response lacks result list')
        if api == 'openalex':
            return [{'key': ids.candidate_key(doi=ids.normalize_doi(w.get('doi')),
                                               title=w.get('title') or '',
                                               url=w.get('id') or ''),
                     'title': w.get('title') or '', 'provider_id': w.get('id')}
                    for w in items]
        return [{'key': ids.candidate_key(doi=ids.normalize_doi(w.get('DOI')),
                                           title=(w.get('title') or [''])[0],
                                           url=w.get('URL') or ''),
                 'title': (w.get('title') or [''])[0], 'provider_id': w.get('DOI')}
                for w in items]
    root = ET.fromstring(payload)
    if root.tag != '{http://www.w3.org/2005/Atom}feed':
        raise ValueError('provider response is not Atom')
    ns = {'a': 'http://www.w3.org/2005/Atom'}
    result = []
    for entry in root.findall('a:entry', ns):
        title = entry.findtext('a:title', '', ns).strip()
        url = entry.findtext('a:id', '', ns)
        result.append({'key': ids.candidate_key(doi=None, title=title, url=url),
                       'title': title, 'provider_id': ids.arxiv_id(url)})
    return result


def run(plan_path: Path, *, execute=False, store_base='store'):
    plan, project, store, plan_sha, urls = prepare(plan_path, store_base)
    held = [r for r in store.read(LEDGER) if r.get('campaign') == plan['campaign']]
    if any(r.get('plan_sha256') != plan_sha for r in held):
        raise ValueError('campaign name already used with another plan')
    prior = {r['api']: r for r in held}
    pending = [(q, url) for q, url in zip(plan['queries'], urls)
               if not prior.get(q['api'], {}).get('ok')]
    report = {'campaign': plan['campaign'], 'plan_sha256': plan_sha,
              'execute': execute, 'max_physical_requests': plan['max_physical_requests'],
              'pending': [{'api': q['api'], 'mode': q['mode'], 'term': q['term'],
                           'limit': q['limit']} for q, _ in pending],
              'completed': sorted(api for api, row in prior.items() if row.get('ok')),
              'status': 'PREVIEW'}
    if not execute or not pending:
        if execute:
            report['status'] = 'COMPLETE'
        return report
    transport = net.Fetcher(excluded_hosts=frozenset(project.excluded_hosts),
                            allowed_hosts=frozenset(HOSTS.values()),
                            enforce_global_addresses=True,
                            max_physical_requests=plan['max_physical_requests'])
    known = set(store.latest_by('candidates.jsonl', 'candidate_key'))
    try:
        for q, url in pending:
            recorder = RecordingFetcher(transport, store, purpose='search_strategy_probe',
                                        campaign=plan['campaign'], plan_sha256=plan_sha,
                                        source_api=q['api'], query=q['term'])
            outcome = recorder.get(url)
            row = {'campaign': plan['campaign'], 'plan_sha256': plan_sha, 'api': q['api'],
                   'mode': q['mode'], 'term': q['term'], 'limit': q['limit'],
                   'ok': outcome.ok, 'http_status': outcome.status,
                   'failure_class': outcome.failure_class,
                   'response_sha256': digest(outcome.body) if outcome.body else None,
                   'provider_credits': outcome.provider_usage}
            if outcome.ok and outcome.body:
                try:
                    records = _records(q['api'], outcome.body)
                except (ValueError, KeyError, TypeError, ET.ParseError) as exc:
                    row['ok'] = False
                    row['failure_class'] = 'INVALID_SEARCH_RESPONSE'
                    row['detail'] = str(exc)[:200]
                else:
                    row['returned'] = len(records)
                    row['known_keys'] = sum(r['key'] in known for r in records)
                    row['new_keys'] = sum(r['key'] not in known for r in records)
                    row['results'] = records
            store.append(LEDGER, row)
            prior[q['api']] = row
            if not row['ok']:
                break
    finally:
        transport._session.close()
    report['completed'] = sorted(api for api, row in prior.items() if row.get('ok'))
    report['pending'] = [q['api'] for q in plan['queries'] if not prior.get(q['api'], {}).get('ok')]
    report['status'] = 'STOPPED_ON_FAILURE' if report['pending'] else 'COMPLETE'
    return report


def readout(plan_path: Path, *, store_base='store', reference_packet: Path | None = None):
    """Recalculate the comparison from retained bytes, leaving the append-only probe alone."""
    plan, project, store, plan_sha, _ = prepare(plan_path, store_base)
    held = [r for r in store.read(LEDGER) if r.get('campaign') == plan['campaign']]
    if any(r.get('plan_sha256') != plan_sha for r in held):
        raise ValueError('campaign plan changed')
    latest = {r['api']: r for r in held if r.get('ok')}
    known = store.latest_by('candidates.jsonl', 'candidate_key')
    known_titles = {ids.normalize_title(r.get('title')) for r in known.values()}
    references = {}
    reference_titles = {}
    reference_sha = None
    if reference_packet is not None:
        packet_bytes = reference_packet.read_bytes()
        reference_sha = digest(packet_bytes)
        packet = json.loads(packet_bytes)
        cases = packet.get('cases')
        if not isinstance(cases, list) or not cases:
            raise ValueError('reference packet has no cases')
        for case in cases:
            key = str(case.get('candidate_key') or '')
            doi = ids.normalize_doi(case.get('doi'))
            title = ids.normalize_title(case.get('title'))
            if not key or not doi or not title or key in references:
                raise ValueError('reference case lacks a unique DOI, title or key')
            references[key] = {'doi': doi, 'title': title}
            reference_titles.setdefault(title, set()).add(key)
    by_key = defaultdict(set)
    exact_reference_hits = set()
    title_reference_hints = set()
    possible_version_pairs = set()
    summary = []
    for q in plan['queries']:
        api = q['api']
        row = latest.get(api)
        if row is None or not row.get('response_sha256'):
            summary.append({'api': api, 'status': 'NO_SUCCESSFUL_RESPONSE'})
            continue
        raw = store.path(f"requests/raw/{row['response_sha256']}.bin").read_bytes()
        if digest(raw) != row['response_sha256']:
            raise ValueError('saved response hash mismatch')
        records = _records(api, raw)
        api_exact = set()
        api_title = set()
        for record in records:
            by_key[record['key']].add(api)
            for key, reference in references.items():
                if record['key'] == f"doi:{reference['doi']}":
                    exact_reference_hits.add(key)
                    api_exact.add(key)
            for key in reference_titles.get(ids.normalize_title(record['title']), set()):
                title_reference_hints.add(key)
                api_title.add(key)
                if record['key'] != f"doi:{references[key]['doi']}":
                    possible_version_pairs.add((key, record['key']))
        summary.append({'api': api, 'returned': len(records),
                        'known_identity_hits': sum(r['key'] in known for r in records),
                        'known_title_hits': sum(ids.normalize_title(r['title']) in known_titles
                                                for r in records),
                        'reference_exact_doi_hits': len(api_exact),
                        'reference_title_hints': len(api_title),
                        'unique_keys': len({r['key'] for r in records}),
                        'response_sha256': row['response_sha256']})
    report = {'campaign': plan['campaign'], 'plan_sha256': plan_sha,
              'basis': 'saved provider bytes; title matches are hints, not identity decisions',
              'providers': summary, 'unique_keys_all_providers': len(by_key),
              'keys_in_multiple_providers': sum(len(apis) > 1 for apis in by_key.values())}
    if reference_packet is not None:
        report['reference_packet_sha256'] = reference_sha
        report['reference_count'] = len(references)
        report['reference_exact_doi_hits'] = sorted(exact_reference_hits)
        report['reference_title_hints'] = sorted(title_reference_hints)
        report['reference_unmatched_doi_keys'] = sorted(set(references) - exact_reference_hits)
        report['possible_version_pairs'] = [
            {'reference_key': reference_key, 'result_key': result_key}
            for reference_key, result_key in sorted(possible_version_pairs)]
    data = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
    path = store.path(f'audits/research-search/variant-probe/readout-{digest(data)}.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    report['readout_path'] = str(path)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--store-base', default='store')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--readout', action='store_true', help='recalculate from saved bytes offline')
    parser.add_argument('--reference-packet', type=Path,
                        help='compare saved results with a separate frozen DOI/title packet')
    args = parser.parse_args()
    load_environment(Path('.env'))
    if args.execute and args.readout:
        parser.error('--execute and --readout are mutually exclusive')
    if args.reference_packet is not None and not args.readout:
        parser.error('--reference-packet requires --readout')
    action = readout if args.readout else run
    kwargs = {'store_base': args.store_base,
              'reference_packet': args.reference_packet} if args.readout else {
        'execute': args.execute, 'store_base': args.store_base}
    print(json.dumps(action(args.plan, **kwargs), indent=2))


if __name__ == '__main__':
    main()
