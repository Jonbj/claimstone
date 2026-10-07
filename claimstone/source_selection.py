"""Append-only observations about source identity and question relevance.

These ledgers are deliberately outside admission: an AI observation can order work,
but neither an exclusion nor an inclusion here changes a round denominator.
"""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import hashlib
import json
from typing import Any, Iterable

from claimstone.store import Store

SOURCE_SELECTION_VERSION = 1
IDENTITY_RELATION_VERSION = 2
SCREENING_LEDGER = 'source_screening.jsonl'
IDENTITY_LEDGER = 'source_identity.jsonl'
DECISIONS = frozenset({'INCLUDE', 'EXCLUDE', 'UNCERTAIN'})
ROLES = frozenset({'DIRECT_CANDIDATE', 'CONTEXT', 'NOT_DIRECT', 'UNRESOLVED'})


def _digest(record: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def identified(record: dict[str, Any], id_field: str) -> dict[str, Any]:
    """Content identity includes every observation and its explicit supersession link."""
    base = {key: value for key, value in record.items() if key != id_field}
    return {**base, id_field: _digest(base)}


def _valid_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def validate_screening(row: dict[str, Any]) -> None:
    if row.get('selection_version') != SOURCE_SELECTION_VERSION:
        raise ValueError('unknown source-selection record version')
    if not all(isinstance(row.get(k), str) and row[k] for k in
               ('scope_id', 'question_id', 'candidate_key', 'source_class', 'reason', 'assessed_by')):
        raise ValueError('screening observation lacks scope, identity, class or reason')
    if not _valid_digest(row.get('registry_sha256')) or not _valid_digest(row.get('input_sha256')):
        raise ValueError('screening observation lacks frozen input/registry hashes')
    if row.get('assessment_status') != 'AI_PROVISIONAL' or row.get('decision') not in DECISIONS:
        raise ValueError('this ledger currently accepts only provisional AI screening')
    role = row.get('role')
    if role not in ROLES or (row['decision'] == 'INCLUDE' and role != 'DIRECT_CANDIDATE') or \
            (row['decision'] == 'UNCERTAIN' and role != 'UNRESOLVED') or \
            (row['decision'] == 'EXCLUDE' and role not in {'CONTEXT', 'NOT_DIRECT'}):
        raise ValueError('screening decision and role disagree')
    if row.get('screening_level') not in {'ABSTRACT', 'FULLTEXT'}:
        raise ValueError('screening level must be explicit')
    if not isinstance(row.get('criterion_ids'), list) or not row['criterion_ids'] or any(
            not isinstance(criterion, str) or not criterion for criterion in row['criterion_ids']):
        raise ValueError('screening criteria are missing')
    evidence = row.get('evidence')
    if not isinstance(evidence, list) or not evidence or any(
            not isinstance(e, dict) or not isinstance(e.get('quote'), str) or not e['quote']
            or not _valid_digest(e.get('text_sha256')) or
            not isinstance(e.get('locator'), str) or not e['locator'] for e in evidence):
        raise ValueError('screening evidence lacks quote, text hash or locator')
    if row.get('supersedes') is not None and not _valid_digest(row['supersedes']):
        raise ValueError('invalid screening supersession')
    if row.get('assessment_id') != _digest({k: v for k, v in row.items() if k != 'assessment_id'}):
        raise ValueError('screening observation identity does not match its content')


def validate_identity(row: dict[str, Any]) -> None:
    version = row.get('selection_version')
    if version not in {SOURCE_SELECTION_VERSION, IDENTITY_RELATION_VERSION}:
        raise ValueError('unknown source-selection identity version')
    if not all(isinstance(row.get(k), str) and row[k] for k in
               ('scope_id', 'candidate_key', 'source_class', 'status', 'reason', 'assessed_by')):
        raise ValueError('identity observation lacks scope, source or reason')
    if row['status'] not in {'POSSIBLE_VERSION', 'POSSIBLE_SUPPLEMENT', 'CONFLICT',
                             'UNVERIFIED', 'VERIFIED_SAME_WORK', 'DISTINCT_WORKS'}:
        raise ValueError('identity observations cannot silently merge works')
    if row['status'] == 'VERIFIED_SAME_WORK' and not row.get('canonical_work_key'):
        raise ValueError('verified work relation needs an explicit canonical key')
    if not _valid_digest(row.get('metadata_sha256')) or not _valid_digest(row.get('copy_sha256')):
        raise ValueError('identity observation lacks metadata/copy hashes')
    if version == IDENTITY_RELATION_VERSION:
        kind = row.get('related_kind')
        related = row.get('related_key')
        if kind not in {'CANDIDATE', 'HELD_COPY'} or not isinstance(related, str) or not related:
            raise ValueError('identity relation needs an explicit counterpart')
        if kind == 'CANDIDATE' and related == row['candidate_key']:
            raise ValueError('identity relation cannot point a candidate to itself')
        if kind == 'HELD_COPY' and related != row['copy_sha256']:
            raise ValueError('held-copy relation must name its exact copy hash')
    if not isinstance(row.get('observations'), list) or len(row['observations']) < 2 or \
            any(not isinstance(o, str) or not o for o in row['observations']) or \
            len(set(row['observations'])) != len(row['observations']):
        raise ValueError('identity assessment needs located observations')
    if row.get('supersedes') is not None and not _valid_digest(row['supersedes']):
        raise ValueError('invalid identity supersession')
    if row.get('observation_id') != _digest({k: v for k, v in row.items() if k != 'observation_id'}):
        raise ValueError('identity observation identity does not match its content')


def _key(row: dict[str, Any], *, identity: bool) -> tuple[str, ...]:
    return ((row['scope_id'], row['candidate_key'],
             row.get('related_kind', 'HELD_COPY'), row.get('related_key', row['copy_sha256']))
            if identity else
            (row['scope_id'], row['question_id'], row['candidate_key']))


def _replay(existing: Iterable[dict[str, Any]], proposed: Iterable[dict[str, Any]], *,
            identity: bool) -> tuple[dict[tuple[str, ...], dict[str, Any]], list[dict[str, Any]]]:
    validator = validate_identity if identity else validate_screening
    id_field = 'observation_id' if identity else 'assessment_id'
    latest: dict[tuple[str, ...], dict[str, Any]] = {}
    seen: set[str] = set()
    for row in existing:
        validator(row)
        key = _key(row, identity=identity)
        if row[id_field] in seen:
            raise ValueError('duplicate existing observation id')
        previous = latest.get(key)
        if row.get('supersedes') != (previous[id_field] if previous else None):
            raise ValueError('existing source-selection supersession chain is broken')
        if previous and not identity:
            _validate_screening_transition(previous, row)
        seen.add(row[id_field])
        latest[key] = row
    new = []
    for row in proposed:
        validator(row)
        if row[id_field] in seen:
            continue
        key = _key(row, identity=identity)
        previous = latest.get(key)
        if row.get('supersedes') != (previous[id_field] if previous else None):
            raise ValueError('new source-selection row does not supersede current observation')
        if previous and not identity:
            _validate_screening_transition(previous, row)
        latest[key] = row
        seen.add(row[id_field])
        new.append(row)
    return latest, new


def _validate_screening_transition(previous: dict[str, Any], row: dict[str, Any]) -> None:
    if previous['registry_sha256'] != row['registry_sha256'] or \
            previous['source_class'] != row['source_class']:
        raise ValueError('screening registry or source class changed within one scope')
    if previous['screening_level'] == 'FULLTEXT' and row['screening_level'] == 'ABSTRACT':
        raise ValueError('screening evidence level regressed within one scope')


def append_observations(store: Store, screening: list[dict[str, Any]],
                        identity: list[dict[str, Any]], *, scope_id: str,
                        question_id: str, inventory_keys: set[str]) -> dict[str, int]:
    """Validate and append under one project lock, with a frozen inventory boundary."""
    if not scope_id or not question_id or not isinstance(inventory_keys, set):
        raise ValueError('scope, question and inventory are required for append')
    if any(row.get('scope_id') != scope_id or row.get('question_id') != question_id or
           row.get('candidate_key') not in inventory_keys for row in screening) or any(
           row.get('scope_id') != scope_id or row.get('candidate_key') not in inventory_keys or
           (row.get('related_kind') == 'CANDIDATE' and
            row.get('related_key') not in inventory_keys)
           for row in identity):
        raise ValueError('proposed source-selection row is outside the frozen scope or inventory')
    with _writer_lock(store):
        current_screening, new_screening = _replay(
            store.read(SCREENING_LEDGER), screening, identity=False)
        current_identity, new_identity = _replay(
            store.read(IDENTITY_LEDGER), identity, identity=True)
        if any(key[0] == scope_id and key[1] == question_id and key[2] not in inventory_keys
               for key in current_screening) or any(
               key[0] == scope_id and (key[1] not in inventory_keys or
                                      (key[2] == 'CANDIDATE' and
                                       key[3] not in inventory_keys))
               for key in current_identity):
            raise ValueError('existing source-selection row is outside the frozen inventory')
        for row in new_screening:
            store.append(SCREENING_LEDGER, row)
        for row in new_identity:
            store.append(IDENTITY_LEDGER, row)
        return {'screening_rows_written': len(new_screening),
                'identity_rows_written': len(new_identity)}


@contextmanager
def _writer_lock(store: Store):
    with store.writer_lock():
        yield


def preview(store: Store, scope_id: str, question_id: str, inventory_keys: set[str],
            screening: list[dict[str, Any]] = (), identity: list[dict[str, Any]] = ()) -> dict[str, Any]:
    all_screening, new_screening = _replay(store.read(SCREENING_LEDGER), screening, identity=False)
    all_identity, new_identity = _replay(store.read(IDENTITY_LEDGER), identity, identity=True)
    latest = {key[2]: row for key, row in all_screening.items()
              if key[0] == scope_id and key[1] == question_id}
    if not set(latest) <= inventory_keys:
        raise ValueError('screened identity is outside the frozen inventory')
    roles = Counter(row['role'] for row in latest.values())
    pending = sorted(key for key in inventory_keys if key not in latest or
                     latest[key]['assessment_status'] == 'AI_PROVISIONAL' or
                     latest[key]['decision'] == 'UNCERTAIN' or
                     latest[key]['source_class'] == 'UNCLASSIFIED')
    identity_rows = {key: row for key, row in all_identity.items() if key[0] == scope_id}
    if any(key[1] not in inventory_keys or
           (key[2] == 'CANDIDATE' and key[3] not in inventory_keys)
           for key in identity_rows):
        raise ValueError('identity observation is outside the frozen inventory')
    return {
        'scope_id': scope_id, 'question_id': question_id, 'inventory_count': len(inventory_keys),
        'screened_count': len(latest), 'unobserved_count': len(inventory_keys - set(latest)),
        'provisional_direct_candidates': roles['DIRECT_CANDIDATE'],
        'provisional_not_direct': roles['NOT_DIRECT'],
        'provisional_context': roles['CONTEXT'],
        'provisional_uncertain': roles['UNRESOLVED'],
        'identity_observations': len(identity_rows),
        'new_screening_rows': len(new_screening), 'new_identity_rows': len(new_identity),
        'pending_keys': pending, 'cohort_closed': False, 'admitted_candidates': 0,
        'acquisition_rate': None, 'literature_recall': None, 'screening_accuracy': None,
    }
