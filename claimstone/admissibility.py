"""The acquisition rate, and whether it permits verdicts at all.

A corpus read at 42% that certifies itself complete is worse than no corpus: that is the
observed state that motivated this project. So the rate is computed every round, reported per
source class before it is reported pooled, and compared against a floor the project declared in
advance. There is no flag that waives it.
"""

from __future__ import annotations

from typing import Any

from claimstone import net
from claimstone.config import Project
from claimstone.store import Store

OK = "OK"
INSUFFICIENT = "INSUFFICIENT_ACQUISITION"


def collapse(store: Store) -> dict[str, dict[str, Any]]:
    """One row per candidate, preferring the latest **successful** attempt.

    Plain latest-wins would let a retry campaign that fails erase a success whose bytes are on
    disk, and the rate would fall while the corpus was unchanged.
    """
    best: dict[str, dict[str, Any]] = {}
    for row in store.read("acquisitions.jsonl"):
        key = row.get("candidate_key")
        if key is None:
            continue
        key = str(key)
        held = best.get(key)
        if held is None or row.get("acquired") or not held.get("acquired"):
            best[key] = row
    return best


def rate(store: Store) -> dict[str, Any]:
    """Acquisition accounting. `rate` is None when nothing was attempted — not 0.0."""
    rows = collapse(store)
    attempted = len(rows)
    acquired = sum(1 for row in rows.values() if row.get("acquired"))

    by_class: dict[str, dict[str, Any]] = {}
    failures: dict[str, int] = {}
    hosts: dict[str, int] = {}
    for row in rows.values():
        klass = str(row.get("source_class") or "UNCLASSIFIED")
        bucket = by_class.setdefault(klass, {"attempted": 0, "acquired": 0, "rate": 0.0})
        bucket["attempted"] += 1
        if row.get("acquired"):
            bucket["acquired"] += 1
            continue
        name = str(row.get("failure_class"))
        failures[name] = failures.get(name, 0) + 1
        host = net.host_of(str(row.get("url") or ""))
        if host:
            hosts[host] = hosts.get(host, 0) + 1

    for bucket in by_class.values():
        bucket["rate"] = bucket["acquired"] / bucket["attempted"]

    return {
        "attempted": attempted,
        "acquired": acquired,
        "rate": (acquired / attempted) if attempted else None,
        "by_class": dict(sorted(by_class.items())),
        "failures_by_class": dict(sorted(failures.items(), key=lambda kv: -kv[1])),
        "failures_by_host": dict(sorted(hosts.items(), key=lambda kv: -kv[1])),
    }


def admit(project: Project, store: Store) -> dict[str, Any]:
    """Whether this round may produce verdicts. Invariant 3: nothing waives the floor."""
    measured = rate(store)
    achieved = measured["rate"]
    status = OK if achieved is not None and achieved >= project.acquisition_floor else INSUFFICIENT
    return {
        "status": status,
        "floor": project.acquisition_floor,
        "floor_version": project.floor_version,
        "floor_set_at": project.floor_set_at or "unrecorded",
        **measured,
    }
