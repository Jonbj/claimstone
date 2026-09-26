# `model_call` — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A file boundary between a stage that needs a model and whatever backend answers, such that two backends can drain the same queue and their answers line up per call — which is what makes "which backend is better at this lane" a measurement rather than a preference.

**Architecture:** A stage writes work units to JSONL; a runner drains them and appends results. `model_call.py` owns identity, validation and the row; `jsonshape.py` validates an output against the shape the request carried; `runners/*` are the only modules that know a vendor exists, and they return raw bytes plus what the backend charged — never a verdict. `model_report.py` sums cost and throughput per backend.

**Tech Stack:** Python ≥ 3.11, stdlib plus `requests`. No SDK, no `jsonschema`. pytest.

**Spec:** `docs/superpowers/specs/2026-09-22-model-call-design.md`. Read it before Task 1; every task cites the section it implements.

---

## Conventions for every task

- Run tests with `.venv/bin/pytest`, the CLI with `.venv/bin/claimstone`.
- **Every commit message ends with the trailer** `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`, shown in full in Task 1 and abbreviated as `<trailer>` afterwards.
- **No test reaches a backend.** Runners are exercised through a fake, or through `monkeypatch` on `subprocess.run` / the fetcher. A live smoke test per runner sits behind `CLAIMSTONE_LIVE=1`, as in stage 2.
- `tests/conftest.py` already sets `CLAIMSTONE_CONTACT_EMAIL` for the session.
- Commit after every task. A task that leaves the suite red is not finished.

## Two spec corrections this plan makes

**1. `call_id` covers the cap and the schema, `prompt_sha256` covers the prompt.** Spec §5 says a retry under a bigger `max_output_tokens` is "honestly a different call", which requires the cap inside `call_id`; spec §4's formula omits it. Resolved by keeping `prompt_sha256` meaning exactly *the prompt* — it is what the echo check verifies, and widening it would make a mismatch ambiguous between "the prompt was mangled" and "the cap differed" — and widening `call_id` instead:

```
prompt_sha256 = sha256(canonical({system, user}))
call_id       = sha256(f"{lane}|{schema_version}|{prompt_sha256}|{max_output_tokens}|{schema_sha256}")
```

**2. There is no JSON Schema validator, and this plan does not add one.** Spec §4 says `response_schema` travels with the request and the validator is not a property of the runner, but the dependency set is stdlib plus `requests`, `PyYAML`, `numpy`. Task 2 writes `jsonshape.py`: a deliberately small subset, where **an unsupported keyword is an error rather than ignored**. A validator that silently skips `minItems` gives false assurance, which is worse than refusing the schema.

Both corrections land in the spec in Task 10.

## Three defects an adversarial review found in this plan, 2026-09-24

All three were in the plan as first written, and all three are corrected above.

**1. The echo check could not fail.** `build_result` hashed `request["system"]` and
`request["user"]` and compared the result to `request["prompt_sha256"]`, which `work_unit` had
computed from those same two fields. `hash(x) == hash(x)`, true by construction. §3 of the spec is
built entirely on that guarantee, and the guarantee was a tautology. A runner now reports the
prompt it actually sent; a runner that reports nothing gets `prompt_verified: false`, which is an
honest third state rather than a pass.

**2. Resumability defeated the comparison primitive.** `Queue.pending()` and
`model_report.summarise()` both collapsed on `call_id` alone, so a batch answered by backend A
looked finished to backend B — and the only justification for this whole module is that two
backends can drain the same requests file and be compared. Identity is now the call *and* the
backend, with every attempt kept, because a retry that timed out was still paid for.

**3. `--model` was optional against runners that require it.** `_model_run` constructed a
`CliRunner` without a model and caught only `ValueError`, so the `TypeError` from the constructor
escaped. `runners.build` now refuses with a sentence, and a backend that can pick its own model
declares one.

## File structure

| File | Action | Responsibility |
|---|---|---|
| `claimstone/jsonshape.py` | create | validate a value against a small schema subset. Pure, no I/O. |
| `claimstone/model_call.py` | create | identity, the queue, the result row, the drain loop. Knows no vendor. |
| `claimstone/runners/base.py` | create | the `Runner` protocol and `RawAnswer`. |
| `claimstone/runners/cli.py` | create | subprocess against `claude`, `codex`, `opencode`. |
| `claimstone/runners/ollama_cloud.py` | create | HTTPS with an API key. |
| `claimstone/runners/llamacpp.py` | create | HTTP to the local server. |
| `claimstone/runners/__init__.py` | create | the registry, name → runner factory. |
| `claimstone/model_report.py` | create | cost and throughput per backend and model. |
| `claimstone/cli.py` | modify | `model-run`, `model-report`. |
| `tests/fakes.py` | modify | `FakeRunner`. |
| `tests/test_jsonshape.py` | create | the validator, including refused keywords |
| `tests/test_model_call.py` | create | identity, the queue, the row, the drain |
| `tests/test_runner_cli.py` | create | argv, exit codes, harness version |
| `tests/test_model_report.py` | create | unpriced calls, per-backend throughput |
| `tests/test_live_runners.py` | create | one real call per runner, skipped by default |
| `docs/contracts/model_calls.md` | create | the two schemas stage 4 and 5 will write and read |

## Scope decision: the drain is sequential

`max_concurrency` is declared on every runner and recorded, but the drain loop in Task 4 runs one call at a time. The queue is resumable by `call_id`, so parallelism is a contained change later that does not touch the file format — and until a lane has been measured on a real backend there is no evidence about what concurrency a subscription endpoint tolerates. Sequential first, and the field is there so the measurement has somewhere to land.

---

### Task 1: Identity — the work unit and its two hashes

Implements spec §4 and correction 1.

**Files:**
- Create: `claimstone/model_call.py`
- Create: `tests/test_model_call.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_model_call.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_model_call.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claimstone.model_call'`

- [ ] **Step 3: Write the identity half of `claimstone/model_call.py`**

```python
"""The boundary between a stage that needs a model and whatever backend answers.

A stage writes work units here and reads results back. It does not open a socket, import a
vendor SDK, or know which backend replied. A runner is a separate process that drains the queue.

**A model call is not reproducible. It is auditable.** Sampling, model updates and a CLI's own
harness all break sameness of answer, and no amount of recording fixes that. What is promised,
and checked in code, is narrower and useful: this exact prompt was sent, this exact response came
back, and here are the hashes. That is why `prompt_sha256` is echoed on the result and verified.

`call_id` is derived rather than assigned, which is what lets two backends drain the same
requests file into two results files whose answers line up per call. Without a content-derived
id, comparing backends means trusting that two runs saw the same inputs.
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any

from claimstone.store import sha256_text

SCHEMA_VERSION = 1

LANES = ("extract", "review")


def canonical(value: Any) -> str:
    """One byte string per value, whatever order the keys arrived in."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


PROMPT_SEPARATOR = "\n\n---\n\n"


def rendered_prompt(system: str, user: str) -> str:
    """The one string a prompt is, for hashing and for any runner that sends it as one.

    It exists so `prompt_sha256` and a runner's `prompt_sent` are comparable at all. A backend that
    takes two messages sends them separately and reports this joining of them; a backend that takes
    one string sends exactly this.
    """
    return f"{system}{PROMPT_SEPARATOR}{user}"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def work_unit(
    *,
    lane: str,
    system: str,
    user: str,
    response_schema: dict[str, Any],
    max_output_tokens: int,
    registry_version: int,
    source_id: str | None = None,
    chunk_id: str | None = None,
    schema_version: int = SCHEMA_VERSION,
) -> dict[str, Any]:
    """One prompt, one structured answer. No tools, no turns, no retrieval inside the call."""
    if lane not in LANES:
        raise ValueError(f"unknown lane {lane!r}: {', '.join(LANES)}")

    # The prompt, and only the prompt: this is what the echo check on the result verifies. A
    # runner that reports `prompt_sent` must report exactly the string `rendered_prompt` returns,
    # or its rows come back PROMPT_MISMATCH — which is the check working.
    prompt_sha256 = sha256_text(rendered_prompt(system, user))
    schema_sha256 = sha256_text(canonical(response_schema))
    # Everything that makes the call a different call, including the cap — a retry under a
    # bigger cap is a different question, not a second attempt at the same one.
    call_id = sha256_text(
        f"{lane}|{schema_version}|{prompt_sha256}|{max_output_tokens}|{schema_sha256}"
    )

    return {
        "call_id": call_id,
        "lane": lane,
        "schema_version": schema_version,
        "registry_version": registry_version,
        "system": system,
        "user": user,
        "response_schema": response_schema,
        "max_output_tokens": max_output_tokens,
        "source_id": source_id,
        "chunk_id": chunk_id,
        "prompt_sha256": prompt_sha256,
        "schema_sha256": schema_sha256,
        "created_at": _now(),
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_model_call.py -q`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add claimstone/model_call.py tests/test_model_call.py
git commit -m "model_call: a call's identity is derived from what makes it a different call

call_id is a hash of the lane, the prompt, the output cap and the schema, so the
same work unit produced twice is one unit and two backends draining the same queue
line up per call. That is the comparison primitive D13 defers lane assignment on:
without a content-derived id, comparing backends means trusting that two runs saw
the same inputs.

prompt_sha256 stays narrower, covering the prompt alone, because it is what the
echo check on the result verifies — widening it would make a mismatch ambiguous
between a mangled prompt and a changed cap.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: The output shape validator

Implements spec §4's "the validator is not a property of the runner", and correction 2.

**Files:**
- Create: `claimstone/jsonshape.py`
- Create: `tests/test_jsonshape.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_jsonshape.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_jsonshape.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claimstone.jsonshape'`

