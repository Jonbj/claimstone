# Overnight local shadow reader — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read a batch with the local `llama.cpp` server overnight. The run happens in an
isolated store and ends in a report that compares the local reader with the cloud readers.

**Architecture:** The runner gains a configurable endpoint, a reasoning switch and an imposed
schema. `runners.build` turns an unsupported option into a usage error. A tool,
`tools/run_local_shadow.py`, copies what harvest needs into
`store/local-shadows/<lane>/<batch>/<project>/`. It drains one call at a time, so it can stop at
a deadline, and it compares the result with the source store while only reading that store.

**Tech Stack:** Python 3.11 stdlib, `requests`, pytest. Spec:
`docs/superpowers/specs/2026-10-03-local-shadow-design.md`.

**Scope note:** Only the extract lane in this version. `--lane review` is refused with a sentence.
The spec mentions review harvest, and this plan defers it, because review agreement needs its own
comparison rule.

---

## File structure

| File | Responsibility |
|---|---|
| `claimstone/runners/llamacpp.py` | endpoint from env, `think`, `enforce_schema`, reasoning kept out of the body |
| `claimstone/runners/__init__.py` | unsupported runner option → `ValueError` |
| `claimstone/cli.py` | `model-run --endpoint` |
| `tools/run_local_shadow.py` | prepare / run / report on an isolated store |
| `tests/test_runner_llamacpp.py`, `tests/test_cli_model.py`, `tests/test_run_local_shadow.py` | tests |
| `docs/GUIDE.md`, `.env.example`, the spec | documentation |

---

### Task 1: llama.cpp runner — endpoint, reasoning, schema

**Files:**
- Modify: `claimstone/runners/llamacpp.py`
- Test: `tests/test_runner_llamacpp.py`

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_runner_llamacpp.py`:

```python
def ok_payload(**message):
    return {"choices": [{"message": {"content": "[]", **message}, "finish_reason": "stop"}]}


def test_the_endpoint_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("CLAIMSTONE_LLAMACPP_URL", "http://127.0.0.1:18081/v1/chat/completions")
    assert llamacpp.LlamaCppRunner().endpoint == "http://127.0.0.1:18081/v1/chat/completions"


def test_an_explicit_endpoint_beats_the_environment(monkeypatch):
    monkeypatch.setenv("CLAIMSTONE_LLAMACPP_URL", "http://elsewhere/v1/chat/completions")
    assert runner(FakePost({}), endpoint="http://here/v1/chat/completions").endpoint \
        == "http://here/v1/chat/completions"


def test_reasoning_off_is_sent_as_a_template_switch():
    post = FakePost(ok_payload())
    runner(post, think=False).run(request())
    assert post.sent["chat_template_kwargs"] == {"enable_thinking": False}


def test_reasoning_unset_sends_nothing():
    post = FakePost(ok_payload())
    runner(post).run(request())
    assert "chat_template_kwargs" not in post.sent


def test_an_enforced_schema_is_a_response_format():
    post = FakePost(ok_payload())
    runner(post, enforce_schema=True).run(request())
    assert post.sent["response_format"] == {
        "type": "json_schema", "json_schema": {"name": "answer", "schema": {"type": "array"}}}


def test_the_harness_names_reasoning_and_shape():
    version = runner(FakePost({}), think=False, enforce_schema=True).harness_version()
    assert version.endswith(" think=off format=schema")


def test_reasoning_never_enters_the_answer_but_its_size_is_recorded():
    post = FakePost(ok_payload(reasoning_content="I think " * 50))
    answer = runner(post).run(request())
    assert answer.body == b"[]"
    assert "reasoning_chars=400" in answer.detail


def test_a_refused_request_keeps_the_server_reason():
    post = FakePost({}, status=400)
    answer = runner(post).run(request())
    assert answer.failure_class == "BACKEND_ERROR"
    assert "server said so" in answer.detail
```

- [ ] **Step 2: Run them and confirm they fail.**

Run: `.venv/bin/pytest -q tests/test_runner_llamacpp.py`
Expected: the new tests fail. Most fail with `TypeError: unexpected keyword argument`, and the
environment test fails on the endpoint.

- [ ] **Step 3: Implement.** In `claimstone/runners/llamacpp.py`, add `import os` and replace the
dataclass body from `class LlamaCppRunner:` to the end of the file with the code below:

```python
def _default_endpoint() -> str:
    # The server's port is the operator's, not the engine's: the cluster script serves on 18081.
    return os.environ.get("CLAIMSTONE_LLAMACPP_URL") or ENDPOINT


