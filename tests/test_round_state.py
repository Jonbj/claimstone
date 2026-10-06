"""round_state: per-stage counts, None-vs-0, the question spine — spec §12 table, row one.

The fixtures are minimal ledgers under tmp_path: the module under test is a *derived view*, so
its tests only need rows, never a network or a model. The example project supplies the registry,
because a registry is input data the engine never owns.
"""

from __future__ import annotations

import json

import pytest

from claimstone import round_state
from claimstone.config import load_project
from claimstone.store import Store


@pytest.fixture()
def project():
    return load_project("projects/example-news-and-returns")


def _write(store: Store, ledger: str, rows: list[dict]) -> None:
    for row in rows:
        store.append(ledger, row)


def test_empty_store_never_renders_unknown_as_zero(project, tmp_path):
    """A store with nothing yet: counts that are knowably empty are 0, unknowables stay None."""
    store = Store("fixture", base=tmp_path)
    rs = round_state.state(project, store)

    discover = rs.stages[0]
    assert discover.outputs == 0            # looked: nothing found, a real zero
    assert discover.inputs is None          # the world's literature has no denominator
    assert discover.detail and "not estimable" in discover.detail.lower()

    extract = rs.stages[3]
    assert extract.outputs is None          # no claims ledger at all: not knowable, not zero
    assert extract.rejected is None
    assert extract.progress is None

    review = rs.stages[4]
    assert review.rejected is None          # review discards nothing, in principle

    # Every question still appears, in registry order, empty and saying why it is empty (§5).
    assert [q.id for q in rs.questions] == [q.id for q in project.questions]
    assert all(q.claims == 0 for q in rs.questions)
    assert all(q.verdict is None for q in rs.questions)
    assert rs.verdicts_recorded == 0        # a knowable count of zero, not an absence


def test_discover_never_gets_a_percentage_single_channel(project, tmp_path):
    """A manifest round has one channel: the state says completeness is not estimable."""
    store = Store("fixture", base=tmp_path)
    _write(store, "candidates.jsonl", [
        {"candidate_key": "a", "source_id": "S01", "round": "manifest", "channel": "manifest"},
    ])
    discover = round_state.state(project, store).stages[0]
    assert discover.outputs == 1
    assert discover.progress is None        # never a percentage, whatever the channels
    assert "not estimable" in (discover.detail or "").lower()


def test_two_discovery_channels_do_not_imply_literature_completeness(project, tmp_path):
    """D10: the channels expose missed works, not a capture-recapture percentage."""
    store = Store("fixture", base=tmp_path)
    _write(store, "candidates.jsonl", [
        {"candidate_key": "a", "round": "routine", "channel": "keyword"},
        {"candidate_key": "b", "round": "routine", "channel": "citation"},
    ])
    discover = round_state.state(project, store).stages[0]
    assert discover.outputs == 2
    assert discover.progress is None
    assert "completeness remains unknown" in (discover.detail or "").lower()


def test_stage_counts_follow_the_current_rule(project, tmp_path):
    """outputs and rejected use the same counting rule: last outcome per claim id, supersede."""
    store = Store("fixture", base=tmp_path)
    _write(store, "claims.jsonl", [
        {"claim_id": "c1", "question_id": "Q01", "source_class": "ACA", "gate_revision": 1,
         "harvested_at": "2026-09-28T10:00:00+00:00"},
        {"claim_id": "c2", "question_id": "Q02", "source_class": "WP", "gate_revision": 1,
         "harvested_at": "2026-09-28T10:00:01+00:00"},
    ])
    _write(store, "rejections.jsonl", [
        {"claim_id": "c1", "failure": "NUMBER_NOT_IN_QUOTE", "gate_revision": 1,
         "harvested_at": "2026-09-28T09:00:00+00:00"},   # superseded by the later acceptance
        {"claim_id": "c3", "failure": "UNPARSEABLE_VALUE", "gate_revision": 2,
         "harvested_at": "2026-09-28T11:00:00+00:00"},
    ])
    rs = round_state.state(project, store)
    extract = rs.stages[3]
    assert extract.outputs == 2             # c1 accepted last, c2 accepted, c3 rejected
    assert extract.rejected == 1
    assert rs.rejections_by_reason == {"UNPARSEABLE_VALUE": 1}

    spine = {q.id: q for q in rs.questions}
    assert spine["Q01"].claims == 1
    assert spine["Q01"].claims_by_class == {"ACA": 1}     # per class before the aggregate
    assert spine["Q02"].claims_by_class == {"WP": 1}


