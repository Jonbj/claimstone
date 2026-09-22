# `model_call` — design

Date: 2026-09-22 · Scope: the boundary between a stage and a model · Status: approved, not implemented

Required by D13. Consumed by stage 4 (extract) and stage 5 (review); specified before either,
because it is their contract.

## 1. What this is

A stage that needs a model **writes work units to JSONL and reads results from JSONL**. It does
not open a socket, import a vendor SDK, or know which backend answered. A *runner* is a separate
process that drains the queue.

```
store/<project>/calls/<lane>/<batch>/requests.jsonl    written by the stage
store/<project>/calls/<lane>/<batch>/results.jsonl     written by a runner, append-only
store/<project>/calls/<lane>/<batch>/raw/<sha256>      the response bytes, content-addressed
```

`lane` is `extract` or `review`. `batch` is a timestamp plus the registry version, so a batch is
identifiable after the fact without reading it.

## 2. What it is not

**One prompt, one structured answer.** No agentic loop, no tools, no multi-turn, no retrieval
inside the call. That is not a limitation imposed by the boundary; it is the call shape the work
actually has — the question registry plus one chunk in, a short JSON array of claims out. A
boundary that supported conversations would be a boundary nobody could swap backends across.

Not a scheduler either. A runner drains a queue and stops.

## 3. Honesty about reproducibility

**A model call is not reproducible. It is auditable.** These are different claims and the
distinction is the whole reason the schema looks the way it does.

What cannot be promised: that the same prompt yields the same answer. Sampling, model updates,
and a CLI's own harness all break that, and no amount of recording fixes it.

What is promised, and mechanically checked: **this exact prompt was sent, this exact response
came back, and here is the hash of each.** A result whose echoed `prompt_sha256` does not match
the request is rejected — the analogue of the quote gate one stage later, and it catches a runner
that truncated, reordered or templated over the prompt it was given.

## 4. The work unit

```json
{"call_id": "9f2a…",
 "lane": "extract",
 "schema_version": 1,
 "registry_version": 2,
 "system": "…the question registry and the instructions…",
 "user": "…the chunk…",
 "response_schema": {"type": "array", "items": {"…": "…"}},
 "max_output_tokens": 800,
 "source_id": "S07", "chunk_id": "S07#4",
 "prompt_sha256": "…",
 "created_at": "2026-09-22T11:04:00+00:00"}
```

Three fields carry design decisions:

**`system` and `user` are separate.** The stable prefix — registry plus instructions, identical
across every call in a lane — is in `system`; the volatile part is in `user`. This is what makes
prompt caching possible on backends that price cached input separately (Ollama Cloud charges
$0.006 against $0.30 per MTok, fifty-fold), and it puts the cacheability in the *file* rather
than in a runner's cleverness. A runner that ignores the split still works; it just pays more.

**`call_id` is derived, not assigned:** `sha256(lane | schema_version | prompt_sha256)`. So the
same work unit produced twice is the same unit, a batch is resumable by skipping `call_id`s
already answered, and — the point — **two backends can drain the same `requests.jsonl` into two
`results.jsonl` files and their answers line up per `call_id`.** That is the comparison
primitive D13 exists to preserve; without a content-derived id, comparing backends means
trusting that two runs saw the same inputs.

**`response_schema` travels with the request.** The validator is not a property of the runner,
so every backend is held to the same shape and a schema change is visible in the queue.

## 5. The result

```json
{"call_id": "9f2a…",
 "ok": true,
 "backend": "ollama-cloud", "model": "…", "harness_version": "ollama/0.32.0",
 "prompt_sha256": "…",
 "output": [{"question_id": "Q07", "claim": "…", "evidence_quote": "…"}],
 "raw_sha256": "…", "raw_path": "store/…/raw/…",
 "usage": {"input_tokens": 3841, "cached_input_tokens": 1602, "output_tokens": 412},
 "cost_usd": 0.0018,
 "latency_s": 3.2,
 "started_at": "…", "finished_at": "…",
 "failure_class": null}
```

Rules:

1. **Raw response bytes are always stored**, valid or not, content-addressed. Same reason a
   gate-rejected landing page keeps its bytes: without them the answer cannot be re-parsed,
   re-audited, or diffed against another backend's.
