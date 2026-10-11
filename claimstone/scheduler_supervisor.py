"""Single-machine coordinator for existing, bounded local mandates.

The coordinator discovers mandates; it does not grant them. Each pass invokes
the same guarded tick as ``auto-worker`` and isolates a broken project so other
projects can continue. The installation heartbeat is ephemeral, not evidence.
"""

from __future__ import annotations

import pathlib
from typing import Any

from claimstone import autopilot, worker_runtime
from claimstone.config import check_registry_drift, discover_projects, load_project
from claimstone.store import Store


def installation_store(store_dir: str | pathlib.Path) -> Store:
    return Store('_installation', base=store_dir)


def status(store_dir: str | pathlib.Path) -> dict[str, Any]:
    return worker_runtime.status(installation_store(store_dir), 'supervisor')


def scan_once(projects_dir: str | pathlib.Path, store_dir: str | pathlib.Path,
              *, beacon: worker_runtime.Beacon | None = None) -> dict[str, Any]:
    """Advance each enabled mandate at most once; report every refusal by name."""
    report: dict[str, Any] = {'scanned_projects': 0, 'active_mandates': 0,
                              'attempted': 0, 'results': [], 'errors': []}
    for root in discover_projects(projects_dir):
        report['scanned_projects'] += 1
        store = Store(root.name, base=store_dir)
        if not store.path(autopilot.LEDGER).exists():
            continue
        try:
            project = load_project(root)
            check_registry_drift(project, store)
            # Parse the whole ledger before driving: a damaged event cannot be
            # treated as an absent grant.
            mandates = autopilot._rows(store)
        except Exception as exc:
            report['errors'].append({'project': root.name, 'mandate_id': None,
                                     'error': f'{type(exc).__name__}: {exc}'})
            continue
        for mandate_id, rows in sorted(mandates.items()):
            if len(rows) != 1:
                continue
            report['active_mandates'] += 1
            try:
                if beacon is not None:
                    beacon.set_phase('DRIVING')
                with worker_runtime.Beacon(store, mandate_id) as worker:
                    worker.set_phase('DRIVING')
                    result = autopilot.tick(project, store, mandate_id)
                report['attempted'] += 1
                report['results'].append({'project': project.name,
                                          'mandate_id': mandate_id, 'result': result})
            except Exception as exc:
                report['errors'].append({'project': project.name,
                                         'mandate_id': mandate_id,
                                         'error': f'{type(exc).__name__}: {exc}'})
            finally:
                if beacon is not None:
                    beacon.set_phase('IDLE')
    return report
