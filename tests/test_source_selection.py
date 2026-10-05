"""Provisional screening and identity observations cannot silently admit works."""
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from claimstone import source_selection as selection
from claimstone.store import Store


H = 'a' * 64
INVENTORY = {'doi:10.1234/a', 'doi:10.1234/b'}


def append(store, screening, identity, inventory=INVENTORY):
    return selection.append_observations(store, screening, identity, scope_id='q-v1',
                                         question_id='Q1', inventory_keys=inventory)


def assessment(key='doi:10.1234/a', decision='UNCERTAIN', role='UNRESOLVED', supersedes=None):
    return selection.identified({
        'selection_version': selection.SOURCE_SELECTION_VERSION,
        'scope_id': 'q-v1', 'question_id': 'Q1', 'registry_sha256': H,
        'candidate_key': key, 'source_class': 'UNCLASSIFIED',
        'assessment_status': 'AI_PROVISIONAL', 'decision': decision, 'role': role,
        'screening_level': 'ABSTRACT', 'criterion_ids': ['C1'], 'reason': 'needs text',
        'assessed_by': 'test agent', 'input_sha256': H,
        'evidence': [{'quote': 'text', 'locator': 'fixture:1', 'text_sha256': H}],
        'supersedes': supersedes,
    }, 'assessment_id')


def test_provisional_rows_are_append_only_and_never_close_cohort(tmp_path):
    store = Store('fixture', base=tmp_path)
    first = assessment()
    second = assessment(decision='EXCLUDE', role='CONTEXT', supersedes=first['assessment_id'])
    inventory = {'doi:10.1234/a', 'doi:10.1234/b'}
    before = selection.preview(store, 'q-v1', 'Q1', inventory, [first, second])
    assert before['screened_count'] == 1 and before['provisional_context'] == 1
    assert before['unobserved_count'] == 1 and not before['cohort_closed']
    assert not (store.root / selection.SCREENING_LEDGER).exists()
    assert append(store, [first, second], [])['screening_rows_written'] == 2
    assert append(store, [first, second], [])['screening_rows_written'] == 0
    assert len(list(store.read(selection.SCREENING_LEDGER))) == 2
    after = selection.preview(store, 'q-v1', 'Q1', inventory)
    assert after['admitted_candidates'] == 0 and after['pending_keys'] == sorted(inventory)
    assert not (store.root / 'candidates.jsonl').exists()
    assert not (store.root / 'acquisitions.jsonl').exists()


def test_supersession_and_content_identity_are_enforced(tmp_path):
    store = Store('fixture', base=tmp_path)
    first = assessment()
    append(store, [first], [])
    with pytest.raises(ValueError, match='supersede'):
        append(store, [assessment(decision='EXCLUDE', role='CONTEXT')], [])
    tampered = dict(first, reason='changed without new id')
    with pytest.raises(ValueError, match='identity'):
        append(store, [tampered], [])
    assert len(list(store.read(selection.SCREENING_LEDGER))) == 1


def test_identity_lead_is_separate_and_cannot_merge_by_title(tmp_path):
    store = Store('fixture', base=tmp_path)
    row = selection.identified({
        'selection_version': selection.SOURCE_SELECTION_VERSION,
        'scope_id': 'q-v1', 'candidate_key': 'doi:10.1234/a',
        'source_class': 'UNCLASSIFIED', 'status': 'POSSIBLE_VERSION',
        'reason': 'title differs', 'assessed_by': 'test agent',
        'metadata_sha256': H, 'copy_sha256': H,
        'observations': ['metadata:title A', 'held-copy:title B'], 'supersedes': None,
    }, 'observation_id')
    assert append(store, [], [row])['identity_rows_written'] == 1
    assert append(store, [], [row])['identity_rows_written'] == 0
    assert not (store.root / 'documents.jsonl').exists()
    assert list(store.read(selection.IDENTITY_LEDGER))[0]['status'] == 'POSSIBLE_VERSION'


def identity_relation(related_kind, related_key, supersedes=None):
    return selection.identified({
        'selection_version': selection.IDENTITY_RELATION_VERSION,
        'scope_id': 'q-v1', 'candidate_key': 'doi:10.1234/a',
        'source_class': 'UNCLASSIFIED', 'status': 'POSSIBLE_VERSION',
        'reason': 'relationship requires inspection', 'assessed_by': 'test agent',
        'metadata_sha256': H, 'copy_sha256': H,
        'related_kind': related_kind, 'related_key': related_key,
        'observations': ['metadata:title A', 'copy:title B'], 'supersedes': supersedes,
    }, 'observation_id')