@dataclass
class LlamaCppRunner:
    model: str = "local"
    endpoint: str = field(default_factory=_default_endpoint)
    # Same meaning as on ollama-cloud: None sends nothing, which is not the same as off. Sent as the
    # chat template's switch, which is where llama-server's reasoning models read it.
    think: bool | None = None
    # llama-server compiles a JSON schema into a grammar, so here the shape is imposed, not requested.
    enforce_schema: bool = False
    timeout_s: int = 3600
    max_concurrency: int = 1
    min_interval_s: float = 0.0
    post: Callable[..., Any] = field(default_factory=_default_post)

    name: str = "llamacpp"

    def harness_version(self) -> str:
        thinking = "" if self.think is None else f" think={'on' if self.think else 'off'}"
        shape = " format=schema" if self.enforce_schema else ""
        return f"llamacpp/{self.endpoint}{thinking}{shape}"

    def run(self, request: dict[str, Any]) -> RawAnswer:
        body: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": request["system"]},
                {"role": "user", "content": request["user"]},
            ],
            "max_tokens": request["max_output_tokens"],
        }
        if self.think is not None:
            body["chat_template_kwargs"] = {"enable_thinking": self.think}
        if self.enforce_schema and request.get("response_schema"):
            body["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "answer", "schema": request["response_schema"]}}
        try:
            response = self.post(self.endpoint, json=body, headers={}, timeout=self.timeout_s)
        except Exception as exc:
            return RawAnswer(model=self.model, failure_class="BACKEND_ERROR", detail=str(exc))

        status = getattr(response, "status_code", 0)
        if status >= 400:
            # The server's sentence matters here: a schema it cannot compile is a 400 with a reason.
            return RawAnswer(model=self.model, failure_class="BACKEND_ERROR",
                             detail=f"status {status}: {getattr(response, 'text', '')[:200]}")
        try:
            payload = response.json()
        except ValueError as exc:
            return RawAnswer(model=self.model, failure_class="BACKEND_ERROR", detail=str(exc))

        choices = payload.get("choices") or [{}]
        first = choices[0] if choices else {}
        message = first.get("message") or {}
        content = message.get("content") or ""
        # Reasoning spends the output budget without being the answer. Its size is the diagnosis of a
        # TRUNCATED row, so it is recorded; its text is not the reading and never enters the body.
        reasoning = message.get("reasoning_content") or ""
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
            detail=f"reasoning_chars={len(reasoning)}" if reasoning else "",
            # Two messages went out; the echo check compares one string, and this is that string.
            prompt_sent=rendered_prompt(request["system"], request["user"]),
        )
```

- [ ] **Step 4: Run the tests and confirm they pass.**

Run: `.venv/bin/pytest -q tests/test_runner_llamacpp.py tests/test_runners_contract.py`
Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
git add claimstone/runners/llamacpp.py tests/test_runner_llamacpp.py
git commit -m "feat: llama.cpp runner takes an endpoint, a reasoning switch and an imposed schema"
```

### Task 2: an unsupported option is a usage error, and `model-run --endpoint`

**Files:**
- Modify: `claimstone/runners/__init__.py` (`build`)
- Modify: `claimstone/cli.py` (`_model_run`, and the `model-run` parser near line 1127)
- Test: `tests/test_cli_model.py`

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_cli_model.py`:

```python
def test_an_option_a_backend_does_not_take_is_a_sentence_not_a_traceback():
    from claimstone import runners

    with pytest.raises(ValueError, match="does not accept 'think'"):
        runners.build("claude-cli", model="m", think=False)


def test_llamacpp_accepts_reasoning_and_schema_flags():
    from claimstone import runners

    built = runners.build("llamacpp", think=False, enforce_schema=True,
                          endpoint="http://127.0.0.1:18081/v1/chat/completions")
    assert built.harness_version() == \
        "llamacpp/http://127.0.0.1:18081/v1/chat/completions think=off format=schema"


def test_model_run_passes_the_endpoint(tmp_path, monkeypatch):
    from claimstone import runners
    from tests.fakes import FakeRunner

    seen = {}

    def build(name, **kw):
        seen.update(kw)
        return FakeRunner()

    monkeypatch.setattr(runners, "build", build)
    main(["model-run", "projects/example-news-and-returns", "extract", "--batch", "b1",
          "--backend", "llamacpp", "--endpoint", "http://x/v1/chat/completions",
          "--store", str(tmp_path)])
    assert seen["endpoint"] == "http://x/v1/chat/completions"
```

- [ ] **Step 2: Run them and confirm they fail.**

Run: `.venv/bin/pytest -q tests/test_cli_model.py`
Expected: the first fails with a `TypeError`, the second with a `TypeError`, and the third
because argparse does not recognise `--endpoint`.

- [ ] **Step 3: Implement.** In `claimstone/runners/__init__.py`, add `import re` at the top and
replace the last line of `build` (`return factories[name](**kwargs)`) with:

```python
    try:
        return factories[name](**kwargs)
    except TypeError as exc:
        # A flag one backend honours and another has no field for. Saying which is a usage error;
        # a constructor traceback is not.
        found = re.search(r"unexpected keyword argument '(\w+)'", str(exc))
        if found is None:
            raise
        raise ValueError(f"backend {name!r} does not accept {found.group(1)!r}") from None
