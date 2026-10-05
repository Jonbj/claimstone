import json

import pytest

from tools.audit_identity_relationships import relationship_audit
from tools.audit_source_selection import digest


def test_correction_preserves_original_acquisition_and_title_matches_need_review(tmp_path):
    inventory = [
        {'candidate_key': 'doi:wrong', 'title': 'Alpha Study'},
        {'candidate_key': 'doi:other', 'title': 'Alpha Study'},
        {'candidate_key': 'doi:appendix', 'title': 'Online Appendix for "Alpha Study"'},
        {'candidate_key': 'doi:blank', 'title': ''},
    ]
    (tmp_path / 'inventory.json').write_text(json.dumps(inventory))
    decisions = [{
        'candidate_key': 'doi:wrong', 'decision': 'EXCLUDE',
        'identity_status': 'CORRECTED', 'checked_by': 'reader',
        'reason': 'The held copy is a different work.', 'criterion_ids': ['identity'],
        'evidence': [{'locator': 'held copy', 'observation': 'Different author and title'}],
        'corrected_identity': {'candidate_key': 'doi:actual', 'title': 'Actual Study',
                               'authority': 'archive record'},
    }]
    (tmp_path / 'decisions.json').write_text(json.dumps(decisions))
    plan = {'version': 1, 'declared_at': '2026-10-03', 'question_id': 'Q1',
            'question_text': 'Example?', 'registry_sha256': 'frozen', 'round': 'test-round',
            'rationale': 'Verify identity before screening',
            'criteria': {'identity': {'dimension': 'identity', 'description': 'Check the held work'}},
            'inventory_path': 'inventory.json', 'decisions_path': 'decisions.json',
            'frozen_inputs': [{'path': 'inventory.json',
                               'sha256': digest(tmp_path / 'inventory.json')}]}
    (tmp_path / 'plan.json').write_text(json.dumps(plan))
    (tmp_path / 'acquisitions.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in [
        {'candidate_key': 'doi:wrong', 'sha256': 'raw-hash',
         'stored_path': 'raw/document.pdf', 'acquired': True},
        {'candidate_key': 'doi:other', 'sha256': 'raw-hash',
         'stored_path': 'raw/document.pdf', 'acquired': True},
    ]))
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}

    result = relationship_audit(tmp_path / 'plan.json', tmp_path / 'acquisitions.jsonl')

    assert result['affected_acquisitions'][0]['original_candidate_key'] == 'doi:wrong'
    assert result['affected_acquisitions'][0]['canonical_candidate_key'] == 'doi:actual'
    assert result['affected_acquisitions'][0]['acquisition_sha256'] == 'raw-hash'
    assert result['same_bytes_groups'] == [{
        'sha256': 'raw-hash', 'candidate_keys': ['doi:other', 'doi:wrong'],
        'status': 'SAME_COPY_BYTES',
    }]
    assert result['same_title_groups'] == [{
        'normalized_title': 'alpha study',
        'candidate_keys': ['doi:other', 'doi:wrong'], 'status': 'REVIEW_REQUIRED',
        'possible_relations': ['same_work_different_version', 'same_copy',
                               'distinct_works_same_title'],
    }]
    assert result['possible_supplements'][0]['possible_parent_keys'] == ['doi:other', 'doi:wrong']
    assert result['automatic_merges'] == result['production_ledger_rows_written'] == 0
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}

    relationships = [{
        'candidate_keys': ['doi:wrong', 'doi:other'], 'relation': 'SAME_WORK',
        'status': 'VERIFIED', 'reason': 'The held cover identifies both records.',
        'evidence': [
            {'locator': 'held first page', 'observation': 'Title and series number'},
            {'locator': 'authority record', 'observation': 'Matching DOI and authors'},
        ],
    }]
    (tmp_path / 'relationships.json').write_text(json.dumps(relationships))
    reviewed = relationship_audit(tmp_path / 'plan.json', tmp_path / 'acquisitions.jsonl',
                                  tmp_path / 'relationships.json')
    assert reviewed['reviewed_relationships'] == relationships
    assert reviewed['relationships_sha256'] == digest(tmp_path / 'relationships.json')

    relationships[0]['candidate_keys'][1] = 'doi:missing'
    (tmp_path / 'relationships.json').write_text(json.dumps(relationships))
    with pytest.raises(ValueError, match='inventory keys'):
        relationship_audit(tmp_path / 'plan.json', relationships_path=tmp_path / 'relationships.json')

    relationships[0]['candidate_keys'][1] = 'doi:other'
    relationships[0]['relation'] = 'POSSIBLE_VERSION'
    (tmp_path / 'relationships.json').write_text(json.dumps(relationships))
    with pytest.raises(ValueError, match='certainty'):
        relationship_audit(tmp_path / 'plan.json', relationships_path=tmp_path / 'relationships.json')
