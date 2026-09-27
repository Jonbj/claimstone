"""Stage 4: work units out, claims and rejections in. No model, no socket."""

import json

import pytest

from claimstone import extract, model_call
from claimstone.config import Question
from claimstone.store import Store

QUESTIONS = (
    Question(id="H02", text="News carries information about future returns.", kind="effect"),
    Question(id="H23", text="The effect survives transaction costs.", kind="effect"),
    Question(id="H06", text="Novelty improves the signal.", kind="heterogeneity"),
    Question(id="H05", text="The event is the unit of inference.", kind="method"),
    Question(id="H01", text="Return is not ground truth.", kind="premise"),
    Question(id="H11", text="Two lanes stay parallel.", kind="operational"),
)

CHUNK_TEXT = ("We find that news tone does indeed have an effect on stock returns. "
              "Portfolios earn excess returns for up to 13 weeks.")


class FakeProject:
    name = "t"
    questions = QUESTIONS
    extraction = {}


def _store(tmp_path, chunks=(("S01", "S01#c1", CHUNK_TEXT),)):
    store = Store("t", base=tmp_path)
    for source_id, chunk_id, text in chunks:
        store.append("documents.jsonl", {"source_id": source_id, "sha256": f"h-{source_id}",
                                         "fulltext_confirmed": True, "source_class": "ACA"})
        store.append("chunks.jsonl", {"chunk_id": chunk_id, "source_id": source_id,
                                      "kind": "prose", "section": "Results", "text": text,
                                      "chars": len(text)})
    return store


# --- building -------------------------------------------------------------------------------------

def test_one_call_per_lane_per_chunk_and_none_for_operational(tmp_path):
    """Four lanes, not one call per question: the lane's system prompt is identical across every
    chunk, which is what a cached-input price applies to. `operational` gets no verdict, so asking
    about it spends a call on an answer nothing reads."""
    store = _store(tmp_path)
    result = extract.build(FakeProject(), store, batch="b1")
    assert result["units"] == 4
    units = model_call.Queue(store, lane="extract", batch="b1").requests()
    # `lane` is model_call's word for its two queues; the four kinds are the registry's.
    assert {u["lane"] for u in units} == {"extract"}
    assert {u["kind"] for u in units} == {"effect", "heterogeneity", "method", "premise"}
    assert result["by_kind"] == {"effect": 1, "heterogeneity": 1, "method": 1, "premise": 1}
    assert "operational" not in result["by_kind"]


def test_the_lane_prompt_carries_only_its_own_questions(tmp_path):
    store = _store(tmp_path)
    extract.build(FakeProject(), store, batch="b1")
    units = model_call.Queue(store, lane="extract", batch="b1").requests()
    effect = next(u for u in units if u["kind"] == "effect")
    assert "H02" in effect["system"] and "H23" in effect["system"]
    assert "H06" not in effect["system"] and "H05" not in effect["system"]


def test_the_schema_admits_only_that_lanes_questions_and_stances(tmp_path):
    from claimstone import claimgate

    store = _store(tmp_path)
    extract.build(FakeProject(), store, batch="b1")
    units = model_call.Queue(store, lane="extract", batch="b1").requests()
    method = next(u for u in units if u["kind"] == "method")
    props = method["response_schema"]["items"]["properties"]
    assert props["question_id"]["enum"] == ["H05"]
    assert props["stance"]["enum"] == list(claimgate.STANCES_BY_KIND["method"])


def test_the_chunk_travels_so_harvest_knows_what_to_check_against(tmp_path):
    store = _store(tmp_path)
    extract.build(FakeProject(), store, batch="b1")
    unit = model_call.Queue(store, lane="extract", batch="b1").requests()[0]
    assert unit["chunk_id"] == "S01#c1"
    assert unit["user"] == CHUNK_TEXT


def test_only_confirmed_documents_are_extracted_from(tmp_path):
    """A vendor fact sheet produced no chunks, but a document whose confirmation was withdrawn may
    still have them on disk from an earlier round."""
    store = _store(tmp_path)
    store.append("documents.jsonl", {"source_id": "S01", "sha256": "h-S01",
                                     "fulltext_confirmed": False,
                                     "failure_class": "NOT_A_DOCUMENT"})
    assert extract.build(FakeProject(), store, batch="b1")["units"] == 0


