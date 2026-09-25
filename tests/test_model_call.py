"""The boundary: identity, the queue, the row, the drain."""

from claimstone import model_call

SCHEMA = {"type": "array", "items": {"type": "object",
                                     "properties": {"question_id": {"type": "string"}},
                                     "required": ["question_id"]}}


def unit(**overrides):
    base = {"lane": "extract", "system": "the registry", "user": "a chunk",
            "response_schema": SCHEMA, "max_output_tokens": 800,
            "source_id": "S07", "chunk_id": "S07#4", "registry_version": 2}
    return model_call.work_unit(**{**base, **overrides})


def test_the_same_inputs_give_the_same_call_id():
    assert unit()["call_id"] == unit()["call_id"]


def test_a_different_chunk_is_a_different_call():
    assert unit()["call_id"] != unit(user="another chunk")["call_id"]


def test_a_bigger_output_cap_is_honestly_a_different_call():
    # Spec §5: TRUNCATED is terminal until the cap changes, and a retry under a bigger cap
    # must not masquerade as a retry of the same call.
    assert unit()["call_id"] != unit(max_output_tokens=2000)["call_id"]


def test_a_changed_schema_is_a_different_call():
    other = {"type": "array", "items": {"type": "string"}}
    assert unit()["call_id"] != unit(response_schema=other)["call_id"]


def test_prompt_sha256_covers_the_prompt_and_nothing_else():
    # Widening it would make a mismatch ambiguous between "the prompt was mangled" and
    # "the cap differed", and the echo check exists to catch only the first.
    assert unit()["prompt_sha256"] == unit(max_output_tokens=2000)["prompt_sha256"]
    assert unit()["prompt_sha256"] != unit(system="a different registry")["prompt_sha256"]


def test_the_lane_is_part_of_the_identity():
    assert unit()["call_id"] != unit(lane="review")["call_id"]


def test_key_order_does_not_change_the_hash():
    a = unit(response_schema={"type": "object", "properties": {"x": {"type": "string"}}})
    b = unit(response_schema={"properties": {"x": {"type": "string"}}, "type": "object"})
    assert a["call_id"] == b["call_id"]


def test_two_chunks_with_the_same_text_are_one_call():
    """Deliberate, and it costs something: identical prompts are paid for once.

    What it costs is provenance — one answer, two chunks that asked for it. The identity cannot fix
    that without giving up the dedup, so the queue carries every (call_id, chunk_id) that was asked
    and fans one result back out to all of them. Measured on the 406-chunk corpus: 406 distinct
    texts, so this is a property to preserve rather than a case already occurring.
    """
    a = unit(source_id="S01", chunk_id="S01#c3")
    b = unit(source_id="S02", chunk_id="S02#c9")
    assert a["call_id"] == b["call_id"]
    assert (a["chunk_id"], b["chunk_id"]) == ("S01#c3", "S02#c9")


import pytest

from claimstone import jsonshape
from claimstone.store import Store


def test_a_batch_name_says_when_and_against_which_registry():
    name = model_call.batch_name(registry_version=2, at="2026-09-24T11:04:07+00:00")
    assert name == "2026-09-24T1104Z-r2"


def test_writing_a_queue_stores_the_units(tmp_path):
    store = Store("t", base=tmp_path)
    queue = model_call.Queue(store, lane="extract", batch="b1")
    written = queue.write([unit(), unit(user="another chunk")])
    assert written == 2
    assert len(list(queue.requests())) == 2


def test_the_same_unit_twice_is_written_once(tmp_path):
    store = Store("t", base=tmp_path)
    queue = model_call.Queue(store, lane="extract", batch="b1")
    assert queue.write([unit(), unit()]) == 1


def test_a_schema_the_validator_cannot_honour_is_refused_at_write_time(tmp_path):
    store = Store("t", base=tmp_path)
    queue = model_call.Queue(store, lane="extract", batch="b1")
    with pytest.raises(jsonshape.UnsupportedSchema):
        queue.write([unit(response_schema={"type": "string", "pattern": "^Q"})])


def test_pending_skips_what_already_succeeded(tmp_path):
    store = Store("t", base=tmp_path)
    queue = model_call.Queue(store, lane="extract", batch="b1")
    queue.write([unit(), unit(user="another chunk")])
    first = next(iter(queue.requests()))
    store.append(queue.results_name,
                 {"call_id": first["call_id"], "backend": "fake", "ok": True})
    pending = [u["call_id"] for u in queue.pending(backend="fake")]
    assert first["call_id"] not in pending
    assert len(pending) == 1


