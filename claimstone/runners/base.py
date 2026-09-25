"""What a runner is, and — just as much — what it is not.

A runner talks to one backend and returns **raw bytes plus what the backend charged**. It does
not parse the answer, validate it, or decide whether the call succeeded. Those belong to
`model_call`, in one place, for every backend: if each runner decided for itself what counted as
a valid answer, two backends' results would not be comparable, and comparability is the only
reason this boundary exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