def test_building_twice_adds_nothing(tmp_path):
    store = _store(tmp_path)
    extract.build(FakeProject(), store, batch="b1")
    assert extract.build(FakeProject(), store, batch="b1")["units"] == 0


# --- harvesting -----------------------------------------------------------------------------------

def _answer(store, *, records, lane_kind="effect"):
    """Put a drained result in the queue, as model-run would have."""
    queue = model_call.Queue(store, lane="extract", batch="b1")
    unit = next(u for u in queue.requests() if u["kind"] == lane_kind)
    store.append(queue.results_name, {
        "call_id": unit["call_id"], "backend": "fake", "ok": True, "output": records,
        "model": "m", "harness_version": "fake/1", "attempt_no": 1, "cost_usd": None})
    return unit


def test_a_clean_record_becomes_a_claim(tmp_path):
    store = _store(tmp_path)
    extract.build(FakeProject(), store, batch="b1")
    _answer(store, records=[{"question_id": "H02", "stance": "SUPPORTS",
                             "claim": "News tone affects returns.",
                             "evidence_quote": "news tone does indeed have an effect"}])
    result = extract.harvest(FakeProject(), store, batch="b1")
    assert (result["proposed"], result["accepted"], result["rejected"]) == (1, 1, 0)
    claim = next(iter(store.read("claims.jsonl")))
    assert claim["question_id"] == "H02"
    assert claim["source_id"] == "S01"
    assert claim["chunk_id"] == "S01#c1"
    assert claim["source_class"] == "ACA"


def test_a_rejected_record_is_kept_whole_with_the_check_that_failed(tmp_path):
    store = _store(tmp_path)
    extract.build(FakeProject(), store, batch="b1")
    bad = {"question_id": "H02", "stance": "SUPPORTS", "claim": "News tone affects returns.",
           "evidence_quote": "a quote that is nowhere in the chunk"}
    _answer(store, records=[bad])
    result = extract.harvest(FakeProject(), store, batch="b1")
    assert (result["accepted"], result["rejected"]) == (0, 1)
    rejection = next(iter(store.read("rejections.jsonl")))
    assert rejection["failure"] == "QUOTE_NOT_FOUND"
    assert rejection["record"] == bad
    assert list(store.read("claims.jsonl")) == []


def test_harvest_opens_no_socket(tmp_path, monkeypatch):
    import socket

    store = _store(tmp_path)
    extract.build(FakeProject(), store, batch="b1")
    _answer(store, records=[])

    def refuse(*args, **kwargs):
        raise AssertionError("harvest reads results.jsonl and writes ledgers")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    extract.harvest(FakeProject(), store, batch="b1")


def test_harvesting_twice_does_not_double_a_claim(tmp_path):
    store = _store(tmp_path)
    extract.build(FakeProject(), store, batch="b1")
    _answer(store, records=[{"question_id": "H02", "stance": "SUPPORTS",
                             "claim": "News tone affects returns.",
                             "evidence_quote": "news tone does indeed have an effect"}])
    extract.harvest(FakeProject(), store, batch="b1")
    again = extract.harvest(FakeProject(), store, batch="b1")
    assert again["accepted"] == 0
    assert len(list(store.read("claims.jsonl"))) == 1


def test_a_call_two_chunks_asked_for_yields_a_claim_for_each(tmp_path):
    """The fan-out model_call records. Two chunks with identical text are one call and two places the
    answer came from, and a claim bound to only one of them loses the other's provenance."""
    store = _store(tmp_path, chunks=(("S01", "S01#c1", CHUNK_TEXT), ("S02", "S02#c9", CHUNK_TEXT)))
    extract.build(FakeProject(), store, batch="b1")
    queue = model_call.Queue(store, lane="extract", batch="b1")
    effect = [u for u in queue.requests() if u["kind"] == "effect"]
    assert len(effect) == 1, "identical chunks are one call"
    assert len(effect[0]["asked_by"]) == 2

    store.append(queue.results_name, {
        "call_id": effect[0]["call_id"], "backend": "fake", "ok": True, "model": "m",
        "harness_version": "fake/1", "attempt_no": 1, "cost_usd": None,
        "output": [{"question_id": "H02", "stance": "SUPPORTS",
                    "claim": "News tone affects returns.",
                    "evidence_quote": "news tone does indeed have an effect"}]})
    extract.harvest(FakeProject(), store, batch="b1")
    assert {c["chunk_id"] for c in store.read("claims.jsonl")} == {"S01#c1", "S02#c9"}


