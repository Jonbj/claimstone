"""Finite authorization for legal copies discovered by an approved schedule.

The policy does not fetch. It delegates only exact-host, HTTPS acquisition
plans for previously unknown candidates that an approved discovery query
actually found. The regular operation executor retains robots, redirect,
domain-budget and content gates.
"""

from __future__ import annotations

import datetime as dt
import os
import pwd
import urllib.parse
from typing import Any

from claimstone import flows, net, network_schedule, operations, scope
from claimstone.config import Project
from claimstone.store import Store

LEDGER = 'copy_policies.jsonl'
VERSION = 1


def _append(store: Store, event: str, policy_id: str, **fields: Any) -> None:
    body = {'version': VERSION, 'event': event, 'policy_id': policy_id, **fields}
    store.append(LEDGER, body | {'event_id': operations._digest(body), 'at': operations._now()})


def _read(store: Store) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in store.read(LEDGER):
        body = {key: value for key, value in row.items() if key not in {'event_id', 'at'}}
        policy_id = row.get('policy_id')
        if (not isinstance(policy_id, str) or row.get('event_id') != operations._digest(body)
                or row.get('version') != VERSION):
            raise operations.OperationError('invalid copy policy event')
        history = out.setdefault(policy_id, [])
        event = row.get('event')
        if event == 'planned':
            if history or operations._digest(row.get('policy')) != policy_id:
                raise operations.OperationError('invalid copy policy plan')
        elif event == 'authorized':
            if len(history) != 1:
                raise operations.OperationError('invalid copy policy authorization')
        elif event == 'revoked':
            if len(history) != 2:
                raise operations.OperationError('invalid copy policy revocation')
        else:
            raise operations.OperationError('unknown copy policy event')
        history.append(row)
    return out


def plan(project: Project, store: Store, schedule_id: str, *,
         allowed_hosts: list[str], source_classes: list[str], max_candidates: int,
         max_requests_each: int, not_before: str, expires_at: str) -> dict[str, Any]:
    """Freeze a lifetime ceiling over unknown future candidates; no permission yet."""
    if (type(max_candidates) is not int or not 1 <= max_candidates <= 1000 or
            type(max_requests_each) is not int or not 1 <= max_requests_each <= 20):
        raise operations.OperationError('copy policy requires positive bounded candidates and requests')
    hosts = operations._exact_hosts(allowed_hosts)
    if set(hosts) & set(project.excluded_hosts):
        raise operations.OperationError('copy policy contains an excluded host')
    classes = sorted(set(source_classes))
    if not classes or set(classes) - {item.id for item in project.classes}:
        raise operations.OperationError('copy policy needs declared source classes')
    start = network_schedule._instant(not_before)
    end = network_schedule._instant(expires_at)
    now = dt.datetime.now(dt.timezone.utc)
    if start >= end or end <= now or end > now + dt.timedelta(days=366):
        raise operations.OperationError('copy policy needs a finite future UTC window')
    schedule = network_schedule.status(store, schedule_id)
    if schedule['plan']['project'] != project.name or any(
            entry['stage'] != 'discover' for entry in schedule['plan']['entries']):
        raise operations.OperationError('copy policy requires a discovery schedule for this project')
    query_ids_by_flow: dict[str, dict[str, str]] = {}
    events = operations._events(store)
    for entry in schedule['plan']['entries']:
        flow_id = entry['flow_id']
        operations._flow(project, store, flow_id)
        ids = query_ids_by_flow.setdefault(flow_id, {})
        for operation_id in entry['operation_ids']:
            rows = events.get(operation_id)
            if rows is None or rows[0]['plan']['stage'] != 'discover':
                raise operations.OperationError('schedule has a missing discovery operation')
            ids[rows[0]['plan']['query']['query_id']] = operation_id
    policy = {'version': VERSION, 'project': project.name,
              'schedule_id': schedule_id,
              'flow_ids': list(query_ids_by_flow),
              'query_ids_by_flow': query_ids_by_flow,
              'allowed_hosts': hosts, 'source_classes': classes,
              'max_candidates': max_candidates,
              'max_requests_each': max_requests_each,
              'max_total_requests': max_candidates * max_requests_each,
              'not_before': start.isoformat(), 'expires_at': end.isoformat(),
              'code_sha256': operations._code_identity(),
              'protocol_sha256': flows.protocol_digest(project)}
    policy_id = operations._digest(policy)
    with store.writer_lock():
        if policy_id not in _read(store):
            _append(store, 'planned', policy_id, policy=policy)
    return status(store, policy_id)


def authorize(store: Store, policy_id: str, *,
              identity: dict[str, Any] | None = None) -> dict[str, Any]:
    with store.writer_lock():
        history = _read(store).get(policy_id)
        if history is None:
            raise operations.OperationError('unknown copy policy')
        if history[-1]['event'] == 'revoked':
            raise operations.OperationError('copy policy was revoked')
        if len(history) == 1:
            if network_schedule._instant(history[0]['policy']['expires_at']) <= dt.datetime.now(dt.timezone.utc):
                raise operations.OperationError('copy policy window expired')
            if identity is None:
                identity = {'uid': os.getuid(), 'login': pwd.getpwuid(os.getuid()).pw_name}
            _append(store, 'authorized', policy_id, identity=identity)
        return status(store, policy_id)


def revoke(store: Store, policy_id: str, *,
           identity: dict[str, Any] | None = None) -> dict[str, Any]:
    with store.writer_lock():
        history = _read(store).get(policy_id)
        if history is None or len(history) == 1:
            raise operations.OperationError('copy policy is not authorized')
        if history[-1]['event'] != 'revoked':
            if identity is None:
                identity = {'uid': os.getuid(), 'login': pwd.getpwuid(os.getuid()).pw_name}
            _append(store, 'revoked', policy_id, identity=identity)
        return status(store, policy_id)


