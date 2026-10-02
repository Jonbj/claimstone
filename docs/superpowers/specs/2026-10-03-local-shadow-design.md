# Overnight local shadow reader

Date: 2026-10-03 · Status: approved design, not implemented

## Purpose

The local `llama.cpp` server costs no cloud tokens. At night it reads a batch that a cloud reader
has already answered, in an **isolated store**, so that by morning there is a measurement:
FlashNext's throughput, how many of its answers are valid, what the claim gate accepts, and how
far it agrees with the cloud reader on the same units.

This is a D13 measurement. It does not adopt a reader, assign a lane, write into a production
store, or produce a verdict. The result becomes an entry in `DESIGN_DECISIONS.md` only if the
operator records it.

D4's figures (11.6 min per call, ~2 claims per call) were measured on another model at Q8_0 and
are not inherited here. The first report measures FlashNext from scratch.

First target: `alembic-s4-lungo`, extract batch `s4-taratura-v1-2026-09-28`, with 40 units that
are already answered and reviewed in the cloud.

## Why isolation is required

`extract.harvest` gates **every** result row in the batch into `claims.jsonl`, whatever its
backend. A local run in the production batch would put local claims into the production ledger
on the next harvest. The shadow therefore runs in its own store, following the pattern of
`tools/run_prompt_comparison.py`.

## 1. Runner: `claimstone/runners/llamacpp.py`

- `endpoint` is configurable. The order is: the `--endpoint` option on `model-run`, then
  `CLAIMSTONE_LLAMACPP_URL`, then the existing default. The endpoint is already part of
  `harness_version`.
- `think: bool | None`. Setting it to `False` sends `chat_template_kwargs: {"enable_thinking": false}`
  and `True` sends `true`. When it is `None`, nothing is sent.
- `enforce_schema: bool`. When set, the request schema is sent as
  `response_format: {"type": "json_object", "schema": ...}`. llama-server turns that into a
  grammar, so the shape is imposed rather than requested. `harness_version` records it, as
  `ollama_cloud` already does with `shape`.
- `reasoning_content` from the response is never part of the answer body. Its length is recorded
  in `detail`, so truncation caused by reasoning can be diagnosed.
- `runners.build` validates kwargs against the factory. Any option a backend does not accept
  raises `ValueError` with a sentence, so the CLI prints a usage error and exits 2 instead of
  showing a `TypeError` traceback.

## 2. Tool: `tools/run_local_shadow.py`

All three subcommands take `--project`, `--lane` and `--batch`. The shadow root is
`store/local-shadows/<project>/<lane>/<batch>/`, which is gitignored like `store/`.

**`prepare`.** This creates the shadow store and copies in only what harvest needs:
- the batch's `requests.jsonl`, but not its `results.jsonl`;
- `chunks.jsonl`, `documents.jsonl` and `registry.jsonl`.

`claims.jsonl` and `rejections.jsonl` start empty, so everything harvested in the shadow comes
from the local reader. The step writes `shadow.json` with the source store path and the SHA256
of every copied file. If `shadow.json` already exists and the source hashes have changed, the
step refuses to continue: a moved source makes the comparison meaningless. It never writes to the
source store.

**`run --until HH:MM [--endpoint URL] [--no-think] [--enforce-schema] [--limit N]`.**
1. Before doing anything, it checks that `/health` returns 200 and that no slot is processing.
   If either check fails, it exits with a stated reason and makes no call.
2. It drains the shadow queue through the normal `model_call` path, with `backend=llamacpp`
   and `max_concurrency=1`.
3. Before starting each call it estimates when that call would finish: the mean duration of the
   calls already made in this run, or, before the first call, no estimate (so the first call
   always goes ahead). If the estimate is past `--until`, it stops with `STOPPED_DEADLINE`.
4. It is resumable by `call_id` through the existing queue logic. Nothing is retried unless
   `--retry-class` names it.
5. It appends one line per run to `runs.jsonl`: start, stop, stop reason, calls made, and
   `harness_version`.

**`report [--json]`.**
1. Runs `extract.harvest`, or `review.harvest` for the review lane, on the shadow store only.
2. Reads the cloud results for the same `call_id`s from the source store, **read-only**, along
   with the claims and rejections those results produced.
3. Prints the following for the local reader:
   - calls made and calls pending;
   - calls per hour and the median seconds per call;
   - input and output tokens per second, taken from `usage`;
   - the count for each `failure_class`, including `TRUNCATED` and `SCHEMA_INVALID`;
   - claims proposed, accepted and rejected by the gate, with rejection reasons.

   It prints the same figures for each cloud reader on the same units.
4. Prints agreement per unit: the units where both readers returned claims, where only one did,
   and where neither did; and how many accepted local claims share a chunk, and an overlapping
   evidence quote, with an accepted cloud claim.
5. Every count is labelled a count. The report says **which reader is right on a disagreement is
   not measured**: it has no human reference.

## 3. Overnight launch

The tool does not schedule itself. The operator uses
`systemd-run --user --on-calendar=<time> .venv/bin/python tools/run_local_shadow.py run ...`
or an equivalent timer, and runs `report` in the morning. The `/health` and slot checks keep the
run from colliding with other use of the local server. There is one writer per shadow store.

## 4. Error handling

- A connection failure or HTTP 5xx is recorded as `BACKEND_ERROR`, which is the existing runner
  behaviour. After three consecutive `BACKEND_ERROR`s, `run` stops with `STOPPED_BACKEND`, so a
  server that has gone down does not fill the night with failures.
- A failure is never swallowed and every attempt leaves a result row (CLAUDE.md conventions).
- A process killed mid-append leaves a partial final line, which `Store.read`/`Store.repair`
  already handle.

## 5. Tests

- Runner, with a fake `post`:
  - the endpoint comes from the option and from the environment;
  - `think=False` produces `chat_template_kwargs`;
  - `enforce_schema` produces `response_format`;
  - `reasoning_content` is excluded from the body;
  - `finish_reason=length` sets `truncated`.
- `runners.build`: an unknown kwarg raises `ValueError`.
- CLI: `model-run --backend llamacpp --no-think` no longer raises.
- Tool, on a synthetic store:
  - **isolation**: after `prepare`, `run` and `report`, every file in the source store is
    byte-identical;
  - **resume**: a second `run` makes no call for units already answered;
  - **deadline**: with a fake clock and a fake runner, `run` stops at `--until` with
    `STOPPED_DEADLINE`;
  - **health**: if the server is unavailable or busy, no call is made;
  - **drift**: when a source file changes after `prepare`, the next command refuses to run.
