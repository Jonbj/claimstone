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
import re
import threading
from typing import Any

from claimstone.store import sha256_text

SCHEMA_VERSION = 1
RESULT_JUDGE_VERSION = 2

LANES = ("extract", "review")


def canonical(value: Any) -> str:
    """One byte string per value, whatever order the keys arrived in."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


PROMPT_SEPARATOR = "\n\n---\n\n"

# A body that is nothing but a fenced block. Measured on the first real batch: two calls on
# claude-cli returned exactly the asked-for shape, with 16 of 16 evidence quotes exact substrings of
# their chunk, and both were recorded NOT_JSON because the answer arrived inside a ```json fence the
# prompt had forbidden in as many words.
#
# Unwrapping it is not softening a verdict about the literature: the fence is a presentation habit of
# the harness, one envelope layer outside the answer, and the schema still judges what is inside.
# Narrow on purpose — prose *beside* the fence stays NOT_JSON, because a model saying something the
# schema cannot see must not have that something pass unread.
_FENCED = re.compile(r"\A\s*```[A-Za-z0-9_+-]*[ \t]*\r?\n(.*?)\r?\n?\s*```\s*\Z", re.S)


def unfence(body: str) -> str:
    """The contents of a body that is exactly one fenced block, or the body unchanged."""
    found = _FENCED.match(body)
    return found.group(1) if found else body


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


# Terminal for this backend: a retry changes nothing until the request or the backend does.
# Transient: the next drain should try again. TRUNCATED is terminal because raising the cap
# changes `call_id`, so a retry under a bigger cap is a different call and not a second
# attempt at this one.
TERMINAL = frozenset({"NOT_JSON", "SCHEMA_INVALID", "REFUSED", "PROMPT_MISMATCH",
                      "TRUNCATED", "MODEL_IDENTITY_MISMATCH"})
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
            # Refuse here, not when the answer arrives: a schema this validator cannot honour
            # is a mistake by the stage that wrote it, and it should fail where it was made.
            jsonshape.check_schema(unit["response_schema"])
            asker = {"source_id": unit.get("source_id"), "chunk_id": unit.get("chunk_id")}
            previous = held.get(unit["call_id"])
            if previous is None:
                row = {**unit, "asked_by": [asker]}
                if self.lane == 'review':
                    row['review_targets'] = [review_target(unit)]
                held[unit["call_id"]] = row
                self.store.append(self.requests_name, row)
                written += 1
                continue
            askers = list(previous.get("asked_by") or [])
            targets = list(previous.get('review_targets') or [review_target(previous)])
            target = review_target(unit)
            new_target = self.lane == 'review' and target not in targets
            if asker in askers and not new_target:
                continue
            row = {**previous, "asked_by": askers if asker in askers else askers + [asker]}
            if new_target:
                row['review_targets'] = targets + [target]
            held[unit["call_id"]] = row
            self.store.append(self.requests_name, row)
        return written

    def requests(self) -> list[dict[str, Any]]:
        """One row per call, the latest. Never the raw rows: merging an asker appends a row, and a
        drain reading raw rows would pay for the same call once per chunk that asked for it.
        """
        return list(self.store.latest_by(self.requests_name, "call_id").values())

    def request_rows(self) -> list[dict[str, Any]]:
        """Every row ever written, for auditing how a call's asker list grew."""
        return list(self.store.read(self.requests_name))

    def results(
        self, *, backend: str | None = None, model: str | None = None
    ) -> dict[str, dict[str, Any]]:
        """The latest result per call, **per reader** — and a reader is a (backend, model) pair.

        Collapsing on `call_id` alone was the first draft, and it destroyed the one property this
        whole boundary exists for: after backend A answered a batch, draining it with backend B
        produced nothing, because every call already looked done. Two backends over the same
        requests file is the comparison primitive — it cannot be defeated by the resumability
        logic.

        The **model** joined that key on trying to compare four models on one backend: `ollama-cloud` with
        deepseek and `ollama-cloud` with mistral shared a key, so the second found the batch answered and
        the first's rows vanished from the collapse. D30's claim is about comparing readers, and a reader is
        not a backend.
        """
        latest: dict[str, dict[str, Any]] = {}
        requests = {row['call_id']: row for row in self.requests()}
        origins = {}
        for row in self.store.read(self.results_name):
            if backend is not None and row.get("backend") != backend:
                continue
            if model is not None and str(row.get("model") or "") != model:
                continue
            # The row's own `result_key`, not a second derivation of it. Two places computing an identity
            # is two places to disagree, and they did: a reader with no declared model wrote a key ending in
            # an empty segment while this rebuilt one from the model the backend *reported*, so a drain
            # never saw its own answer and repeated every call.
            key = result_key(row)
            physical = (row.get('call_id'), row.get('backend'), row.get('model'),
                        row.get('attempt_no', 1), row.get('raw_sha256'))
            if 'rejudged_from' not in row:
                origins[physical] = row
            elif physical in origins:
                # Older rejudge rebuilt a requested-empty key from the reported model. It is the
                # same physical answer, not a new reader; collapse it under that answer's key.
                origin = origins[physical]
                key = result_key(origin)
                row = row | {'result_key': key}
                failure = origin.get('failure_class')
                if failure not in (None, 'NOT_JSON', 'SCHEMA_INVALID', 'EMPTY'):
                    row = row | {'ok': False, 'output': None, 'failure_class': failure}
            request = requests.get(row.get('call_id'))
            if (request and row.get('prompt_sha256') is not None
                    and row['prompt_sha256'] != request['prompt_sha256']):
                row = row | {'ok': False, 'output': None, 'failure_class': 'PROMPT_MISMATCH'}
            elif row.get('failure_class'):
                row = row | {'ok': False, 'output': None}
            latest[key] = row
        return latest

    def attempts(self) -> list[dict[str, Any]]:
        """Every result row ever written, in order. What cost money, not what is current."""
        return list(self.store.read(self.results_name))

    def pending(
        self,
        *,
        backend: str,
        model: str = "",
        retry_classes: frozenset[str] = frozenset(),
    ) -> list[dict[str, Any]]:
        """Units this backend has not answered, plus those its last answer left transient.

        `retry_classes` re-opens a **terminal** class by name, which is the named-campaign rule acquire
        already uses: a class a retry cannot change is left alone on a routine run, and re-running it is a
        deliberate act with a reason. Measured need: `deepseek-v4.1-flash` left 9 of 13 units `TRUNCATED` by
        spending its whole output budget on reasoning, and turning reasoning off makes the retry worth
        paying for — but nothing here could ask for it.
        """
        answered = self.results(backend=backend)
        out: list[dict[str, Any]] = []
        for unit in self.requests():
            held = answered.get(f"{unit['call_id']}|{backend}|{model}")
            if held is None:
                out.append(unit)
                continue
            if held.get("ok"):
                continue
            failure = held.get("failure_class")
            if failure in retry_classes or not is_terminal(failure):
                out.append(unit)
        return out


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
        parsed = json.loads(unfence(answer.body.decode("utf-8", "replace")))
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
    model: str = "",
    raw_sha256: str | None = None,
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
        "result_judge_version": RESULT_JUDGE_VERSION,
        "judged_schema": request["response_schema"],
        "answer_failure_class": answer.failure_class,
        "answer_refused": bool(answer.refused),
        "answer_truncated": bool(answer.truncated),
        # Identity is the call **and the reader** — backend and model — on which attempt. A row keyed by
        # call_id alone cannot say whether a cost was a first try or a third; one keyed by backend alone
        # cannot tell two models of the same backend apart, which is what D30 compares.
        "result_key": f"{request['call_id']}|{backend}|{model}",
        "attempt_no": attempt_no,
        "ok": failure_class is None,
        "backend": backend,
        # What we **asked for**, which is the reader's identity and is knowable before the call — `pending`
        # has to compute this key in advance. What the backend says it used is a different fact and can
        # differ, so it is recorded separately rather than conflated with the identity.
        "model": model or answer.model,
        "model_reported": answer.model,
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