def _reservations(store: Store, policy_id: str) -> list[dict[str, Any]]:
    return [rows[0]['plan'] for rows in operations._events(store).values()
            if len(rows) > 1 and rows[1]['event'] == 'authorized' and
            (rows[1].get('identity') or {}).get('copy_policy_id') == policy_id]


def status(store: Store, policy_id: str) -> dict[str, Any]:
    with store.writer_lock():
        history = _read(store).get(policy_id)
        if history is None:
            raise operations.OperationError('unknown copy policy')
        spec = history[0]['policy']
        reserved = _reservations(store, policy_id)
        if (len(reserved) > spec['max_candidates'] or
                sum(item['max_network_requests'] for item in reserved) > spec['max_total_requests']):
            raise operations.OperationError('copy policy reservations exceed the ceiling')
        return {'policy_id': policy_id, 'state': history[-1]['event'].upper(),
                'policy': spec, 'reserved_candidates': len(reserved),
                'remaining_candidates': spec['max_candidates'] - len(reserved),
                'reserved_requests': sum(item['max_network_requests'] for item in reserved)}


def due(store: Store, policy_id: str) -> bool:
    history = _read(store).get(policy_id)
    if not history or history[-1]['event'] != 'authorized':
        return False
    spec = history[0]['policy']
    now = dt.datetime.now(dt.timezone.utc)
    if not network_schedule._instant(spec['not_before']) <= now < network_schedule._instant(spec['expires_at']):
        return False
    return network_schedule.status(store, spec['schedule_id'])['state'] == 'AUTHORIZED'


def materialize_due(project: Project, store: Store, *, flow_id: str | None = None) -> list[str]:
    """Plan and authorize only matching hits, under one lock and lifetime cap."""
    made: list[str] = []
    with store.writer_lock():
        policies = _read(store)
        if not any(history[-1]['event'] == 'authorized' for history in policies.values()):
            return made
        operation_events = operations._events(store)
        active_keys = {rows[0]['plan']['candidate_key'] for rows in operation_events.values()
                       if len(rows) > 1 and rows[0]['plan']['stage'] == 'acquire' and
                       rows[-1]['event'] in {'authorized', 'started', 'unit_completed'}}
        queries = store.latest_by('queries.jsonl', 'query_id')
        hits = list(store.read('query_hits.jsonl'))
        for policy_id, history in policies.items():
            if history[-1]['event'] != 'authorized' or not due(store, policy_id):
                continue
            spec = history[0]['policy']
            reserved = _reservations(store, policy_id)
            if (len(reserved) > spec['max_candidates'] or
                    sum(row['max_network_requests'] for row in reserved) > spec['max_total_requests']):
                raise operations.OperationError('copy policy reservations exceed the ceiling')
            if spec['project'] != project.name or spec['code_sha256'] != operations._code_identity() or spec['protocol_sha256'] != flows.protocol_digest(project):
                continue
            used = {row['candidate_key'] for row in reserved}
            remaining = spec['max_candidates'] - len(reserved)
            if remaining <= 0:
                continue
            for selected_flow in spec['flow_ids']:
                if flow_id is not None and selected_flow != flow_id:
                    continue
                try:
                    _, selector = operations._flow(project, store, selected_flow)
                except operations.OperationError:
                    continue
                allowed_queries = spec['query_ids_by_flow'][selected_flow]
                eligible_hits: dict[str, set[tuple[Any, Any, Any, Any]]] = {}
                for hit in hits:
                    query_id = hit.get('query_id')
                    if (hit.get('round') != selector.round or
                            hit.get('population_in_scope') is not True or
                            hit.get('query_hit_version') != 2 or
                            query_id not in allowed_queries or
                            queries.get(query_id, {}).get('ok') is not True or
                            queries[query_id].get('campaign') != allowed_queries[query_id] or
                            operation_events.get(allowed_queries[query_id], [{}])[-1].get('event') != 'completed'):
                        continue
                    eligible_hits.setdefault(str(hit['candidate_key']), set()).add(
                        (hit.get('url'), hit.get('title'), hit.get('doi'),
                         hit.get('source_class')))
                for key, candidate in sorted(scope.candidates(store, selector).items()):
                    if remaining <= 0:
                        break
                    url = str(candidate.get('url') or '')
                    try:
                        parsed = urllib.parse.urlsplit(url)
                        host = net.host_of(url)
                    except ValueError:
                        continue
                    fingerprint = (url, candidate.get('title'), candidate.get('doi'),
                                   candidate.get('source_class'))
                    if (fingerprint not in eligible_hits.get(key, set()) or
                            key in used or key in active_keys or
                            candidate.get('source_class') not in spec['source_classes'] or
                            candidate.get('possible_duplicate_of') or
                            parsed.scheme != 'https' or parsed.username is not None or
                            parsed.password is not None or
                            host not in spec['allowed_hosts']):
                        continue
                    if not due(store, policy_id):
                        break
                    try:
                        frozen = operations.plan(project, store, selected_flow, 'acquire',
                                                 candidate_key=key,
                                                 allowed_hosts=spec['allowed_hosts'],
                                                 max_requests=spec['max_requests_each'],
                                                 use_apis=False)
                    except operations.OperationError:
                        continue
                    operation_id = operations._digest(frozen)
                    if len(operations._events(store)[operation_id]) > 1:
                        continue
                    identity = dict(history[1]['identity']) | {'copy_policy_id': policy_id}
                    operations.authorize(store, operation_id, identity=identity)
                    made.append(operation_id)
                    used.add(key)
                    active_keys.add(key)
                    remaining -= 1
    return made