- [ ] **Step 3: Write `claimstone/jsonshape.py`**

```python
"""Validate a model's answer against the shape the request carried.

This is a deliberately small subset of JSON Schema, not an implementation of it. Adding a
`jsonschema` dependency for the handful of keywords these prompts need would buy a spec-complete
validator and a dependency that does not sit behind a process boundary (D7).

The subset is closed, not best-effort: **an unsupported keyword raises.** A validator that
silently ignores `pattern` or `minimum` tells the stage its output was checked when it was not,
and a false assurance about the evidence base is the specific failure this project exists to
prevent.
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

    # Each keyword's SHAPE is checked, not only its name. Two cases got past a version that checked
    # names alone: `additionalProperties: {"type": "string"}` was accepted and then ignored, so an
    # extra integer field passed; and `required: "question_id"` was iterated character by character,
    # turning one typo into eleven invented errors. Both are the silent skip this module refuses,
    # wearing a supported keyword's name.
    if "enum" in schema:
        if not isinstance(schema["enum"], list) or not schema["enum"]:
            raise UnsupportedSchema(f"{path}: enum must be a non-empty list")
    if "additionalProperties" in schema:
        if not isinstance(schema["additionalProperties"], bool):
            raise UnsupportedSchema(
                f"{path}: additionalProperties must be true or false; the schema form is "
                f"not checked by this validator"
            )
        if schema["additionalProperties"] is False and "properties" not in schema:
            raise UnsupportedSchema(
                f"{path}: additionalProperties false needs properties to compare against"
            )
    if "required" in schema:
        if not isinstance(schema["required"], list) or not all(
            isinstance(n, str) for n in schema["required"]
        ):
            raise UnsupportedSchema(f"{path}: required must be a list of field names")
    if "properties" in schema:
        if not isinstance(schema["properties"], dict) or not all(
            isinstance(n, str) for n in schema["properties"]
        ):
            raise UnsupportedSchema(f"{path}: properties must map field names to schemas")
    for name in ("minItems", "maxItems"):
        if name in schema:
            value = schema[name]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise UnsupportedSchema(f"{path}: {name} must be a non-negative integer")

    if declared == "array" and "items" not in schema:
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_jsonshape.py -q`
Expected: PASS, 9 passed

- [ ] **Step 5: Commit**

```bash
git add claimstone/jsonshape.py tests/test_jsonshape.py
git commit -m "jsonshape: a closed subset, because a silent skip is a false assurance

The prompts need eight keywords. Adding a jsonschema dependency would buy a
spec-complete validator and a dependency that does not sit behind a process
boundary, so this implements the subset instead — and refuses any schema that
reaches past it. A validator that quietly ignores 'pattern' tells the stage its
output was checked when it was not, and a false assurance about the evidence base
is the failure this project exists to prevent.

check_schema runs when the request is written, so a schema the validator cannot
honour fails on the stage that wrote it rather than on the answer that comes back.

<trailer>"
```

---

### Task 3: The queue

Implements spec §1's file layout.

**Files:**
- Modify: `claimstone/model_call.py`
- Modify: `tests/test_model_call.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_model_call.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_model_call.py -q`
Expected: FAIL with `AttributeError: module 'claimstone.model_call' has no attribute 'batch_name'`

- [ ] **Step 3: Append the queue to `claimstone/model_call.py`**

```python
# Terminal for this backend: a retry changes nothing until the request or the backend does.
# Transient: the next drain should try again. TRUNCATED is terminal because raising the cap
# changes `call_id`, so a retry under a bigger cap is a different call and not a second
# attempt at this one.
TERMINAL = frozenset({"NOT_JSON", "SCHEMA_INVALID", "REFUSED", "PROMPT_MISMATCH", "TRUNCATED"})
TRANSIENT = frozenset({"TIMEOUT", "RATE_LIMITED", "BACKEND_ERROR", "EMPTY"})


def is_terminal(failure_class: str | None) -> bool:
    """An unrecognised class counts as terminal: a typo must cost a retry, not a loop."""
    return failure_class not in TRANSIENT


def batch_name(*, registry_version: int, at: str | None = None) -> str:
    """A batch says when it was built and which registry it was built against.

    Both belong in the name so a batch is identifiable without reading it, and so a batch
    built before a registry bump cannot be mistaken for one built after.
    """
    stamp = at or _now()
    return f"{stamp[:10]}T{stamp[11:13]}{stamp[14:16]}Z-r{registry_version}"


class Queue:
    """One lane's batch on disk: requests in, results appended beside them."""

    def __init__(self, store: Any, *, lane: str, batch: str) -> None:
        if lane not in LANES:
            raise ValueError(f"unknown lane {lane!r}: {', '.join(LANES)}")
        self.store = store
        self.lane = lane
        self.batch = batch
        self.root = f"calls/{lane}/{batch}"
        self.requests_name = f"{self.root}/requests.jsonl"
        self.results_name = f"{self.root}/results.jsonl"

    def write(self, units: list[dict[str, Any]]) -> int:
        """Append work units, merging any `call_id` already queued. Returns how many *new* calls
        landed — a second chunk asking an identical question adds an asker, not a call.

        Two chunks with identical text hash to one `call_id`, which is deliberate: the prompt is
        paid for once. The first version then dropped the duplicate unit whole, and the second
        chunk's id went with it, so a claim really present in that chunk could never be recorded
        against it. One call, one answer, every place that asked.
        """
        from claimstone import jsonshape

        held = self.store.latest_by(self.requests_name, "call_id")
        written = 0
        for unit in units:
            jsonshape.check_schema(unit["response_schema"])
            asker = {"source_id": unit.get("source_id"), "chunk_id": unit.get("chunk_id")}
            previous = held.get(unit["call_id"])
            if previous is None:
                row = {**unit, "asked_by": [asker]}
                held[unit["call_id"]] = row
                self.store.append(self.requests_name, row)
                written += 1
                continue
            askers = list(previous.get("asked_by") or [])
            if asker in askers:
                continue
            row = {**previous, "asked_by": askers + [asker]}
            held[unit["call_id"]] = row
            self.store.append(self.requests_name, row)
        return written

    def requests(self) -> list[dict[str, Any]]:
        """One row per call, the latest. Never the raw rows: merging an asker appends a row, and a
        drain reading raw rows would pay for the same call once per chunk that asked for it."""
        return list(self.store.latest_by(self.requests_name, "call_id").values())

    def request_rows(self) -> list[dict[str, Any]]:
        """Every row ever written, for auditing how a call's asker list grew."""
        return list(self.store.read(self.requests_name))

    def results(self, *, backend: str | None = None) -> dict[str, dict[str, Any]]:
        """The latest result per call, **per backend**.

        Collapsing on `call_id` alone was the first draft, and it destroyed the one property this
        whole boundary exists for: after backend A answered a batch, draining it with backend B
        produced nothing, because every call already looked done. Two backends over the same
        requests file is the comparison primitive — it cannot be defeated by the resumability
        logic.
        """
        latest: dict[str, dict[str, Any]] = {}
        for row in self.store.read(self.results_name):
            if backend is not None and row.get("backend") != backend:
                continue
            key = f"{row.get('call_id')}|{row.get('backend')}"
            latest[key] = row
        return latest

    def attempts(self) -> list[dict[str, Any]]:
        """Every result row ever written, in order. What cost money, not what is current."""
        return list(self.store.read(self.results_name))

    def pending(self, *, backend: str) -> list[dict[str, Any]]:
        """Units this backend has not answered, plus those its last answer left transient."""
        answered = self.results(backend=backend)
        out: list[dict[str, Any]] = []
        for unit in self.requests():
            held = answered.get(f"{unit['call_id']}|{backend}")
            if held is None:
                out.append(unit)
            elif not held.get("ok") and not is_terminal(held.get("failure_class")):
                out.append(unit)
        return out
```

Add `from typing import Any` if it is not already imported, and note that `Store` is
deliberately typed as `Any` here: `model_call` does not need the class, only `append`,
`read` and `latest_by`, and keeping it loose is what lets a test pass a stub.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_model_call.py -q`
Expected: PASS, 13 passed

- [ ] **Step 5: Commit**

```bash
git add claimstone/model_call.py tests/test_model_call.py
git commit -m "model_call: the queue, resumable by call_id

A batch is named for when it was built and which registry it was built against, so
one built before a registry bump cannot be mistaken for one built after. pending()
skips what succeeded and what failed terminally, and returns what a transient
failure left behind — so a drain interrupted after two hours resumes rather than
restarts.

A schema the validator cannot honour is refused when the request is written, not
when the answer arrives: it is a mistake by the stage that wrote it.