```

In `claimstone/cli.py` `_model_run`, after `extra["enforce_schema"] = True`, add:

```python
    if args.endpoint:
        extra["endpoint"] = args.endpoint
```

In the `model-run` parser, after the `--model` argument, add:

```python
            command.add_argument("--endpoint",
                                 help="the backend's URL, for a server the operator runs; "
                                      "llamacpp also reads CLAIMSTONE_LLAMACPP_URL")
```

- [ ] **Step 4: Run the tests and confirm they pass.**

Run: `.venv/bin/pytest -q tests/test_cli_model.py tests/test_runner_llamacpp.py`
Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
git add claimstone/runners/__init__.py claimstone/cli.py tests/test_cli_model.py
git commit -m "fix: an option a backend does not take is a usage error; model-run takes --endpoint"
```

### Task 3: shadow tool — `prepare` and the drift check

**Files:**
- Create: `tools/run_local_shadow.py`
- Test: `tests/test_run_local_shadow.py`

- [ ] **Step 1: Write the failing tests.** Create `tests/test_run_local_shadow.py`:

```python
"""The overnight shadow reads in its own store and never writes into the source."""
import json

import pytest

from claimstone import extract, model_call
from claimstone.runners.base import RawAnswer
from claimstone.store import Store
from tests.fakes import FakeRunner
from tests.test_run_calibration import RECORD, setup
from tools import run_local_shadow as shadow
from tools.replay_answers import files_snapshot


def answered(body):
    return RawAnswer(body=json.dumps(body).encode(), model="m",
                     usage={"input_tokens": 100, "output_tokens": 20})


def cloud_answered(project, origin):
    """The source batch as a cloud reader left it: answered and harvested."""
    cloud = FakeRunner(name="ollama-cloud", default=answered([RECORD]))
    list(model_call.drain(model_call.Queue(origin, lane="extract", batch="calibration"), cloud))
    extract.harvest(project, origin, batch="calibration")


def test_prepare_copies_requests_but_not_answers(tmp_path):
    project, origin, _ = setup(tmp_path)
    cloud_answered(project, origin)
    store = shadow.prepare(project, origin, lane="extract", batch="calibration",
                           root=tmp_path / "shadows")
    queue = model_call.Queue(store, lane="extract", batch="calibration")
    assert queue.requests()
    assert not store.path(queue.results_name).exists()
    assert not store.path("claims.jsonl").exists()
    assert store.path("chunks.jsonl").read_bytes() == origin.path("chunks.jsonl").read_bytes()


def test_a_moved_source_refuses_the_shadow(tmp_path):
    project, origin, _ = setup(tmp_path)
    shadow.prepare(project, origin, lane="extract", batch="calibration", root=tmp_path / "shadows")
    origin.append("chunks.jsonl", {"chunk_id": "late", "source_id": "X", "text": "new"})
    with pytest.raises(shadow.ShadowDrift):
        shadow.open_shadow(project, origin, lane="extract", batch="calibration",
                           root=tmp_path / "shadows")


def test_the_review_lane_is_refused_by_name(tmp_path):
    project, origin, _ = setup(tmp_path)
    with pytest.raises(ValueError, match="extract"):
        shadow.prepare(project, origin, lane="review", batch="x", root=tmp_path / "shadows")
```

- [ ] **Step 2: Run them and confirm they fail.**

Run: `.venv/bin/pytest -q tests/test_run_local_shadow.py`
Expected: `ModuleNotFoundError: tools.run_local_shadow`.

- [ ] **Step 3: Implement.** Create `tools/run_local_shadow.py`:

