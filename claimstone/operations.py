"""Append-only, single-flow scheduler operations with bounded work units.

An operation is one bounded stage transaction. Planning makes no external
request and an OS-authenticated CLI operator authorizes its exact plan before
execution. Model calls, single-candidate acquisition and one-query discovery
have executors. Paid calls require a persistent budget reservation.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import pwd
import re
from typing import Any

from claimstone import flows, scheduler_preview, scope
from claimstone.config import Project
from claimstone.store import Store

OPERATIONS_VERSION = 3
LEDGER = 'operations.jsonl'
BATCH_LEDGER = 'operation_batches.jsonl'
STAGE_INPUTS = {
    'normalize': ('candidates.jsonl', 'acquisitions.jsonl'),
    'extract-build': ('candidates.jsonl', 'documents.jsonl', 'chunks.jsonl'),
    'review-build': ('candidates.jsonl', 'documents.jsonl', 'chunks.jsonl',
                     'claims.jsonl', 'reviews.jsonl'),
    'synthesize': ('candidates.jsonl', 'acquisitions.jsonl', 'documents.jsonl',
                   'chunks.jsonl', 'claims.jsonl', 'rejections.jsonl', 'reviews.jsonl'),
    'extract-drain': ('candidates.jsonl',),
    'review-drain': ('candidates.jsonl',),
    'extract-harvest': ('candidates.jsonl',),
    'review-harvest': ('candidates.jsonl',),
    'acquire': (),
    'discover': ('populations.jsonl',),
}


class OperationError(ValueError):
    pass


class _IdentityCheckedRunner:
    """A local reader must report the exact model the plan named."""

    def __init__(self, runner: Any):
        self.runner = runner
        self.name = runner.name
        self.model = runner.model
        self.max_concurrency = runner.max_concurrency
        self.min_interval_s = runner.min_interval_s

    def harness_version(self) -> str:
        return self.runner.harness_version() + ' strict-model-report=1'

    def run(self, request: dict[str, Any]) -> Any:
        answer = self.runner.run(request)
        if not answer.failure_class and answer.model != self.model:
            answer.failure_class = 'MODEL_IDENTITY_MISMATCH'
            answer.detail = (f'planned {self.model!r}, backend reported '
                             f'{answer.model!r}')
        return answer


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def _code_identity() -> str:
    root = pathlib.Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*.py')):
        name = str(path.relative_to(root))
        data = path.read_bytes()
        digest.update(name.encode('utf-8') + b'\0' + data + b'\0')
    return digest.hexdigest()


def _file_sha(path: pathlib.Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _exact_hosts(values: list[str] | None) -> list[str]:
    hosts = sorted(set(values or []))
    if not hosts or any(not re.fullmatch(r'[a-z0-9][a-z0-9.-]*[a-z0-9]|[a-z0-9]', host)
                        or '..' in host for host in hosts):
        raise OperationError('exact lowercase hostnames without ports or wildcards are required')
    return hosts


def _inputs(store: Store, stage: str, batch: str | None = None) -> dict[str, str | None]:
    names = list(STAGE_INPUTS[stage])
    if stage in {'extract-drain', 'review-drain', 'extract-harvest', 'review-harvest'}:
        if not batch:
            raise OperationError('a batch is required')
        lane = stage.split('-', 1)[0]
        names.append(f'calls/{lane}/{batch}/requests.jsonl')
        if stage.endswith('harvest'):
            names.append(f'calls/{lane}/{batch}/results.jsonl')
    return {name: _file_sha(store.path(name))
            for name in names}


def _flow(project: Project, store: Store, flow_id: str) -> tuple[dict[str, Any], scope.Selector]:
    held = flows.flows(store).get(flow_id)
    if held is None:
        raise OperationError(f'unknown or invalid flow: {flow_id}')
    binding = flows.binding_state(project, store, held)
    if binding['state'] != 'CURRENT' or held.get('bound_after_data'):
        raise OperationError(f'flow is not safe to execute: {binding["state"]}, late={held.get("bound_after_data")}')
    selected = held['binding']['selector']
    return held, scope.Selector(selected.get('round'), bool(selected.get('manifest_only')))


def _check_queue_scope(store: Store, stage: str, batch: str | None,
                       selector: scope.Selector) -> None:
    if stage not in {'extract-build', 'review-build', 'extract-drain',
                     'review-drain', 'extract-harvest', 'review-harvest'}:
        return
    from claimstone import model_call
    lane = stage.split('-', 1)[0]
    queue = model_call.Queue(store, lane=lane, batch=str(batch))
    allowed = scope.source_ids(store, selector)
    for row in queue.requests():
        sources = {str(row.get('source_id') or '')}
        sources.update(str(asker.get('source_id') or '')
                       for asker in row.get('asked_by') or [])
        if not sources <= allowed:
            raise OperationError(f'batch {batch} contains a request outside this flow')


def _events(store: Store) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    seen: dict[str, bytes] = {}
    for row in store.read(LEDGER):
        event_id = row.get('event_id')
        body = {key: value for key, value in row.items() if key not in {'event_id', 'at'}}
        if event_id != _digest(body) or row.get('operation_version') not in {1, 2, OPERATIONS_VERSION}:
            raise OperationError('invalid operation event id or version')
        packed = _canonical(row)
        if event_id in seen:
            if seen[event_id] != packed:
                raise OperationError('conflicting duplicate operation event')
            continue
        seen[event_id] = packed
        grouped.setdefault(str(row['operation_id']), []).append(row)
    for operation_id, rows in grouped.items():
        if rows[0]['event'] != 'planned' or rows[0].get('plan_id') != operation_id:
            raise OperationError('operation does not begin with its plan')
        plan = rows[0]['plan']
        if _digest(plan) != operation_id:
            raise OperationError('operation plan digest mismatch')
        permitted = {'planned': {'authorized'}, 'authorized': {'started', 'failed'},
                     'started': {'call_started', 'unit_completed', 'failed'},
                     'call_started': {'unit_completed', 'failed'},
                     'unit_completed': {'call_started', 'unit_completed', 'completed', 'failed'},
                     'completed': set(), 'failed': set()}
        previous = 'planned'
        for row in rows[1:]:
            if row.get('plan_id') != operation_id or row.get('flow_id') != plan['flow_id']:
                raise OperationError('operation event binding mismatch')
            if row.get('event') not in permitted[previous]:
                raise OperationError(f'invalid operation transition {previous} -> {row.get("event")}')
            previous = str(row['event'])
    return grouped


def _append(store: Store, operation_id: str, flow_id: str, event: str,
            actor: str, **fields: Any) -> dict[str, Any]:
    body = {'operation_version': OPERATIONS_VERSION, 'operation_id': operation_id,
            'plan_id': operation_id, 'flow_id': flow_id, 'event': event,
            'actor': actor, 'code_sha256': _code_identity(), **fields}
    row = body | {'event_id': _digest(body), 'at': _now()}
    store.append(LEDGER, row)
    return row


def plan(project: Project, store: Store, flow_id: str, stage: str, *,
         batch: str | None = None, reviewer: tuple[str, str] | None = None,
         model: str | None = None, max_calls: int | None = None,
         backend: str = 'llamacpp', budget_id: str | None = None,
         budget_cents: int | None = None, max_call_cents: int | None = None,
         price_in_cents: int | None = None, price_out_cents: int | None = None,
         candidate_key: str | None = None, allowed_hosts: list[str] | None = None,
         max_requests: int | None = None, api: str | None = None,
         topic_id: str | None = None, term: str | None = None,
         per_query: int | None = None, run_label: str | None = None,
         use_apis: bool = False, retry_classes: list[str] | None = None,
         retry_reason: str | None = None) -> dict[str, Any]:
    if stage not in STAGE_INPUTS:
        raise OperationError(f'unsupported stage: {stage}')
    if stage in {'extract-build', 'review-build', 'extract-drain', 'review-drain',
                 'extract-harvest', 'review-harvest'} and not batch:
        raise OperationError('a named batch is required for a model queue')
    if stage == 'review-build' and reviewer is None:
        raise OperationError('reviewer backend/model is required for the different-reader check')
    draining = stage in {'extract-drain', 'review-drain'}
    if draining and (not model or type(max_calls) is not int or max_calls < 1):
        raise OperationError('model and a positive --max-calls are required')
    if draining and backend not in {'llamacpp', 'ollama-cloud'}:
        raise OperationError('scheduler model backend must be llamacpp or ollama-cloud')
    paid = draining and backend == 'ollama-cloud'
    if paid and (not budget_id or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', budget_id)
                 or any(type(value) is not int or value < 1 for value in
                        (budget_cents, max_call_cents, price_in_cents, price_out_cents))):
        raise OperationError('paid drain needs budget ID, positive budget/call cents and price ceilings')
    if not paid and any(value is not None for value in
                        (budget_id, budget_cents, max_call_cents,
                         price_in_cents, price_out_cents)):
        raise OperationError('paid budget options require ollama-cloud drain')
    if stage == 'acquire' and (not candidate_key or type(max_requests) is not int or
                               max_requests < 1 or not allowed_hosts):
        raise OperationError('acquire needs a candidate key, exact hosts and positive request ceiling')
    if stage == 'discover' and (not api or not topic_id or not term or
                                type(per_query) is not int or per_query < 1 or
                                type(max_requests) is not int or max_requests < 1 or
                                not allowed_hosts):
        raise OperationError('discover needs one topic, term, API, per-query cap, hosts and request ceiling')
    if run_label is not None and (not run_label or len(run_label) > 80 or
                                  any(ch not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for ch in run_label)):
        raise OperationError('run label must be 1-80 letters, digits, dash or underscore')
    if retry_classes and (stage != 'acquire' or not retry_reason or not retry_reason.strip()):
        raise OperationError('terminal retry needs acquire stage and a stated reason')
    if use_apis and stage != 'acquire':
        raise OperationError('--use-apis applies only to acquisition')
    with store.writer_lock():
        held, selector = _flow(project, store, flow_id)
        preview = scheduler_preview.preview(project, store, flow_id)
        if preview['state'] == 'BLOCKED':
            raise OperationError(f'flow preview blocked: {preview["blockers"]}')
        if stage != 'discover' and not scope.candidates(store, selector):
            raise OperationError('flow has no candidates; discovery or intake is required first')
        _check_queue_scope(store, stage, batch, selector)
        selected_candidate = None
        prior_acquisition = None
        hosts: list[str] = []
        query_id = None
        prior_query = None
        if stage == 'discover':
            from claimstone import discover
            from claimstone.store import sha256_text
            if selector.round is None:
                raise OperationError('discovery requires a named round')
            if api not in discover.SEARCHERS or not any(
                    topic.id == topic_id and term in topic.terms for topic in project.topics):
                raise OperationError('topic, term or API is absent from the frozen protocol')
            hosts = _exact_hosts(allowed_hosts)
            query_id = sha256_text(f'{selector.round}|{api}|{topic_id}|{term}')
            prior_query = store.latest_by('queries.jsonl', 'query_id').get(query_id)
            if prior_query is not None:
                if (prior_query.get('ok') or not run_label or not retry_reason or
                        not retry_reason.strip() or
                        prior_query.get('failure_class') not in {
                            'NON_GLOBAL_ADDRESS', 'DNS_ERROR', 'NETWORK_ERROR',
                            'PROVIDER_CREDIT_LIMIT'}):
                    raise OperationError('query retry requires a failed pre-transport outcome, run label and reason')
            if any(row.get('event') == 'request_started' and
                   row.get('round') == selector.round and row.get('source_api') == api and
                   row.get('topic_id') == topic_id and row.get('query') == term
                   for row in store.read('requests.jsonl')):
                raise OperationError('earlier physical query request has no outcome; inspect before retry')
        if stage == 'acquire':
            from claimstone import acquire, net
            import urllib.parse
            selected_candidate = scope.candidates(store, selector).get(str(candidate_key))
            if selected_candidate is None or not selected_candidate.get('source_class'):
                raise OperationError('candidate is absent, outside the flow or unclassified')
            target = str(selected_candidate.get('url') or '')
            try:
                parsed_target = urllib.parse.urlsplit(target)
                direct_host = net.host_of(target)
            except ValueError as exc:
                raise OperationError('candidate URL is malformed') from exc
            hosts = _exact_hosts(allowed_hosts)
            if (parsed_target.scheme not in {'https', 'http'} or
                    parsed_target.username is not None or parsed_target.password is not None or
                    direct_host not in hosts):
                raise OperationError('direct URL and exact lowercase hosts are required')
            prior_acquisition = store.latest_by('acquisitions.jsonl', 'candidate_key').get(
                str(candidate_key))
            retries = frozenset(retry_classes or [])
            if retries - (net.TERMINAL | {'UNCLASSIFIED'}):
                raise OperationError('retry class is not a known terminal network class')
            if retries and (prior_acquisition is None or
                            prior_acquisition.get('failure_class') not in retries):
                raise OperationError('retry class does not match the candidate’s prior failure')
            settled_campaigns = {row.get('campaign') for row in store.read('acquisitions.jsonl')
                                 if row.get('candidate_key') == candidate_key}
            if any(row.get('event') == 'request_started' and
                   row.get('candidate_key') == candidate_key and
                   row.get('campaign') not in settled_campaigns
                   for row in store.read('requests.jsonl')):
                raise OperationError('earlier physical acquisition request has no outcome; inspect before retry')
            if not list(acquire.eligible_candidates([selected_candidate],
                    {str(candidate_key): prior_acquisition} if prior_acquisition else {},
                    retry_classes=retries,
                    round_name=selector.round, manifest_only=selector.manifest_only)):
                raise OperationError('candidate is not eligible under the current retry policy')
        call_ids: list[str] = []
        harness = None
        if draining:
            from claimstone import model_call, runners
            runner = _IdentityCheckedRunner(runners.build(backend, model=model))
            harness = runner.harness_version()
            queue = model_call.Queue(store, lane=stage.split('-', 1)[0], batch=batch)
            prior = queue.results(backend=backend, model=model)
            pending = queue.pending(backend=backend, model=model)
            call_ids = [str(row['call_id']) for row in pending
                        if f"{row['call_id']}|{backend}|{model}" not in prior][:max_calls]
            if not call_ids:
                raise OperationError('no never-attempted calls in this batch')
            if stage == 'review-drain':
                chosen = set(call_ids)
                for request in queue.requests():
                    if request['call_id'] not in chosen:
                        continue
                    targets = request.get('review_targets') or [request]
                    for target in targets:
                        reader = target.get('extracted_by') or {}
                        if not reader.get('backend') or not reader.get('model'):
                            raise OperationError('review request lacks extractor identity')
                        if (reader['backend'], reader['model']) == (backend, model):
                            raise OperationError('review model is the extractor for a planned claim')
            if paid:
                if len(call_ids) * max_call_cents > budget_cents:
                    raise OperationError('planned reservations exceed the declared budget')
                selected = {row['call_id']: row for row in queue.requests()}
                for call_id in call_ids:
                    request = selected[call_id]
                    # This is a local estimate, not a provider-enforced billing cap.
                    input_bound = (len(request['system'].encode('utf-8')) +
                                   len(request['user'].encode('utf-8')) + 8192)
                    estimate = (input_bound * price_in_cents +
                                int(request['max_output_tokens']) * price_out_cents +
                                999_999) // 1_000_000
                    if estimate > max_call_cents:
                        raise OperationError(f'call {call_id} exceeds per-call reservation estimate')
        frozen = {'operation_version': OPERATIONS_VERSION, 'project': project.name,
                  'flow_id': flow_id, 'stage': stage, 'selector': selector.as_dict(),
                  'protocol_sha256': held['binding']['protocol_sha256'],
                  'code_sha256': _code_identity(), 'input_sha256': _inputs(store, stage, batch),
                  'batch': batch, 'reviewer': list(reviewer) if reviewer else None,
                  'backend': backend if draining else None, 'model': model,
                  'harness_version': harness, 'call_ids': call_ids,
                  'budget_id': budget_id if paid else None,
                  'budget_cents': budget_cents if paid else None,
                  'max_call_cents': max_call_cents if paid else None,
                  'price_in_cents': price_in_cents if paid else None,
                  'price_out_cents': price_out_cents if paid else None,
                  'candidate_key': candidate_key if stage == 'acquire' else None,
                  'candidate_sha256': _digest(selected_candidate) if selected_candidate else None,
                  'prior_acquisition_sha256': (_digest(prior_acquisition)
                                               if prior_acquisition else None),
                  'allowed_hosts': hosts,
                  'allowed_schemes': (['http', 'https'] if stage == 'acquire' and
                                      parsed_target.scheme == 'http' else ['https'])
                                     if stage in {'acquire', 'discover'} else [],
                  'use_apis': bool(use_apis) if stage == 'acquire' else False,
                  'retry_classes': sorted(set(retry_classes or [])) if stage == 'acquire' else [],
                  'retry_reason': retry_reason if stage == 'acquire' else None,
                  'query': {'api': api, 'topic_id': topic_id, 'term': term,
                            'per_query': per_query, 'query_id': query_id} if stage == 'discover' else None,
                  'prior_query_sha256': _digest(prior_query) if prior_query else None,
                  'query_retry_reason': retry_reason if stage == 'discover' else None,
                  'max_network_requests': max_requests if stage in {'acquire', 'discover'} else 0,
                  'max_model_calls': len(call_ids),
                  'max_spend_usd': (len(call_ids) * max_call_cents / 100 if paid else 0)}
        frozen['run_label'] = run_label
        operation_id = _digest(frozen)
        existing = _events(store).get(operation_id)
        if existing:
            if existing[-1]['event'] == 'failed':
                raise OperationError('identical operation failed; use a new --run-label after resolving the cause')
            return existing[0]['plan']
        _append(store, operation_id, flow_id, 'planned', 'planner', plan=frozen)
        return frozen


def authorize(store: Store, operation_id: str, *, batch_id: str | None = None,
              identity: dict[str, Any] | None = None,
              schedule_id: str | None = None) -> dict[str, Any]:
    """A local logged-in user authorizes exactly one offline plan.

    `identity` is for the control server (portal B12): the authenticated operator who held the
    session, recorded instead of the server process's OS account, which would name the wrong
    person. Omitted, the OS login is recorded exactly as before."""
    with store.writer_lock():
        rows = _events(store).get(operation_id)
        if rows is None:
            raise OperationError(f'unknown operation: {operation_id}')
        if schedule_id:
            from claimstone import network_schedule
            history = network_schedule._read(store).get(schedule_id)
            if (not history or history[-1]['event'] != 'planned' or
                    not any(operation_id in entry['operation_ids'] and
                            batch_id == entry['batch_id']
                            for entry in history[0]['plan']['entries'])):
                raise OperationError('operation is absent from the planned schedule')
        if len(rows) > 1:
            if rows[1]['event'] == 'authorized':
                if schedule_id and rows[1].get('schedule_id') != schedule_id:
                    raise OperationError('operation belongs to another authorization')
                return rows[1]
            raise OperationError('operation is no longer awaiting authorization')
        plan_row = rows[0]['plan']
        if plan_row.get('operation_version') != OPERATIONS_VERSION:
            raise OperationError('legacy operation requires a fresh version 3 plan')
        if plan_row['budget_id']:
            approved = [group[0]['plan'] for group in _events(store).values()
                        if len(group) > 1 and group[1]['event'] == 'authorized'
                        and group[0]['plan'].get('budget_id') == plan_row['budget_id']]
            if any(item['budget_cents'] != plan_row['budget_cents'] for item in approved):
                raise OperationError('budget ID has a different frozen ceiling')
            reserved = sum(item['max_call_cents'] * len(item['call_ids'])
                           for item in approved)
            proposed = plan_row['max_call_cents'] * len(plan_row['call_ids'])
            if reserved + proposed > plan_row['budget_cents']:
                raise OperationError('cumulative paid reservations exceed budget')
        if identity is None:
            identity = {'uid': os.getuid(), 'login': pwd.getpwuid(os.getuid()).pw_name}
        return _append(store, operation_id, rows[0]['flow_id'], 'authorized',
                       'operator', identity=identity, approved_limits={
                           'network_requests': rows[0]['plan']['max_network_requests'],
                           'model_calls': rows[0]['plan']['max_model_calls'],
                           'spend_usd': plan_row['max_spend_usd']}, batch_id=batch_id,
                       schedule_id=schedule_id)


def plan_batch(project: Project, store: Store, flow_id: str, stage: str, *,
               apis: list[str] | None = None, allowed_hosts: list[str] | None = None,
               max_units: int, max_requests_each: int, per_query: int = 25,
               use_apis: bool = False, retry_classes: list[str] | None = None,
               retry_reason: str | None = None) -> dict[str, Any]:
    """Prepare a reviewable set of query or candidate plans; execute none."""
    if stage not in {'discover', 'acquire'}:
        raise OperationError('batch planning supports discover or acquire')
    if type(max_units) is not int or max_units < 1 or type(max_requests_each) is not int or max_requests_each < 1:
        raise OperationError('positive unit and per-unit physical request ceilings are required')
    if not allowed_hosts:
        raise OperationError('exact allowed hosts are required')
    if stage == 'discover' and (not apis or type(per_query) is not int or per_query < 1):
        raise OperationError('APIs and positive per-query result cap are required')
    with store.writer_lock():
        _, selector = _flow(project, store, flow_id)
        scoped_candidates = scope.candidates(store, selector)
        requested: list[dict[str, Any]] = []
        if stage == 'discover':
            if selector.round is None:
                raise OperationError('discovery requires a named round')
            for topic in project.topics:
                for term in topic.terms:
                    for api in sorted(set(apis or [])):
                        requested.append({'api': api, 'topic_id': topic.id, 'term': term,
                                          'per_query': per_query})
        else:
            for key in sorted(scoped_candidates):
                requested.append({'candidate_key': key})
        planned: list[str] = []
        units: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        examined = 0
        for item in requested:
            if len(planned) >= max_units:
                break
            examined += 1
            try:
                one = plan(project, store, flow_id, stage,
                           allowed_hosts=allowed_hosts,
                           max_requests=max_requests_each,
                           use_apis=use_apis, retry_classes=retry_classes,
                           retry_reason=retry_reason, **item)
                operation_id = _digest(one)
                if operation_id not in planned:
                    planned.append(operation_id)
                    units.append({'operation_id': operation_id,
                                  'subject': one['candidate_key'] if stage == 'acquire'
                                  else one['query'],
                                  'direct_url': (scoped_candidates[one['candidate_key']].get('url')
                                                 if stage == 'acquire' else None),
                                  'allowed_hosts': one['allowed_hosts'],
                                  'allowed_schemes': one['allowed_schemes'],
                                  'max_requests': one['max_network_requests'],
                                  'use_apis': one['use_apis'],
                                  'retry_classes': one['retry_classes']})
            except OperationError as exc:
                skipped.append({'subject': str(item.get('candidate_key') or
                                                f"{item.get('api')}:{item.get('topic_id')}:{item.get('term')}"),
                                'reason': str(exc)})
        batch = {'batch_version': OPERATIONS_VERSION, 'project': project.name,
                 'flow_id': flow_id, 'stage': stage, 'operation_ids': planned,
                 'units': units,
                 'selected': examined, 'remaining_unplanned': len(requested) - examined,
                 'skipped': skipped,
                 'max_total_requests': len(planned) * max_requests_each}
        batch_id = _digest(batch)
        if not any(row.get('batch_id') == batch_id for row in store.read(BATCH_LEDGER)):
            store.append(BATCH_LEDGER, batch | {'batch_id': batch_id, 'created_at': _now()})
        return batch | {'batch_id': batch_id}


def authorize_batch(store: Store, batch_id: str, *,
                    identity: dict[str, Any] | None = None) -> dict[str, Any]:
    """One explicit operator action authorizes only the batch's frozen plans."""
    with store.writer_lock():
        batches = {row['batch_id']: row for row in store.read(BATCH_LEDGER)}
        batch = batches.get(batch_id)
        if batch is None or _digest({key: value for key, value in batch.items()
                                    if key not in {'batch_id', 'created_at'}}) != batch_id:
            raise OperationError('unknown or altered batch')
        events = _events(store)
        for operation_id in batch['operation_ids']:
            rows = events.get(operation_id)
            if rows is None or rows[0]['plan']['flow_id'] != batch['flow_id']:
                raise OperationError('batch contains an unknown or mismatched operation')
            if len(rows) > 1 and rows[1]['event'] != 'authorized':
                raise OperationError('batch contains an operation with an invalid state')
        authorized = 0
        for operation_id in batch['operation_ids']:
            if len(events[operation_id]) == 1:
                authorize(store, operation_id, batch_id=batch_id, identity=identity)
                authorized += 1
        return {'batch_id': batch_id, 'authorized_now': authorized,
                'operation_ids': batch['operation_ids'],
                'max_total_requests': batch['max_total_requests']}


