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

ADMISSION_VERSION = 2

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


def rate(
    store: Store, *, round_name: str | None = None, manifest_only: bool = False
) -> dict[str, Any]:
    """Acquisition accounting. The denominator is what was **found**, not what was attempted.

    This is the figure that decides whether a round may produce verdicts, so the denominator is
    the whole point. Dividing by acquisition rows — which this function did until 2026-09-24 —
    let one obtained source out of twenty-five found report a rate of 1.00 and pass an 0.80
    floor: a corpus read at 4% certifying itself complete, which is the exact failure the
    project exists to prevent. `sources.yaml` says the floor is a share of what was *found*, and
    now it is.

    Five states are reported separately because the remedies differ. Found but unclassified needs
    a declared rule; found but never attempted needs the round finishing; attempted and refused
    needs a campaign or a different cascade; obtained but unconfirmed needs stage 3. Collapsing
    them into one ratio hides which one happened.

    `rate` is the lower bound and `rate_upper` the ceiling; `final` says whether anything is still
    outstanding. Only a final round may produce verdicts.
    """
    candidates = {
        key: row
        for key, row in store.latest_by("candidates.jsonl", "candidate_key").items()
        if (round_name is None or row.get("round") == round_name)
        # A curated reading list is the population `sources.yaml`'s floor was written about, and a round is
        # not always the right selector for it: the pilot corpus discovered 199 candidates and then curated
        # 28, so every one of the 28 carries the round that first *found* it — correctly — and judging the
        # floor over that round would divide by 199. A manifest row declares itself with a `source_id`.
        and (not manifest_only or row.get("source_id"))
    }
    rows = {key: row for key, row in collapse(store).items() if key in candidates}

    found = len(candidates)
    classified = sum(1 for row in candidates.values() if row.get("source_class"))
    attempted = len(rows)
    obtained = sum(1 for row in rows.values() if row.get("acquired"))

    # An acquisition row whose candidate is absent means a broken ledger. Adding it to `found`
    # would reintroduce the inflation; dropping it silently would hide the breakage.
    # Only over the whole store. An acquisition row outside a *filtered* population is not an orphan — it
    # belongs to a candidate the filter excluded — and reporting it as one said "the ledger is inconsistent"
    # about a ledger that was fine.
    orphans = (
        sorted(set(collapse(store)) - set(candidates))
        if round_name is None and not manifest_only
        else []
    )

    confirmed_rows = confirmations(store)
    confirmed = 0
    awaiting = 0
    not_a_document: list[str] = []
    for key, row in rows.items():
        if not row.get("acquired"):
            continue
        identifier = str(row.get("source_id") or key)
        held = confirmed_rows.get(identifier)
        if held is None:
            # Unknown, and it stays unknown. It is neither confirmed nor refuted, so it raises
            # the ceiling and never the figure.
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
        bucket = by_class.setdefault(klass, {"found": 0, "obtained": 0, "confirmed": 0, "awaiting_normalize": 0, "rate": 0.0})
        bucket["found"] += 1
        row = rows.get(key)
        if row is not None and row.get("acquired"):
            bucket["obtained"] += 1
            confirmation = confirmed_rows.get(str(row.get('source_id') or key))
            if confirmation is None:
                bucket['awaiting_normalize'] += 1
            elif confirmation.get('fulltext_confirmed'):
                bucket['confirmed'] += 1
            continue
        name = str((row or {}).get("failure_class") or "NOT_ATTEMPTED")
        failures[name] = failures.get(name, 0) + 1
        host = net.host_of(str((row or candidate).get("url") or ""))
        if host:
            hosts[host] = hosts.get(host, 0) + 1
    for bucket in by_class.values():
        bucket['obtained_rate'] = bucket['obtained'] / bucket['found']
        bucket['confirmed_rate'] = bucket['confirmed'] / bucket['found']
        bucket['basis'] = 'confirmed' if confirmed_rows else 'obtained'
        bucket['rate'] = bucket['confirmed_rate'] if confirmed_rows else bucket['obtained_rate']
        bucket['rate_upper'] = ((bucket['confirmed'] + bucket['awaiting_normalize']) / bucket['found']
                                if confirmed_rows else bucket['obtained_rate'])

    # The rate is a **lower bound**: what is established divided by what was found. Awaiting
    # normalization raises the ceiling and never the figure, so admission can only be granted on
    # evidence in hand. The first version of this let the obtained basis carry the headline while
    # normalization ran, which ignored confirmations already recorded — four obtained with one
    # already known not to be a document reported 1.00 and passed an 0.80 floor.
    #
    # A round is **final** only when nothing is outstanding. Work not yet done, an acquisition with
    # no candidate, and a ledger that had to be repaired each mean the corpus is not yet what it
    # will be, and a verdict drawn from it would be provisional whether or not it said so.
    # Before stage 3 has run at all, confirmation is not an axis yet and the acquisition rate is
    # the figure, as it has been all along. Once any source has been confirmed or refuted, the
    # confirmed count becomes the lower bound — including the refutations already in hand, which
    # is the correction a review forced: the obtained rate was carrying the headline while
    # normalization ran, so a source already known not to be a document was ignored.
    started = bool(confirmed_rows)

    blocking: list[str] = []
    search_queries = [row for row in store.latest_by('queries.jsonl', 'query_id').values()
                      if not manifest_only and (round_name is None or row.get('round') == round_name)]
    search_failures = sum(not row.get('ok') for row in search_queries)
    if search_failures:
        blocking.append('awaiting_discovery')
    if classified < found:
        blocking.append("awaiting_classification")
    if attempted < found:
        blocking.append("awaiting_acquire")
    if not started:
        blocking.append("normalize_not_started")
    elif awaiting:
        blocking.append("awaiting_normalize")
    if orphans:
        blocking.append("orphan_acquisitions")
    if any(store.read("ledger_repairs.jsonl")):
        blocking.append("ledger_repairs")
    return {
        "discovery_queries": len(search_queries), "discovery_failures": search_failures,
        "admission_version": ADMISSION_VERSION,
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
        "blocking": blocking,
        "final": not blocking,
        "basis": "confirmed" if started else "obtained",
        "rate": ((confirmed if started else obtained) / found) if found else None,
        "rate_upper": (((confirmed + awaiting) if started else obtained) / found)
        if found
        else None,
        "by_class": dict(sorted(by_class.items())),
        "failures_by_class": dict(sorted(failures.items(), key=lambda kv: -kv[1])),
        "failures_by_host": dict(sorted(hosts.items(), key=lambda kv: -kv[1])),
    }


