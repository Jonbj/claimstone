"""Stage 5: an adversarial second read, and the one rule that makes it a control.

On the corpus that motivated this project, a second read marked 54 of 292 claims OVERSTATED and 21
AMBIGUOUS — 25.7% — **after** they had passed the quote check. The gate verifies that a quote is present;
nothing mechanical can verify that the claim the quote supports is the claim that was made.
"""

import pytest

from claimstone import model_call, review
from claimstone.config import Question
from claimstone.store import Store

QUESTIONS = (
    Question(id="H02", text="News carries information about future returns.", kind="effect"),
    Question(id="H06", text="Novelty improves the signal.", kind="heterogeneity"),
)

CHUNK = ("Unlike prior work, we do not assume that sentiment is exogenous. "
         "We find that news tone does indeed have an effect on stock returns.")


class FakeProject:
    name = "t"
    questions = QUESTIONS
    registry_version = 3


def _store(tmp_path, claims=None):
    store = Store("t", base=tmp_path)
    store.append("chunks.jsonl", {"chunk_id": "S01#c1", "source_id": "S01", "kind": "prose",
                                  "section": "Results", "text": CHUNK, "chars": len(CHUNK)})
    for row in claims or [_claim()]:
        store.append("claims.jsonl", row)
    return store


def _claim(**overrides):
    base = {"claim_id": "c1", "question_id": "H02", "stance": "SUPPORTS",
            "claim": "News tone affects stock returns.",
            "evidence_quote": "news tone does indeed have an effect on stock returns",
            "chunk_id": "S01#c1", "source_id": "S01", "source_class": "ACA", "lane": "effect",
            "backend": "ollama-cloud", "model": "deepseek-v4.1-flash",
            "harness_version": "ollama-cloud/x"}
    return {**base, **overrides}


# --- building ------------------------------------------------------------------------------------

def test_a_review_unit_carries_the_whole_chunk_and_not_only_the_quote(tmp_path):
    """The expensive part and the point: a sentence reading "we find no effect" preceded by "unlike prior
    work, we do not assume" means the opposite of how it reads alone, and the mechanical gate cannot catch
    context-stripping because the substring is exact."""
    store = _store(tmp_path)
    assert review.build(FakeProject(), store, batch="r1")["units"] == 1
    unit = model_call.Queue(store, lane="review", batch="r1").requests()[0]
    assert unit["lane"] == "review"
    assert CHUNK in unit["user"]
    assert "Unlike prior work, we do not assume" in unit["user"]
    assert QUESTIONS[0].text in unit["user"]
    assert "News tone affects stock returns." in unit["user"]


def test_the_four_verdicts_are_the_only_ones_offered(tmp_path):
    store = _store(tmp_path)
    review.build(FakeProject(), store, batch="r1")
    unit = model_call.Queue(store, lane="review", batch="r1").requests()[0]
    assert unit["response_schema"]["properties"]["verdict"]["enum"] == [
        "SUPPORTED", "OVERSTATED", "AMBIGUOUS", "NOT_APPLICABLE"]


def test_a_claim_already_reviewed_is_not_rebuilt(tmp_path):
    store = _store(tmp_path)
    review.build(FakeProject(), store, batch="r1")
    store.append("reviews.jsonl", {"claim_id": "c1", "verdict": "SUPPORTED"})
    assert review.build(FakeProject(), store, batch="r2")["units"] == 0


def test_naming_the_reviewer_up_front_excludes_what_it_cannot_judge(tmp_path):
    """The build knows which reader was asked, so it can say how many claims that reader may not judge
    before a single call is paid for."""
    store = _store(tmp_path, claims=[
        _claim(claim_id="c1", backend="ollama-cloud", model="deepseek-v4.1-flash"),
        _claim(claim_id="c2", backend="claude-cli", model="claude-opus-5")])
    result = review.build(FakeProject(), store, batch="r1",
                          reviewer=("ollama-cloud", "deepseek-v4.1-flash"))
    assert result["units"] == 1
    assert result["same_reader"] == 1
    unit = model_call.Queue(store, lane="review", batch="r1").requests()[0]
    assert unit["claim_id"] == "c2"


# --- harvesting ----------------------------------------------------------------------------------

def _answer(store, *, verdict="SUPPORTED", reason="it is", backend="claude-cli",
            model="claude-opus-5", batch="r1"):
    queue = model_call.Queue(store, lane="review", batch=batch)
    unit = queue.requests()[0]
    store.append(queue.results_name, {
        "call_id": unit["call_id"], "backend": backend, "model": model, "ok": True,
        "harness_version": f"{backend}/1", "attempt_no": 1, "cost_usd": None,
        "output": {"verdict": verdict, "reason": reason}})
    return unit