```python
#!/usr/bin/env python
"""Read an already-answered batch with the local server, overnight, in an isolated store.

A D13 measurement and nothing else. Harvest gates every backend's rows in a batch into
`claims.jsonl`, so a local reading in the production batch would reach the production ledger; the
shadow therefore has its own store, and the source store is opened read-only. No reader is adopted,
no lane is assigned and nothing is signed. D4's figures belong to another model and are not used.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claimstone import model_call
from claimstone.config import check_registry_drift, load_project
from claimstone.store import Store

DEFAULT_ROOT = "store/local-shadows"
COPIED = ("chunks.jsonl", "documents.jsonl", "registry.jsonl")
MANIFEST = "shadow.json"


class ShadowDrift(ValueError):
    """The source moved after `prepare`: the comparison would be against a different batch."""


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _check_lane(lane: str) -> None:
    if lane != "extract":
        raise ValueError(f"lane {lane!r}: the shadow reads the extract lane only, for now")


def _sources(origin: Store, lane: str, batch: str) -> dict[str, str | None]:
    queue = model_call.Queue(origin, lane=lane, batch=batch)
    return {name: _sha256(origin.path(name)) for name in (*COPIED, queue.requests_name)}


def shadow_store(project, *, lane: str, batch: str, root) -> Store:
    return Store(project.name, base=Path(root) / lane / batch)


def prepare(project, origin: Store, *, lane: str, batch: str, root=DEFAULT_ROOT) -> Store:
    """Copy what harvest needs. Requests yes, answers no: the shadow's ledgers hold only its own."""
    _check_lane(lane)
    check_registry_drift(project, origin, record=False)
    store = shadow_store(project, lane=lane, batch=batch, root=root)
    if store.path(MANIFEST).exists():
        return open_shadow(project, origin, lane=lane, batch=batch, root=root)
    queue = model_call.Queue(origin, lane=lane, batch=batch)
    if not queue.requests():
        raise ValueError(f"no requests in {queue.requests_name}")
    for name in (*COPIED, queue.requests_name):
        if origin.path(name).exists():
            store.path(name).parent.mkdir(parents=True, exist_ok=True)
            store.path(name).write_bytes(origin.path(name).read_bytes())
    store.path(MANIFEST).write_text(json.dumps({
        "source_store": str(origin.root), "lane": lane, "batch": batch,
        "prepared_at": model_call._now(), "sources_sha256": _sources(origin, lane, batch),
    }, indent=2) + "\n")
    check_registry_drift(project, store)
    return store


def open_shadow(project, origin: Store, *, lane: str, batch: str, root=DEFAULT_ROOT) -> Store:
    _check_lane(lane)
    store = shadow_store(project, lane=lane, batch=batch, root=root)
    if not store.path(MANIFEST).exists():
        raise ValueError(f"no shadow at {store.root}: run prepare first")
    frozen = json.loads(store.path(MANIFEST).read_text())["sources_sha256"]
    moved = sorted(name for name, digest in _sources(origin, lane, batch).items()
                   if frozen.get(name) != digest)
    if moved:
        raise ShadowDrift(f"source changed since prepare: {', '.join(moved)}")
    check_registry_drift(project, store)
    return store
```

- [ ] **Step 4: Run the tests and confirm they pass.**

Run: `.venv/bin/pytest -q tests/test_run_local_shadow.py`
Expected: 3 passed.

- [ ] **Step 5: Commit.**

```bash
git add tools/run_local_shadow.py tests/test_run_local_shadow.py
git commit -m "feat: prepare an isolated shadow store for a local reading"
```

### Task 4: shadow tool — `run` with server check, deadline and stop rules

**Files:**
- Modify: `tools/run_local_shadow.py`
- Test: `tests/test_run_local_shadow.py`

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_run_local_shadow.py`:

```python
class Local(FakeRunner):
    def __init__(self, **kw):
        super().__init__(name="llamacpp", **kw)
        self.model = "local"
        self.endpoint = "http://127.0.0.1:18081/v1/chat/completions"


def healthy(url, timeout):
    class Response:
        status_code = 200
        def json(self):
            return [{"is_processing": False}]
    return Response()


class Clock:
    def __init__(self, step_s):
        self.now, self.step = dt.datetime(2026, 10, 3, 23, 0), dt.timedelta(seconds=step_s)
    def __call__(self):
        current = self.now
        self.now += self.step
        return current


def prepared(tmp_path):
    project, origin, _ = setup(tmp_path)
    shadow.prepare(project, origin, lane="extract", batch="calibration", root=tmp_path / "shadows")
    return project, origin


def go(tmp_path, project, origin, runner, **kw):
    kw.setdefault("until", dt.datetime(2026, 10, 4, 7, 0))
    kw.setdefault("get", healthy)
    return shadow.run(project, origin, lane="extract", batch="calibration",
                      root=tmp_path / "shadows", runner=runner, **kw)


def test_a_run_drains_and_a_second_run_calls_nothing(tmp_path):
    project, origin = prepared(tmp_path)
    local = Local(default=answered([RECORD]))
    first = go(tmp_path, project, origin, local)
    assert first["stop"] == "DRAINED" and first["calls"] == len(local.calls) > 0
    again = Local(default=answered([RECORD]))
    assert go(tmp_path, project, origin, again)["calls"] == 0 and again.calls == []


