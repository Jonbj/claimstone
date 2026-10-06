"""scope: the one selector, the one predicate — review F1/F3, spec §2.4.

Two rounds with distinct candidate keys and source ids prove that a selector admits exactly its
own rows, that `profile_inputs.population` is the same predicate it always was, and that the
`or "routine"` variant of `_stage_discover` is gone.
"""

from __future__ import annotations

import pytest

from claimstone import profile_inputs, scope
from claimstone.config import load_project
from claimstone.store import Store


@pytest.fixture()
def project():
    return load_project("projects/example-news-and-returns")


@pytest.fixture()
def store(tmp_path) -> Store:
    """Two rounds: r1 has S01/S02 and one claim; r2 has S03 with a fuller trail."""
    fixture = Store("fixture", base=tmp_path)
    fixture.append("candidates.jsonl", {
        "candidate_key": "r1-a", "source_id": "S01", "round": "r1", "channel": "keyword",
        "source_class": "ACA", "discovered_at": "2026-10-01T10:00:00+00:00"})
    fixture.append("candidates.jsonl", {
        "candidate_key": "r1-b", "source_id": "S02", "round": "r1", "channel": "keyword",
        "source_class": "ACA", "discovered_at": "2026-10-01T10:00:01+00:00"})
    fixture.append("candidates.jsonl", {
        "candidate_key": "r2-a", "source_id": "S03", "round": "r2", "channel": "citation",
        "source_class": "ACA", "discovered_at": "2026-10-02T10:00:00+00:00"})
    fixture.append("acquisitions.jsonl", {
        "candidate_key": "r2-a", "source_id": "S03", "acquired": True, "sha256": "0" * 64,
        "url": "https://example.org/s03.pdf", "fetched_at": "2026-10-02T11:00:00+00:00"})
    fixture.append("documents.jsonl", {
        "source_id": "S03", "fulltext_confirmed": True, "generation_sha256": "g1",
        "chunks": 2, "chunk_ids": ["ch1", "ch2"], "built_at": "2026-10-02T12:00:00+00:00"})
    fixture.append("chunks.jsonl", {
        "chunk_id": "ch1", "source_id": "S03", "generation_sha256": "g1", "text": "body one",
        "built_at": "2026-10-02T12:00:01+00:00"})
    fixture.append("chunks.jsonl", {
        "chunk_id": "ch2", "source_id": "S03", "generation_sha256": "g1", "text": "body two",
        "built_at": "2026-10-02T12:00:02+00:00"})
    fixture.append("claims.jsonl", {
        "claim_id": "c0", "question_id": "Q02", "source_id": "S01", "source_class": "ACA",
        "harvested_at": "2026-10-01T11:00:00+00:00", "gate_revision": 1})
    fixture.append("claims.jsonl", {
        "claim_id": "c1", "question_id": "Q01", "source_id": "S03", "source_class": "ACA",
        "chunk_id": "ch1", "harvested_at": "2026-10-03T10:00:00+00:00", "gate_revision": 1})
    fixture.append("claims.jsonl", {
        "claim_id": "c2", "question_id": "Q01", "source_id": "S03", "source_class": "ACA",
        "chunk_id": "ch2", "harvested_at": "2026-10-03T10:00:01+00:00", "gate_revision": 1})
    fixture.append("rejections.jsonl", {
        "claim_id": "c3", "source_id": "S03", "chunk_id": "ch1",
        "failure": "NUMBER_NOT_IN_QUOTE",
        "gate_revision": 1, "harvested_at": "2026-10-03T11:00:00+00:00"})
    fixture.append("reviews.jsonl", {
        "claim_id": "c1", "verdict": "SUPPORTED", "reason": "reads correctly",
        "review_version": 2, "reviewed_at": "2026-10-04T10:00:00+00:00"})
    return fixture


def test_candidate_predicate_matches_admissibility(project, store):
    """T1: `candidate_in_scope` equals the inline predicate `admissibility.rate` uses, row by row."""
    from claimstone import admissibility

    rows = [
        {"round": "r1", "source_id": "S01"},
        {"round": "r2"},
        {"round": None},
        {"source_id": "S01"},
        {},
        {"round": "routine"},
    ]
    for selector in (scope.Selector(None, False), scope.Selector("r1", False),
                     scope.Selector("r2", False), scope.Selector(None, True),
                     scope.Selector("r1", True), scope.Selector("routine", False)):
        for row in rows:
            inline = ((selector.round is None or row.get("round") == selector.round)
                      and (not selector.manifest_only or row.get("source_id")))
            assert scope.candidate_in_scope(row, selector) == inline, (row, selector)


def test_selector_whole_store_and_as_dict():
    assert scope.Selector(None).whole_store is True
    assert scope.Selector(None, True).whole_store is False       # manifest_only is a scope
    assert scope.Selector("r1").whole_store is False
    assert scope.Selector("r1", True).as_dict() == {"round": "r1", "manifest_only": True}