def drain(
    queue: Queue,
    runner: Any,
    *,
    limit: int | None = None,
    retry_classes: frozenset[str] = frozenset(),
    call_ids: frozenset[str] | None = None,
) -> Any:
    """Answer what is pending, appending each result as it lands.

    Up to `runner.max_concurrency` calls run at once and **the rows are appended by this generator's own
    thread**. Append-only JSONL is a single-writer format, so the calls parallelise and the writing does not:
    a torn line stays impossible and the ledger keeps the one writer `Store.read` and `Store.repair` are
    built on.

    Task 4 left this sequential deliberately — "until a lane has been measured on a real backend there is no
    evidence about what concurrency a given endpoint tolerates" — and both halves of that now hold. The
    1,888-call round took fifty minutes one at a time, and the Ollama plan in use permits three at once,
    which is what `OllamaCloudRunner.max_concurrency` declares.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor

    reader_model = str(getattr(runner, "model", "") or "")
    pending = queue.pending(
        backend=runner.name, model=reader_model, retry_classes=retry_classes
    )
    if call_ids is not None:
        pending = [row for row in pending if str(row['call_id']) in call_ids]
    if limit is not None:
        pending = pending[:limit]
    if not pending:
        return

    # Counted once, before anything runs. Reading the whole attempt log per request was quadratic, and under
    # threads it would also be a race against rows this drain is appending.
    prior: dict[str, int] = {}
    for attempt in queue.attempts():
        if ("rejudged_from" not in attempt
                and result_key(attempt) == f"{attempt.get('call_id')}|{runner.name}|{reader_model}"):
            key = str(attempt.get("call_id"))
            prior[key] = prior.get(key, 0) + 1

    lanes = max(1, int(getattr(runner, "max_concurrency", 1) or 1))
    pace = float(getattr(runner, "min_interval_s", 0.0) or 0.0)
    gate = threading.Lock()
    last = 0.0

    def call(request: dict[str, Any]) -> tuple[dict[str, Any], Any, str, float]:
        nonlocal last
        if pace:
            # The interval is between *starts*, held across threads: a per-thread sleep would let `lanes`
            # calls leave at once and pace nothing.
            with gate:
                wait = pace - (time.time() - last)
                if wait > 0:
                    time.sleep(wait)
                last = time.time()
        started_at = _now()
        began = time.time()
        return request, runner.run(dict(request)), started_at, time.time() - began

    harness = runner.harness_version()
    with ThreadPoolExecutor(max_workers=lanes) as pool:
        for request, answer, started_at, latency in pool.map(call, pending):
            raw_sha256 = raw_path = None
            if answer.body:
                digest, path = queue.store.store_bytes_at(
                    f"{queue.root}/raw", answer.body, ".txt")
                raw_sha256, raw_path = digest, str(path)

            row = build_result(
                request, answer,
                attempt_no=prior.get(str(request["call_id"]), 0) + 1,
                backend=runner.name,
                harness_version=harness,
                model=reader_model,
                raw_sha256=raw_sha256,
                raw_path=raw_path,
                started_at=started_at,
                finished_at=_now(),
                latency_s=latency,
            )
            queue.store.append(queue.results_name, row)
            yield row


def rejudge(
    queue: Queue,
    *,
    backend: str | None = None,
    response_schema: dict[str, Any] | None = None,
) -> Any:
    """Re-read every stored answer under the current rules. Opens nothing and calls nobody.

    The counterpart of stage 2's `regate`, and it exists for the same reason: the bytes were paid
    for, they are on disk under their hash, and a fix to the classifier must neither orphan them nor
    re-buy them. The first such fix — a ```json fence the model added and the prompt had
    forbidden — would otherwise have left two answers already paid for permanently mis-recorded as
    NOT_JSON.

    D14 governs the row it writes. A re-judgement is **not** an attempt: it is the same answer read
    again, so it carries `rejudged_from`, no cost and no latency, and `model_report` leaves it out of
    what the queue cost and how fast it went. But it *is* authoritative about that answer, so plain
    latest-wins is right — a tightened schema turns a success into a failure, and the queue says so.

    `response_schema` overrides what the request carried, for asking what a different shape would
    have accepted without writing a new batch.
    """
    import pathlib

    from claimstone.runners.base import RawAnswer

    requests = {row["call_id"]: row for row in queue.requests()}
    originals = {}
    for attempt in queue.attempts():
        if "rejudged_from" not in attempt:
            originals[(result_key(attempt), attempt.get("attempt_no", 1),
                       attempt.get("raw_sha256"))] = attempt
    for held in queue.results(backend=backend).values():
        request = requests.get(str(held.get("call_id")))
        if request is None:
            continue
        stored = held.get("raw_path") or ""
        if not stored or not pathlib.Path(stored).exists():
            # No bytes, no re-reading. Inventing a verdict for an answer nobody can show is the
            # opposite of what keeping the raw bytes is for.
            continue
        if response_schema is not None:
            request = {**request, "response_schema": response_schema}
        elif held.get("judged_schema") is not None:
            request = {**request, "response_schema": held["judged_schema"]}

        origin = originals.get((result_key(held), held.get("attempt_no", 1),
                                held.get("raw_sha256")), held)
        failure = origin.get("failure_class")
        transport = origin.get("answer_failure_class")
        if "answer_failure_class" not in origin and failure not in (
                None, "NOT_JSON", "SCHEMA_INVALID", "EMPTY", "REFUSED", "TRUNCATED"):
            transport = failure
        body = pathlib.Path(stored).read_bytes()
        import hashlib
        if held.get("raw_sha256") and hashlib.sha256(body).hexdigest() != held["raw_sha256"]:
            transport = "RAW_HASH_MISMATCH"

        # Rebuilt from what was recorded, not re-fetched. `truncated` and `refused` are facts the
        # backend reported at the time and cannot be re-derived, so they are carried across.
        answer = RawAnswer(
            body=body,
            model=str(origin.get("model_reported", origin.get("model")) or ""),
            prompt_sent=None,
            usage=dict(held.get("usage") or {}),
            cost_usd=None,
            truncated=bool(origin.get("answer_truncated") or failure == "TRUNCATED"),
            refused=bool(origin.get("answer_refused") or failure == "REFUSED"),
            failure_class=transport,
        )
        row = build_result(
            request, answer,
            attempt_no=int(held.get("attempt_no") or 1),
            backend=str(held.get("backend") or "unknown"),
            model=str(held.get("model") or ""),
            harness_version=str(held.get("harness_version") or ""),
            raw_sha256=held.get("raw_sha256"),
            raw_path=stored,
            started_at=str(held.get("started_at") or ""),
            finished_at=_now(),
            latency_s=0.0,
        )
        # The echo check cannot run on stored bytes: the runner is not here to say what it sent. The
        # earlier row's answer to that question stands, rather than being downgraded by a re-reading
        # that was never in a position to ask.
        row["prompt_sha256"] = origin.get("prompt_sha256")
        row["prompt_verified"] = bool(origin.get("prompt_verified"))
        row["result_key"] = result_key(held)
        if failure == "PROMPT_MISMATCH":
            row.update(ok=False, output=None, failure_class="PROMPT_MISMATCH")
        row["rejudged_from"] = held.get("finished_at") or held.get("started_at") or ""
        ignored = {"finished_at", "rejudged_from", "cost_usd", "latency_s", "detail"}
        if ("rejudged_from" in held and {k: v for k, v in row.items() if k not in ignored}
                == {k: v for k, v in held.items() if k not in ignored}):
            continue
        queue.store.append(queue.results_name, row)
        yield row


def result_key(row: dict[str, Any]) -> str:
    return str(row.get("result_key") or
               f"{row.get('call_id')}|{row.get('backend')}|{row.get('model') or ''}")


def review_target(unit: dict[str, Any]) -> dict[str, Any]:
    return {key: unit.get(key) for key in ('claim_id', 'question_id', 'extracted_by', 'annotation_sha256')}


def current_answers(store: Any, lane: str) -> dict[tuple[str, str], dict[str, Any]]:
    """Read-only batch/reader index. Rejudgements and failures supersede old successes."""
    return {(path.parent.name, key): row
            for path in sorted(store.path(f"calls/{lane}").glob("*/results.jsonl"))
            for key, row in Queue(store, lane=lane, batch=path.parent.name).results().items()}


def answers_for(row: dict[str, Any], answers: dict[tuple[str, str], dict[str, Any]],
                *, reader: dict[str, Any] | None = None) -> list[dict[str, Any]] | None:
    """Legacy rows without a batch can refer to any matching batch, never to an old attempt."""
    if not row.get("call_id"):
        return None
    identity = {**row, **(reader or {})}
    key = result_key(identity)
    batches = row.get('answer_batches') or ([row['batch']] if row.get('batch') else [])
    def same_reader(held_key: str, value: dict[str, Any]) -> bool:
        if row.get('result_key'):
            return held_key == key
        return (value.get('call_id') == row.get('call_id')
                and value.get('backend') == identity.get('backend')
                and str(value.get('model') or '') == str(identity.get('model') or ''))
    matches = [value for (batch, held_key), value in answers.items()
               if same_reader(held_key, value) and (not batches or batch in batches)]
    # Old imports without a model-call ledger retain their documented legacy meaning.
    return matches if matches or batches else None
