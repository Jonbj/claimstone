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
            # Refuse here, not when the answer arrives: a schema this validator cannot honour
            # is a mistake by the stage that wrote it, and it should fail where it was made.
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
        drain reading raw rows would pay for the same call once per chunk that asked for it.
        """
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