<trailer>"
```

---

### Task 4: The result row, and the drain

Implements spec §5 and §6's drain.

**Files:**
- Create: `claimstone/runners/base.py`
- Create: `claimstone/runners/__init__.py`
- Modify: `claimstone/model_call.py`
- Modify: `tests/fakes.py`
- Modify: `tests/test_model_call.py`

- [ ] **Step 1: Write `claimstone/runners/base.py`**

```python
"""What a runner is, and — just as much — what it is not.

A runner talks to one backend and returns **raw bytes plus what the backend charged**. It does
not parse the answer, validate it, or decide whether the call succeeded. Those belong to
`model_call`, in one place, for every backend: if each runner decided for itself what counted as
a valid answer, two backends' results would not be comparable, and comparability is the only
reason this boundary exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field, field
from typing import Any, Protocol


@dataclass
class RawAnswer:
    """What came back, before anyone judges it."""

    body: bytes = b""
    model: str = ""
    # The prompt this runner actually sent, as it sent it. Without this the echo check compares
    # the request against itself and can never fail — see §3 of the plan's corrections.
    prompt_sent: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    # None means "not priced", never "free": a subscription-backed CLI has no per-call price,
    # and rendering that as 0.0 would make a cost report add up to a number that is not true.
    cost_usd: float | None = None
    truncated: bool = False
    refused: bool = False
    # Set only for failures the backend itself reported: a transport error, a rate limit, a
    # timeout. A malformed body is not the runner's verdict to give.
    failure_class: str | None = None
    detail: str = ""


class Runner(Protocol):
    """One backend. The only kind of module in this repository that knows a vendor exists."""

    name: str
    max_concurrency: int
    min_interval_s: float

    def harness_version(self) -> str: ...

    def run(self, request: dict[str, Any]) -> RawAnswer: ...
```

- [ ] **Step 2: Write the failing tests**

Add `FakeRunner` to `tests/fakes.py`:

```python
from claimstone.model_call import rendered_prompt
from claimstone.runners.base import RawAnswer


@dataclass
class FakeRunner:
    """Answers from a dictionary keyed by call_id. Opens nothing."""

    name: str = "fake"
    max_concurrency: int = 1
    min_interval_s: float = 0.0
    answers: dict[str, RawAnswer] = field(default_factory=dict)
    default: RawAnswer | None = None
    calls: list[str] = field(default_factory=list)

    def harness_version(self) -> str:
        return "fake/1"

    def run(self, request: dict[str, Any]) -> RawAnswer:
        self.calls.append(request["call_id"])
        answer = self.answers.get(request["call_id"], self.default)
        if answer is None:
            return RawAnswer(failure_class="BACKEND_ERROR", detail="fake: no answer configured")
        return answer
```

Append to `tests/test_model_call.py`:

```python
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
```

`test_a_runner_that_mangled_the_prompt_is_caught` is the point of the whole echo check: the
runner is handed the request and edits it, which is exactly what a templating bug looks like.

- [ ] **Step 3: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_model_call.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claimstone.runners'`

- [ ] **Step 4: Write `claimstone/runners/__init__.py`**

```python
"""Backends, one module each. Nothing else in the repository names a vendor.

No runner is the default. Which backend serves a lane is a finding, not a design decision
(D13), so the caller names one and the choice lands on every row.
"""

from __future__ import annotations

from typing import Any, Callable

from claimstone.runners.base import RawAnswer, Runner


def available() -> dict[str, Callable[..., Runner]]:
    from claimstone.runners import cli, llamacpp, ollama_cloud

    return {
        "claude-cli": lambda **kw: cli.CliRunner(tool="claude", **kw),
        "codex-cli": lambda **kw: cli.CliRunner(tool="codex", **kw),
        "opencode-cli": lambda **kw: cli.CliRunner(tool="opencode", **kw),
        "ollama-cloud": ollama_cloud.OllamaCloudRunner,
        "llamacpp": llamacpp.LlamaCppRunner,
    }


# A backend that cannot pick a model for you. Passing --model is then required, and saying so is
# better than a TypeError out of a dataclass constructor.
NEEDS_MODEL = frozenset({"claude-cli", "codex-cli", "opencode-cli", "ollama-cloud"})


def build(name: str, *, model: str | None = None, **kwargs: Any) -> Runner:
    factories = available()
    if name not in factories:
        raise ValueError(f"unknown backend {name!r}: {', '.join(sorted(factories))}")
    if model is None and name in NEEDS_MODEL:
        raise ValueError(f"backend {name!r} needs a model: pass --model")
    if model is not None:
        kwargs["model"] = model
    return factories[name](**kwargs)


__all__ = ["RawAnswer", "Runner", "available", "build"]
```

- [ ] **Step 5: Append the result and the drain to `claimstone/model_call.py`**

```python
def _classify(answer: Any, request: dict[str, Any]) -> tuple[Any, str | None, list[str]]:
    """Judge one raw answer. The only place any backend's answer is judged."""
    if answer.failure_class:
        return None, answer.failure_class, []
    if answer.refused:
        # No runner sets this today: a CLI declining returns prose, which lands as NOT_JSON.
        # The branch exists because a backend that reports refusal distinctly should not have
        # that collapsed into "the model wrote something unparseable" — they are different
        # facts about why a chunk produced no claims.
        return None, "REFUSED", []
    if answer.truncated:
        # A partial answer is not a short answer. Parsing what arrived would turn a cut-off
        # list into a complete one, which is a fabricated absence of claims.
        #
        # Checked before the empty body, not after: EMPTY is transient and TRUNCATED is terminal,
        # so an answer cut off before it produced a byte would otherwise be retried on every drain
        # for ever, and each retry would be cut off in the same place.
        return None, "TRUNCATED", []
    if not answer.body:
        # Not "the chunk contained nothing": that is a claim about the literature, and a
        # runner returning zero bytes has not made it.
        return None, "EMPTY", []
    try:
        parsed = json.loads(answer.body.decode("utf-8", "replace"))
    except ValueError:
        return None, "NOT_JSON", []

    from claimstone import jsonshape

    problems = jsonshape.errors(parsed, request["response_schema"])
    if problems:
        return None, "SCHEMA_INVALID", problems
    return parsed, None, []


def build_result(
    request: dict[str, Any],
    answer: Any,
    *,
    attempt_no: int = 1,
    backend: str,
    harness_version: str,
    raw_sha256: str | None,
    raw_path: str | None,
    started_at: str,
    finished_at: str,
    latency_s: float,
) -> dict[str, Any]:
    """One result row. `ok` is true only when there is a validated output to show."""
    # Checked against what the runner says it sent, not against the request we still hold. The
    # first draft of this hashed request["system"] and request["user"] and compared the result to
    # request["prompt_sha256"], which was computed from those same two fields — hash(x) == hash(x),
    # true by construction. A guarantee that cannot fail is not a guarantee.
    #
    # A runner that does not report what it sent gets no verification, and the row says so rather
    # than implying one.
    if answer.prompt_sent is None:
        echoed = None
        verified = False
        output, failure_class, problems = _classify(answer, request)
    else:
        echoed = sha256_text(answer.prompt_sent)
        verified = echoed == request["prompt_sha256"]
        if not verified:
            output, failure_class, problems = None, "PROMPT_MISMATCH", []
        else:
            output, failure_class, problems = _classify(answer, request)

    return {
        "call_id": request["call_id"],
        "lane": request["lane"],
        # Identity is the call **and** who answered it, on which attempt. A row keyed by call_id
        # alone cannot say whether a cost was a first try or a third, or which backend paid it.
        "result_key": f"{request['call_id']}|{backend}",
        "attempt_no": attempt_no,
        "ok": failure_class is None,
        "backend": backend,
        "model": answer.model,
        "harness_version": harness_version,
        "prompt_sha256": echoed,
        # False means this backend does not report what it sent, so no echo check ran. It is not
        # a failure and it is not a pass; conflating either with a verified row would be the
        # tautology again, worn differently.
        "prompt_verified": verified,
        "output": output,
        "schema_errors": problems,
        "raw_sha256": raw_sha256,
        "raw_path": raw_path,
        "usage": dict(answer.usage),
        "cost_usd": answer.cost_usd,
        "latency_s": round(latency_s, 3),
        "started_at": started_at,
        "finished_at": finished_at,
        "failure_class": failure_class,
        "detail": answer.detail[:400],
    }


def drain(queue: Queue, runner: Any, *, limit: int | None = None) -> Any:
    """Answer what is pending, one call at a time, appending each result as it lands.

    Sequential on purpose. The queue is resumable by `call_id`, so parallelism is a contained
    change that does not touch the file format — and until a lane has been measured on a real
    backend there is no evidence about what concurrency a given endpoint tolerates.
    """
    import time

    last = 0.0
    done = 0
    for request in queue.pending(backend=runner.name):
        if limit is not None and done >= limit:
            return
        wait = runner.min_interval_s - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        last = time.time()

        started_at = _now()
        began = time.time()
        answer = runner.run(dict(request))
        latency = time.time() - began

        raw_sha256 = raw_path = None
        if answer.body:
            digest, path = queue.store.store_bytes_at(f"{queue.root}/raw", answer.body, ".txt")
            raw_sha256, raw_path = digest, str(path)

        prior = sum(
            1 for attempt in queue.attempts()
            if attempt.get("call_id") == request["call_id"]
            and attempt.get("backend") == runner.name
        )
        row = build_result(
            request, answer,
            attempt_no=prior + 1,
            backend=runner.name,
            harness_version=runner.harness_version(),
            raw_sha256=raw_sha256,
            raw_path=raw_path,
            started_at=started_at,
            finished_at=_now(),
            latency_s=latency,
        )
        queue.store.append(queue.results_name, row)
        done += 1
        yield row
```

- [ ] **Step 6: Add `store_bytes_at` to `claimstone/store.py`**

`store_bytes` writes into `raw/` at the project root. A batch's answers belong beside the batch,
so the same content-addressing is needed under a given subdirectory:

```python
    def store_bytes_at(self, where: str, data: bytes, suffix: str) -> tuple[str, pathlib.Path]:
        """Write bytes under their own hash, inside `where`. Re-storing the same bytes is a
        no-op, so a re-drain that gets an identical answer costs nothing."""
        digest = sha256_bytes(data)
        directory = self.root / where
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{digest}{suffix}"
        if not target.exists():
            target.write_bytes(data)
        return digest, target
