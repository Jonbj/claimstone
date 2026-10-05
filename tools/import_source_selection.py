#!/usr/bin/env python
"""Import frozen AI screening as append-only advisory observations.

Default is a read-only preview. --apply writes only source_screening.jsonl and
source_identity.jsonl. It never changes candidates, admission, or verdicts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone.config import load_project
from claimstone import ids, source_selection
from claimstone.store import Store
from tools import fetch_screening_abstracts as metadata_lookup

SOURCE_SELECTION_IMPORT_VERSION = 2


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def frozen(item: dict) -> bytes:
    path = Path(item['path'])
    data = path.read_bytes()
    if digest(data) != item['sha256']:
        raise ValueError(f'frozen input changed: {path}')
    return data


def _sha_file(path: Path, expected: str) -> bytes:
    data = path.read_bytes()
    if digest(data) != expected:
        raise ValueError(f'stored source bytes changed: {path}')
    return data


def extract_pdf_text(path: Path) -> str:
    """Recreate the frozen pdftotext -layout output from the held PDF bytes."""
    try:
        result = subprocess.run(['pdftotext', '-layout', str(path), '-'],
                                capture_output=True, check=True, timeout=60)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError('held PDF could not be independently extracted') from exc
    return result.stdout.decode('utf-8')


def prepare(plan_path: Path, *, store_base='store'):
    plan = json.loads(plan_path.read_bytes())
    if plan.get('version') not in {1, SOURCE_SELECTION_IMPORT_VERSION} or \
            not plan.get('scope_id') or not plan.get('question_id'):
        raise ValueError('versioned scope and question required')
    if (plan['version'] == 1 and 'replacement' in plan) or \
            (plan['version'] == SOURCE_SELECTION_IMPORT_VERSION and
             not isinstance(plan.get('replacement'), dict)):
        raise ValueError('replacement requires a version 2 import plan')
    project = load_project(plan['project'])
    if project.registry_sha256 != plan['registry_sha256'] or \
            digest((project.root / 'sources.yaml').read_bytes()) != plan['sources_sha256'] or \
            digest((project.root / 'questions.yaml').read_bytes()) != plan['questions_sha256']:
        raise ValueError('frozen project policy or registry changed')
    if plan['question_id'] not in project.question_ids:
        raise ValueError('question is absent from registry')
    inventory = json.loads(frozen(plan['inventory']))
    packet = json.loads(frozen(plan['packet']))
    ai = json.loads(frozen(plan['ai_screening']))
    override = json.loads(frozen(plan['fulltext_override']))
    fulltext = frozen(plan['fulltext_text']).decode('utf-8')
    if ai.get('label') != 'AI_PROVISIONAL' or ai.get('automatic_adoption') is not False:
        raise ValueError('screening output is not explicitly provisional')
    if ai.get('question_id') != plan['question_id'] or packet.get('question_id') != plan['question_id'] or \
            ai['input_packet']['sha256'] != plan['packet']['sha256'] or \
            packet['registry_sha256'] != plan['registry_sha256']:
        raise ValueError('AI output, packet and registry disagree')
    if len(ai['cases']) != plan['expected_cases'] or len(packet['cases']) != plan['expected_cases']:
        raise ValueError('screening batch size differs from frozen plan')
    by_key = {row['candidate_key']: row for row in packet['cases']}
    inventory_by_key = {row['candidate_key']: row for row in inventory}
    if len(by_key) != len(packet['cases']) or len(inventory_by_key) != len(inventory):
        raise ValueError('duplicate packet or inventory identity')
    if {row['candidate_key'] for row in ai['cases']} != set(by_key) or \
            len({row['candidate_key'] for row in ai['cases']}) != len(ai['cases']) or \
            not set(by_key) <= set(inventory_by_key):
        raise ValueError('AI, packet and inventory identities disagree')
    if not isinstance(packet.get('criteria'), dict) or not packet['criteria']:
        raise ValueError('packet criteria missing')

    store = Store(project.name, base=store_base)
    available_metadata = {}
    for record in store.read(metadata_lookup.LEDGER):
        if record.get('status') == 'ABSTRACT_AVAILABLE':
            available_metadata.setdefault(record.get('candidate_key'), []).append(record)
    rows = []
    ai_by_key = {row['candidate_key']: row for row in ai['cases']}
    for case in ai['cases']:
        key = case['candidate_key']
        source = by_key[key]
        if case.get('decision') not in source_selection.DECISIONS or not case.get('reason'):
            raise ValueError('invalid AI decision or reason')
        if not case.get('decisive_criteria') or any(c not in packet['criteria']
                                                   for c in case['decisive_criteria']):
            raise ValueError('AI decision cites unknown criteria')
        if not source.get('source_text') or source.get('metadata_status') != 'ABSTRACT_AVAILABLE':
            raise ValueError('AI observation lacks a checked abstract')
        if source.get('source_provider') not in {'openalex', 'crossref'}:
            raise ValueError('abstract source provider is not supported')
        if source.get('doi') and key != 'doi:' + ids.normalize_doi(source['doi']):
            raise ValueError('abstract DOI differs from candidate identity')
        if not source.get('doi') and (not key.startswith('title:') or
                                      key != 'title:' + ids.normalize_title(source.get('title')) or
                                      key != 'title:' + ids.normalize_title(
                                          inventory_by_key[key].get('title'))):
            raise ValueError('title-only abstract differs from candidate identity')
        raw_sha = source['source_raw_sha256']
        raw = _sha_file(store.path(f'requests/raw/{raw_sha}.bin'), raw_sha)
        matching = [record for record in available_metadata.get(key, [])
                    if record.get('raw_sha256') == raw_sha and
                    record.get('provider') == source.get('source_provider') and
                    record.get('abstract') == source['source_text'] and
                    record.get('candidate_title') == inventory_by_key[key].get('title') and
                    ids.normalize_doi(record.get('candidate_doi')) ==
                    ids.normalize_doi(inventory_by_key[key].get('doi'))]
        if not matching:
            raise ValueError(f'abstract lacks matching recorded metadata provenance: {key}')
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'raw abstract metadata is invalid: {key}') from exc
        status, reconstructed, title = metadata_lookup.assess(
            {'candidate': inventory_by_key[key]}, payload, SimpleNamespace(ok=True),
            source['source_provider'])
        if status != 'ABSTRACT_AVAILABLE' or reconstructed != source['source_text'] or \
                ids.normalize_title(title) != ids.normalize_title(source.get('title')):
            raise ValueError(f'abstract text or identity differs from raw metadata: {key}')
        quote_rows = case.get('quotes')
        if not isinstance(quote_rows, list) or not quote_rows:
            raise ValueError('AI assessment lacks evidence')
        evidence = []
        text_sha = digest(source['source_text'].encode())
        for quote in quote_rows:
            if not isinstance(quote.get('text'), str) or not quote['text'] or \
                    quote['text'] not in source['source_text']:
                raise ValueError(f'AI quote is absent from abstract: {key}')
            evidence.append({'quote': quote['text'], 'role': quote.get('role'),
                             'locator': f'packet:{plan["packet"]["sha256"]}:{key}',
                             'text_sha256': text_sha, 'metadata_sha256': raw_sha})
        decision = case['decision']
        role = ('DIRECT_CANDIDATE' if decision == 'INCLUDE' else
                'UNRESOLVED' if decision == 'UNCERTAIN' else 'NOT_DIRECT')
        source_class = inventory_by_key[key].get('source_class') or 'UNCLASSIFIED'
        row = source_selection.identified({
            'selection_version': source_selection.SOURCE_SELECTION_VERSION,
            'scope_id': plan['scope_id'], 'question_id': plan['question_id'],
            'registry_sha256': plan['registry_sha256'], 'candidate_key': key,
            'source_class': source_class, 'assessment_status': 'AI_PROVISIONAL',
            'decision': decision, 'role': role, 'screening_level': 'ABSTRACT',
            'criterion_ids': case['decisive_criteria'], 'reason': case['reason'],
            'assessed_by': 'Claude Code interactive', 'identity_status': 'UNVERIFIED',
            'input_sha256': plan['ai_screening']['sha256'], 'evidence': evidence,
            'model': ai['screener'].get('model') or 'unknown',
            'backend': 'claude-code-interactive',
            'harness_version': ai['screener'].get('harness_version') or 'unknown',
            'prompt_sha256': None,  # The interactive prompt was not saved as an exact file.
            'supersedes': None,
        }, 'assessment_id')
        source_selection.validate_screening(row)
        rows.append(row)

    key = override['candidate_key']
    if key not in ai_by_key or ai_by_key[key]['decision'] != 'UNCERTAIN' or \
            override.get('decision') != 'EXCLUDE' or override.get('role') != 'CONTEXT' or \
            override.get('screening_level') != 'FULLTEXT':
        raise ValueError('full-text override must refine an AI-uncertain case to context')
    if override['text_sha256'] != plan['fulltext_text']['sha256'] or \
            not override.get('criterion_ids') or any(c not in packet['criteria']
                                                     for c in override['criterion_ids']):
        raise ValueError('full-text text or criteria disagree with plan')
    pdf_path = store.path(f'requests/raw/{override["pdf_sha256"]}.bin')
    _sha_file(pdf_path, override['pdf_sha256'])
    if plan.get('fulltext_text', {}).get('extractor') != 'pdftotext -layout 26.01.0' or \
            extract_pdf_text(pdf_path) != fulltext:
        raise ValueError('frozen full text differs from held PDF extraction')
    raw_meta = _sha_file(store.path(f'requests/raw/{override["identity"]["metadata_sha256"]}.bin'),
                         override['identity']['metadata_sha256'])
    metadata = json.loads(raw_meta)
    if not isinstance(plan.get('copy_campaign'), str) or not plan['copy_campaign']:
        raise ValueError('held PDF requires a named copy campaign')
    outcomes_path = Path(plan['fulltext_override']['path']).parent / 'outcomes.jsonl'
    if not outcomes_path.is_file():
        raise ValueError('held PDF copy outcome ledger is missing')
    copy_outcomes = [row for row in Store(project.name, base=store_base).read(
        str(outcomes_path.relative_to(store.root)) if outcomes_path.is_relative_to(store.root)
        else str(outcomes_path))
        if row.get('campaign') == plan.get('copy_campaign') and row.get('candidate_key') == key]
    if not any(row.get('status') == 'FULLTEXT_BYTES' and
               row.get('raw_sha256') == override['pdf_sha256'] for row in copy_outcomes):
        raise ValueError('held PDF is not a confirmed byte outcome of the frozen copy campaign')
    if metadata.get('title') != override['identity']['metadata_title'] or \
            ids.normalize_doi(metadata.get('doi')) != key[4:] or \
            not any(loc.get('pdf_url') == override['identity']['copy_url']
                    for loc in metadata.get('locations', [])):
        raise ValueError('held-copy identity metadata changed')
    metadata_authors = {part.get('author', {}).get('display_name')
                        for part in metadata.get('authorships', [])}
    if metadata_authors and not set(override['identity']['pdf_authors']) <= metadata_authors:
        raise ValueError('held PDF authors differ from cached metadata')
    if not isinstance(override['identity'].get('pdf_title'), str) or \
            not override['identity']['pdf_title'].strip() or \
            override['identity']['pdf_title'] not in fulltext or \
            not override['identity'].get('pdf_authors') or \
            not all(name in fulltext for name in override['identity']['pdf_authors']):
        raise ValueError('held PDF title/authors absent from extracted text')
    evidence = []
    for quote in override['quotes']:
        if quote not in fulltext:
            raise ValueError('full-text quote absent from frozen extracted text')
        evidence.append({'quote': quote, 'locator': f'pdf:{override["pdf_sha256"]}',
                         'text_sha256': override['text_sha256'],
                         'copy_sha256': override['pdf_sha256']})
    prior = next(row for row in rows if row['candidate_key'] == key)
    override_row = source_selection.identified({
        'selection_version': source_selection.SOURCE_SELECTION_VERSION,
        'scope_id': plan['scope_id'], 'question_id': plan['question_id'],
        'registry_sha256': plan['registry_sha256'], 'candidate_key': key,
        'source_class': inventory_by_key[key].get('source_class') or 'UNCLASSIFIED',
        'assessment_status': 'AI_PROVISIONAL', 'decision': 'EXCLUDE', 'role': 'CONTEXT',
        'screening_level': 'FULLTEXT', 'criterion_ids': override['criterion_ids'],
        'reason': override['reason'], 'assessed_by': override['assessed_by'],
        'identity_status': 'POSSIBLE_VERSION', 'input_sha256': plan['fulltext_override']['sha256'],
        'evidence': evidence, 'model': 'unknown', 'backend': 'codex-interactive',
        'harness_version': 'unknown', 'prompt_sha256': None,
        'supersedes': prior['assessment_id'],
    }, 'assessment_id')
    source_selection.validate_screening(override_row)
    rows.append(override_row)
    identity = override['identity']
    identity_row = source_selection.identified({
        'selection_version': source_selection.SOURCE_SELECTION_VERSION,
        'scope_id': plan['scope_id'], 'candidate_key': key,
        'source_class': inventory_by_key[key].get('source_class') or 'UNCLASSIFIED',
        'status': identity['status'], 'reason': identity['reason'],
        'assessed_by': override['assessed_by'], 'metadata_title': identity['metadata_title'],
        'copy_title': identity['pdf_title'], 'metadata_sha256': identity['metadata_sha256'],
        'copy_sha256': override['pdf_sha256'], 'observations': identity['observations'],
        'supersedes': None,
    }, 'observation_id')
    source_selection.validate_identity(identity_row)
    if plan['version'] == SOURCE_SELECTION_IMPORT_VERSION:
        replacement = plan['replacement']
        previous_ids = replacement.get('previous_assessment_ids')
        preserved = replacement.get('preserved_fulltext')
        expected_replace = set(ai_by_key) - {key}
        if not isinstance(previous_ids, dict) or set(previous_ids) != expected_replace or \
                not isinstance(preserved, dict) or set(preserved) != {key}:
            raise ValueError('replacement must explicitly cover every abstract and held full text')
        if ai_by_key[key]['decision'] != 'UNCERTAIN':
            raise ValueError('new AI decision conflicts with preserved full-text assessment')
        current, _ = source_selection._replay(store.read(source_selection.SCREENING_LEDGER),
                                              [], identity=False)
        updated = []
        for row in rows[:-1]:
            candidate = row['candidate_key']
            active = current.get((plan['scope_id'], plan['question_id'], candidate))
            if candidate == key:
                if not active or active['assessment_id'] != preserved[candidate] or \
                        active['screening_level'] != 'FULLTEXT' or \
                        active['role'] != 'CONTEXT' or not any(
                            e.get('copy_sha256') == override['pdf_sha256']
                            for e in active['evidence']):
                    raise ValueError('preserved full-text assessment is stale or differs from held copy')
                continue
            replacement_row = source_selection.identified(
                {**row, 'supersedes': previous_ids[candidate]}, 'assessment_id')
            source_selection.validate_screening(replacement_row)
            if active and active['assessment_id'] == replacement_row['assessment_id']:
                updated.append(replacement_row)
                continue
            if not active or active['assessment_id'] != previous_ids[candidate] or \
                    active['screening_level'] != 'ABSTRACT' or \
                    active['input_sha256'] == plan['ai_screening']['sha256']:
                raise ValueError(f'explicit abstract supersession is stale or unchanged: {candidate}')
            updated.append(replacement_row)
        return plan, store, set(inventory_by_key), updated, []
    return plan, store, set(inventory_by_key), rows, [identity_row]


def run(plan_path: Path, *, apply=False, store_base='store') -> dict:
    plan, store, inventory_keys, rows, identity = prepare(plan_path, store_base=store_base)
    before = source_selection.preview(store, plan['scope_id'], plan['question_id'],
                                      inventory_keys, rows, identity)
    written = ({'screening_rows_written': 0, 'identity_rows_written': 0}
               if not apply else source_selection.append_observations(
                   store, rows, identity, scope_id=plan['scope_id'],
                   question_id=plan['question_id'], inventory_keys=inventory_keys))
    after = (before if not apply else source_selection.preview(
        store, plan['scope_id'], plan['question_id'], inventory_keys))
    return {**{k: v for k, v in after.items() if k != 'pending_keys'},
            'pending_examples': after['pending_keys'][:10],
            'preserved_fulltext_keys': sorted(plan.get('replacement', {}).get(
                'preserved_fulltext', {})),
            'provisional_uncertain_keys': sorted(
                {row['candidate_key'] for row in rows if row['decision'] == 'UNCERTAIN'} -
                {row['candidate_key'] for row in rows if row['screening_level'] == 'FULLTEXT'}),
            'manual_prior_audit_imported': False, 'network_requests': 0,
            'model_calls': 0, 'written': written,
            'would_write': {'screening': before['new_screening_rows'],
                            'identity': before['new_identity_rows']} if not apply else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(Path(args.plan), apply=args.apply), indent=2))


if __name__ == '__main__':
    main()
