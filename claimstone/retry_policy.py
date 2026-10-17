"""Finite authorization for delayed retries of transient acquisition failures."""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import pwd
from typing import Any
from urllib.parse import urlsplit

from claimstone import acquire, flows, net, network_schedule, operations, scope
from claimstone.config import Project
from claimstone.store import Store

LEDGER = 'retry_policies.jsonl'
VERSION = 1


def _append(store: Store, event: str, policy_id: str, **fields: Any) -> None:
    body = {'version': VERSION, 'event': event, 'policy_id': policy_id, **fields}
    store.append(LEDGER, body | {'event_id': operations._digest(body), 'at': operations._now()})


def _read(store: Store) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in store.read(LEDGER):
        body = {key: value for key, value in row.items() if key not in {'event_id', 'at'}}
        policy_id = row.get('policy_id')
        if (not isinstance(policy_id, str) or row.get('version') != VERSION or
                row.get('event_id') != operations._digest(body)):
            raise operations.OperationError('invalid retry policy event')
        try:
            network_schedule._instant(row['at'])
        except (KeyError, operations.OperationError) as exc:
            raise operations.OperationError('invalid retry policy timestamp') from exc
        history = out.setdefault(policy_id, [])
        event = row.get('event')
        if event == 'planned':
            if history or operations._digest(row.get('policy')) != policy_id:
                raise operations.OperationError('invalid retry policy plan')
        elif event == 'authorized':
            if len(history) != 1 or not isinstance(row.get('identity'), dict):
                raise operations.OperationError('invalid retry policy authorization')
        elif event == 'revoked':
            if len(history) != 2 or not isinstance(row.get('identity'), dict):
                raise operations.OperationError('invalid retry policy revocation')
        else:
            raise operations.OperationError('unknown retry policy event')
        history.append(row)
    return out


