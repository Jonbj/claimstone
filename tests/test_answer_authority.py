"""Replay must neither resurrect invalid evidence nor overwrite another reader's annotation."""
from types import SimpleNamespace

import pytest

from claimstone import claim_records, extract, model_call, review, review_report
from claimstone.config import Question
from claimstone.runners.base import RawAnswer
from claimstone.store import Store

PROJECT = SimpleNamespace(questions=(Question(id='Q01', text='Is there an effect?', kind='effect'),),
                          registry_version=1, extraction={})
RECORD = {'result_id': 'r1', 'question_id': 'Q01', 'claim': 'There is an effect.',
          'evidence_quote': 'There is an effect.', 'stance': 'SUPPORTS'}


def corpus(tmp_path):
    store = Store('t', base=tmp_path)
    store.append('documents.jsonl', {'source_id': 'S1', 'source_class': 'ACA', 'fulltext_confirmed': True})
    store.append('chunks.jsonl', {'chunk_id': 'S1#1', 'source_id': 'S1', 'text': RECORD['evidence_quote']})
    extract.build(PROJECT, store, batch='e')
    return store


def respond(store, *, lane='extract', batch='e', output=None, model='m1', **overrides):
    queue = model_call.Queue(store, lane=lane, batch=batch)
    unit = queue.requests()[0]
    row = {'call_id': unit['call_id'], 'result_key': f"{unit['call_id']}|fake|{model}",
           'backend': 'fake', 'model': model, 'harness_version': 'fake/1',
           'attempt_no': 1, 'ok': True, 'output': [RECORD] if output is None else output}
    row.update(overrides)
    store.append(queue.results_name, row)
    return row


@pytest.mark.parametrize('output,ok', [(None, False), ([], True)])
def test_invalidated_or_empty_answer_retires_claim_without_erasing_history(tmp_path, output, ok):
    store = corpus(tmp_path)
    respond(store)
    extract.harvest(PROJECT, store, batch='e')
    assert len(claim_records.current(store)[0]) == 1
    respond(store, output=[], ok=ok, rejudged_from='original')
    assert claim_records.current(store)[0] == {}
    assert extract.harvest(PROJECT, store, batch='e')['accepted'] == 0
    assert len(list(store.read('claims.jsonl'))) == 1


def test_rejudged_success_is_harvested_after_failure(tmp_path):
    store = corpus(tmp_path)
    respond(store, ok=False, output=[])
    respond(store, rejudged_from='original')
    assert extract.harvest(PROJECT, store, batch='e')['accepted'] == 1
    assert extract.harvest(PROJECT, store, batch='e')['accepted'] == 0


def test_same_quote_from_two_readers_has_two_immutable_annotations(tmp_path):
    store = corpus(tmp_path)
    respond(store)
    respond(store, model='m2')
    result = extract.harvest(PROJECT, store, batch='e')
    claims = claim_records.current(store)[0]
    assert result['accepted'] == 2
    assert {row['model'] for row in claims.values()} == {'m1', 'm2'}
    assert len(claims) == 2
    assert extract.harvest(PROJECT, store, batch='e')['accepted'] == 0


def test_changed_metadata_gets_new_identity_and_no_inherited_review(tmp_path):
    store = corpus(tmp_path)
    respond(store, output=[RECORD | {'design': 'observational'}])
    extract.harvest(PROJECT, store, batch='e')
    old = next(iter(claim_records.current(store)[0]))
    store.append('reviews.jsonl', {'claim_id': old, 'verdict': 'SUPPORTED'})
    respond(store, output=[RECORD | {'design': 'experimental'}], rejudged_from='original')
    assert review.current(store) == {}
    extract.harvest(PROJECT, store, batch='e')
    new = next(iter(claim_records.current(store)[0]))
    assert new != old
    assert len(list(store.read('claims.jsonl'))) == 2
    assert review_report.summarise(store)['awaiting_review'] == 1