2. **A malformed output is a recorded failure, never a default.** `ok: false` with a
   `failure_class`; no empty array standing in for "the model said nothing usable". A silently
   defaulted result is a claim that a chunk contained nothing, which is a scientific assertion
   the runner is not entitled to make.
3. **`cost_usd` may be `null`, and `null` means "not priced", not "free".** A subscription-backed
   CLI has no per-call price. Rendering that as 0.0 would make a cost report add up to a number
   that is not true.
4. **`harness_version` is mandatory.** A CLI inserts its own system prompt, tools and context
   management between the prompt and the model, and that changes with its version. Without this
   field the ledger records "we asked Claude Code", which is not a description of an experiment.
5. **The echoed `prompt_sha256` is verified** against the request before the row is accepted
   (§3). A mismatch is `PROMPT_MISMATCH` and the row is a failure, whatever the output looks like.

### Failure classes

`NOT_JSON` · `SCHEMA_INVALID` · `TRUNCATED` (the output cap was hit — a partial answer is not a
short answer) · `REFUSED` · `EMPTY` · `PROMPT_MISMATCH` · `BACKEND_ERROR` · `TIMEOUT` ·
`RATE_LIMITED`

Terminal and transient split as in stage 2: `NOT_JSON`, `SCHEMA_INVALID`, `REFUSED` and
`PROMPT_MISMATCH` are terminal for that backend; `TIMEOUT`, `RATE_LIMITED`, `BACKEND_ERROR` and
`EMPTY` are transient. `TRUNCATED` is terminal until `max_output_tokens` changes, which changes
`call_id` — so a retry under a bigger cap is honestly a different call.

## 6. Runners

One module per backend, and **the only place in the repository that knows a vendor exists**.

| runner | shape | concurrency |
|---|---|---|
| `runners/llamacpp.py` | HTTP to the local server | 1 |
| `runners/ollama_cloud.py` | HTTPS with an API key; `requests`, already a dependency | modest, declared |
| `runners/cli.py` | subprocess: `claude -p --output-format json --model M`, `codex exec`, `opencode run` | 1 |

Each exposes `run(request) -> result` and declares `max_concurrency` and `min_interval_s`.
Subscription-backed CLI runners get concurrency 1 and a floor on the interval: an interactive
plan is not batch infrastructure, and a high-volume lane belongs on a backend priced per token.

`claimstone model-run <project> <lane> --backend NAME [--limit N] [--resume]` drains a queue.
It is a separate command from the stage that filled it, deliberately: the stage finishes and
exits, and a run that takes hours can be interrupted, resumed, or pointed at a different backend
without the stage re-running.

**No runner is the default.** Which backend serves a lane is a finding, not a design decision
(D13), so the flag is required and the choice is recorded on every row.

## 7. Cost and throughput reporting

`claimstone model-report <project> <lane>` sums `usage` and `cost_usd` per backend and model, and
reports calls/hour observed. Two rules: a `null` cost is reported as unpriced rather than folded
into a total, and throughput is stated per backend — the rates differ by orders of magnitude
(~5 calls/hour locally against an afternoon for the same queue on a hosted endpoint), so an
aggregate figure would describe nothing.

## 8. Testing

Offline. A `FakeRunner` answers from a dictionary keyed by `call_id`.

| file | covers |
|---|---|
| `test_model_call.py` | `call_id` determinism; the same unit produced twice is one unit; `prompt_sha256` mismatch is rejected; schema validation failure is recorded not defaulted; a truncated output is `TRUNCATED` and not a short answer; `cost_usd: null` survives the round trip |
| `test_runner_cli.py` | the subprocess is invoked with the expected argv; a non-zero exit is `BACKEND_ERROR`; stdout that is not JSON is `NOT_JSON`; `harness_version` is captured from the tool's own `--version` |
| `test_model_report.py` | unpriced calls are not summed into a total; throughput is per backend |

No test invokes a real backend. A live smoke test per runner lives behind
`CLAIMSTONE_LIVE=1`, as in stage 2.

## 9. Out of scope

No agentic loops, tools, or multi-turn (§2). No streaming — the outputs are short by
construction. No automatic backend selection or fallback chain: a lane's backend is chosen by a
human on evidence and recorded, and a runner that silently failed over would destroy the one
property the boundary exists for, which is knowing which model produced which claim.

`model-compare`, which would diff two `results.jsonl` files per `call_id`, is what §4's derived
`call_id` makes possible and is not specified here. It gets written when there are two results
files to compare.