```

Then express the original in terms of it, so there is one implementation:

```python
    def store_bytes(self, data: bytes, suffix: str) -> tuple[str, pathlib.Path]:
        """Write bytes under their own hash. Re-fetching the same bytes is a no-op."""
        return self.store_bytes_at("raw", data, suffix)
```

- [ ] **Step 7: Run to verify it passes**

Run: `.venv/bin/pytest -q`
Expected: PASS, all tests

- [ ] **Step 8: Commit**

```bash
git add claimstone/model_call.py claimstone/runners/ claimstone/store.py \
        tests/fakes.py tests/test_model_call.py
git commit -m "model_call: one place judges every backend's answer

A runner returns raw bytes and what the backend charged. It does not parse,
validate, or decide whether the call succeeded — if each runner judged for itself,
two backends' results would not be comparable, and comparability is the only
reason this boundary exists.

Three things the classifier refuses to soften. An empty body is EMPTY, not a chunk
with no claims: that is an assertion about the literature and zero bytes has not
made it. A truncated answer is TRUNCATED, because parsing what arrived would turn
a cut-off list into a complete one. And a malformed body records a failure with the
bytes kept, never an empty output.

The echoed prompt hash is checked before anything else on the row is believed: the
runner was handed the request, and a test that edits it mid-flight — which is what
a templating bug looks like — must come back PROMPT_MISMATCH.

store gains store_bytes_at so a batch's answers are content-addressed beside the
batch, with the original expressed in terms of it.

<trailer>"
```

---

### Task 5: The CLI runner

Implements spec §6's `runners/cli.py`.

**Files:**
- Create: `claimstone/runners/cli.py`
- Create: `tests/test_runner_cli.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_runner_cli.py`:

```python
"""The subprocess runner. No process is started: subprocess.run is replaced."""

import json
import subprocess

import pytest

from claimstone.runners import cli as cli_runner


def request(**overrides):
    base = {"call_id": "abc", "lane": "extract", "system": "the registry", "user": "a chunk",
            "max_output_tokens": 800, "response_schema": {"type": "array"}}
    return {**base, **overrides}