def test_a_run_stops_before_a_call_that_would_end_past_the_deadline(tmp_path, monkeypatch):
    project, origin = prepared(tmp_path)
    monkeypatch.setattr(model_call, "_now", lambda: "2026-10-03T23:00:00+00:00")
    local = Local(default=answered([RECORD]))
    result = go(tmp_path, project, origin, local, until=dt.datetime(2026, 10, 3, 23, 0, 30),
                now=Clock(step_s=20), mean_s=lambda rows: 20.0)
    assert result["stop"] == "STOPPED_DEADLINE"
    assert result["calls"] == 1


def test_an_unavailable_server_gets_no_call(tmp_path):
    project, origin = prepared(tmp_path)
    def down(url, timeout):
        raise OSError("refused")
    local = Local(default=answered([RECORD]))
    assert go(tmp_path, project, origin, local, get=down)["stop"] == "STOPPED_SERVER"
    assert local.calls == []


def test_a_busy_server_gets_no_call(tmp_path):
    project, origin = prepared(tmp_path)
    def busy(url, timeout):
        class Response:
            status_code = 200
            def json(self):
                return [{"is_processing": True}]
        return Response()
    local = Local(default=answered([RECORD]))
    assert go(tmp_path, project, origin, local, get=busy)["stop"] == "STOPPED_SERVER"
    assert local.calls == []


def test_three_backend_errors_in_a_row_stop_the_night(tmp_path):
    project, origin = prepared(tmp_path)
    local = Local(default=RawAnswer(failure_class="BACKEND_ERROR", detail="down"))
    result = go(tmp_path, project, origin, local)
    assert result["stop"] == "STOPPED_BACKEND" and len(local.calls) == 3


def test_every_run_is_recorded(tmp_path):
    project, origin = prepared(tmp_path)
    go(tmp_path, project, origin, Local(default=answered([RECORD])))
    store = shadow.shadow_store(project, lane="extract", batch="calibration", root=tmp_path / "shadows")
    rows = list(store.read("runs.jsonl"))
    assert rows[-1]["stop"] == "DRAINED" and rows[-1]["harness_version"] == "fake/1"
```

Also add `import datetime as dt` at the top of the test file.

- [ ] **Step 2: Run them and confirm they fail.**

Run: `.venv/bin/pytest -q tests/test_run_local_shadow.py`
Expected: the new tests fail with `AttributeError: module ... has no attribute 'run'`.

- [ ] **Step 3: Implement.** Append to `tools/run_local_shadow.py`:

```python
def _default_get():
    import requests

    return requests.get


def server_state(endpoint: str, *, get=None) -> tuple[bool, str]:
    """Up and idle, or why not. A night of BACKEND_ERROR rows is not a measurement."""
    get = get or _default_get()
    base = endpoint.split("/v1/")[0]
    try:
        health = get(f"{base}/health", timeout=10)
    except Exception as exc:
        return False, f"health: {exc}"
    if getattr(health, "status_code", 0) != 200:
        return False, f"health: status {getattr(health, 'status_code', 0)}"
    try:
        slots = get(f"{base}/slots", timeout=10)
        if getattr(slots, "status_code", 0) == 200 and any(
                slot.get("is_processing") for slot in slots.json()):
            return False, "a slot is processing: the server is in use"
    except Exception as exc:
        # The slots endpoint can be disabled on the server. Health passed, so say so and go on.
        return True, f"slots unknown: {exc}"
    return True, "idle"


def _mean_s(rows: list[dict]) -> float:
    return sum(float(row.get("latency_s") or 0) for row in rows) / len(rows)


def run(project, origin: Store, *, lane: str, batch: str, root=DEFAULT_ROOT, runner,
        until: dt.datetime, retry_classes: frozenset[str] = frozenset(), limit: int | None = None,
        get=None, now=dt.datetime.now, mean_s=_mean_s) -> dict:
    """Drain one call at a time, so the deadline is checked between calls and never mid-call."""
    store = open_shadow(project, origin, lane=lane, batch=batch, root=root)
    queue = model_call.Queue(store, lane=lane, batch=batch)
    record = {"started_at": model_call._now(), "until": until.isoformat(),
              "harness_version": runner.harness_version(), "calls": 0, "stop": "DRAINED"}
    up, why = server_state(getattr(runner, "endpoint", ""), get=get)
    record["server"] = why
    rows: list[dict] = []
    attempts_here: dict[str, int] = {}
    backend_errors = 0
    if not up:
        record["stop"] = "STOPPED_SERVER"
    while up:
        if limit is not None and len(rows) >= limit:
            record["stop"] = "STOPPED_LIMIT"
            break
        # No estimate before the first call: it always goes, unless the deadline already passed.
        expected = dt.timedelta(seconds=mean_s(rows)) if rows else dt.timedelta(0)
        if now() + expected > until:
            record["stop"] = "STOPPED_DEADLINE"
            break
        drained = list(model_call.drain(queue, runner, limit=1, retry_classes=retry_classes))
        if not drained:
            break
        row = drained[0]
        rows.append(row)
        backend_errors = backend_errors + 1 if row.get("failure_class") == "BACKEND_ERROR" else 0
        if backend_errors >= 3:
            record["stop"] = "STOPPED_BACKEND"
            break
        # A transient class, or a reopened terminal one, stays first in `pending`: without this the
        # same unit would be asked all night.
        attempts_here[row["call_id"]] = attempts_here.get(row["call_id"], 0) + 1
        if attempts_here[row["call_id"]] >= 3:
            record["stop"] = "STOPPED_REPEATING"
            break
    record.update(calls=len(rows), finished_at=model_call._now(),
                  ok=sum(1 for row in rows if row.get("ok")))
    store.append("runs.jsonl", record)
    return record
