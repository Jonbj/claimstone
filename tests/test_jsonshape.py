"""A small schema subset, where an unsupported keyword is refused rather than ignored."""

import pytest

from claimstone import jsonshape

CLAIM = {
    "type": "array",
    "maxItems": 20,
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["question_id", "claim", "evidence_quote"],
        "properties": {
            "question_id": {"type": "string"},
            "claim": {"type": "string"},
            "evidence_quote": {"type": "string"},
            "stance": {"type": "string",
                       "enum": ["SUPPORTS", "CONTRADICTS", "QUALIFIES", "METHOD_ONLY"]},
        },
    },
}


def claim(**overrides):
    base = {"question_id": "Q07", "claim": "an effect exists",
            "evidence_quote": "the effect exists"}
    return {**base, **overrides}


def test_a_well_formed_answer_validates():
    assert jsonshape.errors([claim()], CLAIM) == []


def test_a_missing_required_field_is_named():
    problems = jsonshape.errors([{"question_id": "Q07"}], CLAIM)
    assert any("claim" in p for p in problems)
    assert any("evidence_quote" in p for p in problems)


def test_an_unexpected_field_is_refused_when_additional_properties_is_false():
    problems = jsonshape.errors([claim(confidence=0.9)], CLAIM)
    assert any("confidence" in p for p in problems)


def test_a_wrong_type_is_named_with_its_path():
    problems = jsonshape.errors([claim(claim=42)], CLAIM)
    assert any("[0].claim" in p for p in problems)


def test_a_value_outside_the_enum_is_refused():
    problems = jsonshape.errors([claim(stance="MAYBE")], CLAIM)
    assert any("stance" in p for p in problems)


def test_too_many_items_is_refused():
    problems = jsonshape.errors([claim()] * 21, CLAIM)
    assert any("maxItems" in p for p in problems)


def test_an_object_where_an_array_was_asked_for_is_refused():
    assert jsonshape.errors(claim(), CLAIM) != []


def test_an_unsupported_keyword_raises_rather_than_passing():
    # A validator that silently skips a keyword gives false assurance, which is worse than
    # refusing the schema: the stage would believe it had checked something it had not.
    with pytest.raises(jsonshape.UnsupportedSchema, match="pattern"):
        jsonshape.check_schema({"type": "string", "pattern": "^Q"})


def test_check_schema_accepts_the_subset_it_documents():
    jsonshape.check_schema(CLAIM)  # must not raise


# A keyword's *name* being supported is not enough. These two got through check_schema and were then
# ignored by errors(), which is the silent skip this module exists to refuse — one of them turning an
# extra integer field into a pass, the other turning a typo into eleven invented errors.

def test_additional_properties_as_a_schema_is_refused():
    with pytest.raises(jsonshape.UnsupportedSchema, match="additionalProperties"):
        jsonshape.check_schema({"type": "object", "additionalProperties": {"type": "string"},
                                "properties": {"a": {"type": "string"}}})


def test_required_must_be_a_list_of_names():
    with pytest.raises(jsonshape.UnsupportedSchema, match="required"):
        jsonshape.check_schema({"type": "object", "required": "question_id", "properties": {}})


def test_properties_must_map_names_to_schemas():
    with pytest.raises(jsonshape.UnsupportedSchema, match="properties"):
        jsonshape.check_schema({"type": "object", "properties": ["question_id"]})


def test_an_enum_must_be_a_non_empty_list():
    with pytest.raises(jsonshape.UnsupportedSchema, match="enum"):
        jsonshape.check_schema({"type": "string", "enum": []})


def test_an_item_count_must_be_a_non_negative_integer():
    with pytest.raises(jsonshape.UnsupportedSchema, match="maxItems"):
        jsonshape.check_schema({"type": "array", "maxItems": "20",
                                "items": {"type": "string"}})
    with pytest.raises(jsonshape.UnsupportedSchema, match="minItems"):
        jsonshape.check_schema({"type": "array", "minItems": -1, "items": {"type": "string"}})


def test_an_array_schema_must_say_what_its_items_are():
    """Without `items` every element is unchecked, and the array's shape is a claim about nothing."""
    with pytest.raises(jsonshape.UnsupportedSchema, match="items"):
        jsonshape.check_schema({"type": "array", "maxItems": 20})


def test_additional_properties_false_still_needs_properties_to_compare_against():
    with pytest.raises(jsonshape.UnsupportedSchema, match="properties"):
        jsonshape.check_schema({"type": "object", "additionalProperties": False})