def test_multiple_identity_counterparts_have_independent_histories(tmp_path):
    store = Store('fixture', base=tmp_path)
    copy = identity_relation('HELD_COPY', H)
    candidate = identity_relation('CANDIDATE', 'doi:10.1234/b')
    assert append(store, [], [copy, candidate])['identity_rows_written'] == 2
    view = selection.preview(store, 'q-v1', 'Q1', INVENTORY)
    assert view['identity_observations'] == 2
    replacement = selection.identified({**candidate, 'status': 'DISTINCT_WORKS',
                                        'supersedes': candidate['observation_id']},
                                       'observation_id')
    assert append(store, [], [replacement])['identity_rows_written'] == 1
    assert selection.preview(store, 'q-v1', 'Q1', INVENTORY)['identity_observations'] == 2
    assert len(list(store.read(selection.IDENTITY_LEDGER))) == 3
    with pytest.raises(ValueError, match='counterpart'):
        selection.validate_identity(selection.identified({**candidate, 'related_key': ''},
                                                         'observation_id'))


def test_legacy_identity_copy_can_be_superseded_by_explicit_relation(tmp_path):
    store = Store('fixture', base=tmp_path)
    legacy = selection.identified({
        'selection_version': selection.SOURCE_SELECTION_VERSION,
        'scope_id': 'q-v1', 'candidate_key': 'doi:10.1234/a',
        'source_class': 'UNCLASSIFIED', 'status': 'POSSIBLE_VERSION',
        'reason': 'old copy lead', 'assessed_by': 'test agent',
        'metadata_sha256': H, 'copy_sha256': H,
        'observations': ['metadata:title A', 'copy:title B'], 'supersedes': None,
    }, 'observation_id')
    append(store, [], [legacy])
    revised = identity_relation('HELD_COPY', H, supersedes=legacy['observation_id'])
    assert append(store, [], [revised])['identity_rows_written'] == 1
    assert selection.preview(store, 'q-v1', 'Q1', INVENTORY)['identity_observations'] == 1


def test_append_refuses_outside_inventory_before_writing(tmp_path):
    store = Store('fixture', base=tmp_path)
    with pytest.raises(ValueError, match='outside the frozen'):
        append(store, [assessment(key='doi:outside')], [])
    assert not store.path(selection.SCREENING_LEDGER).exists()


def test_screening_transition_cannot_downgrade_evidence_or_change_scope_policy(tmp_path):
    store = Store('fixture', base=tmp_path)
    first = selection.identified({**assessment(), 'screening_level': 'FULLTEXT'}, 'assessment_id')
    append(store, [first], [])
    base = assessment(supersedes=first['assessment_id'])
    with pytest.raises(ValueError, match='regressed'):
        append(store, [base], [])
    changed = selection.identified({**base, 'screening_level': 'FULLTEXT',
                                    'registry_sha256': 'b' * 64}, 'assessment_id')
    with pytest.raises(ValueError, match='registry or source class'):
        append(store, [changed], [])
    assert len(list(store.read(selection.SCREENING_LEDGER))) == 1


def test_malformed_quote_and_criteria_are_rejected(tmp_path):
    store = Store('fixture', base=tmp_path)
    bad = selection.identified({**assessment(), 'criterion_ids': [None]}, 'assessment_id')
    with pytest.raises(ValueError, match='criteria'):
        append(store, [bad], [])
    bad = selection.identified({**assessment(),
                                'evidence': [{'quote': 12, 'locator': 'fixture:1',
                                              'text_sha256': H}]}, 'assessment_id')
    with pytest.raises(ValueError, match='evidence'):
        append(store, [bad], [])


def test_concurrent_appends_replay_inside_one_writer_lock(tmp_path, monkeypatch):
    store = Store('fixture', base=tmp_path)
    first_read = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    second_read = threading.Event()
    read_count = 0
    count_lock = threading.Lock()
    original_read = Store.read

    def observed_read(self, name):
        nonlocal read_count
        if name == selection.SCREENING_LEDGER:
            with count_lock:
                read_count += 1
                index = read_count
            if index == 1:
                first_read.set()
                assert release_first.wait(2)
            else:
                second_read.set()
        return original_read(self, name)

    monkeypatch.setattr(Store, 'read', observed_read)
    row = assessment()
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(append, store, [row], [])
        assert first_read.wait(2)

        def second_append():
            second_started.set()
            return append(store, [row], [])

        two = pool.submit(second_append)
        assert second_started.wait(2)
        assert not second_read.wait(0.05)
        release_first.set()
        assert one.result(timeout=2)['screening_rows_written'] == 1
        assert two.result(timeout=2)['screening_rows_written'] == 0
    assert len(list(original_read(store, selection.SCREENING_LEDGER))) == 1