def test_a_failed_call_is_not_an_absence_of_claims(tmp_path):
    """The distinction the whole module exists for. A call that never returned a valid answer says
    nothing about the chunk, and counting it as zero claims would be a finding it did not earn."""
    store = _store(tmp_path)
    extract.build(FakeProject(), store, batch="b1")
    queue = model_call.Queue(store, lane="extract", batch="b1")
    unit = queue.requests()[0]
    store.append(queue.results_name, {"call_id": unit["call_id"], "backend": "fake", "ok": False,
                                      "failure_class": "TIMEOUT", "output": None})
    result = extract.harvest(FakeProject(), store, batch="b1")
    assert result["proposed"] == 0
    assert result["calls_without_an_answer"] == 1
    assert list(store.read("rejections.jsonl")) == []


def test_a_request_that_does_not_record_its_kind_cannot_have_the_kind_check_run(tmp_path):
    """The same third state as `prompt_verified`. WRONG_KIND exists to catch a model answering about a
    question outside the kind it was asked about, and a request that never recorded which kind was
    asked cannot support that check. Saying so beats inventing a lane — and beats rejecting every
    claim of a batch that predates the field, which was already paid for.
    """
    store = _store(tmp_path)
    extract.build(FakeProject(), store, batch="b1")
    queue = model_call.Queue(store, lane="extract", batch="b1")
    unit = next(u for u in queue.requests() if u["kind"] == "effect")
    # A batch built before the field existed: the stored request carries no `kind`.
    store.append(queue.requests_name, {k: v for k, v in unit.items() if k != "kind"})
    store.append(queue.results_name, {
        "call_id": unit["call_id"], "backend": "fake", "ok": True, "model": "m",
        "harness_version": "fake/1", "attempt_no": 1, "cost_usd": None,
        "output": [{"question_id": "H02", "stance": "SUPPORTS",
                    "claim": "News tone affects returns.",
                    "evidence_quote": "news tone does indeed have an effect"}]})

    result = extract.harvest(FakeProject(), store, batch="b1")
    assert result["accepted"] == 1
    assert result["kind_unverified"] == 1
    claim = next(iter(store.read("claims.jsonl")))
    assert claim["kind_verified"] is False


def test_a_request_recording_its_kind_gets_the_check_and_says_so(tmp_path):
    store = _store(tmp_path)
    extract.build(FakeProject(), store, batch="b1")
    _answer(store, records=[{"question_id": "H02", "stance": "SUPPORTS",
                             "claim": "News tone affects returns.",
                             "evidence_quote": "news tone does indeed have an effect"}])
    result = extract.harvest(FakeProject(), store, batch="b1")
    assert result["kind_unverified"] == 0
    assert next(iter(store.read("claims.jsonl")))["kind_verified"] is True


def test_an_accepted_claim_carries_the_engine_converted_value(tmp_path):
    """The model reports `2.4%` and never `0.024`: the gate checks the as-written string against the
    quote, so the value cannot be wrong in a way the quote could not reveal."""
    text = "net sentiment of 2.4% (0.008) over one week predicts returns"
    store = _store(tmp_path, chunks=(("S01", "S01#c1", text),))
    extract.build(FakeProject(), store, batch="b1")
    _answer(store, records=[{"question_id": "H02", "stance": "SUPPORTS",
                             "claim": "Net sentiment of 2.4% predicts returns.",
                             "evidence_quote": "net sentiment of 2.4% (0.008) over one week",
                             "estimate_as_written": "2.4%",
                             "uncertainty_as_written": "(0.008)"}])
    assert extract.harvest(FakeProject(), store, batch="b1")["accepted"] == 1
    claim = next(iter(store.read("claims.jsonl")))
    assert claim["estimate"] == pytest.approx(0.024)
    assert claim["estimate_scale"] == "fraction"
    assert claim["uncertainty_bracketed"] is True
    assert claim["estimate_as_written"] == "2.4%"


