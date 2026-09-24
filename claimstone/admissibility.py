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


def confirmations(store: Store) -> dict[str, dict[str, Any]]:
    """What stage 3 concluded per source, where it has run. Empty until normalize exists."""
    return store.latest_by("documents.jsonl", "source_id")


def collapse(store: Store) -> dict[str, dict[str, Any]]:
    """One row per candidate: the latest re-gate, else the latest success, else the latest row.

    Two rules that both sound right pull in opposite directions here, and the order between them
    is the whole content of this function.

    A **retry** that fails must not erase a recorded success. Its failure is a fact about the
    world — the host refused us this time — and says nothing about bytes already on disk. Plain
    latest-wins would drop the rate while the corpus was unchanged.

    A **re-gate** that fails must erase one. It is not a new attempt at anything; it is a
    corrected reading of the very artifact the earlier row claimed, and it says that artifact was
    never a document. A row carrying `regated_from` is therefore authoritative, and a genuine
    acquisition afterwards still supersedes it in turn.
    """
    best: dict[str, dict[str, Any]] = {}
    for row in store.read("acquisitions.jsonl"):
        key = row.get("candidate_key")
        if key is None:
            continue
        key = str(key)
        held = best.get(key)
        if (
            held is None
            or row.get("regated_from")
            or row.get("acquired")
            or not held.get("acquired")
        ):
            best[key] = row
    return best


def rate(store: Store, *, round_name: str | None = None) -> dict[str, Any]:
    """Acquisition accounting. The denominator is what was **found**, not what was attempted.

    This is the figure that decides whether a round may produce verdicts, so the denominator is
    the whole point. Dividing by acquisition rows — which this function did until 2026-09-24 —
    let one obtained source out of twenty-five found report a rate of 1.00 and pass an 0.80
    floor: a corpus read at 4% certifying itself complete, which is the exact failure the
    project exists to prevent. `sources.yaml` says the floor is a share of what was *found*, and
    now it is.

    Five states are reported separately because the remedies differ. Found but unclassified
    needs a declared rule; found but never attempted needs the round finishing; attempted and
    refused needs a campaign or a different cascade; obtained but unconfirmed needs stage 3.
    Collapsing them into one ratio hides which one happened.
    """
    candidates = {
        key: row
        for key, row in store.latest_by("candidates.jsonl", "candidate_key").items()
        if round_name is None or row.get("round") == round_name
    }
    rows = {key: row for key, row in collapse(store).items() if key in candidates}

    found = len(candidates)
    classified = sum(1 for row in candidates.values() if row.get("source_class"))
    attempted = len(rows)
    obtained = sum(1 for row in rows.values() if row.get("acquired"))

    # An acquisition row whose candidate is absent means a broken ledger. Adding it to `found`
    # would reintroduce the inflation; dropping it silently would hide the breakage.
    orphans = sorted(set(collapse(store)) - set(candidates)) if round_name is None else []

    confirmed_rows = confirmations(store)
    confirmed: int | None = None
    awaiting = 0
    not_a_document: list[str] = []
    if confirmed_rows:
        confirmed = 0
        for key, row in rows.items():
            if not row.get("acquired"):
                continue
            identifier = str(row.get("source_id") or key)
            held = confirmed_rows.get(identifier)
            if held is None:
                # Not yet normalized is not the same as normalized and rejected. It is counted
                # as awaiting and nothing more: calling it confirmed would give one number two
                # meanings, and calling it unconfirmed would make the rate fall because stage 3
                # had not finished — measuring our progress and reporting it as a property of
                # the corpus.
                awaiting += 1
            elif held.get("fulltext_confirmed"):
                confirmed += 1
            else:
                not_a_document.append(identifier)

    by_class: dict[str, dict[str, Any]] = {}
    failures: dict[str, int] = {}
    hosts: dict[str, int] = {}
    for key, candidate in candidates.items():
        klass = str(candidate.get("source_class") or "UNCLASSIFIED")
        bucket = by_class.setdefault(klass, {"found": 0, "obtained": 0, "rate": 0.0})
        bucket["found"] += 1
        row = rows.get(key)
        if row is not None and row.get("acquired"):
            bucket["obtained"] += 1
            continue
        name = str((row or {}).get("failure_class") or "NOT_ATTEMPTED")
        failures[name] = failures.get(name, 0) + 1
        host = net.host_of(str((row or candidate).get("url") or ""))
        if host:
            hosts[host] = hosts.get(host, 0) + 1
    for bucket in by_class.values():
        bucket["rate"] = bucket["obtained"] / bucket["found"]

    # The confirmed basis only once stage 3 has reached every obtained source. While any remain
    # awaiting, `confirmed` is partial information reported beside the figure, never the figure:
    # a headline that counts unexamined bytes as confirmed is a headline with two meanings.
    complete = confirmed is not None and awaiting == 0
    basis = "confirmed" if complete else "obtained"
    numerator = confirmed if complete else obtained
    return {
        "round": round_name,
        "found": found,
        "classified": classified,
        "unclassified": found - classified,
        "attempted": attempted,
        "obtained": obtained,
        "confirmed": confirmed,
        "awaiting_normalize": awaiting,
        "not_a_document": sorted(not_a_document),
        "orphan_acquisitions": orphans,
        "basis": basis,
        "rate": (numerator / found) if found else None,
        "by_class": dict(sorted(by_class.items())),
        "failures_by_class": dict(sorted(failures.items(), key=lambda kv: -kv[1])),
        "failures_by_host": dict(sorted(hosts.items(), key=lambda kv: -kv[1])),
    }


def admit(
    project: Project, store: Store, *, round_name: str | None = None
) -> dict[str, Any]:
    """Whether this round may produce verdicts. Invariant 3: nothing waives the floor."""
    measured = rate(store, round_name=round_name)
    achieved = measured["rate"]
    status = OK if achieved is not None and achieved >= project.acquisition_floor else INSUFFICIENT
    return {
        "status": status,
        "floor": project.acquisition_floor,
        "floor_version": project.floor_version,
        "floor_set_at": project.floor_set_at or "unrecorded",
        **measured,
    }
