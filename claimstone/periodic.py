"""Plan finite dated discovery rounds and audit their cumulative acquisition.

Planning writes only bindings and frozen operation plans. Transport still requires
the separate, explicit authorization of the resulting network schedule.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from claimstone import admissibility, flows, network_schedule, operations, scope
from claimstone.config import Project
from claimstone.store import Store


def plan(project: Project, store: Store, source_flow_id: str,
         rounds: list[dict[str, str]], *, apis: list[str], allowed_hosts: list[str],
         max_units_each: int, max_requests_each: int, per_query: int = 25) -> dict[str, Any]:
    """Freeze one complete discovery batch per new round, then one finite schedule.

    A retry is safe: flow creation, operation planning, and schedule planning use
    content identities. Partial planning grants no network permission.
    """
    if not isinstance(rounds, list) or not 1 <= len(rounds) <= 32:
        raise operations.OperationError('periodic plan needs 1-32 dated rounds')
    if not apis or not allowed_hosts or any(type(n) is not int or n < 1 for n in
                                            (max_units_each, max_requests_each, per_query)):
        raise operations.OperationError('periodic plan needs APIs, exact hosts and positive caps')
    from claimstone import discover
    if set(apis) - set(discover.SEARCHERS):
        raise operations.OperationError('periodic plan has an unknown discovery API')
    hosts = operations._exact_hosts(allowed_hosts)
    if set(hosts) & set(project.excluded_hosts):
        raise operations.OperationError('periodic plan contains an excluded host')
    query_count = sum(len(topic.terms) for topic in project.topics) * len(set(apis))
    if not query_count or max_units_each < query_count:
        raise operations.OperationError('round cap must cover every frozen discovery query')
    source, _ = operations._flow(project, store, source_flow_id)
    if source['binding']['selector']['manifest_only']:
        raise operations.OperationError('periodic discovery needs a non-manifest source flow')
    now = dt.datetime.now(dt.timezone.utc)
    candidate_rounds = {str(row.get('round')) for row in store.read('candidates.jsonl')}
    existing_flows: dict[str, set[str]] = {}
    for row in flows.flows(store).values():
        name = row['binding']['selector']['round']
        if name is not None:
            existing_flows.setdefault(str(name), set()).add(row['flow_id'])
    seen: set[str] = set()
    checked: list[dict[str, str]] = []
    last_start: dt.datetime | None = None
    last_end: dt.datetime | None = None
    for item in rounds:
        if not isinstance(item, dict) or set(item) != {'round', 'title', 'not_before', 'expires_at'}:
            raise operations.OperationError('round needs round, title and exact UTC window')
        name = item['round']
        if (not isinstance(name, str) or not name or len(name) > 80 or
                re.fullmatch(r'[A-Za-z0-9_-]+', name) is None or
                name in seen or name in candidate_rounds):
            raise operations.OperationError('round names must be new, unique and URL-safe')
        if not isinstance(item['title'], str) or not item['title'].strip():
            raise operations.OperationError('round title is required')
        start = network_schedule._instant(item['not_before'])
        end = network_schedule._instant(item['expires_at'])
        if start <= now or start >= end or end > now + dt.timedelta(days=366):
            raise operations.OperationError('round window must be future-bounded within one year')
        if last_start is not None and start <= last_start:
            raise operations.OperationError('round windows must be ordered by start time')
        if last_end is not None and start < last_end:
            raise operations.OperationError('round windows must not overlap')
        seen.add(name)
        last_start = start
        last_end = end
        checked.append({'round': name, 'title': item['title'],
                        'not_before': start.isoformat(), 'expires_at': end.isoformat()})

    # Check all existing bindings before writing a row. Re-running a partially
    # completed plan accepts only the exact same lineage and protocol.
    previous = source_flow_id
    for item in checked:
        binding = {'project': project.name,
                   'selector': scope.Selector(item['round']).as_dict(),
                   'registry_version': project.registry_version,
                   'registry_sha256': project.registry_sha256,
                   'protocol_sha256': flows.protocol_digest(project),
                   'population_sha256': flows._population_sha(store, item['round']),
                   'derived_from': previous, 'relation': 'derived_from'}
        previous = flows.binding_id(binding)
        if existing_flows.get(item['round'], {previous}) != {previous}:
            raise operations.OperationError('round already has a different flow binding')

    # Every flow freezes its population first. Plan batches only after *all* flow
    # creations: discover operation plans hash populations.jsonl as an input.
    previous = source_flow_id
    created: list[dict[str, Any]] = []
    for item in checked:
        flow, _ = flows.create(project, store, selector=scope.Selector(item['round']),
                               title=item['title'], derived_from=previous,
                               relation='derived_from')
        if flow['bound_after_data']:
            raise operations.OperationError('periodic flow was bound after candidate data')
        previous = flow['flow_id']
        created.append({'round': item['round'], 'flow_id': previous,
                        'not_before': item['not_before'], 'expires_at': item['expires_at']})
    entries: list[dict[str, str]] = []
    for item in created:
        batch = operations.plan_batch(project, store, item['flow_id'], 'discover',
                                      apis=apis, allowed_hosts=hosts,
                                      max_units=max_units_each,
                                      max_requests_each=max_requests_each,
                                      per_query=per_query)
        if batch['remaining_unplanned'] or batch['skipped'] or len(batch['operation_ids']) != query_count:
            raise operations.OperationError('periodic batch did not cover all protocol queries')
        item['batch_id'] = batch['batch_id']
        entries.append({'batch_id': batch['batch_id'],
                        'not_before': item['not_before'], 'expires_at': item['expires_at']})
    schedule = network_schedule.plan(store, project.name, entries,
                                     max_total_requests=query_count * max_requests_each * len(entries))
    return {'rounds': created, 'schedule_id': schedule['schedule_id'],
            'schedule_state': network_schedule.status(store, schedule['schedule_id'])['state'],
            'max_total_requests': schedule['plan']['max_total_requests']}


def audit(project: Project, store: Store, schedule_id: str) -> dict[str, Any]:
    """Read-only per-round and whole-corpus admission; never a verdict."""
    schedule = network_schedule.status(store, schedule_id)
    if schedule['plan']['project'] != project.name:
        raise operations.OperationError('schedule belongs to another project')
    flow_rows = flows.flows(store)
    events = operations._events(store)
    queries = store.latest_by('queries.jsonl', 'query_id')
    rounds: list[dict[str, Any]] = []
    ancestors: list[dict[str, Any]] = []
    parent_id = flow_rows.get(schedule['plan']['entries'][0]['flow_id'], {}).get(
        'binding', {}).get('derived_from')
    seen_parents: set[str] = set()
    while parent_id is not None:
        if parent_id in seen_parents or parent_id not in flow_rows:
            raise operations.OperationError('periodic lineage is cyclic or incomplete')
        seen_parents.add(parent_id)
        parent = flow_rows[parent_id]
        selector = parent['binding']['selector']
        ancestors.append({'flow_id': parent_id, 'round': selector['round'],
                          'binding_state': flows.binding_state(project, store, parent)['state'],
                          'admission': admissibility.admit(
                              project, store, round_name=selector['round'],
                              manifest_only=selector['manifest_only'])})
        parent_id = parent['binding']['derived_from']
    ancestors.reverse()
    previous_flow_id: str | None = None
    for entry in schedule['plan']['entries']:
        if entry['stage'] != 'discover':
            raise operations.OperationError('periodic audit requires discovery-only batches')
        flow = flow_rows.get(entry['flow_id'])
        if flow is None:
            raise operations.OperationError('schedule refers to an invalid flow')
        if previous_flow_id is not None and flow['binding']['derived_from'] != previous_flow_id:
            raise operations.OperationError('periodic schedule has a broken flow lineage')
        previous_flow_id = entry['flow_id']
        name = flow['binding']['selector']['round']
        if name is None:
            raise operations.OperationError('periodic audit needs named rounds')
        if any(op not in events for op in entry['operation_ids']):
            raise operations.OperationError('schedule refers to a missing operation')
        states = [events[op][-1]['event'].upper() for op in entry['operation_ids']]
        query_ids = [events[op][0]['plan']['query']['query_id']
                     for op in entry['operation_ids']]
        successful_queries = sum(queries.get(query_id, {}).get('ok') is True
                                 for query_id in query_ids)
        rounds.append({'round': name, 'flow_id': entry['flow_id'],
                       'binding_state': flows.binding_state(project, store, flow)['state'],
                       'not_before': entry['not_before'], 'expires_at': entry['expires_at'],
                       'operations': dict((state, states.count(state)) for state in sorted(set(states))),
                       'successful_queries': successful_queries,
                       'planned_queries': len(query_ids),
                       'admission': admissibility.admit(project, store, round_name=name)})
    cumulative = admissibility.admit(project, store)
    # A floor reached by older work does not certify newly scheduled rounds.
    complete = (schedule['state'] == 'AUTHORIZED' and
                all(row['binding_state'] == 'CURRENT' and
                    (row['admission']['found'] == 0 or
                     (row['admission']['status'] == admissibility.OK and
                      row['admission']['final'])) for row in ancestors) and
                all(row['binding_state'] == 'CURRENT' and
                    row['operations'] == {'COMPLETED': len(schedule['plan']['entries'][index]['operation_ids'])} and
                    row['successful_queries'] == row['planned_queries'] and
                    (row['admission']['found'] == 0 or
                     (row['admission']['status'] == admissibility.OK and
                      row['admission']['final']))
                    for index, row in enumerate(rounds)) and
                cumulative['status'] == admissibility.OK and cumulative['final'])
    return {'schedule_id': schedule_id, 'schedule_state': schedule['state'],
            'ancestor_rounds': ancestors, 'rounds': rounds,
            'cumulative_admission': cumulative,
            'ready_for_evidence_review': complete, 'verdict': None}
