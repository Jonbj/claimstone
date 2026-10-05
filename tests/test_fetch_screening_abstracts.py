import json
from pathlib import Path

from claimstone import net
from claimstone.config import load_project
from claimstone.store import Store
from tools import fetch_screening_abstracts as abstracts


def fixture_plan(tmp_path):
    project = load_project('projects/example-news-and-returns')
    queue = tmp_path / 'queue.json'
    queue.write_text(json.dumps({'records': [
        {'candidate': {'candidate_key': 'doi:10.1234/example', 'doi': '10.1234/example',
                       'title': 'Example Study', 'source_class': 'WP'}, 'cached_metadata': []},
    ]}))
    plan = {'version': 1, 'campaign': 'test-metadata-v1',
            'project': str(project.root), 'store_base': str(tmp_path / 'store'),
            'registry_sha256': project.registry_sha256,
            'queue_path': str(queue), 'queue_sha256': abstracts.digest(queue),
            'keys': ['doi:10.1234/example'], 'max_requests': 1,
            'project_inputs': {name: abstracts.digest(project.root / name)
                               for name in ('topics.yaml', 'questions.yaml', 'sources.yaml')}}
    path = tmp_path / 'plan.json'; path.write_text(json.dumps(plan))
    return path


def test_abstract_reconstruction_rejects_gaps_and_collisions():
    assert abstracts.reconstruct_abstract({'return': [1], 'Stock': [0]}) == 'Stock return'
    assert abstracts.reconstruct_abstract(None) is None
    for bad in ({'a': [1]}, {'a': [0], 'b': [0]}, {'a': [-1]}):
        try:
            abstracts.reconstruct_abstract(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('malformed index accepted')


def test_preview_is_read_only_and_execution_records_raw_and_resumes(tmp_path, monkeypatch):
    plan = fixture_plan(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    preview = abstracts.run(plan)
    assert preview['status'] == 'PREVIEW' and preview['pending'] == 1
    assert {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()} == before

    monkeypatch.setenv('OPENALEX_API_KEY', 'test-key')
    monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'tests@example.org')
    calls = []
    class Fetcher:
        def get_json(self, url):
            calls.append(url)
            body = json.dumps({'id': 'https://openalex.org/W1', 'doi': 'https://doi.org/10.1234/example',
                'title': 'Example Study', 'abstract_inverted_index': {'Stock': [0], 'returns': [1]}}).encode()
            return json.loads(body), net.Outcome(url, True, status=200, body=body)
    result = abstracts.run(plan, execute=True, fetcher=Fetcher())
    assert result['status'] == 'SELECTED_METADATA_COMPLETE'
    assert result['network_requests'] == 1 and result['pending'] == 0
    assert len(calls) == 1 and 'test-key' not in calls[0]
    store = Store('example-news-and-returns', base=tmp_path / 'store')
    row = list(store.read(abstracts.LEDGER))[0]
    assert row['status'] == 'ABSTRACT_AVAILABLE' and row['abstract'] == 'Stock returns'
    assert row['source_class'] == 'WP'
    assert any(r.get('raw_sha256') for r in store.read('requests.jsonl'))
    assert abstracts.run(plan, execute=True, fetcher=Fetcher())['network_requests'] == 0
    assert len(calls) == 1


def test_identity_conflict_cannot_yield_usable_abstract(tmp_path, monkeypatch):
    plan = fixture_plan(tmp_path)
    monkeypatch.setenv('OPENALEX_API_KEY', 'test-key')
    monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'tests@example.org')
    class Fetcher:
        def get_json(self, url):
            body = json.dumps({'id': 'https://openalex.org/W2', 'doi': '10.1234/example',
                'title': 'Different Study', 'abstract_inverted_index': {'irrelevant': [0]}}).encode()
            return json.loads(body), net.Outcome(url, True, status=200, body=body)
    abstracts.run(plan, execute=True, fetcher=Fetcher())
    row = list(Store('example-news-and-returns', base=tmp_path / 'store').read(abstracts.LEDGER))[0]
    assert row['status'] == 'IDENTITY_CONFLICT' and row['abstract'] is None


def test_changed_frozen_queue_refused(tmp_path):
    plan = fixture_plan(tmp_path)
    queue = Path(json.loads(plan.read_text())['queue_path'])
    queue.write_text('{}')
    try:
        abstracts.run(plan)
    except ValueError as exc:
        assert 'frozen screening queue changed' in str(exc)
    else:
        raise AssertionError('changed queue accepted')


def test_crossref_fallback_strips_markup_and_checks_identity(tmp_path, monkeypatch):
    plan_path = fixture_plan(tmp_path)
    plan = json.loads(plan_path.read_text())
    plan['provider'] = 'crossref'
    plan_path.write_text(json.dumps(plan))
    monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'tests@example.org')
    monkeypatch.delenv('OPENALEX_API_KEY', raising=False)
    class Fetcher:
        def get_json(self, url):
            assert url.startswith('https://api.crossref.org/works/10.1234/example?')
            body = json.dumps({'message': {'DOI': '10.1234/example',
                'title': ['Example Study'],
                'abstract': '<jats:p>Stock <jats:italic>returns</jats:italic> rise.</jats:p>'}}).encode()
            return json.loads(body), net.Outcome(url, True, status=200, body=body)
    result = abstracts.run(plan_path, execute=True, fetcher=Fetcher())
    assert result['status'] == 'SELECTED_METADATA_COMPLETE'
    row = list(Store('example-news-and-returns', base=tmp_path / 'store').read(abstracts.LEDGER))[0]
    assert row['provider'] == 'crossref' and row['abstract'] == 'Stock returns rise.'