def test_identical_review_prompt_fans_out_to_all_annotations(tmp_path):
    store = corpus(tmp_path)
    respond(store)
    respond(store, model='m2')
    extract.harvest(PROJECT, store, batch='e')
    assert review.build(PROJECT, store, batch='r')['units'] == 1
    queue = model_call.Queue(store, lane='review', batch='r')
    assert len(queue.requests()[0]['review_targets']) == 2
    respond(store, lane='review', batch='r', model='reviewer',
            output={'verdict': 'SUPPORTED', 'reason': 'The passage says so.'})
    assert review.harvest(PROJECT, store, batch='r')['reviewed'] == 2
    assert len(review.current(store)) == 2
    assert review.harvest(PROJECT, store, batch='r')['reviewed'] == 0


def test_invalidated_review_is_immediately_unusable_and_replay_can_replace_it(tmp_path):
    store = corpus(tmp_path)
    respond(store)
    extract.harvest(PROJECT, store, batch='e')
    review.build(PROJECT, store, batch='r')
    respond(store, lane='review', batch='r', model='reviewer',
            output={'verdict': 'SUPPORTED', 'reason': 'yes'})
    review.harvest(PROJECT, store, batch='r')
    respond(store, lane='review', batch='r', model='reviewer', ok=False, output={}, rejudged_from='first')
    assert review.current(store) == {}
    assert review_report.summarise(store)['awaiting_review'] == 1
    assert review.build(PROJECT, store, batch='r2')['units'] == 1
    respond(store, lane='review', batch='r', model='reviewer',
            output={'verdict': 'OVERSTATED', 'reason': 'too strong'}, rejudged_from='first')
    assert review.harvest(PROJECT, store, batch='r')['reviewed'] == 1
    assert next(iter(review.current(store).values()))['verdict'] == 'OVERSTATED'


def raw_result(tmp_path, **answer_fields):
    store = Store('raw', base=tmp_path)
    queue = model_call.Queue(store, lane='extract', batch='e')
    unit = model_call.work_unit(lane='extract', system='system', user='text',
                               response_schema={'type': 'array', 'items': {'type': 'string'}}, max_output_tokens=100,
                               registry_version=1, source_id='S1', chunk_id='S1#1')
    queue.write([unit])
    body = b'[]'
    digest, path = store.store_bytes_at(f'{queue.root}/raw', body, '.txt')
    answer = RawAnswer(body=body, model='reported', **answer_fields)
    row = model_call.build_result(unit, answer, backend='fake', model='', harness_version='fake/1',
                                  raw_sha256=digest, raw_path=str(path), started_at='start',
                                  finished_at='finish', latency_s=1)
    store.append(queue.results_name, row)
    return queue, row, path


@pytest.mark.parametrize('fields,failure', [({'refused': True}, 'REFUSED'),
    ({'truncated': True}, 'TRUNCATED'), ({'failure_class': 'BACKEND_ERROR'}, 'BACKEND_ERROR'),
    ({'prompt_sent': 'wrong prompt'}, 'PROMPT_MISMATCH')])
def test_rejudge_preserves_non_parsing_failure_and_requested_reader(tmp_path, fields, failure):
    queue, original, _ = raw_result(tmp_path, **fields)
    row = list(model_call.rejudge(queue))[0]
    assert row['failure_class'] == failure
    assert not row['ok'] and row['output'] is None
    assert row['result_key'] == original['result_key']
    assert len(queue.results()) == 1
    assert list(model_call.rejudge(queue)) == []


def test_rejudge_restores_failure_erased_by_legacy_rejudge(tmp_path):
    queue, original, _ = raw_result(tmp_path, prompt_sent='wrong')
    legacy = {key: value for key, value in original.items()
              if key not in ('answer_failure_class', 'answer_refused', 'answer_truncated', 'judged_schema')}
    legacy.update(ok=True, output=[], failure_class=None, rejudged_from='finish')
    queue.store.append(queue.results_name, legacy)
    row = list(model_call.rejudge(queue))[0]
    assert row['failure_class'] == 'PROMPT_MISMATCH'


def test_changed_raw_bytes_fail_closed(tmp_path):
    queue, _, path = raw_result(tmp_path)
    path.write_bytes(b'[1]')
    row = list(model_call.rejudge(queue))[0]
    assert row['failure_class'] == 'RAW_HASH_MISMATCH'
    assert not row['ok']