def execute(project: Project, store: Store, operation_id: str,
            *, grobid: Any = None) -> dict[str, Any]:
    """Run once; a crash after stage writes can be retried under the same plan."""
    with store.writer_lock():
        rows = _events(store).get(operation_id)
        if rows is None or len(rows) < 2 or rows[1]['event'] != 'authorized':
            raise OperationError('exact plan has not been authorized')
        plan_row = rows[0]['plan']
        if plan_row['project'] != project.name:
            raise OperationError('operation belongs to another project')
        if rows[-1]['event'] == 'completed':
            return rows[-1]['result']
        schedule_id = rows[1].get('schedule_id')
        if schedule_id:
            from claimstone import network_schedule
            if not network_schedule.due(store, schedule_id, operation_id):
                raise OperationError('scheduled authorization is not currently active')
        copy_policy_id = (rows[1].get('identity') or {}).get('copy_policy_id')
        if copy_policy_id:
            from claimstone import copy_policy
            if plan_row['stage'] != 'acquire' or not copy_policy.due(store, copy_policy_id):
                raise OperationError('copy policy authorization is not currently active')
        if plan_row['code_sha256'] != _code_identity():
            raise OperationError('project or code identity changed; prepare a new plan')
        held, selector = _flow(project, store, plan_row['flow_id'])
        if (held['binding']['protocol_sha256'] != plan_row['protocol_sha256'] or
                selector.as_dict() != plan_row['selector'] or
                _inputs(store, plan_row['stage'], plan_row['batch']) != plan_row['input_sha256']):
            raise OperationError('frozen inputs changed; prepare a new plan')
        _check_queue_scope(store, plan_row['stage'], plan_row['batch'], selector)
        acquired_result = None
        if plan_row['stage'] == 'acquire':
            candidate = scope.candidates(store, selector).get(plan_row['candidate_key'])
            if candidate is None or _digest(candidate) != plan_row['candidate_sha256']:
                raise OperationError('candidate changed; prepare a new plan')
            acquired_result = store.latest_by('acquisitions.jsonl', 'candidate_key').get(
                plan_row['candidate_key'])
            if acquired_result is not None and acquired_result.get('campaign') != operation_id:
                if _digest(acquired_result) != plan_row['prior_acquisition_sha256']:
                    raise OperationError('acquisition state changed; prepare a new plan')
        discovery_result = None
        if plan_row['stage'] == 'discover':
            query = plan_row['query']
            discovery_result = store.latest_by('queries.jsonl', 'query_id').get(query['query_id'])
            if discovery_result is not None and discovery_result.get('campaign') != operation_id:
                if (not plan_row.get('prior_query_sha256') or
                        _digest(discovery_result) != plan_row['prior_query_sha256'] or
                        discovery_result.get('ok')):
                    raise OperationError('query outcome belongs to another campaign')
                if any(row.get('event') == 'request_started' and
                       row.get('round') == selector.round and
                       row.get('source_api') == query['api'] and
                       row.get('topic_id') == query['topic_id'] and
                       row.get('query') == query['term']
                       for row in store.read('requests.jsonl')):
                    raise OperationError('prior query has a physical request; inspect before retry')
                discovery_result = None
        draining = plan_row['stage'] in {'extract-drain', 'review-drain'}
        if not draining and len(rows) > 2 and rows[-1]['event'] == 'unit_completed':
            _append(store, operation_id, plan_row['flow_id'], 'completed', 'worker',
                    result=rows[-1]['result'])
            return rows[-1]['result']
        if len(rows) > 2 and rows[-1]['event'] == 'failed':
            raise OperationError('operation failed; prepare a new plan')
        if len(rows) == 2:
            _append(store, operation_id, plan_row['flow_id'], 'started', 'worker',
                    worker_pid=os.getpid(), coordination='PROJECT_WRITER_LOCK')
        stage = plan_row['stage']
        batch = plan_row['batch']
        try:
            if draining:
                from claimstone import model_call, runners
                backend = plan_row['backend']
                options = {}
                if backend == 'ollama-cloud':
                    options = {'price_in': plan_row['price_in_cents'] / 100,
                               'price_out': plan_row['price_out_cents'] / 100}
                runner = _IdentityCheckedRunner(runners.build(
                    backend, model=plan_row['model'], **options))
                if runner.harness_version() != plan_row['harness_version']:
                    raise OperationError('model harness changed; prepare a new plan')
                queue = model_call.Queue(store, lane=stage.split('-', 1)[0], batch=batch)
                if backend == 'ollama-cloud':
                    for row in rows:
                        if row['event'] != 'unit_completed':
                            continue
                        cost = row['result'].get('cost_usd')
                        if (type(cost) not in {int, float} or cost < 0 or
                                cost * 100 > plan_row['max_call_cents'] + 1e-8):
                            raise OperationError('paid result has unknown cost or exceeds its per-call reservation')
                completed = {row['call_id'] for row in rows
                             if row['event'] == 'unit_completed'}
                result_rows = queue.results(backend=backend, model=plan_row['model'])
                for call_id in plan_row['call_ids']:
                    if call_id in completed:
                        continue
                    key = f"{call_id}|{backend}|{plan_row['model']}"
                    answer = result_rows.get(key)
                    if answer is None:
                        if backend == 'ollama-cloud':
                            if any(row['event'] == 'call_started' and
                                   row.get('call_id') == call_id for row in rows):
                                raise OperationError('paid call has no recorded result; inspect provider billing before retry')
                            started = _append(store, operation_id, plan_row['flow_id'],
                                              'call_started', 'worker', call_id=call_id,
                                              reserved_cents=plan_row['max_call_cents'])
                            rows.append(started)
                        generated = list(model_call.drain(queue, runner, limit=1,
                            call_ids=frozenset({call_id})))
                        if len(generated) != 1:
                            raise OperationError(f'planned call did not run: {call_id}')
                        answer = generated[0]
                    finished = _append(store, operation_id, plan_row['flow_id'], 'unit_completed',
                            'worker', call_id=call_id, result={
                                'ok': bool(answer.get('ok')),
                                'failure_class': answer.get('failure_class'),
                                'result_key': answer.get('result_key'),
                                'cost_usd': answer.get('cost_usd')})
                    rows.append(finished)
                    if backend == 'ollama-cloud':
                        cost = answer.get('cost_usd')
                        if (type(cost) not in {int, float} or
                                cost < 0 or cost * 100 > plan_row['max_call_cents'] + 1e-8):
                            raise OperationError('paid result has unknown cost or exceeds its per-call reservation')
                result = {'calls': len(plan_row['call_ids']), 'batch': batch}
            elif stage == 'discover':
                from claimstone import discover, net
                if discovery_result is not None:
                    result = {'query_id': plan_row['query']['query_id'],
                              'ok': bool(discovery_result.get('ok')),
                              'returned': discovery_result.get('returned'),
                              'reconciled': True}
                else:
                    started_requests = [row for row in store.read('requests.jsonl')
                                        if row.get('event') == 'request_started' and
                                        row.get('campaign') == operation_id]
                    if started_requests:
                        raise OperationError('physical request recorded without query row; inspect before retry')
                    query = plan_row['query']
                    fetcher = net.Fetcher(excluded_hosts=frozenset(project.excluded_hosts),
                                          allowed_hosts=frozenset(plan_row['allowed_hosts']),
                                          allowed_schemes=frozenset(plan_row['allowed_schemes']),
                                          enforce_global_addresses=True,
                                          max_physical_requests=plan_row['max_network_requests'])
                    summary = discover.run(project, store, fetcher,
                                           apis=[query['api']], topics=[query['topic_id']],
                                           terms=[query['term']], per_query=query['per_query'],
                                           round_name=selector.round, campaign=operation_id)
                    if summary['queries'] != 1:
                        raise OperationError('planned query did not run exactly once')
                    recorded = store.latest_by('queries.jsonl', 'query_id').get(query['query_id'])
                    if recorded is None or recorded.get('campaign') != operation_id:
                        raise OperationError('query outcome was not recorded')
                    result = {'query_id': query['query_id'], 'ok': bool(recorded.get('ok')),
                              'returned': recorded.get('returned'), 'reconciled': False}
            elif stage == 'acquire':
                from claimstone import acquire, net
                if acquired_result is not None and acquired_result.get('campaign') == operation_id:
                    result = {'candidate_key': plan_row['candidate_key'],
                              'acquired': bool(acquired_result.get('acquired')),
                              'failure_class': acquired_result.get('failure_class'),
                              'reconciled': True}
                else:
                    started_requests = [row for row in store.read('requests.jsonl')
                                        if row.get('event') == 'request_started' and
                                        row.get('campaign') == operation_id]
                    if started_requests:
                        raise OperationError('physical request recorded without acquisition row; inspect before retry')
                    fetcher = net.Fetcher(excluded_hosts=frozenset(project.excluded_hosts),
                                          allowed_hosts=frozenset(plan_row['allowed_hosts']),
                                          allowed_schemes=frozenset(plan_row['allowed_schemes']),
                                          enforce_global_addresses=True,
                                          max_physical_requests=plan_row['max_network_requests'])
                    rows_done = list(acquire.run(
                        [candidate], store, fetcher, campaign=operation_id,
                        retry_classes=frozenset(plan_row['retry_classes']),
                        use_apis=plan_row['use_apis'], thresholds=project.gate_thresholds,
                        policy=project.gate_policy, classes=project.classes,
                        round_name=selector.round,
                        manifest_only=selector.manifest_only, limit=1))
                    if len(rows_done) != 1:
                        raise OperationError('candidate became ineligible before its request')
                    row = rows_done[0]
                    result = {'candidate_key': plan_row['candidate_key'],
                              'acquired': bool(row.get('acquired')),
                              'failure_class': row.get('failure_class'),
                              'reconciled': False}
            elif stage == 'normalize':
                from claimstone import grobid as grobid_module, normalize
                client = grobid or grobid_module.Grobid()
                rows_done = list(normalize.run(store, client,
                                               thresholds=project.normalize_thresholds,
                                               selector=selector))
                result = {'normalized': len(rows_done)}
            elif stage == 'extract-build':
                from claimstone import extract
                result = extract.build(project, store, batch=batch, selector=selector)
            elif stage == 'review-build':
                from claimstone import review
                result = review.build(project, store, batch=batch,
                                      reviewer=tuple(plan_row['reviewer']), selector=selector)
            elif stage == 'extract-harvest':
                from claimstone import extract
                result = extract.harvest(project, store, batch=batch)
            elif stage == 'review-harvest':
                from claimstone import review
                result = review.harvest(project, store, batch=batch)
            else:
                from claimstone import synthesize
                result = synthesize.build(project, store, round_name=selector.round,
                                          manifest_only=selector.manifest_only)
        except Exception as exc:
            _append(store, operation_id, plan_row['flow_id'], 'failed', 'worker',
                    failure_class=type(exc).__name__, detail=str(exc)[:400])
            raise
        if not draining:
            _append(store, operation_id, plan_row['flow_id'], 'unit_completed', 'worker', result=result)
        _append(store, operation_id, plan_row['flow_id'], 'completed', 'worker', result=result)
        return result


