"""A complete profile must describe exactly the population that can be signed."""
from dataclasses import replace

import pytest

from claimstone import admissibility, config, evidence, extract, model_call, synthesize
from claimstone.config import SourceClass
from claimstone.store import Store
from tests.test_adjudicate import RATIONALE
from tests.test_synthesize import _project, claim, review


def corpus(tmp_path):
    project = _project(tmp_path, floor=0.8)
    store = Store('t', base=tmp_path)
    config.check_registry_drift(project, store)
    add_source(store, 'ACA001', 'one')
    answer(project, store)
    return project, store


def add_source(store, source, round_name, *, acquired=True):
    store.append('candidates.jsonl', {'candidate_key': source, 'source_id': source,
                 'source_class': 'ACA', 'round': round_name})
    store.append('acquisitions.jsonl', {'candidate_key': source, 'source_id': source,
                 'acquired': acquired, 'failure_class': None if acquired else 'PAYWALL_403'})
    if acquired:
        store.append('documents.jsonl', {'source_id': source, 'fulltext_confirmed': True})
        store.append('chunks.jsonl', {'source_id': source, 'chunk_id': source + '#c1',
                     'text': 'news tone has an effect', 'kind': 'prose'})


def answer(project, store, *, missing_kind=None, output=None, harvest=True, batch='production'):
    extract.build(project, store, batch=batch)
    queue = model_call.Queue(store, lane='extract', batch=batch)
    for unit in queue.requests():
        if unit['kind'] == missing_kind:
            continue
        records = (output or []) if unit['kind'] == 'effect' else []
        store.append(queue.results_name, {'call_id': unit['call_id'], 'result_key': unit['call_id'] + '|b|m',
                     'backend': 'b', 'model': 'm', 'ok': True, 'output': records})
    if harvest:
        extract.harvest(project, store, batch=batch)


def test_failed_or_absent_reading_is_provisional_even_without_claims(tmp_path):
    project, store = corpus(tmp_path)
    queue = model_call.Queue(store, lane='extract', batch='production')
    unit = next(u for u in queue.requests() if u['kind'] == 'effect')
    store.append(queue.results_name, {'call_id': unit['call_id'], 'result_key': unit['call_id'] + '|b|m',
                 'backend': 'b', 'model': 'm', 'ok': False, 'failure_class': 'NOT_JSON'})
    synthesize.build(project, store)
    profile = synthesize.latest_profiles(store)['H02']
    assert profile['provisional']
    assert profile['extraction']['unanswered'] == 1
    assert 'awaiting_extract' in profile['blocking']
    assert not synthesize.latest_profiles(store)['H06']['provisional']


def test_successful_nonempty_answer_must_be_harvested(tmp_path):
    project, store = corpus(tmp_path)
    answer(project, store, output=[claim(result_id='r1')], harvest=False)
    synthesize.build(project, store)
    profile = synthesize.latest_profiles(store)['H02']
    assert 'awaiting_harvest' in profile['blocking']
    assert profile['extraction']['unharvested'] == 1


def test_unattempted_candidate_prevents_finality_even_above_floor(tmp_path):
    project, store = corpus(tmp_path)
    for i in range(3):
        add_source(store, f'ACA00{i + 2}', 'one')
    store.append('candidates.jsonl', {'candidate_key': 'pending', 'source_class': 'ACA'})
    result = admissibility.admit(project, store)
    assert result['status'] == admissibility.OK
    assert not result['final']
    assert 'awaiting_acquire' in result['blocking']


def test_profile_scope_applies_to_results_and_coverage_and_hash(tmp_path):
    project, store = corpus(tmp_path)
    add_source(store, 'ACA002', 'two')
    for source in ['ACA001', 'ACA002']:
        store.append('claims.jsonl', claim(claim_id=source, source_id=source,
                     registry_version=project.registry_version))
        store.append('reviews.jsonl', review(source))
    answer(project, store)
    synthesize.build(project, store, round_name='one')
    one = synthesize.latest_profiles(store, round_name='one')['H02']
    synthesize.build(project, store, round_name='two')
    two = synthesize.latest_profiles(store, round_name='two')['H02']
    assert one['sources'] == ['ACA001']
    assert two['sources'] == ['ACA002']
    assert one['coverage']['examined'] == two['coverage']['examined'] == 1
    assert one['profile_sha256'] == evidence._digest(one)
    assert two['profile_sha256'] != one['profile_sha256']
    assert synthesize.latest_profiles(store, round_name='one')['H02'] == one