def plan(project: Project, store: Store, flow_id: str, *, allowed_hosts: list[str],
         max_retries: int, max_attempts_each: int, max_requests_each: int,
         use_apis: bool, base_delay_hours: int, max_delay_hours: int,
         expires_at: str) -> dict[str, Any]:
    bounds = ((max_retries, 1, 200), (max_attempts_each, 1, 5),
              (max_requests_each, 1, 20), (base_delay_hours, 1, 72),
              (max_delay_hours, base_delay_hours, 168))
    if any(type(value) is not int or not low <= value <= high for value, low, high in bounds):
        raise operations.OperationError('retry policy limits are outside their bounds')
    if type(use_apis) is not bool:
        raise operations.OperationError('use_apis must be boolean')
    if (not isinstance(allowed_hosts, list) or
            any(not isinstance(host, str) for host in allowed_hosts)):
        raise operations.OperationError('retry policy needs exact hostnames')
    hosts = operations._exact_hosts(allowed_hosts)
    if any(host == excluded or host.endswith('.' + excluded)
           for host in hosts for excluded in project.excluded_hosts):
        raise operations.OperationError('retry policy contains an excluded host')
    if use_apis and not {'api.unpaywall.org', 'api.openalex.org'} <= set(hosts):
        raise operations.OperationError('retry policy requires both resolver hosts')
    start = dt.datetime.now(dt.timezone.utc)
    end = network_schedule._instant(expires_at)
    if end <= start or end > start + dt.timedelta(days=366):
        raise operations.OperationError('retry policy needs a finite future UTC window')
    _, selector = operations._flow(project, store, flow_id)
    if selector.round is None:
        raise operations.OperationError('retry policy requires a named round')
    policy = {'version': VERSION, 'project': project.name, 'flow_id': flow_id,
              'selector': selector.as_dict(), 'allowed_hosts': hosts,
              'max_retries': max_retries, 'max_attempts_each': max_attempts_each,
              'max_requests_each': max_requests_each,
              'max_total_requests': max_retries * max_requests_each,
              'use_apis': use_apis, 'base_delay_hours': base_delay_hours,
              'max_delay_hours': max_delay_hours, 'not_before': start.isoformat(),
              'expires_at': end.isoformat(), 'code_sha256': operations._code_identity(),
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
            raise operations.OperationError('unknown retry policy')
        if history[-1]['event'] == 'revoked':
            raise operations.OperationError('retry policy was revoked')
        if len(history) == 1:
            if network_schedule._instant(history[0]['policy']['expires_at']) <= dt.datetime.now(dt.timezone.utc):
                raise operations.OperationError('retry policy window expired')
            identity = identity or {'uid': os.getuid(), 'login': pwd.getpwuid(os.getuid()).pw_name}
            _append(store, 'authorized', policy_id, identity=identity)
        return status(store, policy_id)


def revoke(store: Store, policy_id: str, *,
           identity: dict[str, Any] | None = None) -> dict[str, Any]:
    with store.writer_lock():
        history = _read(store).get(policy_id)
        if history is None or len(history) == 1:
            raise operations.OperationError('retry policy is not authorized')
        if history[-1]['event'] != 'revoked':
            identity = identity or {'uid': os.getuid(), 'login': pwd.getpwuid(os.getuid()).pw_name}
            _append(store, 'revoked', policy_id, identity=identity)
        return status(store, policy_id)


def _reservations(store: Store, policy_id: str) -> list[dict[str, Any]]:
    return [rows[0]['plan'] for rows in operations._events(store).values()
            if len(rows) > 1 and rows[1]['event'] == 'authorized' and
            (rows[1].get('identity') or {}).get('retry_policy_id') == policy_id]


def status(store: Store, policy_id: str) -> dict[str, Any]:
    with store.writer_lock():
        history = _read(store).get(policy_id)
        if history is None:
            raise operations.OperationError('unknown retry policy')
        spec = history[0]['policy']
        reserved = _reservations(store, policy_id)
        requests = sum(row['max_network_requests'] for row in reserved)
        by_candidate: dict[str, int] = {}
        for row in reserved:
            if (row['stage'] != 'acquire' or row['flow_id'] != spec['flow_id'] or
                    row['max_network_requests'] != spec['max_requests_each'] or
                    row['allowed_hosts'] != spec['allowed_hosts'] or
                    row['use_apis'] != spec['use_apis'] or row['retry_classes']):
                raise operations.OperationError('retry policy reservation outside flow')
            key = row['candidate_key']
            by_candidate[key] = by_candidate.get(key, 0) + 1
        if (len(reserved) > spec['max_retries'] or requests > spec['max_total_requests'] or
                any(n > spec['max_attempts_each'] for n in by_candidate.values())):
            raise operations.OperationError('retry policy reservations exceed the ceiling')
        return {'policy_id': policy_id, 'state': history[-1]['event'].upper(),
                'policy': spec, 'reserved_retries': len(reserved),
                'remaining_retries': spec['max_retries'] - len(reserved),
                'reserved_requests': requests, 'events': history[1:]}


def due(store: Store, policy_id: str) -> bool:
    history = _read(store).get(policy_id)
    if not history or history[-1]['event'] != 'authorized':
        return False
    spec = history[0]['policy']
    now = dt.datetime.now(dt.timezone.utc)
    return network_schedule._instant(spec['not_before']) <= now < network_schedule._instant(spec['expires_at'])


def next_earliest(policy: dict[str, Any], policy_id: str, candidate_key: str,
                  n: int, previous: dict[str, Any]) -> dt.datetime:
    """Compute the deterministic delay from the latest acquisition, without stored timer state."""
    if type(n) is not int or n < 1:
        raise ValueError('retry number must be positive')
    nominal = min(policy['max_delay_hours'], policy['base_delay_hours'] * 2 ** (n - 1))
    seed = f'{policy_id}|{candidate_key}|{n}'.encode('utf-8')
    u = int.from_bytes(hashlib.sha256(seed).digest()[:8], 'big') / 2 ** 64
    delay_s = (nominal / 2 + u * nominal / 2) * 3600
    attempts = previous.get('attempts') or []
    retry_after = max((a.get('retry_after_s', 0) for a in attempts if isinstance(a, dict)), default=0)
    fetched = network_schedule._instant(previous['fetched_at'])
    return fetched + dt.timedelta(seconds=max(delay_s, retry_after))


def materialize_due(project: Project, store: Store, *, flow_id: str | None = None) -> list[str]:
    made: list[str] = []
    with store.writer_lock():
        policies = _read(store)
        if not any(h[-1]['event'] == 'authorized' for h in policies.values()):
            return made
        events = operations._events(store)
        active = {rows[0]['plan']['candidate_key'] for rows in events.values()
                  if len(rows) > 1 and rows[0]['plan']['stage'] == 'acquire' and
                  rows[-1]['event'] in {'authorized', 'started', 'unit_completed'}}
        acquisitions = store.latest_by('acquisitions.jsonl', 'candidate_key')
        for policy_id, history in policies.items():
            if history[-1]['event'] != 'authorized' or not due(store, policy_id):
                continue
            spec = history[0]['policy']
            if (spec['project'] != project.name or
                    flow_id is not None and spec['flow_id'] != flow_id or
                    spec['code_sha256'] != operations._code_identity() or
                    spec['protocol_sha256'] != flows.protocol_digest(project)):
                continue
            try:
                _, selector = operations._flow(project, store, spec['flow_id'])
            except operations.OperationError:
                continue
            if selector.as_dict() != spec['selector']:
                continue
            state = status(store, policy_id)
            reserved = _reservations(store, policy_id)
            counts: dict[str, int] = {}
            for row in reserved:
                key = row['candidate_key']
                counts[key] = counts.get(key, 0) + 1
            remaining = state['remaining_retries']
            requests = state['reserved_requests']
            for key, candidate in sorted(scope.candidates(store, selector).items()):
                if remaining <= 0:
                    break
                previous = acquisitions.get(key)
                if (previous is None or previous.get('acquired') or key in active or
                        counts.get(key, 0) >= spec['max_attempts_each'] or
                        requests + spec['max_requests_each'] > spec['max_total_requests'] or
                        not acquire.should_attempt(previous, retry_classes=frozenset(), retry_after_s=0)):
                    continue
                try:
                    parsed = urlsplit(str(candidate.get('url') or ''))
                    host = net.host_of(str(candidate.get('url') or ''))
                except ValueError:
                    continue
                if (parsed.scheme not in {'http', 'https'} or parsed.username or parsed.password or
                        host not in spec['allowed_hosts']):
                    continue
                if net.recorded_host_failures(store, host) >= net.Fetcher.max_403_per_host:
                    continue
                if dt.datetime.now(dt.timezone.utc) < next_earliest(
                        spec, policy_id, key, counts.get(key, 0) + 1, previous):
                    continue
                try:
                    frozen = operations.plan(project, store, spec['flow_id'], 'acquire',
                                             candidate_key=key, allowed_hosts=spec['allowed_hosts'],
                                             max_requests=spec['max_requests_each'],
                                             use_apis=spec['use_apis'], retry_after_s=0)
                except operations.OperationError:
                    continue
                operation_id = operations._digest(frozen)
                if len(operations._events(store)[operation_id]) > 1:
                    continue
                operations.authorize(store, operation_id,
                                     identity=dict(history[1]['identity']) | {'retry_policy_id': policy_id})
                made.append(operation_id)
                active.add(key)
                counts[key] = counts.get(key, 0) + 1
                remaining -= 1
                requests += spec['max_requests_each']
    return made
