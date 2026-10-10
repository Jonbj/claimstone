"""A durable local-work mandate with reviewable external-work proposals.

The mandate permits the existing local drive to repeat after new evidence
arrives. Version 2 can also plan bounded discovery and acquisition batches,
but never authorizes a network request or a paid model call.
Every local model call is reserved in the operation ledger before execution,
so an interrupted run cannot replenish its allowance by restarting a worker.
"""

from __future__ import annotations

import datetime as dt
import os
import pwd
import time
from typing import Any

from claimstone import operations, scheduler_preview, scope
from claimstone.config import Project
from claimstone.store import Store

LEDGER = 'local_mandates.jsonl'
VERSION = 2


def _rows(store: Store) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in store.read(LEDGER):
        mandate_id = row.get('mandate_id')
        if row.get('version') not in {1, VERSION} or not isinstance(mandate_id, str):
            raise operations.OperationError('invalid local mandate event')
        if row.get('event') == 'enabled':
            mandate = row.get('mandate')
            if (not isinstance(mandate, dict) or
                    mandate.get('version') != row['version'] or
                    operations._digest(mandate) != mandate_id):
                raise operations.OperationError('local mandate digest mismatch')
            if mandate_id in grouped:
                raise operations.OperationError('duplicate local mandate')
            grouped[mandate_id] = [row]
        elif row.get('event') == 'disabled':
            if (mandate_id not in grouped or len(grouped[mandate_id]) != 1 or
                    row['version'] != grouped[mandate_id][0]['version']):
                raise operations.OperationError('invalid local mandate transition')
            grouped[mandate_id].append(row)
        else:
            raise operations.OperationError('unknown local mandate event')
    return grouped


def enable(project: Project, store: Store, flow_id: str, *, extract_model: str,
           review_model: str, max_total_local_calls: int,
           discover_apis: list[str] | None = None,
           discover_hosts: list[str] | None = None,
           acquire_hosts: list[str] | None = None,
           proposal_max_units: int = 10,
           proposal_max_requests_each: int = 3,
           proposal_per_query: int = 25) -> dict[str, Any]:
    """Record local permission and optional bounded, unapproved batch proposals."""
    if (not extract_model or not review_model or extract_model == review_model or
            type(max_total_local_calls) is not int or max_total_local_calls < 0):
        raise operations.OperationError('two different models and a nonnegative total call cap are required')
    if (type(proposal_max_units) is not int or proposal_max_units < 1 or
            type(proposal_max_requests_each) is not int or proposal_max_requests_each < 1 or
            type(proposal_per_query) is not int or proposal_per_query < 1):
        raise operations.OperationError('proposal unit, request and result caps must be positive')
    if bool(discover_apis) != bool(discover_hosts):
        raise operations.OperationError('discovery proposal needs both APIs and exact hosts')
    if discover_apis:
        from claimstone import discover
        unknown = sorted(set(discover_apis) - set(discover.SEARCHERS))
        if unknown:
            raise operations.OperationError(f'unknown discovery API(s): {unknown}')
    discovery_hosts = operations._exact_hosts(discover_hosts) if discover_hosts else []
    acquisition_hosts = operations._exact_hosts(acquire_hosts) if acquire_hosts else []
    if set(discovery_hosts + acquisition_hosts) & set(project.excluded_hosts):
        raise operations.OperationError('proposal host is excluded by the project protocol')
    with store.writer_lock():
        held, selector = operations._flow(project, store, flow_id)
        if discover_apis and selector.round is None:
            raise operations.OperationError('discovery proposals require a named round')
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
            'proposal_policy': {
                'discover_apis': sorted(set(discover_apis or [])),
                'discover_hosts': discovery_hosts,
                'acquire_hosts': acquisition_hosts,
                'max_units': proposal_max_units,
                'max_requests_each': proposal_max_requests_each,
                'per_query': proposal_per_query,
            },
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
        store.append(LEDGER, {'version': rows[0]['version'], 'mandate_id': mandate_id,
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
        pending = []
        events = operations._events(store)
        for batch in store.read(operations.BATCH_LEDGER):
            if batch.get('flow_id') != mandate['flow_id']:
                continue
            awaiting = [operation_id for operation_id in batch.get('operation_ids', [])
                        if operation_id in events and len(events[operation_id]) == 1]
            if awaiting:
                pending.append({'batch_id': batch['batch_id'], 'stage': batch['stage'],
                                'awaiting_approval': len(awaiting),
                                'max_total_requests': batch['max_total_requests']})
        return {'mandate_id': mandate_id,
                'state': 'ENABLED' if len(rows) == 1 else 'DISABLED',
                'flow_id': mandate['flow_id'],
                'reserved_local_calls': reserved,
                'remaining_local_calls': mandate['max_total_local_calls'] - reserved,
                'pending_batches': pending,
                'mandate': mandate}


def _propose(project: Project, store: Store, mandate: dict[str, Any]) -> list[dict[str, Any]]:
    """Freeze the next bounded batches without authorizing any operation."""
    policy = mandate.get('proposal_policy') or {}
    if not policy:
        return []
    existing = {row['batch_id'] for row in store.read(operations.BATCH_LEDGER)}
    out = []
    if policy.get('discover_apis'):
        batch = operations.plan_batch(
            project, store, mandate['flow_id'], 'discover',
            apis=policy['discover_apis'], allowed_hosts=policy['discover_hosts'],
            max_units=policy['max_units'],
            max_requests_each=policy['max_requests_each'],
            per_query=policy['per_query'])
        if batch['operation_ids']:
            out.append({'stage': 'discover', 'batch_id': batch['batch_id'],
                        'units': len(batch['operation_ids']),
                        'max_total_requests': batch['max_total_requests'],
                        'new': batch['batch_id'] not in existing})
    _, selector = operations._flow(project, store, mandate['flow_id'])
    if policy.get('acquire_hosts') and scope.candidates(store, selector):
        batch = operations.plan_batch(
            project, store, mandate['flow_id'], 'acquire',
            allowed_hosts=policy['acquire_hosts'],
            max_units=policy['max_units'],
            max_requests_each=policy['max_requests_each'])
        if batch['operation_ids']:
            out.append({'stage': 'acquire', 'batch_id': batch['batch_id'],
                        'units': len(batch['operation_ids']),
                        'max_total_requests': batch['max_total_requests'],
                        'new': batch['batch_id'] not in existing})
    return out


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
        from claimstone import copy_policy
        copy_policy.materialize_due(project, store, flow_id=mandate['flow_id'])
        result = operations.drive_local(
            project, store, mandate['flow_id'],
            extract_model=mandate['extract_model'],
            review_model=mandate['review_model'],
            max_local_calls=state['remaining_local_calls'],
            authorization_identity=identity,
            authorization_label=mandate_id)
        proposals = _propose(project, store, mandate)
        return result | {'mandate_id': mandate_id,
                         'remaining_total_local_calls': status(store, mandate_id)['remaining_local_calls'],
                         'proposals': proposals}
