"""A tighter gate must remove an old acceptance from every consuming stage."""
from claimstone import claim_records, claimgate, extract, extract_report, model_call, review, review_report, synthesize
from tests.test_extract import FakeProject, _answer, _store
from tests.test_profile_integrity import corpus
from tests.test_synthesize import claim, review as supported_review


def test_a_new_rejection_supersedes_an_acceptance_and_a_new_acceptance_can_restore_it(tmp_path):
    store = _store(tmp_path)
    yes = {'claim_id': 'c', 'claim': 'same annotation', 'gate_revision': 1}
    no = {'claim_id': 'c', 'record': {'claim': 'same annotation'}, 'failure': 'NUMBER_NOT_IN_QUOTE', 'gate_revision': 2}
    store.append('claims.jsonl', yes)
    store.append('rejections.jsonl', no)
    assert claim_records.current(store) == ({}, {'c': no})
    later = yes | {'gate_revision': 3}
    store.append('claims.jsonl', later)
    assert claim_records.current(store) == ({'c': later}, {})
    assert len(list(store.read('claims.jsonl'))) == 2
    assert len(list(store.read('rejections.jsonl'))) == 1


def test_legacy_recovered_claims_keep_their_existing_meaning(tmp_path):
    store = _store(tmp_path)
    store.append('claims.jsonl', {'claim_id': 'c'})
    store.append('rejections.jsonl', {'claim_id': 'c', 'failure': 'UNPARSEABLE_VALUE'})
    assert 'c' in claim_records.current(store)[0]
    assert not claim_records.current(store)[1]


def test_reharvest_with_a_tighter_gate_retires_an_accepted_claim_idempotently(tmp_path):
    text = 'The coefficient is -2 in this sample.'
    store = _store(tmp_path, chunks=(('S01', 'S01#c1', text),))
    project = FakeProject()
    extract.build(project, store, batch='b1')
    raw = {'question_id': 'H02', 'stance': 'SUPPORTS', 'claim': 'The coefficient is 2.', 'evidence_quote': text}
    unit = _answer(store, records=[raw])
    old = raw | {'claim_id': extract.claim_id('S01#c1', 'H02', text), 'call_id': unit['call_id'],
                 'backend': 'fake', 'model': 'm', 'source_id': 'S01', 'chunk_id': 'S01#c1',
                 'source_class': 'ACA', 'registry_version': 0, 'claim_gate_version': 3}
    store.append('claims.jsonl', old)
    store.append('reviews.jsonl', {'claim_id': old['claim_id'], 'verdict': 'SUPPORTED'})
    assert extract.harvest(project, store, batch='b1')['rejected'] == 1
    assert not claim_records.current(store)[0]
    assert extract_report.summarise(store)['accepted'] == 0
    assert extract_report.summarise(store)['rejected'] == 1
    assert review_report.summarise(store)['claims'] == 0
    review.build(project, store, batch='new-review', reviewer=('different', 'model'))
    assert not model_call.Queue(store, lane='review', batch='new-review').requests()
    assert list(store.read('claims.jsonl')) == [old]
    again = extract.harvest(project, store, batch='b1')
    assert again['rejected'] == 0
    assert again['already_held'] == 1
    assert len(list(store.read('rejections.jsonl'))) == 1


def test_reharvest_records_a_new_instrument_version_once_even_when_verdict_is_unchanged(tmp_path, monkeypatch):
    store = _store(tmp_path)
    extract.build(FakeProject(), store, batch='b1')
    _answer(store, records=[{'question_id': 'H02', 'stance': 'SUPPORTS',
             'claim': 'News tone affects returns.', 'evidence_quote': 'news tone does indeed have an effect'}])
    extract.harvest(FakeProject(), store, batch='b1')
    monkeypatch.setattr(claimgate, 'CLAIM_GATE_VERSION', claimgate.CLAIM_GATE_VERSION + 1)
    assert extract.harvest(FakeProject(), store, batch='b1')['accepted'] == 1
    assert extract.harvest(FakeProject(), store, batch='b1')['already_held'] == 1
    rows = list(store.read('claims.jsonl'))
    assert [row['gate_revision'] for row in rows] == [1, 2]


def test_a_retired_claim_is_not_used_in_a_profile_even_with_an_old_supported_review(tmp_path):
    project, store = corpus(tmp_path)
    yes = claim(registry_version=project.registry_version, gate_revision=1)
    store.append('claims.jsonl', yes)
    store.append('reviews.jsonl', supported_review())
    synthesize.build(project, store)
    before = synthesize.latest_profiles(store)['H02']['profile_sha256']
    store.append('rejections.jsonl', {key: yes[key] for key in ['claim_id', 'source_id', 'registry_version']} |
                 {'record': yes, 'failure': 'NUMBER_NOT_IN_QUOTE', 'gate_revision': 2})
    rows, _ = synthesize.preview(project, store)
    current = rows[0]
    assert not current['results']
    assert current['gate_rejected'] == {'NUMBER_NOT_IN_QUOTE': 1}
    assert current['profile_sha256'] != before


def test_a_profile_cannot_be_signed_before_its_legacy_annotations_reach_the_current_gate(tmp_path):
    project, store = corpus(tmp_path)
    store.append('claims.jsonl', claim(registry_version=project.registry_version, claim_gate_version=3))
    store.append('reviews.jsonl', supported_review())
    synthesize.build(project, store)
    profile = synthesize.latest_profiles(store)['H02']
    assert profile['provisional']
    assert profile['extraction']['unregated'] == 1
    assert 'awaiting_regate' in profile['blocking']
    assert profile['claim_gate_version'] == claimgate.CLAIM_GATE_VERSION
