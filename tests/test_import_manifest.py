"""Seeding candidates from a manifest. Nothing covered this, and a syntax error hid in it."""

import pytest

from claimstone import discover
from claimstone.config import ManifestEntry
from claimstone.store import Store


def entry(**overrides):
    base = {"source_id": "S01", "source_class": "ACA", "declared_format": "pdf",
            "url": "https://x.example/a", "title": "A paper"}
    return ManifestEntry(**{**base, **overrides})


def test_a_manifest_becomes_candidates(tmp_path):
    store = Store("t", base=tmp_path)
    result = discover.import_manifest(store, [entry()])
    assert result == {"rows": 1, "new": 1, "updated": 0, "total": 1}
    row = next(iter(store.read("candidates.jsonl")))
    assert row["source_class"] == "ACA"
    assert row["source_id"] == "S01"
    assert row["source_api"] == "manifest"


def test_importing_twice_adds_nothing(tmp_path):
    store = Store("t", base=tmp_path)
    discover.import_manifest(store, [entry()])
    result = discover.import_manifest(store, [entry()])
    assert (result["new"], result["updated"]) == (0, 0)
    assert len(list(store.read("candidates.jsonl"))) == 1


def test_a_changed_class_appends_a_corrected_row(tmp_path):
    # An earlier import stored the manifest's own word for the class instead of the id it
    # resolves to. Skipping on the key alone would freeze that and split one class into two.
    store = Store("t", base=tmp_path)
    discover.import_manifest(store, [entry(source_class="academic")])
    result = discover.import_manifest(store, [entry(source_class="ACA")])
    assert (result["new"], result["updated"]) == (0, 1)
    assert len(list(store.read("candidates.jsonl"))) == 2
    latest = store.latest_by("candidates.jsonl", "candidate_key")
    assert next(iter(latest.values()))["source_class"] == "ACA"


def test_a_doi_in_the_url_becomes_the_candidate_key(tmp_path):
    store = Store("t", base=tmp_path)
    discover.import_manifest(
        store, [entry(url="https://doi.org/10.1016/j.jfineco.2019.05.001")])
    row = next(iter(store.read("candidates.jsonl")))
    assert row["candidate_key"] == "doi:10.1016/j.jfineco.2019.05.001"


def test_a_round_is_the_one_that_first_found_a_candidate(tmp_path):
    """Not the one that last mentioned it. `round` answers "which round brought this into the corpus",
    so a re-import under a new name must not move a candidate out of the round that found it — which
    latest-wins would do silently, emptying the earlier round's population.
    """
    store = Store("t", base=tmp_path)
    entries = [entry(), entry(source_id="S02", url="https://x.example/b", title="Another")]
    discover.import_manifest(store, entries, round_name="manifest")
    second = discover.import_manifest(store, entries, round_name="autumn")
    assert second["new"] == 0
    assert {r["round"] for r in store.latest_by("candidates.jsonl", "candidate_key").values()} \
        == {"manifest"}


def test_a_row_written_before_rounds_existed_is_stamped_on_re_import(tmp_path):
    """Otherwise the 25 manifest candidates already in a store can never be given a round, and
    `report --round` finds nothing where the whole corpus is."""
    store = Store("t", base=tmp_path)
    entries = [entry(), entry(source_id="S02", url="https://x.example/b", title="Another")]
    discover.import_manifest(store, entries, round_name="manifest")
    # Simulate the pre-round ledger: the same rows with no round recorded.
    for row in list(store.latest_by("candidates.jsonl", "candidate_key").values()):
        store.append("candidates.jsonl", {k: v for k, v in row.items() if k != "round"})

    result = discover.import_manifest(store, entries, round_name="manifest")
    assert result["updated"] == len(entries)
    assert all(r.get("round") == "manifest"
               for r in store.latest_by("candidates.jsonl", "candidate_key").values())