def test_old_registry_claims_are_not_relabelled_current(tmp_path):
    project, store = corpus(tmp_path)
    store.append('claims.jsonl', claim(registry_version=project.registry_version - 1))
    store.append('reviews.jsonl', review())
    synthesize.build(project, store)
    assert synthesize.latest_profiles(store)['H02']['results'] == []


def test_cached_profile_cannot_be_signed_after_floor_failure(tmp_path):
    project, store = corpus(tmp_path)
    synthesize.build(project, store)
    held = synthesize.latest_profiles(store)['H02']['profile_sha256']
    add_source(store, 'failed', 'one', acquired=False)
    with pytest.raises(synthesize.NotAdmissible):
        synthesize.adjudicate(store, 'H02', project=project, verdict='SUPPORTED', rationale=RATIONALE,
                             by='synthetic operator', signer_auth='cli-declared', actor=None, profile_sha256=held)
    assert not list(store.read(synthesize.ADJUDICATIONS))


def test_signature_requires_hash_and_detects_changes_without_rebuilding(tmp_path):
    project, store = corpus(tmp_path)
    synthesize.build(project, store)
    held = synthesize.latest_profiles(store)['H02']['profile_sha256']
    with pytest.raises(ValueError, match='hash'):
        synthesize.adjudicate(store, 'H02', project=project, verdict='SUPPORTED', rationale=RATIONALE,
                             by='synthetic operator', signer_auth='cli-declared', actor=None)
    synthesize.adjudicate(store, 'H02', project=project, verdict='SUPPORTED', rationale=RATIONALE,
                         by='synthetic operator', signer_auth='cli-declared', actor=None, profile_sha256=held)
    store.append('claims.jsonl', claim(registry_version=project.registry_version))
    store.append('reviews.jsonl', review())
    shown = synthesize.verdicts(store, project=project)
    assert shown['stale'] == 1
    assert shown['rows'][0]['profile']['profile_sha256'] != held
    with pytest.raises(synthesize.StaleProfile):
        synthesize.adjudicate(store, 'H02', project=project, verdict='SUPPORTED', rationale=RATIONALE,
                             by='synthetic operator', signer_auth='cli-declared', actor=None, profile_sha256=held)


def test_reopening_a_previously_recorded_registry_is_still_a_rollback(tmp_path):
    project, store = corpus(tmp_path)
    config.check_registry_drift(replace(project, registry_version=4, frozen_at='2026-09-29'), store)
    with pytest.raises(config.RegistryDrift, match='below'):
        config.check_registry_drift(project, store)


def test_no_queued_units_and_no_chunks_are_not_completed_readings(tmp_path):
    project = _project(tmp_path)
    store = Store('t', base=tmp_path)
    add_source(store, 'ACA001', 'one')
    synthesize.build(project, store)
    assert 'awaiting_extract' in synthesize.latest_profiles(store)['H02']['blocking']
    store.append('candidates.jsonl', {'candidate_key': 'ACA002', 'source_id': 'ACA002', 'source_class': 'ACA'})
    store.append('acquisitions.jsonl', {'candidate_key': 'ACA002', 'source_id': 'ACA002', 'acquired': True})
    store.append('documents.jsonl', {'source_id': 'ACA002', 'fulltext_confirmed': True})
    synthesize.build(project, store)
    assert 'awaiting_chunks' in synthesize.latest_profiles(store)['H02']['blocking']


def test_obsolete_prompts_and_historical_probes_do_not_certify_or_block_current_work(tmp_path):
    project, store = corpus(tmp_path)
    queue = model_call.Queue(store, lane='extract', batch='probe')
    unit = model_call.work_unit(lane='extract', system='old prompt', user='news tone has an effect',
           response_schema={'type': 'array', 'items': {'type': 'object'}}, max_output_tokens=20,
           registry_version=project.registry_version, source_id='ACA001', chunk_id='ACA001#c1')
    unit['kind'] = 'effect'
    queue.write([unit])
    # This unpaid historical experiment does not block the current production reading.
    synthesize.build(project, store)
    assert not synthesize.latest_profiles(store)['H02']['provisional']
    # Changing the frozen question with a dated bump makes the old successful readings obsolete.
    bumped = replace(project, registry_version=4, frozen_at='2026-09-29', registry_sha256='new',
                     questions=(replace(project.questions[0], text='A different effect.'),) + project.questions[1:])
    synthesize.build(bumped, store)
    assert synthesize.latest_profiles(store)['H02']['extraction']['unanswered'] == 1