def test_a_value_the_engine_cannot_read_is_a_recorded_rejection_not_a_null(tmp_path):
    """A null would read as "no estimate reported", which is a claim about the paper that a parser
    failure has not earned."""
    text = "sentiment of two-thirds of a standard deviation predicts returns"
    store = _store(tmp_path, chunks=(("S01", "S01#c1", text),))
    extract.build(FakeProject(), store, batch="b1")
    _answer(store, records=[{"question_id": "H02", "stance": "SUPPORTS",
                             "claim": "Sentiment predicts returns.",
                             "evidence_quote": "sentiment of two-thirds of a standard deviation",
                             "estimate_as_written": "two-thirds"}])
    result = extract.harvest(FakeProject(), store, batch="b1")
    assert (result["accepted"], result["rejected"]) == (0, 1)
    rejection = next(iter(store.read("rejections.jsonl")))
    assert rejection["failure"] == "UNPARSEABLE_VALUE"
    assert "two-thirds" in rejection["detail"]
    assert list(store.read("claims.jsonl")) == []


def test_a_re_harvest_says_what_it_already_held_rather_than_reporting_zero(tmp_path):
    """`0 accepted, 0 rejected` beside `SECONDHAND_CLAIM 2` reads as a contradiction. The counts are
    what was newly written; what was judged is a different number and both are printed."""
    store = _store(tmp_path)
    extract.build(FakeProject(), store, batch="b1")
    _answer(store, records=[{"question_id": "H02", "stance": "SUPPORTS",
                             "claim": "News tone affects returns.",
                             "evidence_quote": "news tone does indeed have an effect"}])
    extract.harvest(FakeProject(), store, batch="b1")
    again = extract.harvest(FakeProject(), store, batch="b1")
    assert (again["accepted"], again["rejected"]) == (0, 0)
    assert again["already_held"] == 1
    assert again["proposed"] == 1


def test_a_single_kind_can_be_built_alone(tmp_path):
    """So one lane can be measured on its own budget. Without it, testing the gate on a kind it has
    never seen means building all four and draining in request order, which is the first document's
    chunks four times over."""
    store = _store(tmp_path)
    result = extract.build(FakeProject(), store, batch="b1", kind="heterogeneity")
    assert result["by_kind"] == {"heterogeneity": 1}
    assert result["units"] == 1


def test_an_unknown_kind_is_refused_by_name(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError, match="nonsense"):
        extract.build(FakeProject(), store, batch="b1", kind="nonsense")


def test_the_limit_applies_within_a_kind_and_not_across_all_four(tmp_path):
    chunks = tuple((f"S{n:02d}", f"S{n:02d}#c1", f"{CHUNK_TEXT} {n}") for n in range(5))
    store = _store(tmp_path, chunks=chunks)
    result = extract.build(FakeProject(), store, batch="b1", limit=3)
    # Three chunks of each kind, not three units in total: a limit that stopped after the first kind
    # would silently measure one lane and call it a sample of four.
    assert result["by_kind"] == {"effect": 3, "heterogeneity": 3, "method": 3, "premise": 3}


def test_two_results_sharing_a_quote_are_two_claims_when_they_say_so(tmp_path):
    """The spec's `result_id`: a chunk reporting three estimates that bear on one question produces three
    records, and a claim_id keyed on the quote alone would collapse any two that cite the same sentence.
    Zero collisions in the 66 measured claims, and reachable — a table row quoted once supports several
    estimates."""
    text = "the coefficient is 2.4% at one week and 1.1% at four weeks, both significant"
    store = _store(tmp_path, chunks=(("S01", "S01#c1", text),))
    extract.build(FakeProject(), store, batch="b1")
    quote = "the coefficient is 2.4% at one week and 1.1% at four weeks"
    _answer(store, records=[
        {"result_id": "r1", "question_id": "H02", "stance": "SUPPORTS",
         "claim": "The one-week coefficient is 2.4%.", "evidence_quote": quote},
        {"result_id": "r2", "question_id": "H02", "stance": "SUPPORTS",
         "claim": "The four-week coefficient is 1.1%.", "evidence_quote": quote}])
    assert extract.harvest(FakeProject(), store, batch="b1")["accepted"] == 2
    assert len({c["claim_id"] for c in store.read("claims.jsonl")}) == 2


def test_a_record_without_a_result_id_keeps_the_identity_it_already_had(tmp_path):
    """A batch built before the field cannot supply one, and re-deriving every stored claim's id would
    write the 63 already harvested a second time for nothing. Same reasoning as `kind_verified`."""
    store = _store(tmp_path)
    extract.build(FakeProject(), store, batch="b1")
    _answer(store, records=[{"question_id": "H02", "stance": "SUPPORTS",
                             "claim": "News tone affects returns.",
                             "evidence_quote": "news tone does indeed have an effect"}])
    extract.harvest(FakeProject(), store, batch="b1")
    stored = next(iter(store.read("claims.jsonl")))["claim_id"]
    assert stored == extract.claim_id("S01#c1", "H02", "news tone does indeed have an effect")


