import json

from claimstone.config import load_project
from claimstone.store import Store
from tools import build_screening_reference_packet as packet
from tests.test_fetch_screening_abstracts import fixture_plan


def test_packet_has_provenance_and_no_model_or_inferred_label(tmp_path):
    plan_path = fixture_plan(tmp_path)
    plan = json.loads(plan_path.read_text())
    scope_path = tmp_path / 'scope.json'
    scope_path.write_text(json.dumps({'selection_protocol_version': 2, 'question_id': 'Q01',
        'question_text': 'Example question',
        'registry_sha256': load_project(plan['project']).registry_sha256,
        'criteria': {'E': {'dimension': 'exposure', 'description': 'example'}}}))
    store = Store('example-news-and-returns', base=tmp_path / 'store')
    empty = packet.build(plan_path, scope_path)
    assert empty['available_abstracts'] == 0
    assert empty['cases'][0]['human_decision'] is None
    assert empty['cases'][0]['source_text'] is None
    store.append('screening_metadata.jsonl', {'campaign': 'test-metadata-v1',
        'candidate_key': 'doi:10.1234/example', 'status': 'ABSTRACT_AVAILABLE',
        'abstract': 'The exact supplied abstract.', 'raw_sha256': 'a' * 64,
        'provider': 'openalex'})
    populated = packet.build(plan_path, scope_path)
    assert populated['available_abstracts'] == 1
    case = populated['cases'][0]
    assert case['source_text'] == 'The exact supplied abstract.'
    assert case['source_raw_sha256'] == 'a' * 64
    assert case['human_decision'] is None and case['human_reason'] is None
    assert 'model' not in case
