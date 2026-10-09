#!/usr/bin/env python
"""Inspect one bounded OpenAlex page after a saved first-page probe.

The default preview is offline. Execution records the response under a separate audit;
it cannot write candidates, production query rows, or admission decisions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import ids, net, searchers
from claimstone.config import load_project
from claimstone.request_log import RecordingFetcher
from claimstone.store import Store
from tools.complete_question_round import load_environment
from tools.probe_search_variants import _records

LEDGER = 'audits/research-search/variant-probe/pages.jsonl'
HOST = 'api.openalex.org'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare(plan_path: Path, *, store_base: str = 'store'):
    raw = plan_path.read_bytes()
    plan = json.loads(raw)
    if set(plan) != {'version', 'campaign', 'project', 'input_sha256',
                    'parent_plan_path', 'parent_plan_sha256', 'parent_response_sha256',
                    'page', 'max_physical_requests'} or plan['version'] != 1:
        raise ValueError('expected a version 1 page plan with exact fields')
    if not isinstance(plan['campaign'], str) or not plan['campaign']:
        raise ValueError('named campaign required')
    if any(not isinstance(plan[name], str) or
           not re.fullmatch(r'[0-9a-f]{64}', plan[name])
           for name in ('parent_plan_sha256', 'parent_response_sha256')):
        raise ValueError('parent hashes must be SHA-256 hex digests')
    if plan['page'] != 2 or plan['max_physical_requests'] != 2:
        raise ValueError('this pilot permits page 2 and at most two physical requests')
    parent_path = Path(plan['parent_plan_path'])
    parent_raw = parent_path.read_bytes()
    if sha(parent_raw) != plan['parent_plan_sha256']:
        raise ValueError('parent query plan changed')
    parent = json.loads(parent_raw)
    if plan['campaign'] == parent.get('campaign'):
        raise ValueError('page campaign must differ from parent campaign')
    if parent.get('project') != plan['project'] or parent.get('input_sha256') != plan['input_sha256']:
        raise ValueError('page and parent project inputs differ')
    queries = [q for q in parent.get('queries', []) if q.get('api') == 'openalex']
    if len(queries) != 1 or queries[0].get('mode') != 'title_abstract_keywords':
        raise ValueError('expected one scoped OpenAlex parent query')
    query = queries[0]
    if (not isinstance(query.get('term'), str) or not query['term'].strip() or
            type(query.get('limit')) is not int or not 1 <= query['limit'] <= 100):
        raise ValueError('invalid parent query term or result cap')
    project = load_project(plan['project'])
    expected_inputs = {'topics.yaml', 'questions.yaml', 'sources.yaml'}
    if (project.root / 'manifest.tsv').exists():
        expected_inputs.add('manifest.tsv')
    if set(plan['input_sha256']) != expected_inputs:
        raise ValueError('all existing project inputs must be frozen')
    for name, expected in plan['input_sha256'].items():
        if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
            raise ValueError(f'invalid project input hash: {name}')
        if sha((project.root / name).read_bytes()) != expected:
            raise ValueError(f'project input changed: {name}')
    store = Store(project.name, base=store_base)
    first_path = store.path(f"requests/raw/{plan['parent_response_sha256']}.bin")
    first_raw = first_path.read_bytes()
    if sha(first_raw) != plan['parent_response_sha256']:
        raise ValueError('first-page response hash mismatch')
    parent_outcomes = store.read('audits/research-search/variant-probe/outcomes.jsonl')
    if not any(r.get('campaign') == parent.get('campaign') and
               r.get('plan_sha256') == plan['parent_plan_sha256'] and
               r.get('api') == 'openalex' and r.get('ok') and
               r.get('response_sha256') == plan['parent_response_sha256']
               for r in parent_outcomes):
        raise ValueError('first-page response is not a completed parent probe')
    if not any(r.get('campaign') == parent.get('campaign') and r.get('ok') and
               r.get('raw_sha256') == plan['parent_response_sha256'] and
               r.get('source_api') == 'openalex' and r.get('query') == query['term'] and
               r.get('event') in {'response', 'validated_response', 'transport'}
               for r in store.read('requests.jsonl')):
        raise ValueError('first-page bytes lack a matching recorded request')
    first = json.loads(first_raw)
    meta = first.get('meta') if isinstance(first, dict) else None
    if not isinstance(meta, dict) or meta.get('page') != 1 or meta.get('per_page') != query['limit']:
        raise ValueError('parent is not the declared first basic page')
    count = meta.get('count')
    if type(count) is not int or count <= query['limit'] or count > 10_000:
        raise ValueError('parent count is not a capped query eligible for basic page 2')
    first_rows = _records('openalex', first_raw)
    if len(first_rows) != query['limit']:
        raise ValueError('first page does not fill the declared cap')
    url = searchers.openalex_query_url(query['term'], per_page=query['limit'],
                                       mode='search.title_abstract_keywords', page=2)
    return plan, project, store, sha(raw), query, first_rows, count, url


def run(plan_path: Path, *, execute: bool = False, store_base: str = 'store',
        fetcher=None):
    plan, project, store, plan_sha, query, first_rows, count, url = prepare(
        plan_path, store_base=store_base)
    held = [r for r in store.read(LEDGER) if r.get('campaign') == plan['campaign']]
    if any(r.get('plan_sha256') != plan_sha for r in held):
        raise ValueError('campaign name already used with another plan')
    completed = next((r for r in reversed(held) if r.get('ok')), None)
    if completed is not None:
        response_sha = completed.get('response_sha256')
        if not isinstance(response_sha, str):
            raise ValueError('completed page has no response hash')
        saved = store.path(f'requests/raw/{response_sha}.bin').read_bytes()
        if sha(saved) != response_sha:
            raise ValueError('completed page response hash mismatch')
        return {'campaign': plan['campaign'], 'plan_sha256': plan_sha,
                'status': 'COMPLETE', 'execute': execute, 'page': 2}
    starts = [r for r in store.read('requests.jsonl')
              if r.get('campaign') == plan['campaign'] and r.get('event') == 'request_started']
    report = {'campaign': plan['campaign'], 'plan_sha256': plan_sha,
              'status': 'PREVIEW', 'execute': execute, 'page': 2,
              'per_page': query['limit'], 'first_page_total_available': count,
              'max_physical_requests': 2, 'physical_requests_started': len(starts),
              'estimated_openalex_credits': 10}
    if not execute:
        return report
    if starts:
        raise ValueError('prior physical request without a completed page; inspect before a new campaign')
    transport = fetcher or net.Fetcher(excluded_hosts=frozenset(project.excluded_hosts),
                                       allowed_hosts=frozenset({HOST}),
                                       allowed_schemes=frozenset({'https'}),
                                       enforce_global_addresses=True,
                                       max_physical_requests=2)
    try:
        recorded = RecordingFetcher(transport, store, purpose='search_page_probe',
                                    campaign=plan['campaign'], plan_sha256=plan_sha,
                                    source_api='openalex', query=query['term'], page=2)
        payload, outcome = recorded.get_json(url)
        row = {'campaign': plan['campaign'], 'plan_sha256': plan_sha,
               'parent_response_sha256': plan['parent_response_sha256'],
               'page': 2, 'per_page': query['limit'], 'ok': outcome.ok,
               'http_status': outcome.status, 'failure_class': outcome.failure_class,
               'response_sha256': sha(outcome.body) if outcome.body else None,
               'provider_usage': outcome.provider_usage}
        if outcome.ok:
            try:
                meta = payload['meta']
                if (not isinstance(meta, dict) or meta.get('page') != 2 or
                        meta.get('per_page') != query['limit']):
                    raise ValueError('provider did not return the planned page')
                rows = _records('openalex', outcome.body)
                if len(rows) > query['limit']:
                    raise ValueError('page exceeded the planned result cap')
                first_keys = {r['key'] for r in first_rows}
                row.update(returned=len(rows), total_available=meta.get('count'),
                           overlap_first_page=sum(r['key'] in first_keys for r in rows),
                           result_keys=[r['key'] for r in rows])
            except (ValueError, KeyError, TypeError) as exc:
                row['ok'] = False
                row['failure_class'] = 'INVALID_SEARCH_RESPONSE'
                row['detail'] = str(exc)[:200]
        store.append(LEDGER, row)
        report.update(status='COMPLETE' if row['ok'] else 'STOPPED_ON_FAILURE',
                      outcome=row)
        return report
    finally:
        if fetcher is None:
            transport._session.close()


def readout(plan_path: Path, *, reference_packet: Path, store_base: str = 'store'):
    """Recalculate page yield and reference clues from retained response bytes."""
    plan, _, store, plan_sha, _, first_rows, parent_count, _ = prepare(
        plan_path, store_base=store_base)
    completed = [r for r in store.read(LEDGER)
                 if r.get('campaign') == plan['campaign'] and
                 r.get('plan_sha256') == plan_sha and r.get('ok')]
    if len(completed) != 1:
        raise ValueError('expected one completed page for this frozen plan')
    page_row = completed[0]
    page_sha = page_row.get('response_sha256')
    if not isinstance(page_sha, str):
        raise ValueError('completed page lacks raw response hash')
    raw = store.path(f'requests/raw/{page_sha}.bin').read_bytes()
    if sha(raw) != page_sha:
        raise ValueError('saved second page hash mismatch')
    second_rows = _records('openalex', raw)
    packet_raw = reference_packet.read_bytes()
    packet = json.loads(packet_raw)
    cases = packet.get('cases')
    if not isinstance(cases, list) or not cases:
        raise ValueError('reference packet has no cases')
    references = {}
    for case in cases:
        key = str(case.get('candidate_key') or '')
        doi = ids.normalize_doi(case.get('doi'))
        title = ids.normalize_title(case.get('title'))
        if not key or not doi or not title or key in references:
            raise ValueError('reference case lacks a unique DOI, title or key')
        references[key] = (doi, title)

    def compare(records):
        exact = set()
        title_hints = set()
        possible_versions = set()
        for record in records:
            folded = ids.normalize_title(record['title'])
            for key, (doi, title) in references.items():
                if record['key'] == f'doi:{doi}':
                    exact.add(key)
                if folded == title:
                    title_hints.add(key)
                    if record['key'] != f'doi:{doi}':
                        possible_versions.add((key, record['key']))
        return exact, title_hints, possible_versions

    first_exact, _, _ = compare(first_rows)
    second_exact, second_titles, second_versions = compare(second_rows)
    first_keys = {r['key'] for r in first_rows}
    second_keys = {r['key'] for r in second_rows}
    report = {
        'campaign': plan['campaign'], 'plan_sha256': plan_sha,
        'parent_response_sha256': plan['parent_response_sha256'],
        'page2_response_sha256': page_sha,
        'reference_packet_sha256': sha(packet_raw),
        'first_page_reported_count': parent_count,
        'second_page_reported_count': page_row.get('total_available'),
        'page1_returned': len(first_rows), 'page2_returned': len(second_rows),
        'exact_key_overlap': len(first_keys & second_keys),
        'unique_keys_both_pages': len(first_keys | second_keys),
        'reference_count': len(references),
        'reference_exact_doi_page1': sorted(first_exact),
        'reference_exact_doi_page2': sorted(second_exact),
        'reference_new_exact_doi_page2': sorted(second_exact - first_exact),
        'reference_title_hints_page2': sorted(second_titles),
        'possible_version_pairs_page2': [
            {'reference_key': key, 'result_key': result}
            for key, result in sorted(second_versions)],
        'basis': 'saved provider bytes; title equality is a clue, not a work merge',
    }
    data = (json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2) + '\n').encode()
    path = store.path(f'audits/research-search/variant-probe/page2-readout-{sha(data)}.json')
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
    parser.add_argument('--readout', action='store_true', help='compare saved pages offline')
    parser.add_argument('--reference-packet', type=Path)
    args = parser.parse_args()
    load_environment(Path('.env'))
    if args.execute and args.readout:
        parser.error('--execute and --readout are mutually exclusive')
    if args.readout and args.reference_packet is None:
        parser.error('--readout requires --reference-packet')
    if args.reference_packet is not None and not args.readout:
        parser.error('--reference-packet requires --readout')
    result = (readout(args.plan, reference_packet=args.reference_packet,
                      store_base=args.store_base) if args.readout else
              run(args.plan, execute=args.execute, store_base=args.store_base))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result.get('status') == 'STOPPED_ON_FAILURE')


if __name__ == '__main__':
    raise SystemExit(main())
