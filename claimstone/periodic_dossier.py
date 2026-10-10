"""Whole-corpus evidence handoff for a finite periodic discovery schedule.

The live view is read-only. Finalization appends a content-addressed snapshot
only after the schedule, acquisition gate and every scientific profile are final.
It never supplies or signs a verdict.
"""

from __future__ import annotations

from typing import Any

from claimstone import evidence, flows, network_schedule, operations, periodic, synthesize
from claimstone.config import Project
from claimstone.store import Store

LEDGER = 'periodic_dossiers.jsonl'
VERSION = 1
READY = 'READY_FOR_HUMAN_READING'


def _history(store: Store, schedule_id: str) -> list[dict[str, Any]]:
    rows = []
    for row in store.read(LEDGER):
        if (row.get('version') != VERSION or
                row.get('dossier_id') != operations._digest(row.get('snapshot'))):
            raise operations.OperationError('invalid periodic dossier row')
        if row.get('schedule_id') == schedule_id:
            rows.append(row)
    return rows


def preview(project: Project, store: Store, schedule_id: str) -> dict[str, Any]:
    """Recompute the cumulative handoff from current ledgers without writing."""
    audit = periodic.audit(project, store, schedule_id)
    profiles: list[dict[str, Any]] = []
    blockers: list[str] = []
    if not audit['ready_for_evidence_review']:
        blockers.append('SCHEDULE_OR_ROUND_INCOMPLETE')
    try:
        profiles, _ = synthesize.preview(project, store)
    except synthesize.NotAdmissible:
        blockers.append('INSUFFICIENT_CUMULATIVE_ACQUISITION')
    if profiles and any(row.get('provisional') for row in profiles
                        if row.get('state') != evidence.NOT_APPLICABLE):
        blockers.append('INCOMPLETE_CUMULATIVE_EVIDENCE')
    if not profiles:
        blockers.append('NO_ADMISSIBLE_PROFILE')
    # This snapshot excludes human signatures. Signing changes the decision
    # display, never the evidence a person was shown.
    snapshot = {
        'version': VERSION, 'schedule_id': schedule_id,
        'registry_version': project.registry_version,
        'registry_sha256': project.registry_sha256,
        'protocol_sha256': flows.protocol_digest(project),
        'audit_sha256': operations._digest(audit),
        'profile_sha256': {str(row['question_id']): row['profile_sha256']
                           for row in profiles},
    }
    history = _history(store, schedule_id)
    last = history[-1] if history else None
    decisions = synthesize.verdicts(store, project=project)['rows']
    decision_by_question = {str(row['profile']['question_id']): {
        'question_id': str(row['profile']['question_id']),
        'verdict': row['verdict'], 'stale': row['stale'],
        'stored_profile_stale': row['stored_profile_stale'],
        'unavailable': row['unavailable'],
    } for row in decisions}
    state = READY if not blockers else (
        'INSUFFICIENT_ACQUISITION'
        if 'INSUFFICIENT_CUMULATIVE_ACQUISITION' in blockers else
        'WAITING_FOR_SCHEDULE' if 'SCHEDULE_OR_ROUND_INCOMPLETE' in blockers else
        'WAITING_FOR_EVIDENCE')
    return {
        'schedule_id': schedule_id, 'state': state, 'blockers': blockers,
        'audit': audit, 'profiles': profiles,
        'human_decisions': [decision_by_question.get(question_id, {
            'question_id': question_id, 'verdict': None,
            'stale': False, 'stored_profile_stale': False, 'unavailable': '',
        }) for question_id in sorted(set(decision_by_question) | {
            str(row['question_id']) for row in profiles})],
        'snapshot_sha256': operations._digest(snapshot),
        'finalized_dossier_id': last['dossier_id'] if last else None,
        'finalized_at': last['at'] if last else None,
        'snapshot_stale': bool(last and last['dossier_id'] != operations._digest(snapshot)),
        'needs_finalization': state == READY and
                              (last is None or last['dossier_id'] != operations._digest(snapshot)),
        'history_count': len(history),
        'verdict': None,
    }


def finalize(project: Project, store: Store, schedule_id: str) -> dict[str, Any]:
    """Persist final cumulative profiles and a snapshot, idempotently."""
    with store.writer_lock():
        report = preview(project, store, schedule_id)
        if report['state'] != READY or not report['needs_finalization']:
            return report
        stored = synthesize.latest_profiles(store)
        if any(stored.get(str(row['question_id']), {}).get('profile_sha256') != row['profile_sha256']
               for row in report['profiles']):
            synthesize.build(project, store)
        # Recompute after writes; a content hash is never inferred from a
        # pre-write view, even when profile bytes are expected to match.
        report = preview(project, store, schedule_id)
        if report['state'] != READY:
            return report
        snapshot = {
            'version': VERSION, 'schedule_id': schedule_id,
            'registry_version': project.registry_version,
            'registry_sha256': project.registry_sha256,
            'protocol_sha256': flows.protocol_digest(project),
            'audit_sha256': operations._digest(report['audit']),
            'profile_sha256': {str(row['question_id']): row['profile_sha256']
                               for row in report['profiles']},
        }
        dossier_id = operations._digest(snapshot)
        if report['needs_finalization']:
            store.append(LEDGER, {'version': VERSION, 'schedule_id': schedule_id,
                                  'dossier_id': dossier_id, 'snapshot': snapshot,
                                  'at': operations._now()})
        return preview(project, store, schedule_id)


def due_for_flow(store: Store, flow_id: str) -> list[str]:
    """Only discovery schedules whose dated child flow the mandate is driving."""
    held = flows.flows(store)
    result = []
    for schedule_id, rows in network_schedule._read(store).items():
        entries = rows[0]['plan']['entries']
        if (all(entry['stage'] == 'discover' for entry in entries) and
                any(entry['flow_id'] == flow_id for entry in entries) and
                held.get(entries[0]['flow_id'], {}).get('binding', {}).get('derived_from')):
            result.append(schedule_id)
    return sorted(result)
