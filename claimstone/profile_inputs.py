"""The declared population and the current readings that a profile may describe.

Read-only: completeness is derived from current chunks and prompts, rather than all historical
experiments in calls/. A valid empty answer is a reading; a terminal failure is not.
"""
from __future__ import annotations

from typing import Any

from . import chunk_sets, admissibility, claim_records, claimgate, evidence, extract, model_call, review, scope
from .config import Project
from .store import Store


def population(store: Store, *, round_name: str | None, manifest_only: bool) -> set[str]:
    # The one predicate, in the one place (claimstone/scope.py): a second copy here is how the
    # profile's population and the portal's population would come to disagree.
    return scope.source_ids(store, scope.Selector(round_name, manifest_only))


def collect(project: Project, store: Store, *, round_name: str | None,
            manifest_only: bool) -> dict[str, Any]:
    sources = population(store, round_name=round_name, manifest_only=manifest_only)
    documents = {str(key): row for key, row in
                 store.latest_by('documents.jsonl', 'source_id').items() if str(key) in sources}
    acquired = {str(row.get('source_id') or key)
                for key, row in admissibility.collapse(store).items() if row.get('acquired')}
    confirmed = {key for key, row in documents.items()
                 if row.get('fulltext_confirmed') and key in acquired}
    chunks = {str(key): row for key, row in chunk_sets.current(store).items()
              if str(row.get('source_id')) in confirmed}

    def current(row: dict[str, Any]) -> bool:
        return (str(row.get('source_id')) in confirmed
                and row.get('registry_version') == project.registry_version
                and (not row.get('registry_sha256')
                     or row['registry_sha256'] == project.registry_sha256))

    active_claims, active_rejections = claim_records.current(store)
    claims = [dict(row) for row in active_claims.values() if current(row)]
    accepted = {str(row['claim_id']) for row in claims}
    rejections = [row for row in active_rejections.values()
                  if current(row) and str(row.get('claim_id')) not in accepted]
    review_requests = {}
    for path in sorted(store.path('calls/review').glob('*/requests.jsonl')):
        review_requests.update(store.latest_by(str(path.relative_to(store.root)), 'call_id'))
    claim_questions = {str(row['claim_id']): str(row.get('question_id')) for row in claims}

    def current_review(key: str, row: dict[str, Any]) -> bool:
        if str(row.get('question_id')) != claim_questions[key]:
            return False
        version = row.get('registry_version')
        if row.get('call_id'):
            version = (review_requests.get(str(row['call_id'])) or {}).get('registry_version')
            if version is None:
                return False
        return version is None or version == project.registry_version

    reviews = {str(key): dict(row) for key, row in
               review.current(store).items()
               if str(key) in accepted and current_review(str(key), row)}
    harvested = {}
    for row in claims + rejections:
        key = (str(row.get('chunk_id')), str(row.get('call_id')),
               str(row.get('backend')), str(row.get('model')))
        harvested.setdefault(key, []).append(row)

    requests: dict[tuple[str, str], list[tuple[dict[str, Any], list[dict[str, Any]]]]] = {}
    for path in sorted(store.path('calls/extract').glob('*/requests.jsonl')):
        queue = model_call.Queue(store, lane='extract', batch=path.parent.name)
        results: dict[str, list[dict[str, Any]]] = {}
        for result in queue.results().values():
            results.setdefault(str(result.get('call_id')), []).append(result)
        for unit in queue.requests():
            if unit.get('registry_version') != project.registry_version:
                continue
            if unit.get('registry_sha256') and unit['registry_sha256'] != project.registry_sha256:
                continue
            for asker in unit.get('asked_by') or [unit]:
                key = (str(asker.get('chunk_id')), str(unit.get('kind')))
                requests.setdefault(key, []).append((unit, results.get(str(unit['call_id']), [])))

    question_kinds = {str(q.id): q.kind for q in project.questions}

    def record_kind(row: dict[str, Any]) -> str:
        question_id = (row.get('record') or {}).get('question_id') or row.get('question_id')
        return str(row.get('lane') or question_kinds.get(str(question_id), ''))

    completion: dict[str, dict[str, int]] = {}
    for kind in sorted({q.kind for q in project.questions if q.kind in extract.KINDS}):
        questions = [q for q in project.questions if q.kind == kind]
        system = extract.system_prompt(kind, questions)
        schema = extract.response_schema(kind, questions)
        bucket = {'expected': len(chunks), 'unanswered': 0, 'unharvested': 0,
                  'unchunked_sources': len(confirmed - {str(c.get('source_id')) for c in chunks.values()}),
                  'unregated': sum(1 for row in claims + rejections if record_kind(row) == kind
                                   and row.get('claim_gate_version', 1) != claimgate.CLAIM_GATE_VERSION)}
        for chunk_id, chunk in chunks.items():
            answers = [result for unit, results in requests.get((chunk_id, kind), [])
                       if unit.get('system') == system and unit.get('user') == chunk.get('text')
                       and unit.get('response_schema') == schema
                       for result in results if result.get('ok') and isinstance(result.get('output'), list)]
            if not answers:
                bucket['unanswered'] += 1
                continue
            # At least one valid reader must have reached the gate. Old probe batches need not
            # complete, and an alternative reader's failure does not erase a completed reading.
            def gated(result: dict[str, Any]) -> bool:
                annotations = harvested.get((chunk_id, str(result.get('call_id')),
                                             str(result.get('backend')), str(result.get('model'))), [])
                return all(any(claim_records.matches(row, record) for row in annotations)
                           for record in result['output'])
            if not any(gated(result) for result in answers):
                bucket['unharvested'] += 1
        completion[kind] = bucket
    # Hash the annotations too: a changed review rationale or a rejected record can matter to
    # an adjudicator even when the visible counts happen to stay equal. Wall clocks do not.
    def semantic(row: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in row.items()
                if key not in ('harvested_at', 'reviewed_at', 'created_at')}

    evidence_sha256 = {}
    for question in project.questions:
        mine = [row for row in claims if str(row.get('question_id')) == str(question.id)]
        identifiers = {str(row['claim_id']) for row in mine}
        rejected = [row for row in rejections
                    if str((row.get('record') or {}).get('question_id') or row.get('question_id'))
                    == str(question.id)]
        evidence_sha256[str(question.id)] = evidence._digest({
            'claims': sorted((semantic(row) for row in mine), key=lambda row: str(row['claim_id'])),
            'reviews': {key: semantic(row) for key, row in reviews.items() if key in identifiers},
            'rejections': sorted((semantic(row) for row in rejected),
                                 key=lambda row: str(row.get('claim_id'))),
            'chunks': {key: semantic(row) for key, row in chunks.items()},
        })
    return {'sources': sorted(sources), 'chunks': chunks, 'claims': claims, 'reviews': reviews,
            'rejections': rejections, 'completion': completion,
            'examined': len({str(row.get('source_id')) for row in chunks.values()}),
            'evidence_sha256': evidence_sha256}
