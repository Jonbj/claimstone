"""Verifiable, downloadable whole-corpus dossier export from frozen ledger prefixes."""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import os
import pathlib
import re
import tempfile
import zipfile
from typing import Any

from claimstone import export, flows, operations, periodic_dossier, portal_state
from claimstone.config import Project
from claimstone.store import Store

LEDGER = 'periodic_exports.jsonl'
VERSION = export.EXPORT_VERSION
FILES = ('manifest.json', 'dossier.json', 'questions.csv', 'report.md')


def _outputs(report: dict[str, Any]) -> dict[str, bytes]:
    decisions = {row['question_id']: row for row in report['human_decisions']}
    questions = export._csv(
        ['question_id', 'state', 'provisional', 'profile_sha256', 'verdict', 'verdict_stale'],
        [[row['question_id'], row.get('state'), row.get('provisional'),
          row.get('profile_sha256'),
          (decisions.get(row['question_id']) or {}).get('verdict'),
          (decisions.get(row['question_id']) or {}).get('stale')]
         for row in report['profiles']])
    lines = ['# Cumulative research dossier', '',
             f"Schedule: {report['schedule_id']}",
             f"Dossier: {report['finalized_dossier_id']}",
             f"State: {report['state']}", '',
             'Question verdicts, if present, were signed by a person. '
             'This export does not decide a verdict.', '']
    return {'dossier.json': export._dump(report), 'questions.csv': questions,
            'report.md': ('\n'.join(lines)).encode('utf-8')}


def _identity(project: Project, schedule_id: str, dossier_id: str,
              prefixes: list[dict[str, Any]]) -> dict[str, Any]:
    return {'version': VERSION, 'project': project.name, 'schedule_id': schedule_id,
            'dossier_id': dossier_id,
            'protocol_sha256': flows.protocol_digest(project),
            'registry_sha256': project.registry_sha256,
            'instrument_versions': portal_state.instrument_versions(),
            'prefixes': [{key: row[key] for key in ('path', 'bytes', 'rows', 'sha256')}
                         for row in sorted(prefixes, key=lambda item: item['path'])]}