def test_another_backend_still_has_everything_to_do(tmp_path):
    # The point of the whole boundary. Collapsing results on call_id alone made a batch answered
    # by A look finished to B, which is the comparison primitive defeated by its own bookkeeping.
    store = Store("t", base=tmp_path)
    queue = model_call.Queue(store, lane="extract", batch="b1")
    queue.write([unit(), unit(user="another chunk")])
    for request in queue.requests():
        store.append(queue.results_name,
                     {"call_id": request["call_id"], "backend": "a", "ok": True})
    assert queue.pending(backend="a") == []
    assert len(queue.pending(backend="b")) == 2


def test_every_attempt_is_kept_for_cost_accounting(tmp_path):
    store = Store("t", base=tmp_path)
    queue = model_call.Queue(store, lane="extract", batch="b1")
    queue.write([unit()])
    call_id = next(iter(queue.requests()))["call_id"]
    store.append(queue.results_name, {"call_id": call_id, "backend": "a", "ok": False,
                                      "failure_class": "TIMEOUT", "cost_usd": 0.001})
    store.append(queue.results_name, {"call_id": call_id, "backend": "a", "ok": True,
                                      "cost_usd": 0.002})
    # The collapse shows one current answer; the attempts show both, because both were paid for.
    assert len(queue.results(backend="a")) == 1
    assert len(queue.attempts()) == 2


def test_pending_retries_a_transient_failure_but_not_a_terminal_one(tmp_path):
    store = Store("t", base=tmp_path)
    queue = model_call.Queue(store, lane="extract", batch="b1")
    queue.write([unit(), unit(user="another chunk")])
    units = list(queue.requests())
    store.append(queue.results_name, {"call_id": units[0]["call_id"], "backend": "fake",
                                      "ok": False, "failure_class": "TIMEOUT"})
    store.append(queue.results_name, {"call_id": units[1]["call_id"], "backend": "fake",
                                      "ok": False, "failure_class": "SCHEMA_INVALID"})
    pending = [u["call_id"] for u in queue.pending(backend="fake")]
    assert pending == [units[0]["call_id"]]


def test_a_second_chunk_asking_the_same_question_is_recorded_and_not_dropped(tmp_path):
    """Two chunks with identical text are one call, and both are places the answer came from.

    The queue used to dedup on call_id and drop the whole unit, taking the second chunk's id with
    it — so a claim that really is in the corpus would never be recorded against that chunk. One
    call, one answer, two askers.
    """
    store = Store("t", base=tmp_path)
    queue = model_call.Queue(store, lane="extract", batch="b1")
    assert queue.write([unit(source_id="S01", chunk_id="S01#c3")]) == 1
    assert queue.write([unit(source_id="S02", chunk_id="S02#c9")]) == 0

    held = list(queue.requests())
    assert len(held) == 1
    assert held[0]["asked_by"] == [
        {"source_id": "S01", "chunk_id": "S01#c3"},
        {"source_id": "S02", "chunk_id": "S02#c9"},
    ]


def test_a_merged_request_is_still_drained_once(tmp_path):
    """The merge appends a row. If pending read raw rows, the drain would pay for the call twice."""
    store = Store("t", base=tmp_path)
    queue = model_call.Queue(store, lane="extract", batch="b1")
    queue.write([unit(chunk_id="S01#c3")])
    queue.write([unit(chunk_id="S02#c9")])
    assert len(queue.pending(backend="fake")) == 1


def test_the_identical_asker_twice_adds_nothing(tmp_path):
    store = Store("t", base=tmp_path)
    queue = model_call.Queue(store, lane="extract", batch="b1")
    queue.write([unit(), unit()])
    assert [row["asked_by"] for row in queue.requests()] == [
        [{"source_id": "S07", "chunk_id": "S07#4"}]
    ]


import json as _json

from claimstone.runners.base import RawAnswer
from tests.fakes import FakeRunner


def answer(payload, **overrides):
    body = _json.dumps(payload).encode() if not isinstance(payload, bytes) else payload
    return RawAnswer(body=body, model="m1", usage={"input_tokens": 10, "output_tokens": 5},
                     cost_usd=0.001, **overrides)


def _drain(tmp_path, runner, units=None):
    store = Store("t", base=tmp_path)
    queue = model_call.Queue(store, lane="extract", batch="b1")
    queue.write(units or [unit()])
    rows = list(model_call.drain(queue, runner))
    return queue, rows


def test_a_valid_answer_is_recorded_as_ok(tmp_path):
    runner = FakeRunner(default=answer([{"question_id": "Q07"}]))
    _, rows = _drain(tmp_path, runner)
    assert rows[0]["ok"] is True
    assert rows[0]["output"] == [{"question_id": "Q07"}]
    assert rows[0]["backend"] == "fake"
    assert rows[0]["harness_version"] == "fake/1"


