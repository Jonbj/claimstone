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