def test_the_built_schema_asks_for_a_result_id(tmp_path):
    store = _store(tmp_path)
    extract.build(FakeProject(), store, batch="b1")
    unit = model_call.Queue(store, lane="extract", batch="b1").requests()[0]
    assert "result_id" in unit["response_schema"]["items"]["required"]


# --- The four call shapes, and the fields stage 6 needs -------------------------------------------
#
# Measured: the first complete round produced 3,971 claims and **zero** carried a converted value, because
# the schema asked only for the core four fields. numbers.py existed and harvest called it and there was
# nothing to convert. A stage 6 input that does not exist is not improved by a converter that works.

def test_the_effect_shape_asks_for_the_figures_as_the_paper_wrote_them(tmp_path):
    store = _store(tmp_path)
    extract.build(FakeProject(), store, batch="b1", kind="effect")
    props = model_call.Queue(store, lane="extract", batch="b1").requests()[0][
        "response_schema"]["items"]["properties"]
    for field in ("estimate_as_written", "uncertainty_as_written", "horizon_as_written",
                  "sample", "design", "dependence"):
        assert field in props, field
    # Optional, every one. A chunk that reports an estimate and no standard error is ordinary, and
    # requiring the field would reject the claim for something the passage does not have.
    required = model_call.Queue(store, lane="extract", batch="b1").requests()[0][
        "response_schema"]["items"]["required"]
    assert set(required) == {"result_id", "question_id", "claim", "evidence_quote", "stance"}


def test_the_heterogeneity_shape_asks_for_the_contrast_and_its_sides(tmp_path):
    store = _store(tmp_path)
    extract.build(FakeProject(), store, batch="b1", kind="heterogeneity")
    props = model_call.Queue(store, lane="extract", batch="b1").requests()[0][
        "response_schema"]["items"]["properties"]
    for field in ("moderator", "high_side", "low_side", "contrast_as_written",
                  "contrast_uncertainty_as_written", "prespecified"):
        assert field in props, field
    assert props["prespecified"]["type"] == "boolean"


def test_the_method_shape_asks_how_the_literature_answered(tmp_path):
    store = _store(tmp_path)
    extract.build(FakeProject(), store, batch="b1", kind="method")
    props = model_call.Queue(store, lane="extract", batch="b1").requests()[0][
        "response_schema"]["items"]["properties"]
    assert props["support_type"]["enum"] == ["ENDORSEMENT", "DEMONSTRATED_FAILURE"]
    # The source's declared role comes from sources.yaml and is added by the engine: which classes are
    # methodological is project data, and reading it off the class id would be domain knowledge.
    assert "role" not in props


def test_the_premise_shape_asks_for_nothing_else(tmp_path):
    store = _store(tmp_path)
    extract.build(FakeProject(), store, batch="b1", kind="premise")
    props = model_call.Queue(store, lane="extract", batch="b1").requests()[0][
        "response_schema"]["items"]["properties"]
    assert set(props) == {"result_id", "question_id", "claim", "evidence_quote", "stance"}


def test_an_effect_claim_arrives_with_a_converted_estimate(tmp_path):
    text = "net sentiment of 2.4% (0.008) over one week predicts returns in US equities 1996-2008"
    store = _store(tmp_path, chunks=(("S01", "S01#c1", text),))
    extract.build(FakeProject(), store, batch="b1", kind="effect")
    _answer(store, records=[{"result_id": "r1", "question_id": "H02", "stance": "SUPPORTS",
                             "claim": "Net sentiment of 2.4% predicts returns.",
                             "evidence_quote": "net sentiment of 2.4% (0.008) over one week",
                             "estimate_as_written": "2.4%",
                             "uncertainty_as_written": "(0.008)",
                             "horizon_as_written": "one week",
                             "sample": "US equities 1996-2008"}])
    assert extract.harvest(FakeProject(), store, batch="b1")["accepted"] == 1
    claim = next(iter(store.read("claims.jsonl")))
    assert claim["estimate"] == pytest.approx(0.024)
    assert claim["estimate_scale"] == "fraction"
    assert claim["uncertainty_bracketed"] is True
    # Prose is carried and not converted: a horizon is not a number.
    assert claim["horizon_as_written"] == "one week"
    assert "horizon" not in claim
