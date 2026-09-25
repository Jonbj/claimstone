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
from dataclasses import dataclass, field
from typing import Any

from claimstone.model_call import rendered_prompt
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
