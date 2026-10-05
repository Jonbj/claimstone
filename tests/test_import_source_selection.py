"""Frozen AI output is checked against original text before entering advisory ledgers."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import import_source_selection as importer


def _write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False).encode() if not isinstance(value, bytes) else value
    path.write_bytes(data)
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest()}


def _pdf(text: str) -> bytes:
    stream = f'BT /F1 12 Tf 72 720 Td ({text}) Tj ET'.encode()
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream',
    ]
    data = b'%PDF-1.4\n'
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(data))
        data += f'{index} 0 obj\n'.encode() + body + b'\nendobj\n'
    start = len(data)
    data += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    for offset in offsets[1:]:
        data += f'{offset:010d} 00000 n \n'.encode()
    return data + f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()


def _fixture(tmp_path, monkeypatch):
    registry = 'a' * 64
    project_root = tmp_path / 'project'
    project_root.mkdir()
    (project_root / 'sources.yaml').write_text('classes: []')
    (project_root / 'questions.yaml').write_text('questions: []')
    monkeypatch.setattr(importer, 'load_project', lambda _: SimpleNamespace(
        root=project_root, name='fixture', registry_sha256=registry,
        question_ids={'Q1'}))
    store_base = tmp_path / 'store'
    raw = store_base / 'fixture/requests/raw'
    raw.mkdir(parents=True)
    metadata = {'title': 'Metadata title', 'doi': 'https://doi.org/10.1234/a',
                'abstract_inverted_index': {'Abstract': [0], 'says': [1],
                                            'weekly': [2], 'sector': [3], 'returns.': [4]},
                'locations': [{'pdf_url': 'https://school.example/a.pdf'}]}
    metadata_bytes = json.dumps(metadata).encode()
    meta_sha = hashlib.sha256(metadata_bytes).hexdigest()
    (raw / (meta_sha + '.bin')).write_bytes(metadata_bytes)
    pdf = _pdf('PDF title Author X Weekly sector index returns from newspaper text.')
    pdf_sha = hashlib.sha256(pdf).hexdigest()
    (raw / (pdf_sha + '.bin')).write_bytes(pdf)
    text = importer.extract_pdf_text(raw / (pdf_sha + '.bin'))
    inventory = _write(tmp_path / 'inventory.json', [{'candidate_key': 'doi:10.1234/a',
                                                       'doi': '10.1234/a',
                                                       'title': 'Metadata title',
                                                       'source_class': None}])
    screening_row = {'candidate_key': 'doi:10.1234/a', 'provider': 'openalex',
                     'candidate_doi': '10.1234/a', 'candidate_title': 'Metadata title',
                     'status': 'ABSTRACT_AVAILABLE', 'raw_sha256': meta_sha,
                     'abstract': 'Abstract says weekly sector returns.'}
    (store_base / 'fixture/screening_metadata.jsonl').write_text(json.dumps(screening_row) + '\n')
    packet = _write(tmp_path / 'packet.json', {
        'question_id': 'Q1', 'registry_sha256': registry, 'criteria': {'C1': {'description': 'unit'}},
        'cases': [{'candidate_key': 'doi:10.1234/a', 'doi': '10.1234/a',
                   'metadata_status': 'ABSTRACT_AVAILABLE',
                   'title': 'Metadata title', 'source_provider': 'openalex',
                   'source_text': 'Abstract says weekly sector returns.',
                   'source_raw_sha256': meta_sha}],
    })
    ai = _write(tmp_path / 'ai.json', {
        'label': 'AI_PROVISIONAL', 'automatic_adoption': False,
        'question_id': 'Q1', 'input_packet': {'sha256': packet['sha256']},
        'screener': {'model': 'test-model', 'harness_version': 'test-1'},
        'cases': [{'candidate_key': 'doi:10.1234/a', 'decision': 'UNCERTAIN',
                   'decisive_criteria': ['C1'], 'reason': 'unit unclear',
                   'quotes': [{'role': 'unit', 'text': 'weekly sector returns'}]}],
    })
    override = _write(tmp_path / 'override.json', {
        'candidate_key': 'doi:10.1234/a', 'decision': 'EXCLUDE', 'role': 'CONTEXT',
        'screening_level': 'FULLTEXT', 'assessed_by': 'test agent',
        'criterion_ids': ['C1'], 'reason': 'sector, not firm',
        'pdf_sha256': pdf_sha, 'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'quotes': ['Weekly sector index returns'],
        'identity': {'status': 'POSSIBLE_VERSION', 'metadata_sha256': meta_sha,
                     'metadata_title': 'Metadata title', 'copy_url': 'https://school.example/a.pdf',
                     'pdf_title': 'PDF title', 'pdf_authors': ['Author X'],
                     'reason': 'title differs', 'observations': ['metadata title', 'PDF title']},
    })
    text_file = _write(tmp_path / 'fulltext.txt', text.encode())
    outcomes = {'campaign': 'fixture-copy', 'candidate_key': 'doi:10.1234/a',
                'status': 'FULLTEXT_BYTES', 'raw_sha256': pdf_sha}
    (tmp_path / 'outcomes.jsonl').write_text(json.dumps(outcomes) + '\n')
    plan = {'version': 1, 'project': str(project_root), 'scope_id': 'fixture-v1',
            'copy_campaign': 'fixture-copy',
            'question_id': 'Q1', 'expected_cases': 1, 'registry_sha256': registry,
            'sources_sha256': hashlib.sha256((project_root / 'sources.yaml').read_bytes()).hexdigest(),
            'questions_sha256': hashlib.sha256((project_root / 'questions.yaml').read_bytes()).hexdigest(),
            'inventory': inventory, 'packet': packet, 'ai_screening': ai,
            'fulltext_override': override,
            'fulltext_text': {**text_file, 'extractor': 'pdftotext -layout 26.01.0'}}
    plan_path = tmp_path / 'plan.json'
    plan_path.write_text(json.dumps(plan))
    return plan_path, store_base, plan


def test_import_is_read_only_by_default_and_idempotent_when_applied(tmp_path, monkeypatch):
    plan_path, store_base, _ = _fixture(tmp_path, monkeypatch)
    preview = importer.run(plan_path, store_base=store_base)
    assert preview['would_write'] == {'screening': 2, 'identity': 1}
    assert preview['provisional_context'] == 1 and preview['admitted_candidates'] == 0
    assert not (store_base / 'fixture/source_screening.jsonl').exists()
    applied = importer.run(plan_path, apply=True, store_base=store_base)
    assert applied['written'] == {'screening_rows_written': 2, 'identity_rows_written': 1}
    assert importer.run(plan_path, apply=True, store_base=store_base)['written'] == {
        'screening_rows_written': 0, 'identity_rows_written': 0}
    assert not (store_base / 'fixture/candidates.jsonl').exists()
    assert not (store_base / 'fixture/acquisitions.jsonl').exists()


def test_import_refuses_an_exact_quote_not_in_source(tmp_path, monkeypatch):
    plan_path, store_base, plan = _fixture(tmp_path, monkeypatch)
    ai_path = Path(plan['ai_screening']['path'])
    ai = json.loads(ai_path.read_text())
    ai['cases'][0]['quotes'][0]['text'] = 'invented passage'
    plan['ai_screening'] = _write(ai_path, ai)
    plan_path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='quote is absent'):
        importer.run(plan_path, apply=True, store_base=store_base)
    assert not (store_base / 'fixture/source_screening.jsonl').exists()


def test_import_refuses_packet_text_unrelated_to_raw_metadata(tmp_path, monkeypatch):
    plan_path, store_base, plan = _fixture(tmp_path, monkeypatch)
    packet_path = Path(plan['packet']['path'])
    packet = json.loads(packet_path.read_text())
    packet['cases'][0]['source_text'] = 'Totally unrelated invented abstract.'
    plan['packet'] = _write(packet_path, packet)
    ai_path = Path(plan['ai_screening']['path'])
    ai = json.loads(ai_path.read_text())
    ai['input_packet']['sha256'] = plan['packet']['sha256']
    ai['cases'][0]['quotes'] = [{'role': 'unit', 'text': 'invented abstract'}]
    plan['ai_screening'] = _write(ai_path, ai)
    plan_path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='metadata provenance|raw metadata'):
        importer.run(plan_path, apply=True, store_base=store_base)
    assert not (store_base / 'fixture/source_screening.jsonl').exists()


def test_import_refuses_missing_campaign_and_unrelated_pdf_text(tmp_path, monkeypatch):
    plan_path, store_base, plan = _fixture(tmp_path, monkeypatch)
    plan.pop('copy_campaign')
    plan_path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='named copy campaign'):
        importer.run(plan_path, store_base=store_base)
    plan['copy_campaign'] = 'fixture-copy'
    changed = 'PDF title Author X Weekly sector index returns from invented text.'
    plan['fulltext_text'] = {**_write(Path(plan['fulltext_text']['path']), changed.encode()),
                             'extractor': 'pdftotext -layout 26.01.0'}
    override_path = Path(plan['fulltext_override']['path'])
    override = json.loads(override_path.read_text())
    override['text_sha256'] = plan['fulltext_text']['sha256']
    plan['fulltext_override'] = _write(override_path, override)
    plan_path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='differs from held PDF'):
        importer.run(plan_path, store_base=store_base)


def test_import_refuses_missing_copy_outcome_and_empty_pdf_title(tmp_path, monkeypatch):
    plan_path, store_base, plan = _fixture(tmp_path, monkeypatch)
    Path(plan['fulltext_override']['path']).with_name('outcomes.jsonl').write_text('')
    with pytest.raises(ValueError, match='confirmed byte outcome'):
        importer.run(plan_path, store_base=store_base)
    override_path = Path(plan['fulltext_override']['path'])
    outcomes = {'campaign': 'fixture-copy', 'candidate_key': 'doi:10.1234/a',
                'status': 'FULLTEXT_BYTES',
                'raw_sha256': json.loads(override_path.read_text())['pdf_sha256']}
    override_path.with_name('outcomes.jsonl').write_text(json.dumps(outcomes) + '\n')
    override = json.loads(override_path.read_text())
    override['identity']['pdf_title'] = ''
    plan['fulltext_override'] = _write(override_path, override)
    plan_path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='title/authors absent'):
        importer.run(plan_path, store_base=store_base)


def test_explicit_rescreen_supersedes_abstract_and_preserves_fulltext(tmp_path, monkeypatch):
    plan_path, store_base, plan = _fixture(tmp_path, monkeypatch)
    key = 'doi:10.1234/b'
    metadata = {'title': 'Other title', 'doi': 'https://doi.org/10.1234/b',
                'abstract_inverted_index': {'Other': [0], 'abstract': [1],
                                            'about': [2], 'returns.': [3]}}
    raw = _write(store_base / 'fixture/requests/raw/other.bin', metadata)
    raw_path = Path(raw['path'])
    raw_path.rename(raw_path.with_name(raw['sha256'] + '.bin'))
    ledger = store_base / 'fixture/screening_metadata.jsonl'
    with ledger.open('a') as handle:
        handle.write(json.dumps({'candidate_key': key, 'provider': 'openalex',
                                 'candidate_doi': '10.1234/b', 'candidate_title': 'Other title',
                                 'status': 'ABSTRACT_AVAILABLE', 'raw_sha256': raw['sha256'],
                                 'abstract': 'Other abstract about returns.'}) + '\n')
    inventory_path = Path(plan['inventory']['path'])
    inventory = json.loads(inventory_path.read_text())
    inventory.append({'candidate_key': key, 'doi': '10.1234/b',
                      'title': 'Other title', 'source_class': None})
    plan['inventory'] = _write(inventory_path, inventory)
    packet_path = Path(plan['packet']['path'])
    packet = json.loads(packet_path.read_text())
    packet['cases'].append({'candidate_key': key, 'doi': '10.1234/b',
                            'title': 'Other title', 'source_provider': 'openalex',
                            'metadata_status': 'ABSTRACT_AVAILABLE',
                            'source_text': 'Other abstract about returns.',
                            'source_raw_sha256': raw['sha256']})
    plan['packet'] = _write(packet_path, packet)
    ai_path = Path(plan['ai_screening']['path'])
    ai = json.loads(ai_path.read_text())
    ai['input_packet']['sha256'] = plan['packet']['sha256']
    ai['cases'].append({'candidate_key': key, 'decision': 'EXCLUDE',
                        'decisive_criteria': ['C1'], 'reason': 'other reason',
                        'quotes': [{'role': 'exclusion', 'text': 'Other abstract'}]})
    plan['ai_screening'] = _write(ai_path, ai)
    plan['expected_cases'] = 2
    plan_path.write_text(json.dumps(plan))
    assert importer.run(plan_path, apply=True, store_base=store_base)['written'] == {
        'screening_rows_written': 3, 'identity_rows_written': 1}
    ledger_path = store_base / 'fixture/source_screening.jsonl'
    current = {row['candidate_key']: row for row in map(json.loads, ledger_path.read_text().splitlines())}

    ai['review_note'] = 'new frozen AI output'
    plan['ai_screening'] = _write(ai_path, ai)
    plan['version'] = importer.SOURCE_SELECTION_IMPORT_VERSION
    plan['replacement'] = {
        'previous_assessment_ids': {key: current[key]['assessment_id']},
        'preserved_fulltext': {'doi:10.1234/a': current['doi:10.1234/a']['assessment_id']},
    }
    plan_path.write_text(json.dumps(plan))
    assert importer.run(plan_path, store_base=store_base)['would_write'] == {
        'screening': 1, 'identity': 0}
    assert importer.run(plan_path, apply=True, store_base=store_base)['written'] == {
        'screening_rows_written': 1, 'identity_rows_written': 0}
    assert importer.run(plan_path, apply=True, store_base=store_base)['written'] == {
        'screening_rows_written': 0, 'identity_rows_written': 0}
    rows = list(map(json.loads, ledger_path.read_text().splitlines()))
    assert rows[-1]['supersedes'] == current[key]['assessment_id']
    assert current['doi:10.1234/a']['assessment_id'] == rows[-2]['assessment_id']


def test_rescreen_rejects_stale_explicit_link(tmp_path, monkeypatch):
    plan_path, store_base, plan = _fixture(tmp_path, monkeypatch)
    importer.run(plan_path, apply=True, store_base=store_base)
    ai_path = Path(plan['ai_screening']['path'])
    ai = json.loads(ai_path.read_text())
    ai['review_note'] = 'new frozen AI output'
    plan['ai_screening'] = _write(ai_path, ai)
    plan['version'] = importer.SOURCE_SELECTION_IMPORT_VERSION
    plan['replacement'] = {'previous_assessment_ids': {},
                           'preserved_fulltext': {'doi:10.1234/a': 'b' * 64}}
    plan_path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='preserved full-text assessment is stale'):
        importer.run(plan_path, apply=True, store_base=store_base)