def admit(
    project: Project,
    store: Store,
    *,
    round_name: str | None = None,
    manifest_only: bool = False,
) -> dict[str, Any]:
    """Whether this round may produce verdicts. Invariant 3: nothing waives the floor."""
    measured = rate(store, round_name=round_name, manifest_only=manifest_only)
    achieved = measured["rate"]
    status = OK if achieved is not None and achieved >= project.acquisition_floor else INSUFFICIENT

    # A class may declare its own floor, and it is an **additional** constraint. Obtainability is a property
    # of the genre — measured on alembic-s4, MET 0.83, ACA 0.70, IND 0.33, because IND is vendor research with
    # no open copy in existence — so one floor over a mixed manifest measures the proportions of the manifest.
    #
    # It can only make admission harder. A round the project floor refused stays refused however generous a
    # class's own bar is, which is the property that keeps this from being "lower the bar until it clears".
    declared = {
        c.id: c.acquisition_floor
        for c in getattr(project, "classes", ())
        if getattr(c, "acquisition_floor", None) is not None
    }
    below: list[str] = []
    for klass, bucket in measured["by_class"].items():
        bucket["floor"] = declared.get(klass, project.acquisition_floor)
        bucket["meets_floor"] = bucket["rate"] >= bucket["floor"]
        if not bucket["meets_floor"]:
            below.append(klass)
    if below:
        status = INSUFFICIENT

    return {
        "classes_below_floor": sorted(below),
        "class_floors": dict(sorted(declared.items())),
        "status": status,
        "floor": project.acquisition_floor,
        "floor_version": project.floor_version,
        "floor_set_at": project.floor_set_at or "unrecorded",
        **measured,
    }
