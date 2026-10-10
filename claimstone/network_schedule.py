"""Finite, revocable advance authorization for already frozen network batches."""

from __future__ import annotations

import datetime as dt
import os
import pwd
from typing import Any

from claimstone import operations
from claimstone.store import Store

LEDGER = 'network_schedules.jsonl'
VERSION = 1


def _append(store: Store, event: str, schedule_id: str, **fields: Any) -> None:
    body = {'version': VERSION, 'event': event, 'schedule_id': schedule_id, **fields}
    store.append(LEDGER, body | {'event_id': operations._digest(body),
                                 'at': operations._now()})


def _instant(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError) as exc:
        raise operations.OperationError('schedule requires an ISO-8601 UTC instant') from exc
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise operations.OperationError('schedule instant must be UTC')
    return parsed.astimezone(dt.timezone.utc)


def _read(store: Store) -> dict[str, list[dict[str, Any]]]:
    schedules: dict[str, list[dict[str, Any]]] = {}
    for row in store.read(LEDGER):
        schedule_id = row.get('schedule_id')
        body = {k: v for k, v in row.items() if k not in {'event_id', 'at'}}
        if (not isinstance(schedule_id, str) or
                row.get('event_id') != operations._digest(body) or
                row.get('version') != VERSION or
                row.get('event') not in {'planned', 'authorized', 'revoked'}):
            raise operations.OperationError('invalid network schedule event')
        history = schedules.setdefault(str(schedule_id), [])
        if row['event'] == 'planned':
            if history or operations._digest(row['plan']) != schedule_id:
                raise operations.OperationError('invalid network schedule plan')
        elif not history or row['event'] not in (
                {'authorized'} if len(history) == 1 else {'revoked'} if len(history) == 2 else set()):
            raise operations.OperationError('invalid network schedule transition')
        history.append(row)
    return schedules


def plan(store: Store, project: str, entries: list[dict[str, str]], *,
         max_total_requests: int) -> dict[str, Any]:
    """Bind exact batches and UTC windows. This does not permit transport."""
    if (not isinstance(entries, list) or not 1 <= len(entries) <= 32 or
            type(max_total_requests) is not int or max_total_requests < 1):
        raise operations.OperationError('schedule needs 1-32 batches and a positive lifetime ceiling')
    now = dt.datetime.now(dt.timezone.utc)
    with store.writer_lock():
        batches = {row['batch_id']: row for row in store.read(operations.BATCH_LEDGER)}
        events = operations._events(store)
        frozen = []
        seen: set[str] = set()
        seen_operations: set[str] = set()
        total = 0
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {'batch_id', 'not_before', 'expires_at'}:
                raise operations.OperationError('schedule entry requires batch_id and exact UTC window')
            batch_id = entry['batch_id']
            start = _instant(entry['not_before'])
            end = _instant(entry['expires_at'])
            if start >= end or end <= now or end > now + dt.timedelta(days=366):
                raise operations.OperationError('schedule window must be future-bounded within one year')
            batch = batches.get(batch_id)
            if batch_id in seen or batch is None or batch['project'] != project:
                raise operations.OperationError('duplicate, unknown or foreign schedule batch')
            if operations._digest({k: v for k, v in batch.items()
                                   if k not in {'batch_id', 'created_at'}}) != batch_id:
                raise operations.OperationError('altered schedule batch')
            if not batch['operation_ids']:
                raise operations.OperationError('empty schedule batch')
            for operation_id in batch['operation_ids']:
                if operation_id in seen_operations:
                    raise operations.OperationError('operation appears in more than one schedule window')
                rows = events.get(operation_id)
                if rows is None or rows[0]['plan']['flow_id'] != batch['flow_id']:
                    raise operations.OperationError('schedule contains an unknown or mismatched operation')
                seen_operations.add(operation_id)
            total += batch['max_total_requests']
            seen.add(batch_id)
            frozen.append({'batch_id': batch_id, 'operation_ids': batch['operation_ids'],
                           'flow_id': batch['flow_id'], 'stage': batch['stage'],
                           'units': batch['units'],
                           'max_total_requests': batch['max_total_requests'],
                           'not_before': start.isoformat(), 'expires_at': end.isoformat()})
        if total != max_total_requests:
            raise operations.OperationError('lifetime request ceiling differs from frozen batches')
        spec = {'version': VERSION, 'project': project, 'entries': frozen,
                'max_total_requests': total}
        schedule_id = operations._digest(spec)
        if schedule_id not in _read(store):
            if any(len(events[operation_id]) != 1 for operation_id in seen_operations):
                raise operations.OperationError('schedule requires unapproved exact operations')
            _append(store, 'planned', schedule_id, plan=spec)
        return {'schedule_id': schedule_id, 'plan': spec}


def authorize(store: Store, schedule_id: str, *,
              identity: dict[str, Any] | None = None) -> dict[str, Any]:
    """One operator action preapproves the finite schedule; partial crash is resumable."""
    with store.writer_lock():
        history = _read(store).get(schedule_id)
        if not history:
            raise operations.OperationError('unknown schedule')
        if history[-1]['event'] == 'revoked':
            raise operations.OperationError('schedule has been revoked')
        spec = history[0]['plan']
        if identity is None:
            identity = {'uid': os.getuid(), 'login': pwd.getpwuid(os.getuid()).pw_name}
        if len(history) == 1:
            if any(_instant(entry['expires_at']) <= dt.datetime.now(dt.timezone.utc)
                   for entry in spec['entries']):
                raise operations.OperationError('a schedule window expired before authorization')
            events = operations._events(store)
            for entry in spec['entries']:
                for operation_id in entry['operation_ids']:
                    rows = events.get(operation_id)
                    if rows is None or (len(rows) > 1 and
                                        rows[1].get('schedule_id') != schedule_id):
                        raise operations.OperationError('schedule operation was separately authorized')
                    if len(rows) > 1 and rows[1].get('identity') != identity:
                        raise operations.OperationError('partial schedule approval belongs to another operator')
            for entry in spec['entries']:
                for operation_id in entry['operation_ids']:
                    operations.authorize(store, operation_id, batch_id=entry['batch_id'],
                                         identity=identity, schedule_id=schedule_id)
            _append(store, 'authorized', schedule_id, identity=identity)
        return status(store, schedule_id)


def revoke(store: Store, schedule_id: str, *,
           identity: dict[str, Any] | None = None) -> dict[str, Any]:
    with store.writer_lock():
        history = _read(store).get(schedule_id)
        if not history or len(history) < 2:
            raise operations.OperationError('schedule is not authorized')
        if history[-1]['event'] != 'revoked':
            if identity is None:
                identity = {'uid': os.getuid(), 'login': pwd.getpwuid(os.getuid()).pw_name}
            _append(store, 'revoked', schedule_id, identity=identity)
        return status(store, schedule_id)


def status(store: Store, schedule_id: str) -> dict[str, Any]:
    history = _read(store).get(schedule_id)
    if not history:
        raise operations.OperationError('unknown schedule')
    return {'schedule_id': schedule_id, 'state': history[-1]['event'].upper(),
            'plan': history[0]['plan'], 'events': history[1:]}


def due(store: Store, schedule_id: str, operation_id: str) -> bool:
    history = _read(store).get(schedule_id)
    if not history or history[-1]['event'] != 'authorized':
        return False
    now = dt.datetime.now(dt.timezone.utc)
    return any(operation_id in entry['operation_ids'] and
               _instant(entry['not_before']) <= now < _instant(entry['expires_at'])
               for entry in history[0]['plan']['entries'])