def test_confirmed_empty_answer_can_close_a_reading_and_different_reader_failure_cannot_erase_it(tmp_path):
    project, store = corpus(tmp_path)
    queue = model_call.Queue(store, lane='extract', batch='production')
    unit = next(u for u in queue.requests() if u['kind'] == 'effect')
    store.append(queue.results_name, {'call_id': unit['call_id'], 'backend': 'another',
                 'model': 'reader', 'ok': False, 'failure_class': 'TRUNCATED'})
    result = synthesize.build(project, store)
    assert result['final']
    assert not synthesize.latest_profiles(store)['H02']['provisional']


def test_manifest_filter_also_filters_evidence(tmp_path):
    project, store = corpus(tmp_path)
    add_source(store, 'ACA002', 'two')
    store.append('candidates.jsonl', {'candidate_key': 'ACA002', 'source_class': 'ACA', 'round': 'two'})
    store.append('claims.jsonl', claim(source_id='ACA002', registry_version=project.registry_version))
    store.append('reviews.jsonl', review())
    synthesize.build(project, store, manifest_only=True)
    profile = synthesize.latest_profiles(store, manifest_only=True)['H02']
    assert profile['manifest_only']
    assert not profile['results']
    assert profile['coverage']['examined'] == 1


def test_verdict_display_marks_floor_failure_stale_without_rebuild(tmp_path):
    project, store = corpus(tmp_path)
    synthesize.build(project, store)
    synthesize.adjudicate(store, 'H02', project=project, verdict='SUPPORTED', rationale=RATIONALE,
                         by='synthetic operator', signer_auth='cli-declared', actor=None, profile_sha256=synthesize.latest_profiles(store)['H02']['profile_sha256'])
    add_source(store, 'failed', 'one', acquired=False)
    result = synthesize.verdicts(store, project=project)
    assert result['adjudicated'] == 0
    assert result['stale'] == 1
    assert result['rows'][0]['unavailable'].startswith(admissibility.INSUFFICIENT)
    assert result['awaiting_adjudication'] == 0


def test_a_class_floor_flip_makes_a_signed_verdict_stale_at_unchanged_counts(tmp_path):
    """The recorded counts are not the whole premise. A `discover --reclassify` row that moves a
    failed candidate into a class whose own floor it breaks leaves `found`, `obtained` and
    `confirmed` identical and still refuses the round — and a verdict signed against the round
    that passed is a verdict about a corpus that no longer exists.
    """
    project = replace(
        _project(tmp_path, floor=0.8),
        classes=(SourceClass(id='ACA', name='refereed', weight_hint='high', role='empirical'),
                 SourceClass(id='IND', name='industry', weight_hint='low', role='empirical',
                             acquisition_floor=0.33, floor_set_at='2026-09-25',
                             floor_rationale='vendor research has no open copy in existence')),
    )
    store = Store('t', base=tmp_path)
    config.check_registry_drift(project, store)
    add_source(store, 'ACA001', 'one')
    for source in ('IND001', 'IND002', 'IND003'):
        store.append('candidates.jsonl', {'candidate_key': source, 'source_id': source,
                     'source_class': 'IND', 'round': 'one'})
        store.append('acquisitions.jsonl', {'candidate_key': source, 'source_id': source,
                     'acquired': True})
        store.append('documents.jsonl', {'source_id': source, 'fulltext_confirmed': True})
        store.append('chunks.jsonl', {'source_id': source, 'chunk_id': source + '#c1',
                     'text': 'news tone has an effect', 'kind': 'prose'})
    store.append('candidates.jsonl', {'candidate_key': 'IND004', 'source_id': 'IND004',
                 'source_class': 'IND', 'round': 'one'})
    store.append('acquisitions.jsonl', {'candidate_key': 'IND004', 'source_id': 'IND004',
                 'acquired': False, 'failure_class': 'PAYWALL_403'})
    answer(project, store)
    assert admissibility.admit(project, store)['status'] == admissibility.OK
    synthesize.build(project, store)
    synthesize.adjudicate(store, 'H02', project=project, verdict='SUPPORTED', rationale=RATIONALE,
                         by='synthetic operator', signer_auth='cli-declared', actor=None,
                         profile_sha256=synthesize.latest_profiles(store)['H02']['profile_sha256'])
    # The reclassify re-reads `assign_when` and the paywalled vendor page is a refereed one.
    store.append('candidates.jsonl', {'candidate_key': 'IND004', 'source_id': 'IND004',
                 'source_class': 'ACA', 'round': 'one'})
    measured = admissibility.admit(project, store)
    assert measured['status'] == admissibility.INSUFFICIENT
    assert (measured['found'], measured['obtained'], measured['confirmed']) == (5, 4, 4)
    result = synthesize.verdicts(store, project=project)
    assert result['adjudicated'] == 0
    assert result['stale'] == 1
    assert result['rows'][0]['unavailable'].startswith(admissibility.INSUFFICIENT)


