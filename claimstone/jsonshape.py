"""Validate a model's answer against the shape the request carried.

This is a deliberately small subset of JSON Schema, not an implementation of it. Adding a
`jsonschema` dependency for the handful of keywords these prompts need would buy a spec-complete
validator and a dependency that does not sit behind a process boundary (D7).

The subset is closed, not best-effort: **an unsupported keyword raises.** A validator that
silently ignores `pattern` or `minimum` tells the stage its output was checked when it was not,
and a false assurance about the evidence base is the specific failure this project exists to
prevent.

Closed means each keyword's **shape** is checked too, not only its name. Two cases got past a first
version that checked names alone. `additionalProperties: {"type": "string"}` is legal JSON Schema
meaning "extra fields must be strings"; it was accepted and then ignored, so an extra integer field
passed. And `required: "question_id"` — a string where a list belongs — was accepted and iterated
character by character, turning one typo into eleven invented errors. Both are the silent skip this
module refuses, wearing a supported keyword's name.
"""

from __future__ import annotations

from typing import Any

SUPPORTED = frozenset(
    {"type", "properties", "required", "items", "enum", "additionalProperties",
     "minItems", "maxItems"}
)

_TYPES: dict[str, type | tuple[type, ...]] = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


class UnsupportedSchema(ValueError):
    """The schema uses a keyword this validator does not implement."""


def _count(schema: dict[str, Any], name: str, path: str) -> None:
    if name not in schema:
        return
    value = schema[name]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise UnsupportedSchema(f"{path}: {name} must be a non-negative integer, got {value!r}")


def check_schema(schema: dict[str, Any], path: str = "$") -> None:
    """Refuse a schema that asks for more than this module can check. Call it when writing
    the request, so the failure lands on the stage that wrote it rather than on the answer."""
    if not isinstance(schema, dict):
        raise UnsupportedSchema(f"{path}: a schema must be a mapping")
    unsupported = sorted(set(schema) - SUPPORTED)
    if unsupported:
        raise UnsupportedSchema(
            f"{path}: unsupported keyword(s): {', '.join(unsupported)} "
            f"(supported: {', '.join(sorted(SUPPORTED))})"
        )
    declared = schema.get("type")
    if declared is not None and declared not in _TYPES:
        raise UnsupportedSchema(f"{path}: unknown type {declared!r}")

    if "enum" in schema:
        if not isinstance(schema["enum"], list) or not schema["enum"]:
            raise UnsupportedSchema(f"{path}: enum must be a non-empty list")

    if "additionalProperties" in schema:
        # Only the boolean form. The schema form means "extra fields must match this", which this
        # module does not check — and accepting it while ignoring it is the false assurance above.
        if not isinstance(schema["additionalProperties"], bool):
            raise UnsupportedSchema(
                f"{path}: additionalProperties must be true or false; the schema form "
                f"(\"extra fields must match this\") is not checked by this validator"
            )
        if schema["additionalProperties"] is False and "properties" not in schema:
            raise UnsupportedSchema(
                f"{path}: additionalProperties false needs properties to compare against, "
                f"or it rejects every field"
            )

    if "required" in schema:
        required = schema["required"]
        if not isinstance(required, list) or not all(isinstance(n, str) for n in required):
            raise UnsupportedSchema(f"{path}: required must be a list of field names")

    if "properties" in schema:
        properties = schema["properties"]
        if not isinstance(properties, dict) or not all(isinstance(n, str) for n in properties):
            raise UnsupportedSchema(f"{path}: properties must map field names to schemas")

    _count(schema, "minItems", path)
    _count(schema, "maxItems", path)

    if declared == "array" and "items" not in schema:
        # Without it every element is unchecked and the array's shape is a claim about nothing.
        raise UnsupportedSchema(f"{path}: an array schema must declare items")
    if "items" in schema:
        check_schema(schema["items"], f"{path}[]")
    for name, sub in (schema.get("properties") or {}).items():
        check_schema(sub, f"{path}.{name}")


def errors(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Every way `value` fails `schema`, as readable paths. Empty means it validates."""
    problems: list[str] = []
    declared = schema.get("type")

    if declared is not None:
        expected = _TYPES[declared]
        # bool is an int in Python, which is not what a schema saying "integer" means.
        wrong_type = not isinstance(value, expected) or (
            declared in {"integer", "number"} and isinstance(value, bool)
        )
        if wrong_type:
            return [f"{path}: expected {declared}, got {type(value).__name__}"]

    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path}: {value!r} is not one of {schema['enum']}")

    if declared == "array" or isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            problems.append(f"{path}: {len(value)} items below minItems {schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            problems.append(f"{path}: {len(value)} items above maxItems {schema['maxItems']}")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                problems.extend(errors(item, item_schema, f"{path}[{index}]"))

    if declared == "object" or isinstance(value, dict):
        properties = schema.get("properties") or {}
        for name in schema.get("required") or []:
            if name not in value:
                problems.append(f"{path}.{name}: required field is missing")
        if schema.get("additionalProperties") is False:
            for name in value:
                if name not in properties:
                    problems.append(f"{path}.{name}: unexpected field")
        for name, sub in properties.items():
            if name in value:
                problems.extend(errors(value[name], sub, f"{path}.{name}"))

    return problems