def test_stricter_schema_stays_authoritative_on_repeat_rejudge(tmp_path):
    queue, _, _ = raw_result(tmp_path)
    strict = {'type': 'object'}
    assert list(model_call.rejudge(queue, response_schema=strict))[0]['failure_class'] == 'SCHEMA_INVALID'
    assert list(model_call.rejudge(queue)) == []
    assert not next(iter(queue.results().values()))['ok']


def test_merged_review_cannot_review_its_own_extraction(tmp_path):
    store = corpus(tmp_path)
    respond(store)
    respond(store, model='m2')
    extract.harvest(PROJECT, store, batch='e')
    review.build(PROJECT, store, batch='r')
    respond(store, lane='review', batch='r', model='m1',
            output={'verdict': 'SUPPORTED', 'reason': 'yes'})
    counts = review.harvest(PROJECT, store, batch='r')
    assert counts['reviewed'] == 1 and counts['same_reader'] == 1
    row = next(iter(review.current(store).values()))
    assert row['extracted_by']['model'] == 'm2'


def test_legacy_missing_metadata_is_not_mistaken_for_unchanged_annotation(tmp_path):
    legacy = RECORD | {'design': 'observational'}
    assert not claim_records.matches(legacy, RECORD)


def test_recorded_prompt_mismatch_stays_invalid_even_after_bad_old_rejudge(tmp_path):
    queue, original, _ = raw_result(tmp_path, prompt_sent='wrong')
    queue.store.append(queue.results_name, original | {
        'ok': True, 'failure_class': None, 'output': [], 'rejudged_from': 'finish'})
    held = next(iter(queue.results().values()))
    assert not held['ok'] and held['failure_class'] == 'PROMPT_MISMATCH'


def test_same_annotation_in_two_batches_has_idempotent_provenance_union(tmp_path):
    store = corpus(tmp_path)
    extract.build(PROJECT, store, batch='e2')
    respond(store)
    respond(store, batch='e2')
    for batch in ('e', 'e2'):
        extract.harvest(PROJECT, store, batch=batch)
    claims = claim_records.current(store)[0]
    assert len(claims) == 1
    assert next(iter(claims.values()))['answer_batches'] == ['e', 'e2']
    for batch in ('e', 'e2'):
        assert extract.harvest(PROJECT, store, batch=batch)['accepted'] == 0
    respond(store, batch='e', output=[], ok=False)
    assert len(claim_records.current(store)[0]) == 1
    respond(store, batch='e2', output=[], ok=False)
    assert claim_records.current(store)[0] == {}


def test_legacy_claim_tracks_undeclared_reader_by_reported_model(tmp_path):
    store = corpus(tmp_path)
    queue = model_call.Queue(store, lane='extract', batch='e')
    key = queue.requests()[0]['call_id'] + '|fake|'
    row = respond(store, result_key=key)
    store.append('claims.jsonl', RECORD | {
        'claim_id': 'legacy', 'chunk_id': 'S1#1', 'call_id': row['call_id'],
        'backend': 'fake', 'model': 'm1', 'harness_version': 'fake/1'})
    store.append(queue.results_name, row | {'ok': False, 'output': None})
    assert claim_records.current(store)[0] == {}


def test_changed_harness_retires_old_annotation_and_changes_identity(tmp_path):
    store = corpus(tmp_path)
    respond(store)
    extract.harvest(PROJECT, store, batch='e')
    old = next(iter(claim_records.current(store)[0]))
    respond(store, harness_version='fake/2')
    assert claim_records.current(store)[0] == {}
    extract.harvest(PROJECT, store, batch='e')
    assert old not in claim_records.current(store)[0]
    assert len(claim_records.current(store)[0]) == 1


def test_legacy_rejudge_cannot_create_a_phantom_reported_model_reader(tmp_path):
    queue, original, _ = raw_result(tmp_path, failure_class='BACKEND_ERROR')
    legacy = {key: value for key, value in original.items() if key != 'result_judge_version'}
    queue.store.append(queue.results_name, legacy | {
        'result_key': original['call_id'] + '|fake|reported',
        'ok': True, 'output': [], 'failure_class': None, 'rejudged_from': 'finish'})
    assert len(queue.results()) == 1
    assert not next(iter(queue.results().values()))['ok']
    row = list(model_call.rejudge(queue))[0]
    assert row['result_key'] == original['result_key']
    assert row['failure_class'] == 'BACKEND_ERROR'