```

- [ ] **Step 4: Run the tests and confirm they pass.**

Run: `.venv/bin/pytest -q tests/test_run_local_shadow.py`
Expected: all pass. The deadline test: the first call goes at 23:00:00. At the second check the
clock reads 23:00:20, and adding the 20 s mean gives 23:00:40, which is past 23:00:30. The run
stops with `calls == 1`.

- [ ] **Step 5: Commit.**

```bash
git add tools/run_local_shadow.py tests/test_run_local_shadow.py
git commit -m "feat: shadow run checks the server, stops at a deadline and on repeated failure"
```

### Task 5: shadow tool — `report` and the command line

**Files:**
- Modify: `tools/run_local_shadow.py`
- Test: `tests/test_run_local_shadow.py`

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_run_local_shadow.py`:

```python
def test_report_compares_readers_and_leaves_the_source_untouched(tmp_path):
    project, origin, _ = setup(tmp_path)
    cloud_answered(project, origin)
    before = files_snapshot(origin)
    shadow.prepare(project, origin, lane="extract", batch="calibration", root=tmp_path / "shadows")
    go(tmp_path, project, origin, Local(default=answered([RECORD])))
    result = shadow.report(project, origin, lane="extract", batch="calibration",
                           root=tmp_path / "shadows")
    assert files_snapshot(origin) == before
    local, cloud = result["readers"]["llamacpp/local"], result["readers"]["ollama-cloud/m"]
    assert local["calls"] == cloud["calls"] > 0
    assert local["accepted"] == cloud["accepted"] > 0
    agreement = result["agreement"]["ollama-cloud/m"]
    assert agreement["only_local"] == agreement["only_other"] == 0
    assert agreement["local_claims_with_overlapping_quote"] == local["accepted"]
    assert "not measured" in result["caveat"]
    assert "llamacpp/local" in shadow.format_report(result)


def test_the_command_line_prepares_and_reports(tmp_path, capsys):
    project, origin, _ = setup(tmp_path)
    args = ["--store", str(origin.root.parent), "--root", str(tmp_path / "shadows"),
            "--batch", "calibration"]
    assert shadow.main(["prepare", str(project.root), *args]) == 0
    assert shadow.main(["report", str(project.root), *args, "--json"]) == 0
    assert "readers" in json.loads(capsys.readouterr().out.splitlines()[-1])
```

> **Check before Step 1:** `tests/test_synthesize._project` must return an object with a `.root`
> path that `load_project` accepts. If it does not, write the project to `tmp_path` the way
> `test_run_calibration.py:113-116` does and pass that path instead.

- [ ] **Step 2: Run them and confirm they fail.**

Run: `.venv/bin/pytest -q tests/test_run_local_shadow.py`
Expected: `AttributeError: ... 'report'`.

- [ ] **Step 3: Implement.** Append to `tools/run_local_shadow.py`:

