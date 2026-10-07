"""api contract: A2 — every payload validates against `docs/contracts/portal-api.schema.json`,
and the committed schema equals the regenerated one (spec §3.4).

The validator below is deliberately minimal: `type`, `required`, `properties`, `enum`,
`items` and `additionalProperties` (as `false` or as a schema for map values), recursively,
with JSON Schema's per-type applicability — `required`/`properties` are checked only for
objects, `items` only for arrays — and with Python's `bool`-is-an-`int` collapse refused.
No `jsonschema` dependency: the point is that the contract is checkable with the stdlib
alone, forever.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from claimstone import flows
from claimstone.api_schema import ROUTES
from tests.test_api import PROJECT, _error_json, _get_json, _q02_sha, _routes, _served
from tests.test_portal_state import build_workspace

REPO = pathlib.Path(__file__).resolve().parent.parent
SCHEMA_FILE = REPO / "docs" / "contracts" / "portal-api.schema.json"

_TAIL_PARAM = {"questions": "qid", "claims": "claim_id", "sources": "candidate_key"}


@pytest.fixture()
def workspace(tmp_path):
    return build_workspace(tmp_path)


# --- the minimal validator ----------------------------------------------------------------------


def _is_type(value, name: str) -> bool:
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    raise AssertionError(f"the contract uses an unsupported type: {name!r}")


def _enum_ok(value, candidates) -> bool:
    # `True == 1` in Python; an `enum: [1]` must not admit a boolean, and vice versa.
    return any(isinstance(value, bool) == isinstance(candidate, bool) and value == candidate
               for candidate in candidates)


def validate(instance, schema, where: str = "$") -> list[str]:
    """Every violation, as `path: what` strings. Empty means the payload keeps the contract."""
    problems: list[str] = []
    if "type" in schema:
        names = schema["type"]
        names = [names] if isinstance(names, str) else names
        if not any(_is_type(instance, name) for name in names):
            problems.append(f"{where}: expected type {schema['type']!r}, "
                            f"got {type(instance).__name__}")
    if "enum" in schema and not _enum_ok(instance, schema["enum"]):
        problems.append(f"{where}: {instance!r} is not in the vocabulary")
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                problems.append(f"{where}: missing required {key!r}")
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, value in instance.items():
            child = f"{where}.{key}"
            if key in properties:
                problems.extend(validate(value, properties[key], child))
            elif extra is False:
                problems.append(f"{where}: additional property {key!r}")
            elif isinstance(extra, dict):
                problems.extend(validate(value, extra, child))
    if isinstance(instance, list) and "items" in schema:
        for index, item in enumerate(instance):
            problems.extend(validate(item, schema["items"], f"{where}[{index}]"))
    return problems


def _schema_for(route: str) -> str:
    """The §3.2 template a concrete route serves. `flows/{id}` and `unbound/{slug}` share
    the `{sel}` schemas by design."""
    parts = route.split("?", 1)[0].split("/")
    assert parts[1:3] == ["api", "v1"], route
    rest = parts[3:]
    if rest in (["meta"], ["admin"], ["projects"]):
        return f"/{rest[0]}"
    if len(rest) == 3 and rest[0] == "projects" and rest[2] in ("integrity", "activity",
                                                               "poll"):
        return f"/projects/{{p}}/{rest[2]}"
    if len(rest) in (5, 6, 7) and rest[0] == "projects" and rest[2] in ("flows", "unbound"):
        if len(rest) == 5 and rest[4] in ("summary", "overview", "inbox"):
            return f"/projects/{{p}}/{{sel}}/{rest[4]}"
        if len(rest) == 6 and rest[4] in _TAIL_PARAM:
            return f"/projects/{{p}}/{{sel}}/{rest[4]}/{{{_TAIL_PARAM[rest[4]]}}}"
        if len(rest) == 7 and rest[4] == "questions" and rest[6] == "profile-diff":
            return "/projects/{p}/{sel}/questions/{qid}/profile-diff"
    raise AssertionError(f"no schema route for {route!r}")


# --- A2 ------------------------------------------------------------------------------------------------


def test_committed_schema_equals_the_regeneration():
    """The committed file is the declaration, byte for byte — a stale schema must fail here,
    not mislead `gen:types` in the frontend."""
    import importlib.util

    assert SCHEMA_FILE.exists()
    spec = importlib.util.spec_from_file_location(
        "build_portal_api_schema", REPO / "tools" / "build_portal_api_schema.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert SCHEMA_FILE.read_text(encoding="utf-8") == module.render()


def test_every_route_payload_validates_against_the_schema(workspace):
    """A2: each payload from every §3.2 route (both selector kinds, the whole-store slug and
    the `?limit=` query) validates against its route schema."""
    with _served(workspace) as (_httpd, base, store):
        flow_id = next(iter(flows.flows(store)))
        for route in _routes(flow_id, _q02_sha(store)):
            status, _headers, payload = _get_json(base + route)
            assert status == 200, route
            problems = validate(payload, ROUTES[_schema_for(route)])
            assert problems == [], f"{route}: {problems}"


def test_error_envelopes_validate_against_the_schema(workspace):
    """A2: the §3.3 envelope keeps its own schema — an unknown code would be a contract
    failure, never a state the frontend renders hopefully."""
    with _served(workspace) as (httpd, base, _store):
        _status, payload = _error_json(base + "/api/v1/projects/nope/overview")
        assert validate(payload, ROUTES["/error"]) == []
        from tests.test_api import _raw_json

        port = httpd.server_address[1]
        status, payload = _raw_json(port, "/api/v1/meta", "evil.example:1")
        assert status == 421
        assert validate(payload, ROUTES["/error"]) == []


def test_validator_refuses_what_the_contract_refuses():
    """The validator's own refusals: a bool is not an integer, an extra key is a failure,
    an unknown word never passes an enum, and `required` does not apply to `null`."""
    schema = {"type": "object", "required": ["n", "v"],
              "properties": {"n": {"type": "integer"}, "v": {"enum": [None, "SUPPORTED"]}},
              "additionalProperties": False}
    assert validate({"n": 1, "v": None}, schema) == []
    assert validate({"n": True, "v": None}, schema) == ['$.n: expected type \'integer\', got bool']
    assert validate({"n": 1, "v": "NEVER_ASKED"}, schema) == [
        "$.v: 'NEVER_ASKED' is not in the vocabulary"]
    assert validate({"n": 1, "v": "SUPPORTED", "extra": 0}, schema) == [
        "$: additional property 'extra'"]
    optional = {"type": ["object", "null"], "required": ["x"],
                "properties": {"x": {"type": "integer"}}}
    assert validate(None, optional) == []


def test_schema_file_covers_every_declared_route():
    """The committed document's route keys are exactly `api_schema.ROUTES`, closed with
    `additionalProperties: false`, so an undeclared route is impossible to serve silently."""
    document = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    assert sorted(document["properties"]) == sorted(ROUTES)
    assert document["additionalProperties"] is False
    assert document["required"] == sorted(ROUTES)
    assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_a_signed_verdict_keeps_the_contract(workspace):
    """Review of S5: a real `adjudicate` row carries all fourteen fields. Listing six under
    `additionalProperties: false` made the first signed verdict fail the contract. B3: the
    served verdict names its signer class, and an old row read through the same API is
    normalized to `cli-declared` without the ledger being touched."""
    from claimstone import synthesize
    _projects_dir, _store_dir, project, store = workspace
    question = next(q for q in project.questions if q.kind != "operational")
    stored = synthesize.latest_profiles(store, round_name="r1")[question.id]
    synthesize.adjudicate(store, question.id, project=project, round_name="r1",
                          verdict="UNANSWERED_IN_LITERATURE", rationale="r" * 130,
                          by="a person", signer_auth="portal-session", actor="op-1",
                          profile_sha256=stored["profile_sha256"])
    with _served(workspace) as (_httpd, base, store_):
        flow_id = next(iter(flows.flows(store_)))
        status, _headers, payload = _get_json(
            base + f"/api/v1/projects/{PROJECT}/flows/{flow_id}/questions/{question.id}")
    assert status == 200
    assert payload["verdict"]["verdict"] == "UNANSWERED_IN_LITERATURE"
    # B3: the served verdict names its signer class and its actor, verbatim from the row.
    assert payload["verdict"]["signer_auth"] == "portal-session"
    assert payload["verdict"]["actor"] == "op-1"
    assert payload["verdict"]["adjudication_version"] == 2
    schema = ROUTES["/projects/{p}/{sel}/questions/{qid}"]
    assert validate(payload, schema) == []
    # Signed and current: nothing left to sign on this question.
    assert payload["adjudication_card"] is None