@pytest.fixture
def recorder(monkeypatch):
    seen: dict[str, list] = {"argv": [], "input": []}

    def fake_run(argv, **kwargs):
        seen["argv"].append(argv)
        seen["input"].append(kwargs.get("input"))
        if argv[1:2] == ["--version"]:
            return subprocess.CompletedProcess(argv, 0, stdout="2.1.280 (Claude Code)\n",
                                               stderr="")
        payload = json.dumps({"result": '[{"question_id": "Q07"}]'})
        return subprocess.CompletedProcess(argv, 0, stdout=payload, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return seen


def test_claude_is_invoked_in_print_mode_with_json_output(recorder):
    runner = cli_runner.CliRunner(tool="claude", model="claude-opus-5")
    runner.run(request())
    argv = recorder["argv"][-1]
    assert argv[0] == "claude"
    assert "--print" in argv or "-p" in argv
    assert "--output-format" in argv and "json" in argv
    assert "--model" in argv and "claude-opus-5" in argv


def test_the_prompt_goes_in_on_stdin_not_on_the_command_line(recorder):
    # A chunk is thousands of characters and may contain anything; an argv full of it is a
    # length limit and a quoting bug waiting to happen.
    runner = cli_runner.CliRunner(tool="claude", model="m")
    runner.run(request(user="a chunk with 'quotes' and $dollars"))
    assert "a chunk with 'quotes' and $dollars" in recorder["input"][-1]
    assert not any("dollars" in part for part in recorder["argv"][-1])


def test_the_harness_version_comes_from_the_tool_itself(recorder):
    runner = cli_runner.CliRunner(tool="claude", model="m")
    assert runner.harness_version() == "claude 2.1.280 (Claude Code)"


def test_a_non_zero_exit_is_a_backend_error(monkeypatch):
    def failing(argv, **kwargs):
        if argv[1:2] == ["--version"]:
            return subprocess.CompletedProcess(argv, 0, stdout="1.0\n", stderr="")
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", failing)
    answer = cli_runner.CliRunner(tool="claude", model="m").run(request())
    assert answer.failure_class == "BACKEND_ERROR"
    assert "boom" in answer.detail


def test_a_timeout_is_a_timeout(monkeypatch):
    def timing_out(argv, **kwargs):
        if argv[1:2] == ["--version"]:
            return subprocess.CompletedProcess(argv, 0, stdout="1.0\n", stderr="")
        raise subprocess.TimeoutExpired(argv, 60)

    monkeypatch.setattr(subprocess, "run", timing_out)
    answer = cli_runner.CliRunner(tool="claude", model="m").run(request())
    assert answer.failure_class == "TIMEOUT"


def test_the_envelope_is_unwrapped_but_its_payload_is_not_parsed(recorder):
    # The CLI answers with its own JSON envelope; the model's answer is a string inside it.
    # model_call parses that, so the runner hands the bytes over untouched.
    answer = cli_runner.CliRunner(tool="claude", model="m").run(request())
    assert answer.body == b'[{"question_id": "Q07"}]'


def test_a_subscription_backed_call_is_unpriced(recorder):
    answer = cli_runner.CliRunner(tool="claude", model="m").run(request())
    assert answer.cost_usd is None


def test_the_cli_runner_is_serial_and_paced():
    runner = cli_runner.CliRunner(tool="claude", model="m")
    assert runner.max_concurrency == 1
    assert runner.min_interval_s >= 1.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_runner_cli.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claimstone.runners.cli'`

- [ ] **Step 3: Write `claimstone/runners/cli.py`**

```python
"""A coding-assistant CLI as a backend, through its documented non-interactive mode.

`claude -p --output-format json` is a supported scripting surface, and a subprocess is exactly
the process boundary D7 asks for — better on that axis than an in-process SDK. Two properties
are recorded rather than wished away.

A CLI puts its own harness between the prompt and the model: a system prompt, tools, context
management, all outside our control and all changing with its version. That is why
`harness_version` comes from the tool itself and is mandatory on every row.

And an interactive subscription is not batch infrastructure. `max_concurrency` is 1 and
`min_interval_s` has a floor, so a high-volume lane belongs on a backend priced per token.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any

from claimstone.runners.base import RawAnswer

# argv template per tool. The prompt never travels on the command line: a chunk is thousands of
# characters and may contain anything, so argv would be a length limit and a quoting bug.
ARGV: dict[str, list[str]] = {
    "claude": ["claude", "--print", "--output-format", "json", "--model", "{model}"],
    "codex": ["codex", "exec", "--json", "--model", "{model}", "-"],
    "opencode": ["opencode", "run", "--model", "{model}"],
}

# Where each tool's envelope keeps the model's own text.
PAYLOAD_KEYS: dict[str, tuple[str, ...]] = {
    "claude": ("result",),
    "codex": ("last_agent_message", "result"),
    "opencode": ("result", "output"),
}


@dataclass
class CliRunner:
    tool: str
    model: str
    timeout_s: int = 600
    max_concurrency: int = 1
    # A floor, not a measurement: an interactive plan is not a queue, and pacing is the least
    # we can do about that.
    min_interval_s: float = 2.0
    # Asked once. The drain reads harness_version per call, and a subprocess per call to print a
    # version number is time spent on nothing.
    _harness: str | None = field(default=None, repr=False, compare=False)

    @property
    def name(self) -> str:
        return f"{self.tool}-cli"

    def harness_version(self) -> str:
        """The tool's own version. Mandatory: its harness changes with it."""
        if self._harness is not None:
            return self._harness
        self._harness = self._ask_version()
        return self._harness

    def _ask_version(self) -> str:
        try:
            done = subprocess.run(
                [self.tool, "--version"], capture_output=True, text=True, timeout=30
            )
            return f"{self.tool} {done.stdout.strip() or 'unknown'}"
        except (OSError, subprocess.SubprocessError):
            return f"{self.tool} unknown"

    def _argv(self) -> list[str]:
        template = ARGV.get(self.tool)
        if template is None:
            raise ValueError(f"no argv known for tool {self.tool!r}: {', '.join(sorted(ARGV))}")
        return [part.format(model=self.model) for part in template]

    def _unwrap(self, stdout: str) -> bytes:
        """Take the model's answer out of the CLI's envelope, without parsing it.

        `model_call` parses and validates for every backend, so the bytes are handed over
        untouched — a runner that pre-parsed would be judging, which is not its job.
        """
        try:
            envelope = json.loads(stdout)
        except ValueError:
            # No envelope: the tool printed the answer directly. Pass it through and let
            # model_call call it NOT_JSON if that is what it is.
            return stdout.strip().encode()
        if isinstance(envelope, dict):
            for key in PAYLOAD_KEYS.get(self.tool, ()):
                value = envelope.get(key)
                if isinstance(value, str):
                    return value.strip().encode()
        return stdout.strip().encode()

    def run(self, request: dict[str, Any]) -> RawAnswer:
        # `model_call` owns this string. Rebuilding the join here would put a second copy of the
        # separator in the repository, and it would diverge silently from the hash it is compared
        # against — the echo check would then fail on every row for a reason that is not a bug in
        # the prompt.
        prompt = rendered_prompt(request["system"], request["user"])
        try:
            done = subprocess.run(
                self._argv(), input=prompt, capture_output=True, text=True,
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired:
            return RawAnswer(model=self.model, failure_class="TIMEOUT",
                             detail=f"{self.tool} exceeded {self.timeout_s}s")
        except OSError as exc:
            return RawAnswer(model=self.model, failure_class="BACKEND_ERROR", detail=str(exc))

        if done.returncode != 0:
            return RawAnswer(
                model=self.model, failure_class="BACKEND_ERROR", prompt_sent=prompt,
                detail=f"exit {done.returncode}: {(done.stderr or '').strip()}",
            )

        # `prompt_sent` costs nothing here and it is what makes the echo check run at all: without
        # it every row from this backend comes back prompt_verified false, which is honest but
        # establishes nothing.
        #
        # No usage and no price: a subscription reports neither, and inventing a 0.0 would make
        # a cost report add up to a number that is not true.
        return RawAnswer(body=self._unwrap(done.stdout), model=self.model, cost_usd=None,
                         prompt_sent=prompt)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_runner_cli.py -q`
Expected: PASS, 8 passed

- [ ] **Step 5: Commit**

```bash
git add claimstone/runners/cli.py tests/test_runner_cli.py
git commit -m "runners/cli: a coding CLI as a backend, with its harness recorded

claude -p --output-format json is a documented scripting surface and a subprocess
is exactly the process boundary D7 wants — better on that axis than an in-process
SDK. Two things are recorded rather than wished away: the tool's own version, since
its harness sits between the prompt and the model and changes with it, and the
absence of a price, since a subscription reports none and a 0.0 would make a cost
report add up to a number that is not true.

Concurrency 1 with a floor on the interval. An interactive plan is not batch
infrastructure and a high-volume lane belongs elsewhere.

The prompt goes in on stdin. A chunk is thousands of characters of arbitrary text,
and an argv full of it is a length limit and a quoting bug.

<trailer>"
```

---

### Task 6: The Ollama Cloud runner

Implements spec §6's `runners/ollama_cloud.py`.

**Files:**
- Create: `claimstone/runners/ollama_cloud.py`
- Create: `tests/test_runner_ollama.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_runner_ollama.py`:

```python
"""The hosted-endpoint runner. No socket: the transport is injected."""

import json

from claimstone.runners import ollama_cloud


def request(**overrides):
    base = {"call_id": "abc", "lane": "extract", "system": "the registry", "user": "a chunk",
            "max_output_tokens": 800, "response_schema": {"type": "array"}}
    return {**base, **overrides}


class FakePost:
    """Stands in for requests.post. Records what it was sent."""

    def __init__(self, payload, status=200):
        self.payload, self.status = payload, status
        self.sent: dict = {}
        self.headers: dict = {}

    def __call__(self, url, *, json=None, headers=None, timeout=None):
        self.sent, self.headers = json or {}, headers or {}

        class Response:
            status_code = self.status
            text = "server said so"

            def json(inner):
                return self.payload

        return Response()


# A key that cannot collide with anything else in the body. The first version used "k", and the
# assertion "k" not in the body failed on the letter k in "deepseek" — a one-character substring
# test verifies nothing.
API_KEY = "sk-test-NOTINTHEBODY-7f3a"


def runner(post, **kw):
    return ollama_cloud.OllamaCloudRunner(
        model="deepseek-v4.1-flash", api_key=API_KEY, post=post, **kw)


def test_the_stable_prefix_is_sent_as_its_own_message():
    # The registry is identical across every call in a lane. Keeping it in its own system
    # message is what lets a backend charge it as cached input — $0.006 against $0.30 per
    # MTok, fifty-fold — and it puts the cacheability in the file rather than in the runner.
    post = FakePost({"message": {"content": "[]"}})
    runner(post).run(request())
    roles = [m["role"] for m in post.sent["messages"]]
    assert roles == ["system", "user"]
    assert post.sent["messages"][0]["content"] == "the registry"


def test_the_output_cap_is_passed_through():
    post = FakePost({"message": {"content": "[]"}})
    runner(post).run(request(max_output_tokens=800))
    assert post.sent["options"]["num_predict"] == 800


def test_the_api_key_travels_in_the_header_not_the_body():
    post = FakePost({"message": {"content": "[]"}})
    runner(post).run(request())
    assert API_KEY in post.headers.get("Authorization", "")
    assert API_KEY not in json.dumps(post.sent)


def test_usage_and_cost_are_carried_when_the_endpoint_reports_them():
    post = FakePost({"message": {"content": "[]"},
                     "prompt_eval_count": 3841, "eval_count": 412})
    answer = runner(post, price_in=0.30, price_out=1.20).run(request())
    assert answer.usage == {"input_tokens": 3841, "output_tokens": 412}
    assert answer.cost_usd == round(3841 / 1e6 * 0.30 + 412 / 1e6 * 1.20, 8)


def test_without_declared_prices_the_call_is_unpriced_not_free():
    post = FakePost({"message": {"content": "[]"}, "prompt_eval_count": 10, "eval_count": 5})
    assert runner(post).run(request()).cost_usd is None


def test_a_cut_off_answer_is_reported_as_truncated():
    post = FakePost({"message": {"content": "[{"}, "done_reason": "length"})
    assert runner(post).run(request()).truncated is True


def test_a_429_is_rate_limited():
    post = FakePost({}, status=429)
    assert runner(post).run(request()).failure_class == "RATE_LIMITED"


def test_a_500_is_a_backend_error():
    post = FakePost({}, status=500)
    assert runner(post).run(request()).failure_class == "BACKEND_ERROR"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_runner_ollama.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claimstone.runners.ollama_cloud'`

- [ ] **Step 3: Write `claimstone/runners/ollama_cloud.py`**

```python
"""A hosted open-model endpoint, priced per token against a monthly credit.

This is the backend a high-volume lane belongs on: per-token pricing, a real queue, and cached
input charged at a fiftieth of fresh input — which is why the work unit keeps the stable prefix
in `system` and the volatile part in `user`. A runner that concatenated them would still work;
it would just pay fifty times over for the registry on every call.

Prices are passed in rather than hard-coded. A rate table in the engine goes stale silently and
then a cost report is wrong without saying so; unset means unpriced, which is honest.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

from claimstone.model_call import rendered_prompt
from claimstone.runners.base import RawAnswer

ENDPOINT = "https://ollama.com/api/chat"


def _default_post() -> Callable[..., Any]:
    import requests

    return requests.post


@dataclass
class OllamaCloudRunner:
    model: str
    api_key: str | None = None
    price_in: float | None = None          # USD per million input tokens
    price_out: float | None = None         # USD per million output tokens
    # Declared separately because the whole argument for this backend is that cached input costs a
    # fiftieth of fresh input. Unset charges cached tokens at the fresh rate — the conservative
    # reading, which can overstate a bill but never understate one.
    price_cached_in: float | None = None   # USD per million cached input tokens
    timeout_s: int = 300
    max_concurrency: int = 4
    min_interval_s: float = 0.2
    endpoint: str = ENDPOINT
    post: Callable[..., Any] = field(default_factory=_default_post)

    name: str = "ollama-cloud"

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.environ.get("OLLAMA_API_KEY") or None

    def harness_version(self) -> str:
        return f"ollama-cloud/{self.endpoint}"

    def _price(self, usage: dict[str, int]) -> float | None:
        if self.price_in is None or self.price_out is None:
            # Unpriced, not free. A cost report that folded this in would be wrong.
            return None
        cached = usage.get("cached_input_tokens", 0)
        fresh = max(usage.get("input_tokens", 0) - cached, 0)
        cached_rate = self.price_in if self.price_cached_in is None else self.price_cached_in
        return round(
            fresh / 1e6 * self.price_in
            + cached / 1e6 * cached_rate
            + usage.get("output_tokens", 0) / 1e6 * self.price_out,
            8,
        )

    def run(self, request: dict[str, Any]) -> RawAnswer:
        if not self.api_key:
            return RawAnswer(model=self.model, failure_class="BACKEND_ERROR",
                             detail="set OLLAMA_API_KEY or pass api_key")

        body = {
            "model": self.model,
            "stream": False,
            # Two messages, not one concatenated string: the first is identical across the
            # lane and is what a cached-input price applies to.
            "messages": [
                {"role": "system", "content": request["system"]},
                {"role": "user", "content": request["user"]},
            ],
            "options": {"num_predict": request["max_output_tokens"]},
        }

        try:
            response = self.post(
                self.endpoint, json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout_s,
            )
        except Exception as exc:  # transport failures of every shape
            return RawAnswer(model=self.model, failure_class="BACKEND_ERROR", detail=str(exc))

        status = getattr(response, "status_code", 0)
        if status == 429:
            return RawAnswer(model=self.model, failure_class="RATE_LIMITED", detail="429")
        if status >= 400:
            return RawAnswer(model=self.model, failure_class="BACKEND_ERROR",
                             detail=f"status {status}: {getattr(response, 'text', '')[:200]}")

        try:
            payload = response.json()
        except ValueError as exc:
            return RawAnswer(model=self.model, failure_class="BACKEND_ERROR",
                             detail=f"endpoint did not return JSON: {exc}")

        usage = {
            key: int(payload[source])
            for key, source in (("input_tokens", "prompt_eval_count"),
                                ("output_tokens", "eval_count"))
            if isinstance(payload.get(source), int)
        }
        if isinstance(payload.get("prompt_cache_hit_count"), int):
            usage["cached_input_tokens"] = int(payload["prompt_cache_hit_count"])

        content = ((payload.get("message") or {}).get("content") or "")
        return RawAnswer(
            body=content.strip().encode(),
            model=str(payload.get("model") or self.model),
            usage=usage,
            cost_usd=self._price(usage),
            truncated=payload.get("done_reason") == "length",
            # Two messages went out; the echo check compares one string, and this is that string.
            prompt_sent=rendered_prompt(request["system"], request["user"]),
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_runner_ollama.py -q`
Expected: PASS, 8 passed

- [ ] **Step 5: Commit**

```bash
git add claimstone/runners/ollama_cloud.py tests/test_runner_ollama.py
git commit -m "runners/ollama_cloud: the backend a high-volume lane belongs on

Per-token pricing against a monthly credit, and cached input charged at a
fiftieth of fresh input — which is why the work unit keeps the registry in system
and the chunk in user, and why this runner sends them as two messages.
Concatenating them would still work and would pay fifty times over for the
registry on every call.

Prices are passed in, not hard-coded: a rate table inside the engine goes stale
silently and then a cost report is wrong without saying so. Unset means unpriced,
which a report must render as unpriced and never as zero.

<trailer>"
```

---

### Task 7: The local runner

Implements spec §6's `runners/llamacpp.py`.

**Files:**
- Create: `claimstone/runners/llamacpp.py`
- Create: `tests/test_runner_llamacpp.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_runner_llamacpp.py`:

```python
"""The local server runner. No socket: the transport is injected."""

from claimstone.runners import llamacpp
from tests.test_runner_ollama import FakePost, request


def runner(post, **kw):
    return llamacpp.LlamaCppRunner(post=post, **kw)


def test_the_prefix_is_its_own_message_here_too():
    post = FakePost({"choices": [{"message": {"content": "[]"}, "finish_reason": "stop"}]})
    runner(post).run(request())
    assert [m["role"] for m in post.sent["messages"]] == ["system", "user"]


def test_the_local_server_is_serial():
    # Measured at 11.6 minutes per call on the target machine: a second concurrent call does
    # not halve that, it queues behind the first on one GPU.
    assert runner(FakePost({})).max_concurrency == 1


def test_a_local_call_is_unpriced_because_it_has_no_price():
    post = FakePost({"choices": [{"message": {"content": "[]"}, "finish_reason": "stop"}],
                     "usage": {"prompt_tokens": 10, "completion_tokens": 5}})
    answer = runner(post).run(request())
    assert answer.cost_usd is None
    assert answer.usage == {"input_tokens": 10, "output_tokens": 5}


def test_a_length_finish_is_truncated():
    post = FakePost({"choices": [{"message": {"content": "[{"}, "finish_reason": "length"}]})
    assert runner(post).run(request()).truncated is True


def test_a_dead_server_is_a_backend_error():
    def refuse(*args, **kwargs):
        raise OSError("connection refused")

    assert runner(refuse).run(request()).failure_class == "BACKEND_ERROR"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_runner_llamacpp.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claimstone.runners.llamacpp'`

- [ ] **Step 3: Write `claimstone/runners/llamacpp.py`**

```python
"""The local `llama.cpp` server, over its OpenAI-compatible chat endpoint.

Measured on the target machine at Q8_0: 11.6 minutes per call on ~8K-token prompts, ~5 calls an
hour (D4). `max_concurrency` is 1 because a second simultaneous call does not halve that — it
queues behind the first on one GPU.

D4's window finding belongs to this backend and does not travel: see the perimeter note on D4
before carrying its numbers anywhere else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from claimstone.runners.base import RawAnswer

ENDPOINT = "http://127.0.0.1:8080/v1/chat/completions"


def _default_post() -> Callable[..., Any]:
    import requests

    return requests.post


@dataclass
class LlamaCppRunner:
    model: str = "local"
    endpoint: str = ENDPOINT
    timeout_s: int = 3600
    max_concurrency: int = 1
    min_interval_s: float = 0.0
    post: Callable[..., Any] = field(default_factory=_default_post)

    name: str = "llamacpp"

    def harness_version(self) -> str:
        return f"llamacpp/{self.endpoint}"

    def run(self, request: dict[str, Any]) -> RawAnswer:
        body = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": request["system"]},
                {"role": "user", "content": request["user"]},
            ],
            "max_tokens": request["max_output_tokens"],
        }
        try:
            response = self.post(self.endpoint, json=body, headers={}, timeout=self.timeout_s)
        except Exception as exc:
            return RawAnswer(model=self.model, failure_class="BACKEND_ERROR", detail=str(exc))

        status = getattr(response, "status_code", 0)
        if status >= 400:
            return RawAnswer(model=self.model, failure_class="BACKEND_ERROR",
                             detail=f"status {status}")
        try:
            payload = response.json()
        except ValueError as exc:
            return RawAnswer(model=self.model, failure_class="BACKEND_ERROR", detail=str(exc))

        choices = payload.get("choices") or [{}]
        first = choices[0] if choices else {}
        content = ((first.get("message") or {}).get("content") or "")
        reported = payload.get("usage") or {}
        usage = {
            key: int(reported[source])
            for key, source in (("input_tokens", "prompt_tokens"),
                                ("output_tokens", "completion_tokens"))
            if isinstance(reported.get(source), int)
        }
        return RawAnswer(
            body=content.strip().encode(),
            model=str(payload.get("model") or self.model),
            usage=usage,
            # Electricity is a cost and not a per-call price. Unpriced, not free.
            cost_usd=None,
            truncated=first.get("finish_reason") == "length",
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_runner_llamacpp.py -q`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add claimstone/runners/llamacpp.py tests/test_runner_llamacpp.py
git commit -m "runners/llamacpp: the local server, serial because the GPU is

Concurrency 1: at 11.6 minutes per call a second simultaneous request does not
halve the wait, it queues behind the first on one card. Unpriced rather than free —
electricity is a cost, not a per-call price.

D4's window finding stays with this backend. The perimeter note on D4 says why it
must not be carried to another one.

<trailer>"
```

---

### Task 8: Cost and throughput

Implements spec §7.

**Files:**
- Create: `claimstone/model_report.py`
- Create: `tests/test_model_report.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_model_report.py`:

```python
"""What the queue cost and how fast it went — per backend, because the rates differ hugely."""

from claimstone import model_report
from claimstone.store import Store


def result(call_id, *, backend, model="m", cost=None, latency=2.0, ok=True, failure=None,
           usage=None):
    return {"call_id": call_id, "backend": backend, "model": model, "ok": ok,
            "failure_class": failure, "cost_usd": cost, "latency_s": latency,
            "usage": usage or {"input_tokens": 100, "output_tokens": 50}}


def _store(tmp_path, rows):
    store = Store("t", base=tmp_path)
    for row in rows:
        store.append("calls/extract/b1/results.jsonl", row)
    return store


def test_a_retry_is_two_payments_not_one(tmp_path):
    # A timeout that cost money and was retried was paid for twice. Summing the collapse would
    # report one, and "what did this batch cost" is the question the report exists to answer.
    store = _store(tmp_path, [
        result("a", backend="x", cost=0.001, ok=False, failure="TIMEOUT"),
        result("a", backend="x", cost=0.002),
    ])
    summary = model_report.summarise(store, lane="extract", batch="b1")
    assert summary["calls"] == 1
    assert summary["attempts"] == 2
    assert summary["by_backend"]["x"]["cost_usd"] == 0.003


def test_two_backends_over_the_same_calls_are_not_collapsed(tmp_path):
    store = _store(tmp_path, [result("a", backend="x"), result("a", backend="y")])
    summary = model_report.summarise(store, lane="extract", batch="b1")
    assert summary["calls"] == 2
    assert set(summary["by_backend"]) == {"x", "y"}


def test_cost_is_summed_per_backend_and_model(tmp_path):
    store = _store(tmp_path, [result("a", backend="ollama-cloud", cost=0.001),
                              result("b", backend="ollama-cloud", cost=0.002)])
    summary = model_report.summarise(store, lane="extract", batch="b1")
    bucket = summary["by_backend"]["ollama-cloud"]
    assert bucket["calls"] == 2
    assert bucket["cost_usd"] == 0.003


def test_an_unpriced_call_is_counted_but_not_summed(tmp_path):
    # Folding a null price into a total would make the total a number that is not true.
    store = _store(tmp_path, [result("a", backend="claude-cli", cost=None),
                              result("b", backend="claude-cli", cost=None)])
    bucket = model_report.summarise(store, lane="extract", batch="b1")["by_backend"]["claude-cli"]
    assert bucket["calls"] == 2
    assert bucket["unpriced"] == 2
    assert bucket["cost_usd"] is None


def test_a_mixed_backend_reports_both_the_total_and_what_it_excludes(tmp_path):
    store = _store(tmp_path, [result("a", backend="x", cost=0.5),
                              result("b", backend="x", cost=None)])
    bucket = model_report.summarise(store, lane="extract", batch="b1")["by_backend"]["x"]
    assert bucket["cost_usd"] == 0.5
    assert bucket["unpriced"] == 1


def test_throughput_is_per_backend(tmp_path):
    # ~5 calls an hour locally against an afternoon for the same queue on a hosted endpoint:
    # an aggregate figure across the two would describe neither.
    store = _store(tmp_path, [result("a", backend="llamacpp", latency=696.0),
                              result("b", backend="ollama-cloud", latency=3.0)])
    by_backend = model_report.summarise(store, lane="extract", batch="b1")["by_backend"]
    assert round(by_backend["llamacpp"]["calls_per_hour"], 1) == 5.2
    assert round(by_backend["ollama-cloud"]["calls_per_hour"]) == 1200


def test_failures_are_broken_down_by_class(tmp_path):
    store = _store(tmp_path, [result("a", backend="x", ok=False, failure="SCHEMA_INVALID"),
                              result("b", backend="x", ok=False, failure="SCHEMA_INVALID"),
                              result("c", backend="x", ok=True)])
    bucket = model_report.summarise(store, lane="extract", batch="b1")["by_backend"]["x"]
    assert bucket["ok"] == 1
    assert bucket["failures_by_class"] == {"SCHEMA_INVALID": 2}


def test_an_empty_batch_has_no_throughput_rather_than_zero(tmp_path):
    store = _store(tmp_path, [])
    summary = model_report.summarise(store, lane="extract", batch="b1")
    assert summary["by_backend"] == {}
    assert summary["calls"] == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_model_report.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'claimstone.model_report'`

- [ ] **Step 3: Write `claimstone/model_report.py`**

```python
"""What a queue cost and how fast it went.

Two rules, both about not producing a figure that describes nothing. A `null` cost is reported
as unpriced rather than folded into a total, because a subscription has no per-call price and a
total that absorbed it would be wrong without saying so. And throughput is stated per backend:
the local server runs at about five calls an hour where a hosted endpoint finishes the same
queue in an afternoon, so an average across them describes neither.
"""

from __future__ import annotations

from typing import Any

from claimstone.store import Store


def summarise(store: Store, *, lane: str, batch: str) -> dict[str, Any]:
    """Per backend and model: calls, outcomes, tokens, cost, observed throughput."""
    # Every attempt, not the latest per call: a timeout that cost money and was retried is two
    # payments, and collapsing them reports one. Correctness is counted on the collapse below.
    attempts = list(store.read(f"calls/{lane}/{batch}/results.jsonl"))
    current: dict[str, dict[str, Any]] = {}
    for row in attempts:
        current[f"{row.get('call_id')}|{row.get('backend')}"] = row
    rows = {key: row for key, row in current.items()}

    by_backend: dict[str, dict[str, Any]] = {}
    for row in attempts:
        key = str(row.get("backend") or "unknown")
        bucket = by_backend.setdefault(key, {
            "calls": 0, "ok": 0, "unpriced": 0,
            "cost_usd": None, "latency_total_s": 0.0,
            "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0,
            "models": set(), "failures_by_class": {},
        })
        bucket["calls"] += 1
        bucket["models"].add(str(row.get("model") or "unknown"))
        if row.get("ok"):
            bucket["ok"] += 1
        else:
            name = str(row.get("failure_class"))
            bucket["failures_by_class"][name] = bucket["failures_by_class"].get(name, 0) + 1

        cost = row.get("cost_usd")
        if cost is None:
            bucket["unpriced"] += 1
        else:
            bucket["cost_usd"] = round((bucket["cost_usd"] or 0.0) + float(cost), 8)

        bucket["latency_total_s"] += float(row.get("latency_s") or 0.0)
        usage = row.get("usage") or {}
        for field_name in ("input_tokens", "cached_input_tokens", "output_tokens"):
            bucket[field_name] += int(usage.get(field_name) or 0)

    for bucket in by_backend.values():
        spent = bucket.pop("latency_total_s")
        # Observed, not promised: it is the rate this queue actually ran at on this backend.
        bucket["calls_per_hour"] = (bucket["calls"] / spent * 3600) if spent else None
        bucket["models"] = sorted(bucket["models"])
        bucket["failures_by_class"] = dict(
            sorted(bucket["failures_by_class"].items(), key=lambda kv: -kv[1])
        )

    return {
        "lane": lane,
        "batch": batch,
        # Distinct (call, backend) pairs currently answered, and how many of those stand valid.
        "calls": len(rows),
        "ok": sum(1 for row in rows.values() if row.get("ok")),
        # What was actually paid for and waited on, retries included.
        "attempts": len(attempts),
        "by_backend": dict(sorted(by_backend.items())),
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_model_report.py -q`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add claimstone/model_report.py tests/test_model_report.py
git commit -m "model_report: unpriced is not free, and throughput is per backend

A null cost is counted and reported as unpriced rather than folded into a total: a
subscription has no per-call price and a total that absorbed it would be wrong
without saying so. Throughput stays per backend because the local server runs at
about five calls an hour where a hosted endpoint finishes the same queue in an
afternoon, and an average across the two describes neither.

<trailer>"
```

---

### Task 9: Wiring the CLI

Implements spec §6's `model-run` and §7's `model-report`.

**Files:**
- Modify: `claimstone/cli.py`
- Create: `tests/test_cli_model.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_model.py`:

```python
"""model-run and model-report at the command line."""

import pytest

from claimstone.cli import build_parser, main


def test_a_backend_must_be_named():
    # D13 defers lane assignment to measurement, so there is no default to fall back on.
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["model-run", "projects/example-news-and-returns", "extract", "--batch", "b1"])


def test_a_backend_that_needs_a_model_says_so_rather_than_crashing(capsys):
    code = main(["model-run", "projects/example-news-and-returns", "extract",
                 "--batch", "b1", "--backend", "claude-cli"])
    assert code == 2
    error = capsys.readouterr().err
    assert "--model" in error


def test_a_backend_with_a_default_model_needs_no_flag():
    from claimstone import runners

    # llamacpp serves whatever the local server has loaded; naming it is not the caller's job.
    assert runners.build("llamacpp").model == "local"


def test_an_unknown_backend_is_refused_by_name(capsys):
    code = main(["model-run", "projects/example-news-and-returns", "extract",
                 "--batch", "b1", "--backend", "nonesuch"])
    assert code == 2
    assert "nonesuch" in capsys.readouterr().err


def test_an_unknown_lane_is_refused(capsys):
    code = main(["model-run", "projects/example-news-and-returns", "synthesis",
                 "--batch", "b1", "--backend", "llamacpp"])
    assert code == 2


def test_model_report_on_an_empty_batch_says_so(tmp_path, capsys):
    code = main(["model-report", "projects/example-news-and-returns", "extract",
                 "--batch", "b1", "--store", str(tmp_path)])
    assert code == 0
    assert "no calls" in capsys.readouterr().out
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_cli_model.py -q`
Expected: FAIL — `model-run` is not a known command

- [ ] **Step 3: Add both handlers to `claimstone/cli.py`**

```python
def _model_run(args: argparse.Namespace) -> int:
    from claimstone import model_call, runners
    from claimstone.store import Store

    if args.lane not in model_call.LANES:
        print(f"unknown lane {args.lane!r}: {', '.join(model_call.LANES)}", file=sys.stderr)
        return 2
    try:
        runner = runners.build(args.backend, model=args.model)
    except ValueError as exc:
        # Includes "this backend needs --model": a missing model is a usage error with a sentence,
        # not a TypeError from a constructor.
        print(str(exc), file=sys.stderr)
        return 2

    project = load_project(args.project)
    store = Store(project.name, base=args.store)
    queue = model_call.Queue(store, lane=args.lane, batch=args.batch)

    pending = len(queue.pending())
    done = ok = 0
    for row in model_call.drain(queue, runner, limit=args.limit):
        done += 1
        if row["ok"]:
            ok += 1
        mark = "ok  " if row["ok"] else "fail"
        detail = "" if row["ok"] else f"  {row['failure_class']}"
        print(f"[{done:>4}/{pending}] {ok / done:.2f}  {mark}  {row['call_id'][:12]}"
              f"  {row['latency_s']:.1f}s{detail}", file=sys.stderr)
    print(f"{done} answered, {ok} valid, on {runner.name} ({runner.harness_version()})")
    return 0


def _model_report(args: argparse.Namespace) -> int:
    from claimstone import model_report
    from claimstone.store import Store

    project = load_project(args.project)
    summary = model_report.summarise(
        Store(project.name, base=args.store), lane=args.lane, batch=args.batch)

    if args.json:
        import json

        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    if not summary["calls"]:
        print(f"{project.name} {args.lane}/{args.batch}: no calls recorded")
        return 0

    print(f"{project.name} {args.lane}/{args.batch} — {summary['calls']} calls, "
          f"{summary['ok']} valid")
    for backend, bucket in summary["by_backend"].items():
        cost = "unpriced" if bucket["cost_usd"] is None else f"${bucket['cost_usd']:.4f}"
        if bucket["unpriced"] and bucket["cost_usd"] is not None:
            cost += f" (+{bucket['unpriced']} unpriced)"
        rate = "—" if bucket["calls_per_hour"] is None else f"{bucket['calls_per_hour']:.0f}/h"
        print(f"  {backend:<14} {bucket['ok']}/{bucket['calls']}  {cost:<24} {rate:>9}"
              f"  {', '.join(bucket['models'])}")
        if bucket["failures_by_class"]:
            print("                 " + "  ".join(
                f"{k} {v}" for k, v in bucket["failures_by_class"].items()))
    return 0
```

Register both, noting that they take a lane and a batch rather than only a project:

```python
    for name, handler, help_text in (
        ("model-run", _model_run, "drain a lane's queue on a named backend"),
        ("model-report", _model_report, "what a queue cost and how fast it went"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("project", help="path to a project directory")
        command.add_argument("lane", help="extract or review")
        command.add_argument("--batch", required=True, help="which batch to work on")
        command.add_argument("--store", default="store", help="where generated data lives")
        command.set_defaults(func=handler)
        if name == "model-run":
            # Required: which backend serves a lane is a finding, not a default (D13).
            command.add_argument("--backend", required=True,
                                 help="one of " + ", ".join(BACKENDS))
            command.add_argument("--model", help="model id for backends that need one")
            command.add_argument("--limit", type=int, default=None)
        if name == "model-report":
            command.add_argument("--json", action="store_true")
```

Building the parser must not import three runner modules, so the names are a literal beside
`SWEEP_VALUES`:

```python
BACKENDS = ("claude-cli", "codex-cli", "llamacpp", "ollama-cloud", "opencode-cli")
```

- [ ] **Step 4: Pin the literal against the registry**

Two lists that must agree. Append to `tests/test_cli_model.py`:

```python
def test_the_backend_list_in_help_matches_the_registry():
    # Two lists that must agree, so a runner added without updating the help is a failing test
    # rather than a backend nobody can select.
    from claimstone import runners
    from claimstone.cli import BACKENDS

    assert set(BACKENDS) == set(runners.available())
```

- [ ] **Step 5: Run everything**

Run: `.venv/bin/pytest -q`
Expected: PASS, all tests

Run: `.venv/bin/claimstone model-run --help`
Expected: usage showing `--backend` as required

- [ ] **Step 6: Commit**

```bash
git add claimstone/cli.py tests/test_cli_model.py
git commit -m "cli: model-run and model-report, with no default backend

--backend is required. D13 defers lane assignment to measurement, so there is
nothing to fall back on, and a silent default would answer by habit the question
the boundary exists to answer by evidence.

The backend names appear both in the registry and in the parser's help, so a test
pins them together: a runner added without updating the help is a failing test
rather than a backend nobody can select.

<trailer>"
```

---

### Task 10: The contract, the spec corrections, and a live smoke test

Implements spec §8's live test and lands the two corrections this plan made.

**Files:**
- Create: `docs/contracts/model_calls.md`
- Create: `tests/test_live_runners.py`
- Modify: `docs/superpowers/specs/2026-09-22-model-call-design.md`

- [ ] **Step 1: Write `tests/test_live_runners.py`**

```python
"""One real call per backend. Skipped everywhere by default, including CI.

Its job is to catch a backend rotting — an envelope key renamed, a flag removed, an endpoint
moved — which no fake can detect, because a fake is written from the same assumption the code is.
"""

import os

import pytest

from claimstone import model_call

pytestmark = pytest.mark.skipif(
    os.environ.get("CLAIMSTONE_LIVE") != "1", reason="set CLAIMSTONE_LIVE=1 to run"
)

SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["answer"], "properties": {"answer": {"type": "string"}}}

UNIT = dict(
    lane="extract", registry_version=1, max_output_tokens=200, response_schema=SCHEMA,
    system='Answer only with JSON of the form {"answer": "..."}. No prose.',
    user="What is the capital of France?",
)


@pytest.mark.network
@pytest.mark.parametrize("backend,model", [
    ("claude-cli", "claude-opus-5"),
    ("ollama-cloud", "deepseek-v4.1-flash"),
    ("llamacpp", "local"),
])
def test_a_backend_returns_something_the_validator_accepts(backend, model):
    from claimstone import runners

    runner = runners.build(backend, model=model)
    request = model_call.work_unit(**UNIT)
    answer = runner.run(dict(request))
    if answer.failure_class:
        pytest.skip(f"{backend} unavailable: {answer.failure_class} {answer.detail}")

    row = model_call.build_result(
        request, answer, backend=runner.name, harness_version=runner.harness_version(),
        raw_sha256=None, raw_path=None, started_at="", finished_at="", latency_s=0.0)
    assert row["ok"], f"{backend}: {row['failure_class']} {row['schema_errors']} {row['detail']}"
    assert "paris" in row["output"]["answer"].lower()
```

An unavailable backend **skips** rather than fails: a missing API key or a stopped local server
is not a defect in this repository.

- [ ] **Step 2: Verify it is skipped by default**

Run: `.venv/bin/pytest tests/test_live_runners.py -q`
Expected: `3 skipped`

- [ ] **Step 3: Land the two corrections in the spec**

In `docs/superpowers/specs/2026-09-22-model-call-design.md`, §4, replace the `call_id` formula
paragraph's first sentence:

> **`call_id` is derived, not assigned:** `sha256(lane | schema_version | prompt_sha256)`.

with:

> **`call_id` is derived, not assigned:**
> `sha256(lane | schema_version | prompt_sha256 | max_output_tokens | schema_sha256)`, where
> `prompt_sha256 = sha256(canonical({system, user}))`. The cap and the schema are inside the id
> because §5 makes a retry under a bigger cap "honestly a different call"; `prompt_sha256` stays
> narrower because it is what the echo check verifies, and widening it would make a mismatch
> ambiguous between a mangled prompt and a changed cap.

And add to §4, after the `response_schema` paragraph:

> **The validator is `jsonshape.py`, a closed subset.** `type`, `properties`, `required`,
> `items`, `enum`, `additionalProperties`, `minItems`, `maxItems` — and **an unsupported keyword
> raises** rather than being ignored, checked when the request is written so the failure lands on
> the stage that wrote it. A `jsonschema` dependency would be spec-complete and would not sit
> behind a process boundary (D7); a validator that silently skipped `pattern` would tell a stage
> its output was checked when it was not, which is the class of false assurance this project
> exists to prevent.

- [ ] **Step 4: Write `docs/contracts/model_calls.md`**

```markdown
# `calls/<lane>/<batch>/` — the contract

Written by stage 4 (extract) and stage 5 (review); drained by `claimstone model-run`.

```
requests.jsonl   the work units, written by the stage
results.jsonl    append-only, written by a runner
raw/<sha256>     the response bytes, content-addressed
```

**A model call is not reproducible. It is auditable.** Sampling, model updates and a CLI's own
harness all break sameness of answer. What is promised and checked: this exact prompt was sent,
this exact response came back, and here are the hashes.

## The work unit

| field | meaning |
|---|---|
| `call_id` | `sha256(lane \| schema_version \| prompt_sha256 \| max_output_tokens \| schema_sha256)` |
| `lane` | `extract` or `review` |
| `schema_version`, `registry_version` | the row shape, and the question registry it was built against |
| `system` | the stable prefix: registry plus instructions, identical across the lane |
| `user` | the volatile part: one chunk, or one claim and its quote |
| `response_schema` | the shape the answer must satisfy, validated by `jsonshape` |
| `max_output_tokens` | the cap. Part of `call_id`: raising it makes a different call |
| `source_id`, `chunk_id` | where the input came from |
| `prompt_sha256` | `sha256(canonical({system, user}))` — the prompt and nothing else |
| `schema_sha256` | `sha256(canonical(response_schema))` |
| `created_at` | UTC, ISO 8601, seconds |

`system` and `user` are separate so a backend that prices cached input separately can charge the
registry once. A runner that concatenates them still works; it pays fifty times over.

## The result

| field | meaning |
|---|---|
| `call_id` | the unit this answers |
| `ok` | true only when there is a validated output |
| `backend`, `model`, `harness_version` | who answered, and what sat between the prompt and the model |
| `prompt_sha256` | echoed and verified; a mismatch is `PROMPT_MISMATCH` |
| `output` | the parsed, validated answer, or `null` |
| `schema_errors` | why validation failed, by path |
| `raw_sha256`, `raw_path` | the bytes, always kept |
| `usage` | `input_tokens`, `cached_input_tokens`, `output_tokens` where reported |
| `cost_usd` | `null` means **not priced**, never free |
| `latency_s`, `started_at`, `finished_at` | observed, per call |
| `failure_class`, `detail` | what went wrong |

## Failure classes

Terminal — a retry changes nothing until the request or the backend does:
`NOT_JSON` · `SCHEMA_INVALID` · `REFUSED` · `PROMPT_MISMATCH` · `TRUNCATED`

Transient — the next drain tries again:
`TIMEOUT` · `RATE_LIMITED` · `BACKEND_ERROR` · `EMPTY`

`TRUNCATED` is terminal because raising the cap changes `call_id`: a retry under a bigger cap is
a different call, not a second attempt at this one. An unrecognised class counts as terminal.

**None of these ever becomes an empty output.** `EMPTY` is not "the chunk contained no claims"
and `TRUNCATED` is not "the answer was short": both would be assertions about the literature that
a failed call has not earned. Stage 4's rejection ledger is the denominator, and it can only be
that if a failure stays a failure.

## Resuming

`pending()` returns units with no result and units whose last result was transient. So a drain
interrupted after two hours resumes, and pointing a second backend at the same `requests.jsonl`
produces a second `results.jsonl` whose rows line up per `call_id` — which is what makes "is
backend A better than B at this lane" a question with an answer.
```

- [ ] **Step 5: Run everything and commit**

Run: `.venv/bin/pytest -q` — expected: all pass, 6 skipped
Run: `.venv/bin/claimstone validate --all-projects` — expected: OK for both

```bash
git add docs/contracts/model_calls.md tests/test_live_runners.py \
        docs/superpowers/specs/2026-09-22-model-call-design.md
git commit -m "docs: the model_call contract, and the two corrections the plan made

call_id now covers the output cap and the schema, because the spec called a retry
under a bigger cap a different call while its own formula left the cap out.
prompt_sha256 stays narrow: it is what the echo check verifies, and widening it
would make a mismatch ambiguous between a mangled prompt and a changed cap.

And the spec named a validator that did not exist. jsonshape is a closed subset
that raises on any keyword it cannot honour, checked when the request is written
so the failure lands on the stage that wrote it.

One live call per backend, skipped everywhere by default, skipping rather than
failing when a backend is simply not configured. No fake catches an envelope key
renamed or an endpoint moved, because a fake is written from the same assumption
the code is.

<trailer>"
```

---

## What this plan does not do

- **No stage 4 or 5.** This is their contract, not their implementation. Nothing here builds a prompt, chunks a document, or extracts a claim; `system` and `user` arrive as strings from a caller that does not exist yet.
- **No parallel drain.** Sequential, with `max_concurrency` declared and recorded so the measurement has somewhere to land. The queue is resumable by `call_id`, so adding it later touches no file format.
- **No `model-compare`.** Diffing two `results.jsonl` files per `call_id` is what the derived `call_id` makes possible, and it gets written when there are two results files worth comparing.
- **No automatic backend selection or fallback chain** (spec §9). A runner that silently failed over would destroy the one property this boundary exists for: knowing which model produced which claim.