def test_candidates_and_source_ids_are_scoped(store):
    assert set(scope.candidates(store, scope.Selector("r1"))) == {"r1-a", "r1-b"}
    assert scope.source_ids(store, scope.Selector("r1")) == {"S01", "S02"}
    assert scope.source_ids(store, scope.Selector("r2")) == {"S03"}
    assert scope.source_ids(store, scope.Selector(None)) == {"S01", "S02", "S03"}
    assert scope.source_ids(store, scope.Selector(None, True)) == {"S01", "S02", "S03"}


def test_row_in_scope_table(store):
    """The §2.1 table: each ledger is scoped by the identity that ledger carries."""
    keys = set(scope.candidates(store, scope.Selector("r1")))
    sources = scope.source_ids(store, scope.Selector("r1"))
    claim_sources = {"c0": "S01"}
    r1 = scope.Selector("r1")
    assert scope.row_in_scope("candidates.jsonl", {"candidate_key": "r1-a"}, selector=r1,
                              keys=keys, sources=sources, claim_sources=claim_sources)
    assert not scope.row_in_scope("candidates.jsonl", {"candidate_key": "r2-a"}, selector=r1,
                                  keys=keys, sources=sources, claim_sources=claim_sources)
    assert not scope.row_in_scope("acquisitions.jsonl", {"candidate_key": "r2-a"}, selector=r1,
                                  keys=keys, sources=sources, claim_sources=claim_sources)
    assert scope.row_in_scope("claims.jsonl", {"source_id": "S01"}, selector=r1,
                              keys=keys, sources=sources, claim_sources=claim_sources)
    assert not scope.row_in_scope("claims.jsonl", {"source_id": "S03"}, selector=r1,
                                  keys=keys, sources=sources, claim_sources=claim_sources)
    assert not scope.row_in_scope("documents.jsonl", {"source_id": "S03"}, selector=r1,
                                  keys=keys, sources=sources, claim_sources=claim_sources)
    assert scope.row_in_scope("reviews.jsonl", {"claim_id": "c0"}, selector=r1,
                              keys=keys, sources=sources, claim_sources=claim_sources)
    assert not scope.row_in_scope("reviews.jsonl", {"claim_id": "c1"}, selector=r1,
                                  keys=keys, sources=sources, claim_sources=claim_sources)
    assert scope.row_in_scope("profiles.jsonl", {"round": "r1", "manifest_only": False},
                              selector=r1, keys=keys, sources=sources, claim_sources=claim_sources)
    assert not scope.row_in_scope("profiles.jsonl", {"round": "r2", "manifest_only": False},
                                  selector=r1, keys=keys, sources=sources, claim_sources=claim_sources)
    assert not scope.row_in_scope("profiles.jsonl", {"round": None, "manifest_only": False},
                                  selector=r1, keys=keys, sources=sources, claim_sources=claim_sources)
    assert not scope.row_in_scope("populations.jsonl", {"round": "r1"}, selector=r1,
                                  keys=keys, sources=sources, claim_sources=claim_sources)
    # Whole store: every row of the nine ledgers, and only those.
    whole = scope.Selector(None)
    for ledger in ("candidates.jsonl", "acquisitions.jsonl", "documents.jsonl", "chunks.jsonl",
                   "claims.jsonl", "rejections.jsonl", "reviews.jsonl", "profiles.jsonl",
                   "adjudications.jsonl"):
        assert scope.row_in_scope(ledger, {"round": "r2", "source_id": "S03"}, selector=whole,
                                  keys=set(), sources=set(), claim_sources={})


def test_profile_population_refactor_is_identical(store):
    """T6: `profile_inputs.population` returns the same set as the pre-refactor body, everywhere."""
    def pre_refactor(store, *, round_name, manifest_only):
        return {
            str(row.get("source_id") or key)
            for key, row in store.latest_by("candidates.jsonl", "candidate_key").items()
            if (round_name is None or row.get("round") == round_name)
            and (not manifest_only or row.get("source_id"))
        }

    for round_name, manifest_only in ((None, False), ("r1", False), ("r2", False),
                                      (None, True), ("r1", True)):
        assert profile_inputs.population(
            store, round_name=round_name, manifest_only=manifest_only
        ) == pre_refactor(store, round_name=round_name, manifest_only=manifest_only)


def test_round_less_candidate_is_not_routine(store):
    """T8: a candidate without `round` belongs to no round, not to the round named "routine"."""
    assert not scope.candidate_in_scope({}, scope.Selector("routine"))
    assert not scope.candidate_in_scope({"round": None}, scope.Selector("routine"))
    assert scope.candidate_in_scope({}, scope.Selector(None))
    store.append("candidates.jsonl", {"candidate_key": "no-round", "round": None,
                                      "channel": "keyword"})
    assert "no-round" not in scope.candidates(store, scope.Selector("routine"))
    assert "no-round" in scope.candidates(store, scope.Selector(None))