def _frozen(project: Project, prefixes: list[dict[str, Any]], directory: pathlib.Path) -> Store:
    root = directory / project.name
    for prefix in prefixes:
        target = root / prefix['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(prefix['content'])
    return Store(project.name, base=directory)


def create(project: Project, store: Store, schedule_id: str, *, dossier_id: str,
           actor: str | None = None) -> tuple[pathlib.Path, bool]:
    """Snapshot only a final current dossier; recover a crash before ledger append."""
    with store.writer_lock():
        current = periodic_dossier.preview(project, store, schedule_id)
        if (current['state'] != periodic_dossier.READY or current['snapshot_stale'] or
                current['finalized_dossier_id'] != dossier_id):
            raise operations.OperationError('cumulative dossier is not finalized and current')
        prefixes, torn = export.snapshot(store)
        identity = _identity(project, schedule_id, dossier_id, prefixes)
        export_id = operations._digest(identity)
        base = store.root / 'periodic_exports'
        destination = base / export_id
        created = not destination.is_dir()
        if not created:
            problems = verify(project, store, export_id, require_record=False)
            if problems:
                raise operations.OperationError(
                    'existing cumulative export failed verification: ' + ', '.join(problems))
        if created:
            base.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory() as frozen_dir, tempfile.TemporaryDirectory(
                    prefix='.pending-', dir=base) as staging:
                frozen = _frozen(project, prefixes, pathlib.Path(frozen_dir))
                report = periodic_dossier.preview(project, frozen, schedule_id)
                if (report['state'] != periodic_dossier.READY or
                        report['finalized_dossier_id'] != dossier_id or
                        report['snapshot_stale']):
                    raise operations.OperationError('frozen dossier differs from the approved one')
                outputs = _outputs(report)
                manifest = {'identity': identity, 'export_id': export_id,
                            'torn_tails': sorted(torn),
                            'output_sha256': {name: hashlib.sha256(data).hexdigest()
                                              for name, data in outputs.items()},
                            'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                            'actor': actor}
                for name, data in outputs.items():
                    (pathlib.Path(staging) / name).write_bytes(data)
                (pathlib.Path(staging) / 'manifest.json').write_bytes(export._dump(manifest))
                os.replace(staging, destination)
        if not any(row.get('export_id') == export_id for row in store.read(LEDGER)):
            manifest_sha256 = hashlib.sha256(
                (destination / 'manifest.json').read_bytes()).hexdigest()
            store.append(LEDGER, {'version': VERSION, 'export_id': export_id,
                                  'schedule_id': schedule_id, 'dossier_id': dossier_id,
                                  'manifest_sha256': manifest_sha256,
                                  'actor': actor, 'at': operations._now()})
        return destination, created


def verify(project: Project, store: Store, export_id: str, *,
           require_record: bool = True) -> list[str]:
    """Check identity, live append-only prefixes, then recompute every output."""
    if re.fullmatch(r'[0-9a-f]{64}', export_id) is None:
        return ['INVALID_EXPORT_ID']
    directory = store.root / 'periodic_exports' / export_id
    try:
        manifest_bytes = (directory / 'manifest.json').read_bytes()
        manifest = json.loads(manifest_bytes.decode('utf-8'))
        recorded = next((row for row in store.read(LEDGER)
                         if row.get('export_id') == export_id), None)
        if require_record and recorded is None:
            return ['UNRECORDED_EXPORT']
        if (recorded is not None and
                recorded.get('manifest_sha256') != hashlib.sha256(manifest_bytes).hexdigest()):
            return ['MANIFEST_CHANGED']
        identity = manifest['identity']
        if (identity['project'] != project.name or
                manifest['export_id'] != export_id or
                operations._digest(identity) != export_id or
                identity['protocol_sha256'] != flows.protocol_digest(project) or
                identity['registry_sha256'] != project.registry_sha256 or
                identity['instrument_versions'] != portal_state.instrument_versions()):
            return ['IDENTITY_CHANGED']
        prefixes = []
        problems = []
        for entry in identity['prefixes']:
            path = entry['path']
            if (not isinstance(path, str) or pathlib.PurePosixPath(path).is_absolute() or
                    '..' in pathlib.PurePosixPath(path).parts):
                return ['INVALID_PREFIX_PATH']
            try:
                data = (store.root / path).read_bytes()[:entry['bytes']]
            except OSError:
                data = b''
            if (len(data) != entry['bytes'] or
                    hashlib.sha256(data).hexdigest() != entry['sha256']):
                problems.append(f'PREFIX_CHANGED {path}')
            prefixes.append(entry | {'content': data})
        if problems:
            return problems
        with tempfile.TemporaryDirectory() as frozen_dir:
            frozen = _frozen(project, prefixes, pathlib.Path(frozen_dir))
            report = periodic_dossier.preview(project, frozen, identity['schedule_id'])
            if (report['finalized_dossier_id'] != identity['dossier_id'] or
                    report['snapshot_stale']):
                return ['DOSSIER_CHANGED']
            for name, expected in _outputs(report).items():
                held = directory / name
                if (not held.is_file() or held.read_bytes() != expected or
                        hashlib.sha256(expected).hexdigest() !=
                        manifest['output_sha256'].get(name)):
                    problems.append(f'OUTPUT_DIFFERS {name}')
        return problems
    except (OSError, ValueError, KeyError, TypeError, operations.OperationError):
        return ['INVALID_EXPORT']


def archive(directory: pathlib.Path) -> bytes:
    """A deterministic zip of report files only; held source copies never enter."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as package:
        for name in FILES:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            package.writestr(info, (directory / name).read_bytes())
    return buffer.getvalue()