def test_spine_coverage_is_post_review_and_from_the_profiles(project, tmp_path):
    """Coverage comes from the profile the engine built, never from raw claim counts."""
    store = Store("fixture", base=tmp_path)
    _write(store, "profiles.jsonl", [
        {"question_id": "Q01", "round": None, "manifest_only": False,
         "coverage": {"sources": 2, "examined": 9}, "provisional": False,
         "state": None, "profile_sha256": "a" * 64},
        {"question_id": "Q02", "round": None, "manifest_only": False,
         "coverage": {"sources": 0, "examined": 9}, "provisional": True,
         "blocking": ["awaiting_review"], "state": "NO_VERIFIED_CLAIM",
         "profile_sha256": "b" * 64},
    ])
    rs = round_state.state(project, store)
    spine = {q.id: q for q in rs.questions}
    assert (spine["Q01"].coverage_sources, spine["Q01"].coverage_examined) == (2, 9)
    # Q02 has not been read: zero certified sources is the honest coverage, not the claim count.
    assert spine["Q02"].coverage_sources == 0
    assert spine["Q02"].provisional is True
    assert spine["Q02"].blocking == ("awaiting_review",)
    assert spine["Q02"].state == "NO_VERIFIED_CLAIM"


def test_no_verified_claim_is_never_a_never_asked_verdict(project, tmp_path):
    """The founding distinction: the engine says nothing survived; only a person says never asked."""
    store = Store("fixture", base=tmp_path)
    _write(store, "profiles.jsonl", [
        {"question_id": "Q03", "round": None, "manifest_only": False,
         "coverage": {"sources": 0, "examined": 5}, "provisional": False,
         "state": "NO_VERIFIED_CLAIM", "profile_sha256": "c" * 64},
    ])
    _write(store, "adjudications.jsonl", [
        {"question_id": "Q03", "round": None, "manifest_only": False,
         "verdict": "NEVER_ASKED", "profile_sha256": "c" * 64,
         "adjudicated_at": "2026-09-28T12:00:00+00:00", "adjudicated_by": "a person"},
    ])
    rs = round_state.state(project, store)
    q3 = {q.id: q for q in rs.questions}["Q03"]
    assert q3.state == "NO_VERIFIED_CLAIM"  # the engine's categorical outcome
    assert q3.verdict == "NEVER_ASKED"      # the person's verdict, from adjudications
    assert q3.verdict_stale is False        # same hash: the judgement is about this evidence


def test_stale_verdict_is_marked_not_hidden(project, tmp_path):
    """Evidence moved: the verdict stays on screen as stale, with the hashes the row carries."""
    store = Store("fixture", base=tmp_path)
    _write(store, "profiles.jsonl", [
        {"question_id": "Q01", "round": None, "manifest_only": False,
         "coverage": {"sources": 3, "examined": 5}, "provisional": False,
         "state": None, "profile_sha256": "d" * 64},
    ])
    _write(store, "adjudications.jsonl", [
        {"question_id": "Q01", "round": None, "manifest_only": False,
         "verdict": "CONTRADICTED", "profile_sha256": "older" + "0" * 57,
         "adjudicated_at": "2026-09-27T09:00:00+00:00", "adjudicated_by": "a person"},
    ])
    rs = round_state.state(project, store)
    q1 = {q.id: q for q in rs.questions}["Q01"]
    assert q1.verdict == "CONTRADICTED"
    assert q1.verdict_stale is True
    assert rs.verdicts_stale == 1
    assert rs.verdicts_recorded == 0        # a stale verdict certifies nothing


def test_extract_fraction_denominator_is_expected_readings(project, tmp_path):
    """The honest extract fraction: readings answered over readings expected (D45)."""
    store = Store("fixture", base=tmp_path)
    _write(store, "profiles.jsonl", [
        {"question_id": "Q01", "round": None, "manifest_only": False,
         "extraction": {"expected": 10, "unanswered": 2, "unharvested": 0, "unregated": 0},
         "provisional": True, "blocking": ["awaiting_extract"],
         "coverage": {"sources": 0, "examined": 0}, "profile_sha256": "e" * 64},
        {"question_id": "Q02", "round": None, "manifest_only": False,
         "extraction": {"expected": 30, "unanswered": 5, "unharvested": 0, "unregated": 0},
         "provisional": True, "blocking": ["awaiting_extract"],
         "coverage": {"sources": 0, "examined": 0}, "profile_sha256": "f" * 64},
    ])
    rs = round_state.state(project, store)
    extract = rs.stages[3]
    assert extract.progress is not None
    assert extract.progress.total == 40
    assert extract.progress.done == 33     # 40 expected, 7 unanswered across the two questions
    assert "expected" in extract.progress.label


