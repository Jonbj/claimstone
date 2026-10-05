import json

import pytest

from tools.audit_source_selection import audit, digest


def inputs(tmp_path):
    inventory = [{'candidate_key': 'a', 'title': 'Eligible but unavailable'},
                 {'candidate_key': 'b', 'title': 'Unrelated but downloadable'},
                 {'candidate_key': 'c', 'title': 'Uncertain'}]
    (tmp_path/'inventory.json').write_text(json.dumps(inventory))
    plan = dict(version=1, declared_at='2026-09-29', question_id='Q1',
                question_text='Public example question', registry_sha256='hash',
                round='new-selection', rationale='Eligibility independent of retrieval',
                criteria={'topic': {'dimension': 'topic', 'description': 'Addresses the declared question'}},
                inventory_path='inventory.json', decisions_path='decisions.json',
                frozen_inputs=[{'path': 'inventory.json', 'sha256': digest(tmp_path/'inventory.json')}])
    (tmp_path/'plan.json').write_text(json.dumps(plan))
    decisions = [dict(candidate_key=k, decision=d, identity_status='VERIFIED',
                      checked_by='reader', reason='Declared topic criterion',
                      criterion_ids=['topic'], evidence=[{'locator': 'public abstract',
                                                        'observation': 'Scope checked'}])
                 for k, d in [('a', 'INCLUDE'), ('b', 'EXCLUDE')]]
    (tmp_path/'decisions.json').write_text(json.dumps(decisions))
    return tmp_path/'plan.json', decisions


def test_partial_screening_keeps_unknowns_and_does_not_establish_a_floor(tmp_path):
    path, _ = inputs(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    result = audit(path)
    assert result['included_keys'] == ['a']
    assert result['excluded_keys'] == ['b']
    assert result['pending_keys'] == ['c']
    assert not result['cohort_closed']
    assert result['acquisition_rate'] is result['literature_recall'] is None
    assert result['production_ledger_rows_written'] == result['model_calls'] == 0
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_identity_conflict_blocks_inclusion_and_correction_retains_original_key(tmp_path):
    path, decisions = inputs(tmp_path)
    decisions[0]['identity_status'] = 'CONFLICT'
    (tmp_path/'decisions.json').write_text(json.dumps(decisions))
    assert 'a' in audit(path)['pending_keys']
    decisions[0].update(identity_status='CORRECTED', corrected_identity={
        'candidate_key': 'canonical-a', 'title': 'Verified title', 'authority': 'publisher record'})
    (tmp_path/'decisions.json').write_text(json.dumps(decisions))
    result = audit(path)
    assert result['identity_corrections'][0]['original_candidate_key'] == 'a'
    assert result['included_keys'] == ['a']
    assert result['eligible_inventory'][0]['candidate_key'] == 'canonical-a'


def test_changed_inventory_or_unsupported_exclusion_is_refused(tmp_path):
    path, decisions = inputs(tmp_path)
    decisions[1]['criterion_ids'] = ['could_not_download']
    (tmp_path/'decisions.json').write_text(json.dumps(decisions))
    with pytest.raises(ValueError, match='declared criteria'):
        audit(path)
    (tmp_path/'inventory.json').write_text('[]')
    with pytest.raises(ValueError, match='frozen input changed'):
        audit(path)


def test_even_exclusions_with_unknown_identity_remain_pending(tmp_path):
    path, decisions = inputs(tmp_path)
    decisions[1]['identity_status'] = 'UNVERIFIED'
    decisions.append(dict(decisions[0], candidate_key='c', decision='UNCERTAIN'))
    (tmp_path/'decisions.json').write_text(json.dumps(decisions))
    assert audit(path)['pending_keys'] == ['b', 'c']


def test_closed_cohort_needs_all_cases_decided_and_at_least_one_inclusion(tmp_path):
    path, decisions = inputs(tmp_path)
    decisions.append(dict(decisions[0], candidate_key='c', decision='EXCLUDE'))
    (tmp_path/'decisions.json').write_text(json.dumps(decisions))
    assert audit(path)['cohort_closed']
    decisions[0]['decision'] = 'EXCLUDE'
    (tmp_path/'decisions.json').write_text(json.dumps(decisions))
    assert not audit(path)['cohort_closed']


def test_downloadability_cannot_be_declared_as_a_selection_dimension(tmp_path):
    path, _ = inputs(tmp_path)
    plan = json.loads(path.read_text())
    plan['criteria']['topic']['dimension'] = 'download_success'
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='project-supplied criteria'):
        audit(path)


def test_corrected_duplicate_is_not_silently_merged(tmp_path):
    path, decisions = inputs(tmp_path)
    decisions[0].update(identity_status='CORRECTED', corrected_identity={
        'candidate_key': 'c', 'title': 'Actual work', 'authority': 'publisher'})
    decisions.append(dict(decisions[1], candidate_key='c', decision='INCLUDE'))
    (tmp_path/'decisions.json').write_text(json.dumps(decisions))
    with pytest.raises(ValueError, match='collide'):
        audit(path)
