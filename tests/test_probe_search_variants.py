"""Provider result identities in a frozen search comparison."""

import json
import hashlib
from pathlib import Path

from claimstone.store import Store
from tools.probe_search_variants import _records
from tools import probe_search_variants


def test_openalex_and_crossref_doi_formats_compare_as_one_identity():
    openalex = json.dumps({'results': [{
        'id': 'https://openalex.org/W1',
        'doi': 'https://doi.org/10.1234/SAME', 'title': 'A news study'}]}).encode()
    crossref = json.dumps({'message': {'items': [{
        'DOI': '10.1234/same', 'title': ['A news study'],
        'URL': 'https://doi.org/10.1234/same'}]}}).encode()
    assert _records('openalex', openalex)[0]['key'] == 'doi:10.1234/same'
    assert _records('crossref', crossref)[0]['key'] == 'doi:10.1234/same'


def test_reference_readout_keeps_same_title_different_doi_as_hint(tmp_path, monkeypatch):
    monkeypatch.setenv('CLAIMSTONE_CONTACT_EMAIL', 'research@example.org')
    project = Path('projects/example-news-and-returns')
    inputs = {name: hashlib.sha256((project / name).read_bytes()).hexdigest()
              for name in ('topics.yaml', 'questions.yaml', 'sources.yaml')}
    plan = {'version': 1, 'campaign': 'probe-test', 'project': str(project),
            'input_sha256': inputs, 'max_physical_requests': 6,
            'queries': [{'api': 'openalex', 'mode': 'title_abstract_keywords',
                         'term': 'news sentiment stock returns', 'limit': 100},
                        {'api': 'crossref', 'mode': 'title',
                         'term': 'news sentiment stock returns', 'limit': 100},
                        {'api': 'arxiv', 'mode': 'title_abstract',
                         'term': 'news sentiment returns', 'limit': 100}]}
    plan_path = tmp_path / 'plan.json'
    plan_path.write_text(json.dumps(plan))
    plan_sha = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    store = Store(project.name, base=tmp_path / 'store')
    payloads = {
        'openalex': {'results': [{'id': 'https://openalex.org/W1',
                                  'doi': 'https://doi.org/10.1234/other',
                                  'title': 'Same title'}]},
        'crossref': {'message': {'items': [{'DOI': '10.1234/original',
                                            'title': ['Same title']}]}}
    }
    for api, payload in payloads.items():
        raw = json.dumps(payload).encode()
        raw_sha, _ = store.store_bytes_at('requests/raw', raw, '.bin')
        store.append(probe_search_variants.LEDGER, {
            'campaign': 'probe-test', 'plan_sha256': plan_sha,
            'api': api, 'ok': True, 'response_sha256': raw_sha})
    packet_path = tmp_path / 'packet.json'
    packet_path.write_text(json.dumps({'cases': [{
        'candidate_key': 'doi:10.1234/original', 'doi': '10.1234/original',
        'title': 'Same title'}]}))
    report = probe_search_variants.readout(plan_path,
        store_base=str(tmp_path / 'store'), reference_packet=packet_path)
    assert report['reference_exact_doi_hits'] == ['doi:10.1234/original']
    assert report['possible_version_pairs'] == [{
        'reference_key': 'doi:10.1234/original',
        'result_key': 'doi:10.1234/other'}]