def status(store: Store, operation_id: str) -> dict[str, Any]:
    rows = _events(store).get(operation_id)
    if rows is None:
        raise OperationError(f'unknown operation: {operation_id}')
    return {'operation_id': operation_id, 'plan': rows[0]['plan'],
            'state': (('RUNNING_OR_LOCK_HELD' if store.writer_busy() else 'INTERRUPTED')
                      if rows[-1]['event'] in {'started', 'call_started', 'unit_completed'}
                      else rows[-1]['event'].upper()),
            'events': rows}


def tick(project: Project, store: Store, *, max_operations: int = 1,
         flow_id: str | None = None,
         stages: frozenset[str] | None = None) -> dict[str, Any]:
    """Execute up to N authorized or interrupted local operations, in plan order."""
    if type(max_operations) is not int or max_operations < 1:
        raise OperationError('max_operations must be positive')
    from claimstone import copy_policy
    copy_policy.materialize_due(project, store, flow_id=flow_id)
    grouped = _events(store)
    ready = [operation_id for operation_id, rows in grouped.items()
             if rows[-1]['event'] in {'authorized', 'started', 'call_started', 'unit_completed'}
             and rows[0]['plan']['project'] == project.name
             and (flow_id is None or rows[0]['plan']['flow_id'] == flow_id)
             and (stages is None or rows[0]['plan']['stage'] in stages)]
    from claimstone import network_schedule
    ready = [operation_id for operation_id in ready
             if not grouped[operation_id][1].get('schedule_id') or
             network_schedule.due(store, grouped[operation_id][1]['schedule_id'], operation_id)]
    ready = [operation_id for operation_id in ready
             if not (grouped[operation_id][1].get('identity') or {}).get('copy_policy_id') or
             copy_policy.due(store, grouped[operation_id][1]['identity']['copy_policy_id'])]
    results: list[dict[str, Any]] = []
    for operation_id in ready[:max_operations]:
        try:
            result = execute(project, store, operation_id)
            results.append({'operation_id': operation_id, 'state': 'COMPLETED',
                            'result': result})
        except Exception as exc:
            with store.writer_lock():
                current = _events(store).get(operation_id)
                if current and current[-1]['event'] in {
                        'authorized', 'started', 'call_started', 'unit_completed'}:
                    _append(store, operation_id, current[0]['flow_id'], 'failed',
                            'worker', failure_class=type(exc).__name__,
                            detail=str(exc)[:400])
            results.append({'operation_id': operation_id, 'state': 'FAILED',
                            'failure_class': type(exc).__name__,
                            'detail': str(exc)[:400]})
    return {'considered': len(ready), 'processed': len(results), 'operations': results}


