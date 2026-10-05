#!/usr/bin/env python
"""Build an offline reading dossier from explicitly curated passages, without scientific ledger writes.

Mechanical quote verification does not certify applicability, synthesis or a question verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import admissibility, chunk_sets, claimgate
from claimstone.config import load_project, check_registry_drift
from claimstone.store import Store
from tools.replay_answers import files_snapshot, validate_history


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(project, store, plan):
    if plan['registry_sha256'] != project.registry_sha256:
        raise ValueError('dossier registry changed')
    check_registry_drift(project, store, record=False)
    question = next(q for q in project.questions if q.id == plan['question_id'])
    admission = admissibility.admit(project, store, round_name=plan['round'])
    if admission['status'] != admissibility.OK:
        raise ValueError('acquisition floor blocks this reading dossier')
    chunks = chunk_sets.current(store)
    documents = store.latest_by('documents.jsonl', 'source_id')
    manifest = {m.source_id: m for m in project.manifest}
    passages = plan['passages']
    if not passages or len({p['id'] for p in passages}) != len(passages):
        raise ValueError('unique curated passages required')
    readings = []
    for passage in passages:
        chunk = chunks.get(passage['chunk_id'])
        if chunk is None or sha(chunk['text'].encode()) != passage['text_sha256']:
            raise ValueError('curated passage changed or missing')
        document = documents[chunk['source_id']]
        if document['sha256'] != passage['document_sha256']:
            raise ValueError('source document changed')
        record = passage['record']
        if record['question_id'] != question.id:
            raise ValueError('curated passage addresses another question')
        result = claimgate.check(record, chunk=chunk['text'], questions=project.questions,
            lane=question.kind, comparatives=project.extraction.get('comparatives'))
        if not result.ok:
            raise ValueError(f"{passage['id']}: {result.failure}: {result.detail}")
        source = manifest[chunk['source_id']]
        if source.source_class != document['source_class']:
            raise ValueError('source class changed')
        readings.append({**passage, 'source_id': chunk['source_id'],
            'source_class': document['source_class'], 'title': source.title, 'url': source.url,
            'section': chunk['section'], 'full_passage': chunk['text'],
            'mechanical_gate_version': claimgate.CLAIM_GATE_VERSION, 'mechanical_gate_passed': True})
    return {'status': 'consultative_reading_not_profile_or_adjudication',
        'question_id': question.id, 'question_text': question.text, 'title': plan['title'],
        'curation': plan['curation'], 'scope_note': plan['scope_note'], 'summary_it': plan['summary_it'],
        'next_steps_it': plan['next_steps_it'], 'registry_sha256': project.registry_sha256,
        'admission': admission,
        'selected_sources': len({p['source_id'] for p in readings}),
        'selected_chunks': len({p['chunk_id'] for p in readings}), 'verified_passages': len(readings),
        'model_calls': 0, 'production_ledger_rows_written': 0, 'readings': readings}


def markdown(report):
    lines = ['# '+report['title'], '', report['summary_it'], '',
        '**Lettura consultiva: nessun verdetto firmato e nessun profilo completo.**', '',
        report['scope_note'], '', f"Fonti selezionate: {report['selected_sources']}; passaggi verificati: {report['verified_passages']}.",
        'Sono estratti selezionati, non una lettura integrale dei paper o una ricerca esaustiva.', '',
        '## Evidenze e limiti', '']
    for p in report['readings']:
        lines += ['### '+p['id']+' — '+p['label_it'], '', p['note_it'], '',
            f"Fonte: [{p['title']}]({p['url']}) · classe {p['source_class']} · sezione {p['section']}.", '',
            '> '+p['record']['evidence_quote'].replace('\n', '\n> '), '',
            'Identità del passaggio: `'+p['chunk_id']+'`.', '']
    admission = report['admission']
    lines += ['## Copertura e verifiche', '',
        f"Il giro di acquisizione ha {admission['confirmed']}/{admission['found']} fonti confermate. "
        + 'Blocchi ancora aperti: '+', '.join(admission['blocking'])+'.',
        'Il campione di lettura non modifica il denominatore del corpus e non chiude quei blocchi.',
        'Le citazioni e le cifre dei record passano il gate meccanico; la rilevanza e le note sono valutazioni consultive.',
        'Autore e modalità: '+report['curation']+'. Nessuna nuova chiamata a modelli.', '',
        '## Passi successivi', '', *['- '+s for s in report['next_steps_it']], '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    body = Path(args.plan).read_bytes(); plan = json.loads(body)
    project = load_project(plan['project']); store = Store(project.name, base=plan['store'])
    before = files_snapshot(store)
    report = {**build(project, store, plan), 'plan_sha256': sha(body)}
    if args.write:
        data = json.dumps(report, indent=2, sort_keys=True)+'\n'
        path = store.path('audits/consultative/'+sha(data.encode())+'.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        for target, content in ((path, data), (path.with_suffix('.md'), markdown(report))):
            if target.exists() and target.read_text() != content:
                raise ValueError('existing dossier bytes changed')
            if not target.exists(): target.write_text(content)
        report['dossier_path'] = str(path.with_suffix('.md'))
        allowed = {str(p.relative_to(store.root)) for p in (path, path.with_suffix('.md'))}
        validate_history(store, before, allowed)
    elif files_snapshot(store) != before:
        raise RuntimeError('offline preview changed the store')
    print(json.dumps({k: v for k, v in report.items() if k != 'readings'}, indent=2))
    return 0


if __name__ == '__main__': raise SystemExit(main())
