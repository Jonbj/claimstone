"""Current gate decisions over two append-only ledgers.

Legacy rows have revision zero and keep the historical accepted-wins policy. A re-gate appends a
higher revision, so either outcome can supersede the other without erasing its history.
"""
from __future__ import annotations

from typing import Any

from .store import Store
from . import model_call, chunk_sets

ANNOTATION_VERSION = 2


def matches(row: dict[str, Any], record: dict[str, Any]) -> bool:
    original = row.get('raw_record') or row.get('record')
    if original is not None:
        return original == record
    from . import extract
    fields = {'result_id', 'question_id', 'claim', 'evidence_quote', 'stance'}
    for extra in extract.EXTRA_FIELDS.values():
        fields.update(extra)
    return {key: row[key] for key in fields if key in row} == record


def annotation_id(chunk_id: str, answer: dict[str, Any], record: dict[str, Any]) -> str:
    from .store import sha256_text
    return sha256_text(model_call.canonical([
        ANNOTATION_VERSION, chunk_id, model_call.result_key(answer),
        answer.get('harness_version'), record]))[:32]


def authoritative(row: dict[str, Any], answers: dict) -> bool:
    readings = model_call.answers_for(row, answers)
    if readings is None:
        return True
    return any(answer.get('ok') and isinstance(answer.get('output'), list)
               and (not row.get('harness_version')
                    or row['harness_version'] == answer.get('harness_version'))
               and any(matches(row, record) for record in answer['output']) for answer in readings)


def current(store: Store) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    accepted = store.latest_by('claims.jsonl', 'claim_id')
    rejected = store.latest_by('rejections.jsonl', 'claim_id')
    for identifier in accepted.keys() & rejected.keys():
        yes, no = accepted[identifier], rejected[identifier]
        if int(no.get('gate_revision', 0)) > int(yes.get('gate_revision', 0)):
            del accepted[identifier]
        else:
            del rejected[identifier]
    answers = model_call.current_answers(store, 'extract')
    chunks = chunk_sets.current(store)
    documents = store.latest_by('documents.jsonl', 'source_id')
    requests = {}
    for path in sorted(store.path('calls/extract').glob('*/requests.jsonl')):
        requests.update(store.latest_by(str(path.relative_to(store.root)), 'call_id'))

    def active_chunk(row):
        source = row.get('source_id')
        identifier = row.get('chunk_id') or (row.get('record') or {}).get('chunk_id')
        if source in documents:
            chunk = chunks.get(identifier)
            if chunk is None:
                return False
            if row.get('chunk_text_sha256') and row['chunk_text_sha256'] != chunk_sets.text_hash(chunk):
                return False
            request = requests.get(row.get('call_id'))
            if request and request.get('user') != chunk.get('text'):
                return False
        return True
    return ({key: row for key, row in accepted.items() if active_chunk(row) and authoritative(row, answers)},
            {key: row for key, row in rejected.items() if active_chunk(row) and authoritative(row, answers)})


def decisions(store: Store) -> dict[str, dict[str, Any]]:
    accepted, rejected = current(store)
    return accepted | rejected


def same_decision(previous: dict[str, Any], proposed: dict[str, Any]) -> bool:
    ignored = {'gate_revision', 'harvested_at'}
    return ({key: value for key, value in previous.items() if key not in ignored}
            == {key: value for key, value in proposed.items() if key not in ignored})
