"""Single-machine coordinator for existing, bounded local mandates and approved operations.

The coordinator discovers mandates; it does not grant them. Each pass invokes
the same guarded tick as ``auto-worker`` and isolates a broken project so other
projects can continue. It also runs operations a person has already authorized,
exactly as ``scheduler worker`` would: an authorization with nobody to start it
left the portal saying "waiting for the worker" forever. It plans and authorizes
nothing itself. The installation heartbeat is ephemeral, not evidence.
"""

from __future__ import annotations

import pathlib
from typing import Any

from claimstone import autopilot, operations, worker_runtime
from claimstone.config import check_registry_drift, discover_projects, load_project
from claimstone.store import Store


def installation_store(store_dir: str | pathlib.Path) -> Store:
    return Store('_installation', base=store_dir)


def status(store_dir: str | pathlib.Path) -> dict[str, Any]:
    return worker_runtime.status(installation_store(store_dir), 'supervisor')


OPERATIONS_PER_PASS = 3


def scan_once(projects_dir: str | pathlib.Path, store_dir: str | pathlib.Path,
              *, beacon: worker_runtime.Beacon | None = None) -> dict[str, Any]:
    """Advance each enabled mandate at most once and run already-authorized operations;
    report every refusal by name."""
    report: dict[str, Any] = {'scanned_projects': 0, 'active_mandates': 0,
                              'attempted': 0, 'results': [], 'errors': [],
                              'operations_run': 0, 'operation_results': []}
    for root in discover_projects(projects_dir):
        report['scanned_projects'] += 1
        store = Store(root.name, base=store_dir)
        has_mandates = store.path(autopilot.LEDGER).exists()
        has_operations = store.path(operations.LEDGER).exists()
        if not has_mandates and not has_operations:
            continue
        try:
            project = load_project(root)
            check_registry_drift(project, store)
            # Parse the whole ledger before driving: a damaged event cannot be
            # treated as an absent grant.
            mandates = autopilot._rows(store) if has_mandates else {}
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
        if has_operations:
            _run_authorized(project, store, report, beacon)
    return report


def _run_authorized(project: Any, store: Store, report: dict[str, Any],
                    beacon: worker_runtime.Beacon | None) -> None:
    """Execute what a person authorized, at most a few operations per pass. The same
    'operations' beacon as `scheduler worker` keeps the two from running one plan twice."""
    try:
        if beacon is not None:
            beacon.set_phase('DRIVING')
        with worker_runtime.Beacon(store, 'operations') as worker:
            worker.set_phase('DRIVING')
            result = operations.tick(project, store, max_operations=OPERATIONS_PER_PASS)
        if result['processed']:
            report['operations_run'] += result['processed']
            report['operation_results'].append({'project': project.name, 'result': result})
    except Exception as exc:
        report['errors'].append({'project': project.name, 'mandate_id': None,
                                 'error': f'{type(exc).__name__}: {exc}'})
    finally:
        if beacon is not None:
            beacon.set_phase('IDLE')