def test_the_raw_bytes_are_always_stored(tmp_path):
    import pathlib

    runner = FakeRunner(default=answer(b"not json at all"))
    _, rows = _drain(tmp_path, runner)
    assert rows[0]["ok"] is False
    assert rows[0]["failure_class"] == "NOT_JSON"
    assert pathlib.Path(rows[0]["raw_path"]).exists()


def test_a_malformed_answer_is_a_failure_not_an_empty_output(tmp_path):
    runner = FakeRunner(default=answer(b"{"))
    _, rows = _drain(tmp_path, runner)
    assert rows[0]["output"] is None
    assert rows[0]["failure_class"] == "NOT_JSON"


def test_an_answer_of_the_wrong_shape_is_schema_invalid(tmp_path):
    runner = FakeRunner(default=answer([{"claim": "no question id"}]))
    _, rows = _drain(tmp_path, runner)
    assert rows[0]["failure_class"] == "SCHEMA_INVALID"
    assert any("question_id" in p for p in rows[0]["schema_errors"])


def test_a_truncated_answer_is_truncated_not_a_short_answer(tmp_path):
    runner = FakeRunner(default=answer([{"question_id": "Q07"}], truncated=True))
    _, rows = _drain(tmp_path, runner)
    assert rows[0]["ok"] is False
    assert rows[0]["failure_class"] == "TRUNCATED"


def test_an_empty_body_is_empty_not_no_claims(tmp_path):
    runner = FakeRunner(default=answer(b""))
    _, rows = _drain(tmp_path, runner)
    assert rows[0]["failure_class"] == "EMPTY"


def test_a_backend_failure_is_carried_through(tmp_path):
    runner = FakeRunner(default=RawAnswer(failure_class="RATE_LIMITED", detail="429"))
    _, rows = _drain(tmp_path, runner)
    assert rows[0]["failure_class"] == "RATE_LIMITED"
    assert rows[0]["detail"] == "429"


def test_an_unpriced_call_stays_unpriced(tmp_path):
    runner = FakeRunner(default=RawAnswer(body=b"[]", model="m", cost_usd=None))
    _, rows = _drain(tmp_path, runner)
    assert rows[0]["cost_usd"] is None


def test_a_runner_that_reports_a_different_prompt_is_caught(tmp_path):
    class Mangling(FakeRunner):
        def run(self, request):
            result = answer([{"question_id": "Q07"}])
            # A templating bug: it sent something other than what it was handed, and says so.
            result.prompt_sent = "something else entirely"
            return result

    _, rows = _drain(tmp_path, Mangling())
    assert rows[0]["ok"] is False
    assert rows[0]["failure_class"] == "PROMPT_MISMATCH"
    assert rows[0]["prompt_verified"] is False


def test_a_runner_that_reports_the_right_prompt_is_verified(tmp_path):
    class Honest(FakeRunner):
        def run(self, request):
            result = answer([{"question_id": "Q07"}])
            result.prompt_sent = model_call.rendered_prompt(request["system"], request["user"])
            return result

    _, rows = _drain(tmp_path, Honest())
    assert rows[0]["ok"] is True
    assert rows[0]["prompt_verified"] is True


def test_a_runner_that_reports_nothing_is_neither_verified_nor_failed(tmp_path):
    # The honest third state. Treating silence as a pass is the tautology this replaced;
    # treating it as a failure would make every such backend unusable.
    runner = FakeRunner(default=answer([{"question_id": "Q07"}]))
    _, rows = _drain(tmp_path, runner)
    assert rows[0]["ok"] is True
    assert rows[0]["prompt_verified"] is False
    assert rows[0]["prompt_sha256"] is None


def test_draining_twice_does_not_repeat_a_success(tmp_path):
    runner = FakeRunner(default=answer([{"question_id": "Q07"}]))
    queue, _ = _drain(tmp_path, runner)
    again = list(model_call.drain(queue, runner))
    assert again == []
    assert len(runner.calls) == 1


def test_a_truncated_empty_body_is_truncated_and_not_retried_forever(tmp_path):
    """EMPTY is transient and TRUNCATED is terminal, so the order of the two checks decides whether
    a cut-off answer with no bytes is retried on every drain for ever."""
    runner = FakeRunner(default=RawAnswer(body=b"", model="m", truncated=True))
    queue, rows = _drain(tmp_path, runner)
    assert rows[0]["failure_class"] == "TRUNCATED"
    assert queue.pending(backend="fake") == []
