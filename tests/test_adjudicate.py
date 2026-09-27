"""Layer 2: a person reads the profile and signs. The only place a verdict comes from.

This is slower than a threshold and it is the honest shape. The alternative was an automatic rule that
would have had to be defended, and the defence did not exist.
"""

import pytest

from claimstone import evidence, synthesize
from claimstone.store import Store
from tests.test_synthesize import QUESTIONS, _project, _store, claim, review

RATIONALE = (
    "One refereed source with a converted estimate and a verified quote, against no contrary result. "
    "The sample label is unique so linkage is not at issue, and the magnitude is not judged because no "
    "material-effect bar has been declared for this question."
)


def _built(tmp_path, claims=(), reviews=()):
    store = _store(tmp_path, claims=claims or [claim()], reviews=reviews or [review()])
    synthesize.build(_project(tmp_path), store)
    return store


def _hash(store, question_id="H02"):
    return synthesize.latest_profiles(store)[question_id]["profile_sha256"]


def test_a_verdict_is_recorded_with_the_hash_of_the_profile_it_judged(tmp_path):
    store = _built(tmp_path)
    row = synthesize.adjudicate(store, "H02", verdict="SUPPORTED", rationale=RATIONALE,
                                by="an operator", profile_sha256=_hash(store))
    assert row["verdict"] == "SUPPORTED"
    assert row["profile_sha256"] == _hash(store)
    assert row["adjudicated_by"] == "an operator"
    # The three identities travel with the judgement, not only with the profile.
    assert row["registry_version"] == 3
    assert row["registry_sha256"] == "deadbeef"
    assert row["decision_contract_version"] == 1


def test_a_provisional_profile_is_refused(tmp_path):
    """A verdict recorded against evidence that was still arriving is a verdict about something that no
    longer exists."""
    store = _built(tmp_path, claims=[claim(), claim(claim_id="c2")], reviews=[review()])
    with pytest.raises(synthesize.Provisional) as raised:
        synthesize.adjudicate(store, "H02", verdict="SUPPORTED", rationale=RATIONALE, by="x")
    assert "awaiting_review" in str(raised.value)
    assert list(store.read(synthesize.ADJUDICATIONS)) == []


def test_a_rationale_below_the_declared_minimum_is_refused(tmp_path):
    """The reasoning is the verdict's only defence, and one that does not survive being written down is
    not a verdict."""
    store = _built(tmp_path)
    with pytest.raises(ValueError) as raised:
        synthesize.adjudicate(store, "H02", verdict="SUPPORTED", rationale="Looks right.", by="x")
    assert str(synthesize.MIN_RATIONALE_CHARS) in str(raised.value)
    assert list(store.read(synthesize.ADJUDICATIONS)) == []


def test_a_verdict_outside_the_five_states_is_refused(tmp_path):
    store = _built(tmp_path)
    with pytest.raises(ValueError):
        synthesize.adjudicate(store, "H02", verdict="PROBABLY", rationale=RATIONALE, by="x")


def test_an_operational_question_cannot_be_adjudicated_at_all(tmp_path):
    """No sixth state, and no verdict either."""
    store = _built(tmp_path)
    with pytest.raises(ValueError) as raised:
        synthesize.adjudicate(store, "H11", verdict="SUPPORTED", rationale=RATIONALE, by="x")
    assert "sixth state" in str(raised.value)


def test_a_question_with_no_profile_is_refused_rather_than_invented(tmp_path):
    store = _store(tmp_path, claims=[claim()], reviews=[review()])
    with pytest.raises(KeyError):
        synthesize.adjudicate(store, "H02", verdict="SUPPORTED", rationale=RATIONALE, by="x")


def test_a_hash_that_has_moved_since_the_reader_saw_it_is_refused(tmp_path):
    store = _built(tmp_path)
    with pytest.raises(synthesize.StaleProfile) as raised:
        synthesize.adjudicate(store, "H02", verdict="SUPPORTED", rationale=RATIONALE, by="x",
                              profile_sha256="0" * 64)
    assert "000000000000" in str(raised.value)


def test_no_verified_claim_can_still_be_adjudicated_as_unanswered(tmp_path):
    """The whole point of the fourth state: the corpus was read and does not settle it. `NO_VERIFIED_CLAIM`
    is the profile's description; only a person may turn it into a verdict, and never into NEVER_ASKED
    without having screened for the question."""
    store = _built(tmp_path)
    row = synthesize.adjudicate(store, "H06", verdict="UNANSWERED_IN_LITERATURE",
                                rationale=RATIONALE, by="an operator")
    assert row["verdict"] == "UNANSWERED_IN_LITERATURE"


# --- how verdicts are displayed -------------------------------------------------------------------

def test_a_matching_adjudication_is_displayed_and_not_marked_stale(tmp_path):
    store = _built(tmp_path)
    synthesize.adjudicate(store, "H02", verdict="SUPPORTED", rationale=RATIONALE, by="x")
    result = synthesize.verdicts(store)
    row = next(r for r in result["rows"] if r["profile"]["question_id"] == "H02")
    assert row["stale"] is False
    assert row["verdict"]["verdict"] == "SUPPORTED"
    assert result["adjudicated"] == 1


def test_an_adjudication_whose_evidence_changed_is_shown_as_stale_with_both_hashes(tmp_path):
    """A judgement made against different evidence is a judgement about a different question, and
    quietly keeping it on screen is how a verdict outlives its reason."""
    store = _built(tmp_path)
    synthesize.adjudicate(store, "H02", verdict="SUPPORTED", rationale=RATIONALE, by="x")
    judged = _hash(store)

    # A second source arrives and is reviewed. Same question, different evidence.
    store.append("claims.jsonl", claim(claim_id="c2", source_id="ACA002"))
    store.append("reviews.jsonl", review(claim_id="c2"))
    synthesize.build(_project(tmp_path), store)

    result = synthesize.verdicts(store)
    row = next(r for r in result["rows"] if r["profile"]["question_id"] == "H02")
    assert row["stale"] is True
    assert row["verdict"]["profile_sha256"] == judged
    assert row["profile"]["profile_sha256"] != judged
    assert result["stale"] == 1
    # And it no longer counts as adjudicated.
    assert result["adjudicated"] == 0


def test_a_question_awaiting_a_person_is_counted_and_an_operational_one_is_not(tmp_path):
    store = _built(tmp_path)
    result = synthesize.verdicts(store)
    # H02 and H06 await a person; H11 receives no verdict and is not waiting for one.
    assert result["awaiting_adjudication"] == 2
    assert result["no_controlled_error_rate_across"] == 2


def test_the_disclosure_travels_with_the_display_too(tmp_path):
    store = _built(tmp_path)
    assert synthesize.verdicts(store)["no_controlled_error_rate_across"] == 2


def test_rebuilding_the_same_evidence_does_not_make_a_verdict_stale(tmp_path):
    """A rebuild at a later minute is not different evidence, and treating it as such would make every
    recorded verdict stale overnight."""
    store = _built(tmp_path)
    synthesize.adjudicate(store, "H02", verdict="SUPPORTED", rationale=RATIONALE, by="x")
    synthesize.build(_project(tmp_path), store)
    assert synthesize.verdicts(store)["stale"] == 0