```python
import difflib
import statistics
from collections import Counter

from claimstone import extract

CAVEAT = ("Counts, not a score. Which reader is right on a disagreement is not measured: "
          "there is no human reference for this batch.")


def _reader(row: dict) -> str:
    return f"{row.get('backend')}/{row.get('model') or ''}"


def _overlaps(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    match = difflib.SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
    return match.size >= 40


def _calls(rows: list[dict]) -> dict:
    latencies = [float(r.get("latency_s") or 0) for r in rows]
    seconds = sum(latencies)
    tokens_in = sum(int((r.get("usage") or {}).get("input_tokens", 0)) for r in rows)
    tokens_out = sum(int((r.get("usage") or {}).get("output_tokens", 0)) for r in rows)
    return {
        "calls": len(rows), "ok": sum(1 for r in rows if r.get("ok")),
        "failures": dict(Counter(r["failure_class"] for r in rows if r.get("failure_class"))),
        "calls_per_hour": round(len(rows) / seconds * 3600, 2) if seconds else None,
        "median_s_per_call": round(statistics.median(latencies), 1) if latencies else None,
        "input_tokens_per_s": round(tokens_in / seconds, 1) if seconds else None,
        "output_tokens_per_s": round(tokens_out / seconds, 1) if seconds else None,
        "models_reported": sorted({str(r.get("model_reported") or "") for r in rows}),
    }


def report(project, origin: Store, *, lane: str, batch: str, root=DEFAULT_ROOT) -> dict:
    store = open_shadow(project, origin, lane=lane, batch=batch, root=root)
    harvested = extract.harvest(project, store, batch=batch)
    ids = {u["call_id"] for u in model_call.Queue(store, lane=lane, batch=batch).requests()}

    results = list(model_call.Queue(store, lane=lane, batch=batch).results().values())
    results += [row for row in model_call.Queue(origin, lane=lane, batch=batch).results().values()
                if row.get("backend") != "llamacpp" and row["call_id"] in ids]
    claims = list(store.latest_by("claims.jsonl", "claim_id").values())
    claims += [row for row in origin.latest_by("claims.jsonl", "claim_id").values()
               if row.get("backend") != "llamacpp" and row.get("call_id") in ids]
    rejected = list(store.latest_by("rejections.jsonl", "claim_id").values())
    rejected += [row for row in origin.latest_by("rejections.jsonl", "claim_id").values()
                 if row.get("backend") != "llamacpp" and row.get("call_id") in ids]

    readers: dict[str, dict] = {}
    for name in sorted({_reader(r) for r in results}):
        mine = [c for c in claims if _reader(c) == name]
        refused = [r for r in rejected if _reader(r) == name]
        readers[name] = _calls([r for r in results if _reader(r) == name]) | {
            "accepted": len(mine), "rejected": len(refused),
            "rejection_reasons": dict(Counter(str(r.get("failure")) for r in refused)),
        }

    local_name = next((n for n in readers if n.startswith("llamacpp/")), None)
    agreement: dict[str, dict] = {}
    if local_name:
        local = [c for c in claims if _reader(c) == local_name]
        local_units = {c["call_id"] for c in local}
        for name in readers:
            if name == local_name:
                continue
            other = [c for c in claims if _reader(c) == name]
            other_units = {c["call_id"] for c in other}
            agreement[name] = {
                "both": len(local_units & other_units),
                "only_local": len(local_units - other_units),
                "only_other": len(other_units - local_units),
                "neither": len(ids - local_units - other_units),
                "local_claims_with_overlapping_quote": sum(
                    1 for c in local if any(o.get("chunk_id") == c.get("chunk_id")
                                            and _overlaps(c.get("evidence_quote", ""),
                                                          o.get("evidence_quote", ""))
                                            for o in other)),
            }
    return {"batch": batch, "units": len(ids), "harvest": harvested, "readers": readers,
            "agreement": agreement, "local_reader": local_name, "caveat": CAVEAT}


def format_report(result: dict) -> str:
    lines = [f"batch {result['batch']}: {result['units']} units"]
    for name, r in result["readers"].items():
        lines.append(
            f"  {name:<34} calls {r['ok']}/{r['calls']}  {r['calls_per_hour']} calls/h  "
            f"median {r['median_s_per_call']}s  in {r['input_tokens_per_s']} tok/s  "
            f"out {r['output_tokens_per_s']} tok/s  accepted {r['accepted']}  rejected {r['rejected']}")
        if r["failures"]:
            lines.append("    failures: " + ", ".join(f"{k} {v}" for k, v in r["failures"].items()))
        if r["rejection_reasons"]:
            lines.append("    gate: " + ", ".join(f"{k} {v}" for k, v in r["rejection_reasons"].items()))
    for name, a in result["agreement"].items():
        lines.append(f"  units with accepted claims vs {name}: both {a['both']}, only local "
                     f"{a['only_local']}, only other {a['only_other']}, neither {a['neither']}; "
                     f"local claims with an overlapping quote {a['local_claims_with_overlapping_quote']}")
    lines.append(f"\n  {result['caveat']}")
    return "\n".join(lines)


def _until(text: str, now=dt.datetime.now) -> dt.datetime:
    hour, minute = (int(part) for part in text.split(":"))
    current = now()
    target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target if target > current else target + dt.timedelta(days=1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("prepare", "run", "report"))
    parser.add_argument("project")
    parser.add_argument("--batch", required=True)
    parser.add_argument("--lane", default="extract")
    parser.add_argument("--store", default="store")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--until", help="HH:MM local time; required for run")
    parser.add_argument("--endpoint")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retry-class", action="append", default=[])
    parser.add_argument("--enforce-schema", action="store_true")
    parser.add_argument("--json", action="store_true")
    thinking = parser.add_mutually_exclusive_group()
    thinking.add_argument("--think", dest="think", action="store_true", default=None)
    thinking.add_argument("--no-think", dest="think", action="store_false")
    args = parser.parse_args(argv)

    project = load_project(args.project)
    origin = Store(project.name, base=args.store)
    try:
        if args.command == "prepare":
            store = prepare(project, origin, lane=args.lane, batch=args.batch, root=args.root)
            print(f"shadow ready: {store.root}")
        elif args.command == "run":
            if not args.until:
                parser.error("run needs --until HH:MM")
            from claimstone import runners

            options = {"think": args.think, "enforce_schema": args.enforce_schema}
            if args.endpoint:
                options["endpoint"] = args.endpoint
            record = run(project, origin, lane=args.lane, batch=args.batch, root=args.root,
                         runner=runners.build("llamacpp", **options), until=_until(args.until),
                         retry_classes=frozenset(args.retry_class), limit=args.limit)
            print(json.dumps(record))
        else:
            result = report(project, origin, lane=args.lane, batch=args.batch, root=args.root)
            print(json.dumps(result) if args.json else format_report(result))
    except (ValueError, ShadowDrift) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Move the new imports (`difflib`, `statistics`, `Counter`, `extract`) up into the module's import
block. Keep them in the order the repository already uses.

- [ ] **Step 4: Run the tests and confirm they pass.**

Run: `.venv/bin/pytest -q tests/test_run_local_shadow.py`
Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
git add tools/run_local_shadow.py tests/test_run_local_shadow.py
git commit -m "feat: shadow report compares the local reader with the cloud readers"
```