def test_preview_and_verdict_display_do_not_append_to_any_ledger(tmp_path):
    project, store = corpus(tmp_path)
    synthesize.build(project, store)
    before = {path: path.read_bytes() for path in store.root.rglob('*') if path.is_file()}
    synthesize.preview(project, store)
    synthesize.verdicts(store, project=project)
    after = {path: path.read_bytes() for path in store.root.rglob('*') if path.is_file()}
    assert after == before


def test_signatures_are_separate_per_scope(tmp_path):
    project, store = corpus(tmp_path)
    synthesize.build(project, store, round_name='one')
    held = synthesize.latest_profiles(store, round_name='one')['H02']['profile_sha256']
    synthesize.adjudicate(store, 'H02', project=project, round_name='one', verdict='SUPPORTED',
                         rationale=RATIONALE, by='synthetic operator', signer_auth='cli-declared', actor=None, profile_sha256=held)
    synthesize.build(project, store)
    assert synthesize.verdicts(store, project=project)['adjudicated'] == 0
    assert synthesize.verdicts(store, project=project, round_name='one')['adjudicated'] == 1


def test_registry_check_covers_every_cli_store_entry_before_any_model_or_network_call(tmp_path, capsys):
    from claimstone.cli import main
    from tests.test_registry_drift import project_at
    loaded = project_at(tmp_path, [('Q01', 'An effect exists.')])
    store = Store(loaded.name, base=tmp_path / 'store')
    config.check_registry_drift(loaded, store)
    project_at(tmp_path, [('Q01', 'A changed effect exists.')])
    for command in (['discover', '--reclassify'], ['discover-report'],
                    ['model-run', 'extract', '--batch', 'b', '--backend', 'llamacpp'],
                    ['model-report', 'extract', '--batch', 'b'], ['extract-report', '--batch', 'b']):
        assert main([command[0], str(tmp_path), *command[1:], '--store', str(tmp_path / 'store')]) == 2
        assert 'registry_version 1' in capsys.readouterr().err


def test_a_regated_failure_excludes_an_old_confirmed_source_from_evidence(tmp_path):
    project, store = corpus(tmp_path)
    add_source(store, 'ACA002', 'one')
    project = replace(project, acquisition_floor=0.5)
    store.append('claims.jsonl', claim(source_id='ACA002', registry_version=project.registry_version))
    store.append('reviews.jsonl', review())
    store.append('acquisitions.jsonl', {'candidate_key': 'ACA002', 'source_id': 'ACA002',
                 'acquired': False, 'regated_from': 'old', 'failure_class': 'ABSTRACT_ONLY'})
    synthesize.build(project, store)
    profile = synthesize.latest_profiles(store)['H02']
    assert not profile['results']
    assert profile['coverage']['examined'] == 1


def test_a_changed_review_rationale_changes_identity_but_a_timestamp_does_not(tmp_path):
    project, store = corpus(tmp_path)
    store.append('claims.jsonl', claim(registry_version=project.registry_version))
    store.append('reviews.jsonl', review() | {'rationale': 'Initial interpretation.', 'reviewed_at': 'first'})
    synthesize.build(project, store)
    before = synthesize.latest_profiles(store)['H02']['profile_sha256']
    store.append('reviews.jsonl', review() | {'rationale': 'Initial interpretation.', 'reviewed_at': 'later'})
    same, _ = synthesize.preview(project, store)
    assert same[0]['profile_sha256'] == before
    store.append('reviews.jsonl', review() | {'rationale': 'A different interpretation.', 'reviewed_at': 'later'})
    changed, _ = synthesize.preview(project, store)
    assert changed[0]['profile_sha256'] != before
    # A question's signature is not bound to other questions' review rationales.
    assert changed[1]['profile_sha256'] == same[1]['profile_sha256']


def test_an_old_registry_review_cannot_attest_a_current_claim_with_the_same_id(tmp_path):
    project, store = corpus(tmp_path)
    store.append('claims.jsonl', claim(registry_version=project.registry_version))
    old = model_call.work_unit(lane='review', system='old registry', user='claim',
          response_schema={'type': 'object'}, max_output_tokens=100,
          registry_version=project.registry_version - 1)
    queue = model_call.Queue(store, lane='review', batch='old')
    queue.write([old])
    store.append('reviews.jsonl', review() | {'call_id': old['call_id']})
    synthesize.build(project, store)
    profile = synthesize.latest_profiles(store)['H02']
    assert not profile['results']
    assert profile['awaiting_review'] == 1
    assert profile['provisional']