def drive_local(project: Project, store: Store, flow_id: str, *,
                extract_model: str, review_model: str,
                max_local_calls: int,
                authorization_identity: dict[str, Any] | None = None,
                authorization_label: str | None = None) -> dict[str, Any]:
    """One user-authorized pass through scoped local stages, stopping at human/network gates.

    The CLI invocation or a standing local mandate is the operator's bounded
    instruction. Each generated plan still receives its own append-only
    authorization event.
    No scholarly URL or paid backend is contacted here.
    """
    if (not extract_model or not review_model or extract_model == review_model or
            type(max_local_calls) is not int or max_local_calls < 0):
        raise OperationError('two different local models and a nonnegative call ceiling are required')
    # Freeze the already approved external work at invocation time. New plans
    # authorized while this command runs wait for a later invocation.
    ready_network = [rows for rows in _events(store).values()
                     if rows[-1]['event'] in {'authorized', 'started', 'unit_completed'}
                     and rows[0]['plan']['project'] == project.name
                     and rows[0]['plan']['flow_id'] == flow_id
                     and rows[0]['plan']['stage'] in {'discover', 'acquire'}]
    network = (tick(project, store, max_operations=len(ready_network), flow_id=flow_id,
                    stages=frozenset({'discover', 'acquire'}))
               if ready_network else {'processed': 0, 'operations': []})
    held, selector = _flow(project, store, flow_id)
    preview = scheduler_preview.preview(project, store, flow_id)
    if preview['state'] == 'BLOCKED':
        raise OperationError(f'flow preview blocked: {preview["blockers"]}')
    if not scope.candidates(store, selector):
        return {'flow_id': flow_id, 'steps': [], 'local_calls': 0,
                'network': network,
                'stopped_reason': 'NEEDS_AUTHORIZED_DISCOVERY'}

    from claimstone import admissibility, claim_records, model_call, synthesize
    allowed = scope.source_ids(store, selector)
    steps: list[dict[str, Any]] = []
    remaining = max_local_calls
    extract_batch = f'{flow_id[:16]}-extract'
    review_batch = f'{flow_id[:16]}-review'

    def run_stage(stage: str, **kwargs: Any) -> dict[str, Any]:
        frozen = plan(project, store, flow_id, stage,
                      run_label=authorization_label, **kwargs)
        operation_id = _digest(frozen)
        authorize(store, operation_id, identity=authorization_identity)
        result = execute(project, store, operation_id)
        steps.append({'stage': stage, 'operation_id': operation_id, 'result': result})
        return result

    acquisitions = admissibility.collapse(store)
    if any(row.get('acquired') and str(row.get('source_id') or row.get('candidate_key')) in allowed
           for row in acquisitions.values()):
        run_stage('normalize')

    confirmed = {str(row.get('source_id')) for row in store.read('documents.jsonl')
                 if row.get('fulltext_confirmed') and str(row.get('source_id')) in allowed}
    if confirmed:
        run_stage('extract-build', batch=extract_batch)
        extract_queue = model_call.Queue(store, lane='extract', batch=extract_batch)
        if remaining and extract_queue.pending(backend='llamacpp', model=extract_model):
            try:
                drained = run_stage('extract-drain', batch=extract_batch,
                                    model=extract_model, max_calls=remaining)
                remaining -= drained['calls']
            except OperationError as exc:
                if 'no never-attempted calls' not in str(exc):
                    raise
        if extract_queue.results(backend='llamacpp', model=extract_model):
            run_stage('extract-harvest', batch=extract_batch)

    claims = claim_records.current(store)[0]
    if any(str(row.get('source_id')) in allowed for row in claims.values()):
        run_stage('review-build', batch=review_batch,
                  reviewer=('llamacpp', review_model))
        review_queue = model_call.Queue(store, lane='review', batch=review_batch)
        if remaining and review_queue.pending(backend='llamacpp', model=review_model):
            try:
                drained = run_stage('review-drain', batch=review_batch,
                                    model=review_model, max_calls=remaining)
                remaining -= drained['calls']
            except OperationError as exc:
                if 'no never-attempted calls' not in str(exc):
                    raise
        if review_queue.results(backend='llamacpp', model=review_model):
            run_stage('review-harvest', batch=review_batch)

    try:
        synthesize.preview(project, store, round_name=selector.round,
                           manifest_only=selector.manifest_only)
    except synthesize.NotAdmissible:
        reason = 'NEEDS_ACQUISITION_FLOOR'
    else:
        run_stage('synthesize')
        reason = 'HUMAN_READING_OR_MORE_EVIDENCE'
    return {'flow_id': flow_id, 'steps': steps,
            'network': network,
            'local_calls': max_local_calls - remaining,
            'remaining_local_calls': remaining, 'stopped_reason': reason}
