#!/usr/bin/env python
"""Resume only missing/failed/shallow queries of a frozen search, stopping at any failure.

Default is offline preview. --execute preserves the original round, query identities and
population; it never retries already-completed queries or launches acquisition/model calls.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import discover, net
from claimstone.config import load_project
from claimstone.store import Store
from tools import audit_research_search as audit
from tools.complete_question_round import load_environment


def pending(project, store, plan):
    return [q for q in audit.build(project, store, plan)['queries']
            if q['status'] != 'COMPLETED']


def resume(project, store, plan, queries, fetcher):
    results = []
    for query in queries:
        topic = next(t for t in project.topics if t.id == query['topic_id'])
        scoped = replace(project, topics=(replace(topic, terms=(query['query'],)),))
        result = discover.run(scoped, store, fetcher, apis=(query['source_api'],),
                              per_query=query['per_query'], round_name=plan['search_round'])
        results.append(result)
        if not result['final']:
            break  # A provider refusal is not a reason to try the next sixteen requests.
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--limit', type=int, default=1, help='maximum remaining queries to attempt')
    args = parser.parse_args()
    if args.limit < 1:
        parser.error('--limit must be positive')
    plan = json.loads(Path(args.plan).read_text())
    project = load_project(plan['project'])
    store = Store(project.name, base=plan.get('store', 'store'))
    queries = pending(project, store, plan)
    selected = queries[:args.limit]
    report = {'execute': args.execute, 'remaining_queries': len(queries),
              'selected_queries': selected, 'search_round': plan['search_round'],
              'model_calls': 0, 'status': 'PREVIEW'}
    code = 0
    if args.execute and selected:
        load_environment(Path('.env'))
        if any(q['source_api'] == 'openalex' for q in selected) and not os.environ.get('OPENALEX_API_KEY', '').strip():
            parser.error('set OPENALEX_API_KEY in .env before resuming OpenAlex requests')
        fetcher = net.Fetcher(excluded_hosts=frozenset(project.excluded_hosts))
        try:
            report['results'] = resume(project, store, plan, selected, fetcher)
        finally:
            fetcher._session.close()
        code = int(any(not r['final'] for r in report['results']))
        report['status'] = 'STOPPED_ON_SEARCH_FAILURE' if code else 'SELECTED_QUERIES_COMPLETE'
        report['remaining_queries'] = len(pending(project, store, plan))
        data = (json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2) + '\n').encode()
        path = store.path(f'audits/research-search/resume/{audit.digest(data)}.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        report['audit_path'] = str(path)
    elif args.execute:
        report['status'] = 'NO_PENDING_QUERIES'
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