def test_a_verdict_becomes_a_review_row_and_claims_is_untouched(tmp_path):
    store = _store(tmp_path)
    review.build(FakeProject(), store, batch="r1")
    before = len(list(store.read("claims.jsonl")))
    _answer(store, verdict="OVERSTATED", reason="The quote reports a mean, not predictive power.")
    result = review.harvest(FakeProject(), store, batch="r1")
    assert result["reviewed"] == 1
    row = next(iter(store.read("reviews.jsonl")))
    assert row["claim_id"] == "c1"
    assert row["verdict"] == "OVERSTATED"
    assert row["reviewed_by"] == {"backend": "claude-cli", "model": "claude-opus-5",
                                  "harness_version": "claude-cli/1"}
    # Copied onto the row rather than left to a join: a row that says who produced it and who judged it
    # can be argued with on its own.
    assert row["extracted_by"] == {"backend": "ollama-cloud", "model": "deepseek-v4.1-flash",
                                   "harness_version": "ollama-cloud/x"}
    assert len(list(store.read("claims.jsonl"))) == before


def test_a_reviewer_that_is_the_extractor_is_refused_and_both_are_named(tmp_path):
    """The one rule that makes this a control. A reader sharing the extractor's blind spots is not
    adversarial; it is a second opinion from the same opinion."""
    store = _store(tmp_path)
    review.build(FakeProject(), store, batch="r1")
    _answer(store, backend="ollama-cloud", model="deepseek-v4.1-flash")
    with pytest.raises(review.SameReader, match="deepseek-v4.1-flash"):
        review.harvest(FakeProject(), store, batch="r1")
    assert list(store.read("reviews.jsonl")) == []


def test_the_harness_version_does_not_make_a_reader_different(tmp_path):
    """`claude-cli` at two CLI versions is the same model and the same blind spots."""
    store = _store(tmp_path, claims=[_claim(backend="claude-cli", model="claude-opus-5",
                                            harness_version="claude 2.1.280")])
    review.build(FakeProject(), store, batch="r1")
    _answer(store, backend="claude-cli", model="claude-opus-5")
    with pytest.raises(review.SameReader):
        review.harvest(FakeProject(), store, batch="r1")


def test_harvest_opens_no_socket(tmp_path, monkeypatch):
    import socket

    store = _store(tmp_path)
    review.build(FakeProject(), store, batch="r1")
    _answer(store)

    def refuse(*args, **kwargs):
        raise AssertionError("harvest reads results.jsonl and writes reviews.jsonl")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    review.harvest(FakeProject(), store, batch="r1")


def test_harvesting_twice_does_not_double_a_review(tmp_path):
    store = _store(tmp_path)
    review.build(FakeProject(), store, batch="r1")
    _answer(store)
    review.harvest(FakeProject(), store, batch="r1")
    assert review.harvest(FakeProject(), store, batch="r1")["reviewed"] == 0
    assert len(list(store.read("reviews.jsonl"))) == 1


def test_a_call_with_no_valid_answer_leaves_the_claim_awaiting_review(tmp_path):
    """An unreviewed claim is not a supported claim and not an unsupported one. Counting it either way
    would give the verdict rules an input nobody checked, or make a verdict fall because stage 5 had not
    finished."""
    store = _store(tmp_path)
    review.build(FakeProject(), store, batch="r1")
    queue = model_call.Queue(store, lane="review", batch="r1")
    store.append(queue.results_name, {"call_id": queue.requests()[0]["call_id"],
                                      "backend": "claude-cli", "model": "claude-opus-5",
                                      "ok": False, "failure_class": "TIMEOUT", "output": None})
    result = review.harvest(FakeProject(), store, batch="r1")
    assert result["reviewed"] == 0
    assert result["calls_without_an_answer"] == 1
    assert list(store.read("reviews.jsonl")) == []


def test_building_for_one_question_leaves_the_others_alone(tmp_path):
    """A verdict is per question, and a profile needs only its own claims reviewed. On the real store that
    is 43 calls for the smallest question against 7,021 for the ledger."""
    claims = [_claim(), _claim(claim_id="c2", question_id="H06", lane="heterogeneity")]
    store = _store(tmp_path, claims=claims)
    assert review.build(FakeProject(), store, batch="r1", question_id="H06")["units"] == 1
    requests = list(store.read("calls/review/r1/requests.jsonl"))
    assert [r["question_id"] for r in requests] == ["H06"]
