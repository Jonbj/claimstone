"""#12: a recorded notice binds to the freshness of the signatures it can affect.

D142 recorded Crossref notices and showed them beside the evidence, but deliberately left
`profile_inputs` untouched: a notice changed nothing, so a verdict signed before a retraction
stayed "current". This file pins the binding — the notice enters the per-question evidence
hash of exactly the questions its source feeds, and nothing else.
"""

import pytest

from claimstone import status, synthesize
from tests.test_adjudicate import RATIONALE, _built, _hash
from tests.test_synthesize import _project, _store, claim, review

# Crossref's `updates` filter shape: a work whose update-to names the DOI we asked about.
RETRACTION_UPDATES = {
    "message": {"items": [
        {"DOI": "10.1234/ACA001", "update-to": [
            {"DOI": "10.1234/ACA001", "type": "retraction", "label": "Retraction",
             "source": "Crossref", "updated": {"date-parts": [[2026, 10, 18]]}}]}]}}


def _observe(store, candidate, *, work_ok=False, updates_ok=True, observed_at=None):
    store.append(status.LEDGER, status.observation(
        candidate, f"10.1234/{candidate}", work=None, updates=RETRACTION_UPDATES,
        work_ok=work_ok, updates_ok=updates_ok, observed_at=observed_at))


def _sign(store, question="H02"):
    return synthesize.adjudicate(store, question, project=_project(store.root),
                                 verdict="SUPPORTED", rationale=RATIONALE, by="an operator",
                                 signer_auth="cli-declared", actor=None,
                                 profile_sha256=_hash(store, question))


def _row(result, question="H02"):
    return next(r for r in result["rows"] if r["profile"]["question_id"] == question)


def test_a_withdrawal_marks_the_signature_it_touches_stale(tmp_path):
    store = _built(tmp_path)
    _sign(store)
    assert _row(synthesize.verdicts(store, project=_project(tmp_path)))["stale"] is False

    _observe(store, "ACA001")  # the source of c1, the only claim H02 rests on
    result = synthesize.verdicts(store, project=_project(tmp_path))
    row = _row(result)
    assert row["stale"] is True, "the quote did not change; the paper it was read from did"
    assert result["stale"] == 1

    # The way back is the designed one: re-read, then sign against the new hash.
    synthesize.build(_project(tmp_path), store)
    _sign(store)
    assert _row(synthesize.verdicts(store, project=_project(tmp_path)))["stale"] is False


def test_a_notice_on_a_source_that_feeds_no_question_changes_nothing(tmp_path):
    store = _built(tmp_path)
    _sign(store)
    _observe(store, "MET001")  # acquired and chunked, but no claim of H02 comes from it
    result = synthesize.verdicts(store, project=_project(tmp_path))
    assert _row(result)["stale"] is False
    assert _row(result, "H06")["stale"] is False


def test_signing_is_refused_until_the_notice_is_answered_for(tmp_path):
    store = _built(tmp_path)
    _sign(store)
    _observe(store, "ACA001")
    with pytest.raises(synthesize.StaleProfile):
        _sign(store)  # the reader's hash is the pre-notice one


def test_an_identical_reobservation_does_not_churn_the_hash(tmp_path):
    store = _built(tmp_path)
    _observe(store, "ACA001", observed_at="2026-10-18T10:00:00+00:00")
    synthesize.build(_project(tmp_path), store)
    first = _hash(store)
    _observe(store, "ACA001", observed_at="2026-10-19T10:00:00+00:00")
    assert _hash(store) == first, "wall clocks do not enter the projection"


def test_a_failed_lookup_is_not_evidence(tmp_path):
    store = _built(tmp_path)
    _sign(store)
    _observe(store, "ACA001", updates_ok=False)
    result = synthesize.verdicts(store, project=_project(tmp_path))
    assert _row(result)["stale"] is False, "LOOKUP_FAILED learned nothing"


def test_the_profile_carries_the_observations_it_was_hashed_under(tmp_path):
    store = _store(tmp_path, claims=[claim()], reviews=[review()])
    synthesize.build(_project(tmp_path), store)
    assert "status_observations" not in synthesize.latest_profiles(store)["H02"]

    _observe(store, "ACA001")
    synthesize.build(_project(tmp_path), store)
    observed = synthesize.latest_profiles(store)["H02"]["status_observations"]
    assert observed["ACA001"]["state"] == status.NOTICE_RECORDED
    # JSON turns the sorted tuples into lists; the content is what the hash rests on.
    assert observed["ACA001"]["notices"] == [
        ["retraction", "10.1234/aca001", "withdrawing", "2026-10-18"]]
