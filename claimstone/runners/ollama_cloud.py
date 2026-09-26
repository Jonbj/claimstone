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