### Task 6: documentation and full verification

**Files:**
- Modify: `docs/GUIDE.md` (after the extract section, near line 125)
- Modify: `.env.example`
- Modify: `docs/superpowers/specs/2026-10-03-local-shadow-design.md` (status, path, lane scope)

- [ ] **Step 1: Add to `docs/GUIDE.md`.**

````markdown
### Overnight local shadow

The local `llama.cpp` server costs no cloud tokens and is slow, so it reads at night. It reads a
batch a cloud reader has already answered, **in its own store**: harvest takes every backend's
rows in a batch, so a local reading inside the production batch would reach the production
ledger.

```bash
python tools/run_local_shadow.py prepare projects/<name> --batch <batch>
systemd-run --user --on-calendar='*-*-* 23:30' \
    .venv/bin/python tools/run_local_shadow.py run projects/<name> --batch <batch> \
    --until 07:00 --endpoint http://127.0.0.1:18081/v1/chat/completions --no-think --enforce-schema
python tools/run_local_shadow.py report projects/<name> --batch <batch>
```

`run` makes no call if the server is down or busy. It stops before a call that would end after
`--until`, after three backend errors in a row, or when one unit fails three times. It resumes by
`call_id`. The report shows counts per reader and agreement per unit. It is a D13 measurement,
not an adoption, and D4's figures belong to another model.
````

- [ ] **Step 2: Add to `.env.example`** after `OLLAMA_API_KEY=`:

```
# Optional. The llamacpp runner's URL; default http://127.0.0.1:8080/v1/chat/completions.
CLAIMSTONE_LLAMACPP_URL=
```

- [ ] **Step 3: Update the spec.**
  - Set the status line to `Status: implemented (extract lane); review lane deferred`.
  - Change the shadow path to `store/local-shadows/<lane>/<batch>/<project>/`.

- [ ] **Step 4: Run the full suite and validation.**

Run: `.venv/bin/pytest -q && .venv/bin/claimstone validate --all-projects`
Expected: all pass. Compare the failure count with the baseline taken before Task 1, because
uncommitted work exists in the tree.

- [ ] **Step 5: Commit.**

```bash
git add docs/GUIDE.md .env.example docs/superpowers/specs/2026-10-03-local-shadow-design.md
git commit -m "docs: overnight local shadow"
```

### Task 7: first real night (operator)

- [ ] Wait until `curl -s http://127.0.0.1:18081/health` returns `{"status":"ok"}`.
- [ ] Prepare the shadow:

```bash
.venv/bin/python tools/run_local_shadow.py prepare projects/alembic-s4-lungo \
    --batch s4-taratura-v1-2026-09-28
```

- [ ] Smoke test before the night with `run ... --until <now+1h> --limit 1 --no-think --enforce-schema`.
- [ ] Check the result with `report`. If the row is `BACKEND_ERROR` with a schema reason, drop
  `--enforce-schema` and record the reason.
- [ ] Schedule the overnight `run` with `systemd-run --user`.
- [ ] In the morning run `report`. Record the figures as a D-entry only if the operator decides to.
