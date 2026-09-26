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

from claimstone.model_call import rendered_prompt
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
            # Two messages went out; the echo check compares one string, and this is that string.
            prompt_sent=rendered_prompt(request["system"], request["user"]),
        )
