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
