"""Backends, one module each. Nothing else in the repository names a vendor.

No runner is the default. Which backend serves a lane is a finding, not a design decision
(D13), so the caller names one and the choice lands on every row.
"""

from __future__ import annotations

from typing import Any, Callable

from claimstone.runners.base import RawAnswer, Runner


def available() -> dict[str, Callable[..., Runner]]:
    from claimstone.runners import cli, llamacpp, ollama_cloud

    return {
        "claude-cli": lambda **kw: cli.CliRunner(tool="claude", **kw),
        "codex-cli": lambda **kw: cli.CliRunner(tool="codex", **kw),
        "opencode-cli": lambda **kw: cli.CliRunner(tool="opencode", **kw),
        "ollama-cloud": ollama_cloud.OllamaCloudRunner,
        "llamacpp": llamacpp.LlamaCppRunner,
    }


# A backend that cannot pick a model for you. Passing --model is then required, and saying so is
# better than a TypeError out of a dataclass constructor.
NEEDS_MODEL = frozenset({"claude-cli", "codex-cli", "opencode-cli", "ollama-cloud"})


def build(name: str, *, model: str | None = None, **kwargs: Any) -> Runner:
    factories = available()
    if name not in factories:
        raise ValueError(f"unknown backend {name!r}: {', '.join(sorted(factories))}")
    if model is None and name in NEEDS_MODEL:
        raise ValueError(f"backend {name!r} needs a model: pass --model")
    if model is not None:
        kwargs["model"] = model
    return factories[name](**kwargs)


__all__ = ["RawAnswer", "Runner", "available", "build"]
