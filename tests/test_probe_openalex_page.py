"""A page probe stays bound to saved first-page bytes and never admits results."""

import hashlib
import json
from pathlib import Path

import pytest

from claimstone import net
from claimstone.store import Store
from tools import probe_openalex_page


def _saved_plan(tmp_path):
    project = Path('projects/example-news-and-returns')
    inputs = {name: hashlib.sha256((project / name).read_bytes()).hexdigest()
              for name in ('topics.yaml', 'questions.yaml', 'sources.yaml')}
    query = {'api': 'openalex', 'mode': 'title_abstract_keywords',
             'term': 'news sentiment', 'limit': 100}
    parent = {'campaign': 'parent-test', 'project': str(project),
              'input_sha256': inputs, 'queries': [query]}
    parent_path = tmp_path / 'parent.json'
    parent_path.write_text(json.dumps(parent))
    first = {'meta': {'page': 1, 'per_page': 100, 'count': 101},
             'results': [{'id': f'https://openalex.org/W{i}',
                          'doi': f'https://doi.org/10.1234/a{i}',
                          'title': f'Article {i}'} for i in range(100)]}
    first_bytes = json.dumps(first).encode()
    store = Store(project.name, base=tmp_path / 'store')
    first_sha, _ = store.store_bytes_at('requests/raw', first_bytes, '.bin')
    parent_sha = hashlib.sha256(parent_path.read_bytes()).hexdigest()
    store.append('audits/research-search/variant-probe/outcomes.jsonl', {
        'campaign': parent['campaign'], 'plan_sha256': parent_sha,
        'api': 'openalex', 'ok': True, 'response_sha256': first_sha})
    store.append('requests.jsonl', {'campaign': parent['campaign'], 'ok': True,
        'raw_sha256': first_sha, 'source_api': 'openalex',
        'query': query['term'], 'event': 'response'})
    plan = {'version': 1, 'campaign': 'test-page-2', 'project': str(project),
            'input_sha256': inputs, 'parent_plan_path': str(parent_path),
            'parent_plan_sha256': parent_sha,
            'parent_response_sha256': first_sha, 'page': 2, 'max_physical_requests': 2}
    path = tmp_path / 'page.json'
    path.write_text(json.dumps(plan))
    return path, store


def test_page_probe_uses_saved_parent_and_writes_only_audit(tmp_path, monkeypatch):
    monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'research@example.org')
    path, store = _saved_plan(tmp_path)
    preview = probe_openalex_page.run(path, store_base=str(tmp_path / 'store'))
    assert preview['status'] == 'PREVIEW'
    assert preview['first_page_total_available'] == 101

    body = json.dumps({'meta': {'page': 2, 'per_page': 100, 'count': 101},
                       'results': [{'id': 'https://openalex.org/W100',
                                    'doi': 'https://doi.org/10.1234/a100',
                                    'title': 'Article 100'}]}).encode()

    class Fake:
        calls = []

        def get_json(self, url):
            self.calls.append(url)
            return json.loads(body), net.Outcome(url, True, 200, body=body)

    fake = Fake()
    result = probe_openalex_page.run(path, execute=True,
                                     store_base=str(tmp_path / 'store'), fetcher=fake)
    assert result['status'] == 'COMPLETE'
    assert result['outcome']['returned'] == 1
    assert result['outcome']['overlap_first_page'] == 0
    assert 'page=2' in fake.calls[0]
    assert list(store.read('candidates.jsonl')) == []
    assert list(store.read('queries.jsonl')) == []
    assert probe_openalex_page.run(path, execute=True,
                                  store_base=str(tmp_path / 'store'), fetcher=fake)['status'] == 'COMPLETE'
    assert len(fake.calls) == 1


def test_page_probe_refuses_mutated_parent_response(tmp_path, monkeypatch):
    monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'research@example.org')
    path, store = _saved_plan(tmp_path)
    plan = json.loads(path.read_text())
    store.path(f"requests/raw/{plan['parent_response_sha256']}.bin").write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash mismatch'):
        probe_openalex_page.run(path, store_base=str(tmp_path / 'store'))
