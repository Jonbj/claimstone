"""A durable, bounded local-work mandate for one research flow.

The mandate permits the existing local drive to repeat after new evidence
arrives. It never plans or authorizes a network request or a paid model call.
Every local model call is reserved in the operation ledger before execution,
so an interrupted run cannot replenish its allowance by restarting a worker.
"""

from __future__ import annotations

import datetime as dt
import os
import pwd
import time
from typing import Any

from claimstone import operations, scheduler_preview
from claimstone.config import Project
from claimstone.store import Store

LEDGER = 'local_mandates.jsonl'
VERSION = 1


def _rows(store: Store) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in store.read(LEDGER):
        mandate_id = row.get('mandate_id')
        if row.get('version') != VERSION or not isinstance(mandate_id, str):
            raise operations.OperationError('invalid local mandate event')
        if row.get('event') == 'enabled':
            mandate = row.get('mandate')
            if not isinstance(mandate, dict) or operations._digest(mandate) != mandate_id:
                raise operations.OperationError('local mandate digest mismatch')
            if mandate_id in grouped:
                raise operations.OperationError('duplicate local mandate')
            grouped[mandate_id] = [row]
        elif row.get('event') == 'disabled':
            if mandate_id not in grouped or len(grouped[mandate_id]) != 1:
                raise operations.OperationError('invalid local mandate transition')
            grouped[mandate_id].append(row)
        else:
            raise operations.OperationError('unknown local mandate event')
    return grouped


def enable(project: Project, store: Store, flow_id: str, *, extract_model: str,
           review_model: str, max_total_local_calls: int) -> dict[str, Any]:
    """Record one operator's standing permission for bounded local work."""
    if (not extract_model or not review_model or extract_model == review_model or
            type(max_total_local_calls) is not int or max_total_local_calls < 0):
        raise operations.OperationError('two different models and a nonnegative total call cap are required')
    with store.writer_lock():
        held, _ = operations._flow(project, store, flow_id)
        preview = scheduler_preview.preview(project, store, flow_id)
        if preview['state'] == 'BLOCKED':
            raise operations.OperationError(f'flow preview blocked: {preview["blockers"]}')
        for rows in _rows(store).values():
            if len(rows) == 1 and rows[0]['mandate']['flow_id'] == flow_id:
                raise operations.OperationError('flow already has an active local mandate')
        identity = {'uid': os.getuid(), 'login': pwd.getpwuid(os.getuid()).pw_name}
        mandate = {
            'version': VERSION, 'project': project.name, 'flow_id': flow_id,
            'protocol_sha256': held['binding']['protocol_sha256'],
            'code_sha256': operations._code_identity(),
            'extract_model': extract_model, 'review_model': review_model,
            'max_total_local_calls': max_total_local_calls,
            'authorized_by': identity, 'created_ns': time.time_ns(),
        }
        mandate_id = operations._digest(mandate)
        store.append(LEDGER, {'version': VERSION, 'mandate_id': mandate_id,
                              'event': 'enabled', 'mandate': mandate,
                              'at': dt.datetime.now(dt.timezone.utc).isoformat()})
        return {'mandate_id': mandate_id, 'mandate': mandate}


def disable(store: Store, mandate_id: str) -> dict[str, Any]:
    with store.writer_lock():
        rows = _rows(store).get(mandate_id)
        if rows is None:
            raise operations.OperationError('unknown local mandate')
        if len(rows) == 2:
            return {'mandate_id': mandate_id, 'state': 'DISABLED'}
        store.append(LEDGER, {'version': VERSION, 'mandate_id': mandate_id,
                              'event': 'disabled', 'by': {
                                  'uid': os.getuid(),
                                  'login': pwd.getpwuid(os.getuid()).pw_name},
                              'at': dt.datetime.now(dt.timezone.utc).isoformat()})
        return {'mandate_id': mandate_id, 'state': 'DISABLED'}


def _reserved(store: Store, mandate_id: str) -> int:
    total = 0
    for rows in operations._events(store).values():
        if (len(rows) > 1 and rows[1]['event'] == 'authorized' and
                (rows[1].get('identity') or {}).get('mandate_id') == mandate_id and
                rows[0]['plan']['stage'] in {'extract-drain', 'review-drain'}):
            total += rows[0]['plan']['max_model_calls']
    return total


def status(store: Store, mandate_id: str) -> dict[str, Any]:
    with store.writer_lock():
        rows = _rows(store).get(mandate_id)
        if rows is None:
            raise operations.OperationError('unknown local mandate')
        mandate = rows[0]['mandate']
        reserved = _reserved(store, mandate_id)
        if reserved > mandate['max_total_local_calls']:
            raise operations.OperationError('local mandate reservations exceed ceiling')
        return {'mandate_id': mandate_id,
                'state': 'ENABLED' if len(rows) == 1 else 'DISABLED',
                'flow_id': mandate['flow_id'],
                'reserved_local_calls': reserved,
                'remaining_local_calls': mandate['max_total_local_calls'] - reserved,
                'mandate': mandate}


def tick(project: Project, store: Store, mandate_id: str) -> dict[str, Any]:
    """Advance one flow under the original mandate and cumulative call cap."""
    with store.writer_lock():
        state = status(store, mandate_id)
        if state['state'] != 'ENABLED':
            return state | {'stopped_reason': 'MANDATE_DISABLED', 'steps': []}
        mandate = state['mandate']
        if mandate['project'] != project.name:
            raise operations.OperationError('local mandate belongs to another project')
        held, _ = operations._flow(project, store, mandate['flow_id'])
        if (held['binding']['protocol_sha256'] != mandate['protocol_sha256'] or
                operations._code_identity() != mandate['code_sha256']):
            raise operations.OperationError('protocol or code changed; renew the local mandate')
        identity = dict(mandate['authorized_by']) | {'mandate_id': mandate_id}
        result = operations.drive_local(
            project, store, mandate['flow_id'],
            extract_model=mandate['extract_model'],
            review_model=mandate['review_model'],
            max_local_calls=state['remaining_local_calls'],
            authorization_identity=identity,
            authorization_label=mandate_id)
        return result | {'mandate_id': mandate_id,
                         'remaining_total_local_calls': status(store, mandate_id)['remaining_local_calls']}