def test_activity_newest_first_and_torn_tail_skipped(project, tmp_path):
    """A half-written final line is skipped and reported; the rows read are the rows shown."""
    store = Store("fixture", base=tmp_path)
    _write(store, "claims.jsonl", [
        {"claim_id": "c1", "question_id": "Q01", "harvested_at": "2026-09-28T10:00:00+00:00"},
    ])
    _write(store, "reviews.jsonl", [
        {"claim_id": "c1", "verdict": "SUPPORTED", "reviewed_at": "2026-09-28T11:00:00+00:00"},
    ])
    # A torn tail, written the way a crash leaves it: no trailing newline. Store.read skips it.
    with store.path("profiles.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"question_id": "Q01", "half": True})[:-4])
    rows = round_state.activity(store, limit=10)
    assert rows[0]["stage"] == "review"                     # newest first
    assert rows[0]["when"] == "2026-09-28T11:00:00+00:00"
    assert all(row["row"].get("half") is None for row in rows)  # the fragment never appears
    assert store.torn_tail == ["profiles.jsonl"]            # and the reader recorded it


def test_activity_limit_capped_at_500(project, tmp_path):
    store = Store("fixture", base=tmp_path)
    _write(store, "claims.jsonl", [
        {"claim_id": f"c{i}", "question_id": "Q01",
         "harvested_at": f"2026-09-28T10:00:{i % 60:02d}+00:00"} for i in range(600)
    ])
    assert len(round_state.activity(store, limit=9999)) == 500
    assert len(round_state.activity(store, limit=10)) == 10


def test_registry_drift_becomes_a_named_state_not_a_crash(project, tmp_path):
    """A refused spine is a state: the refusal is named, and the registry spine still renders."""
    store = Store("fixture", base=tmp_path)
    _write(store, "registry.jsonl", [
        {"registry_version": project.registry_version, "registry_sha256": "0" * 64,
         "frozen_at": project.frozen_at},              # same version, different text (inv. 5)
    ])
    rs = round_state.state(project, store)
    assert "registry changed" in rs.unavailable
    assert "invariant 5" in rs.unavailable             # it names the rule, not just "error"
    assert [q.id for q in rs.questions] == [q.id for q in project.questions]
    assert rs.verdicts_recorded == 0 and rs.verdicts_stale == 0


def test_inadmissible_corpus_shows_in_the_floor_and_makes_signed_verdicts_stale(project, tmp_path):
    """INSUFFICIENT_ACQUISITION is state: the floor names it, and verdicts signed against the old
    acquisition are shown stale — even under a matching hash, because the evidence itself moved."""
    store = Store("fixture", base=tmp_path)
    _write(store, "candidates.jsonl", [
        {"candidate_key": f"k{i}", "question_id": "Q01", "round": "routine",
         "channel": "openalex"} for i in range(10)
    ])
    _write(store, "profiles.jsonl", [
        {"question_id": "Q01", "round": None, "manifest_only": False,
         "coverage": {"sources": 1, "examined": 2},
         "acquisition": {"found": 10, "obtained": 10, "confirmed": 10},
         "provisional": False, "state": None, "profile_sha256": "a" * 64},
    ])
    _write(store, "adjudications.jsonl", [
        {"question_id": "Q01", "round": None, "manifest_only": False,
         "verdict": "CONTESTED_IN_LITERATURE", "profile_sha256": "a" * 64,
         "adjudicated_at": "2026-09-27T09:00:00+00:00", "adjudicated_by": "a person"},
    ])
    rs = round_state.state(project, store)
    assert rs.floor is not None
    assert rs.floor["status"] == "INSUFFICIENT_ACQUISITION"
    assert rs.floor["found"] == 10 and rs.floor["obtained"] == 0
    q1 = {q.id: q for q in rs.questions}["Q01"]
    assert q1.verdict == "CONTESTED_IN_LITERATURE"     # shown, never hidden
    assert q1.verdict_stale is True                    # acquisition moved under the signature
    assert rs.verdicts_recorded == 0 and rs.verdicts_stale == 1


def test_cheap_state_absent_ledger_is_not_zero(tmp_path):
    """An absent ledger reports rows: None — not knowable — while a present one reports its count."""
    store = Store("fixture", base=tmp_path)
    _write(store, "claims.jsonl", [{"claim_id": "c1"}])
    cheap = round_state.cheap_state(store)
    assert cheap["ledgers"]["claims.jsonl"]["rows"] == 1
    assert cheap["ledgers"]["profiles.jsonl"]["rows"] is None
    assert cheap["ledgers"]["profiles.jsonl"]["mtime"] is None
    # The running inference says what it is: mtime, not liveness.
    assert "inference" in cheap["pid_note"]


# --- P0, spec §2.4: one selector, honest errors -------------------------------------------


@pytest.fixture()
def two_rounds(project, tmp_path) -> Store:
    """r1: S01/S02, one claim. r2: S03 with a document, two chunks, two claims, a rejection,
    a review — everything a figure might leak across the round boundary from."""
    store = Store("fixture", base=tmp_path)
    _write(store, "candidates.jsonl", [
        {"candidate_key": "r1-a", "source_id": "S01", "round": "r1", "channel": "keyword",
         "source_class": "ACA", "discovered_at": "2026-10-01T10:00:00+00:00"},
        {"candidate_key": "r1-b", "source_id": "S02", "round": "r1", "channel": "keyword",
         "source_class": "ACA", "discovered_at": "2026-10-01T10:00:01+00:00"},
        {"candidate_key": "r2-a", "source_id": "S03", "round": "r2", "channel": "citation",
         "source_class": "ACA", "discovered_at": "2026-10-02T10:00:00+00:00"},
    ])
    _write(store, "acquisitions.jsonl", [
        {"candidate_key": "r2-a", "source_id": "S03", "acquired": True, "sha256": "0" * 64,
         "url": "https://example.org/s03.pdf", "fetched_at": "2026-10-02T11:00:00+00:00"},
    ])
    _write(store, "documents.jsonl", [
        {"source_id": "S03", "fulltext_confirmed": True, "generation_sha256": "g1",
         "chunks": 2, "chunk_ids": ["ch1", "ch2"], "built_at": "2026-10-02T12:00:00+00:00"},
    ])
    _write(store, "chunks.jsonl", [
        {"chunk_id": "ch1", "source_id": "S03", "generation_sha256": "g1", "text": "body one",
         "built_at": "2026-10-02T12:00:01+00:00"},
        {"chunk_id": "ch2", "source_id": "S03", "generation_sha256": "g1", "text": "body two",
         "built_at": "2026-10-02T12:00:02+00:00"},
    ])
    _write(store, "claims.jsonl", [
        {"claim_id": "c0", "question_id": "Q02", "source_id": "S01", "source_class": "ACA",
         "harvested_at": "2026-10-01T11:00:00+00:00", "gate_revision": 1},
        {"claim_id": "c1", "question_id": "Q01", "source_id": "S03", "source_class": "ACA",
         "chunk_id": "ch1", "harvested_at": "2026-10-03T10:00:00+00:00", "gate_revision": 1},
        {"claim_id": "c2", "question_id": "Q01", "source_id": "S03", "source_class": "ACA",
         "chunk_id": "ch2", "harvested_at": "2026-10-03T10:00:01+00:00", "gate_revision": 1},
    ])
    _write(store, "rejections.jsonl", [
        {"claim_id": "c3", "source_id": "S03", "chunk_id": "ch1",
         "failure": "NUMBER_NOT_IN_QUOTE",
         "gate_revision": 1, "harvested_at": "2026-10-03T11:00:00+00:00"},
    ])
    _write(store, "reviews.jsonl", [
        {"claim_id": "c1", "verdict": "SUPPORTED", "reason": "reads correctly",
         "review_version": 2, "reviewed_at": "2026-10-04T10:00:00+00:00"},
    ])
    return store


def _stage(rs, name):
    return next(s for s in rs.stages if s.name == name)


def test_round_state_claims_do_not_leak_between_rounds(project, two_rounds):
    """T2: extract outputs, rejections_by_reason and every QuestionRow.claims count one round only."""
    r1 = round_state.state(project, two_rounds, round_name="r1")
    extract1 = _stage(r1, "extract")
    assert extract1.outputs == 1                       # c0 alone; c1/c2 belong to r2
    assert extract1.rejected is None                   # no r1 rejection rows at all
    assert r1.rejections_by_reason == {}
    spine1 = {q.id: q for q in r1.questions}
    assert spine1["Q02"].claims == 1
    assert spine1["Q01"].claims == 0
    assert spine1["Q02"].claims_by_class == {"ACA": 1}

    r2 = round_state.state(project, two_rounds, round_name="r2")
    extract2 = _stage(r2, "extract")
    assert extract2.outputs == 2                       # c1 and c2, never c0
    assert extract2.rejected == 1                      # c3
    assert r2.rejections_by_reason == {"NUMBER_NOT_IN_QUOTE": 1}
    spine2 = {q.id: q for q in r2.questions}
    assert spine2["Q01"].claims == 2
    assert spine2["Q02"].claims == 0


def test_round_state_review_and_chunks_scoped(project, two_rounds):
    """T3: the review progress denominator and the extract inputs count the selected round only."""
    r2 = round_state.state(project, two_rounds, round_name="r2")
    review2 = _stage(r2, "review")
    assert review2.inputs == 2                         # r2's two claims
    assert review2.outputs == 1                        # the c1 review
    assert review2.progress.total == 2
    assert _stage(r2, "extract").inputs == 2           # r2's two chunks

    r1 = round_state.state(project, two_rounds, round_name="r1")
    review1 = _stage(r1, "review")
    assert review1.inputs == 1                         # c0 alone
    assert review1.outputs is None                     # no r1 review rows exist
    assert review1.progress.total == 1
    # r1 wrote no chunks: zero is countable, and `or None` keeps the honest rendering (§4).
    assert _stage(r1, "extract").inputs is None


def test_scoped_activity_and_last_write_exclude_other_round(project, two_rounds):
    """T4: scoped activity carries no other round's rows, and a stage the selector never wrote
    has no last write — even though another round wrote that ledger."""
    from claimstone.scope import Selector

    rows = round_state.activity(two_rounds, 50, Selector("r1"))
    assert rows, "r1 wrote candidates and a claim; its own rows must appear"
    for row in rows:
        assert row["row"].get("source_id") != "S03"
        assert row["row"].get("candidate_key") != "r2-a"
        assert row["ledger"] != "documents.jsonl" and row["ledger"] != "chunks.jsonl"

    r1 = round_state.state(project, two_rounds, round_name="r1")
    assert _stage(r1, "normalize").last_write is None   # r2 alone wrote documents/chunks
    assert _stage(r1, "review").last_write is None      # the one review belongs to r2's claim
    assert _stage(r1, "extract").last_write is not None  # c0 is r1's, with its own timestamp
    # Whole store keeps the mtime behaviour: the same stage now sees r2's write.
    whole = round_state.state(project, two_rounds)
    assert _stage(whole, "normalize").last_write is not None


def test_whole_store_state_unchanged(project, two_rounds):
    """T5: round_name=None keeps today's numbers — the concrete ones this fixture implies."""
    rs = round_state.state(project, two_rounds)
    assert _stage(rs, "discover").outputs == 3
    assert _stage(rs, "extract").outputs == 3            # c0, c1, c2 — every round's claims
    assert _stage(rs, "extract").rejected == 1
    assert _stage(rs, "extract").inputs == 2             # both chunks, no round asked
    assert _stage(rs, "review").inputs == 3
    assert _stage(rs, "review").outputs == 1
    assert rs.rejections_by_reason == {"NUMBER_NOT_IN_QUOTE": 1}
    spine = {q.id: q for q in rs.questions}
    assert spine["Q01"].claims == 2
    assert spine["Q02"].claims == 1
    assert rs.errors == ()


def test_corrupt_acquisitions_is_an_error_not_zero(project, tmp_path):
    """T7: interior damage in acquisitions.jsonl is named in errors and withholds the figures."""
    store = Store("fixture", base=tmp_path)
    _write(store, "candidates.jsonl", [
        {"candidate_key": "k1", "source_id": "S01", "round": "r1", "channel": "keyword",
         "source_class": "ACA"},
    ])
    _write(store, "acquisitions.jsonl", [
        {"candidate_key": "k1", "source_id": "S01", "acquired": True,
         "fetched_at": "2026-10-01T11:00:00+00:00"},
    ])
    # Interior damage, not a torn tail: a complete line of non-JSON between two valid rows.
    with store.path("acquisitions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{bad\n")
    _write(store, "acquisitions.jsonl", [
        {"candidate_key": "k1", "source_id": "S01", "acquired": False},
    ])

    rs = round_state.state(project, store)
    assert any(error.startswith("LEDGER_CORRUPT") for error in rs.errors)
    acquire = _stage(rs, "acquire")
    normalize = _stage(rs, "normalize")
    assert acquire.outputs is None and acquire.inputs is None       # withheld, not zero
    assert normalize.outputs is None and normalize.inputs is None
    assert acquire.detail == "ledger damaged: figures withheld"
    assert rs.floor is None                                          # no figure over damage
