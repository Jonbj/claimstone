"""What every runner owes, checked against every runner that is registered.

`prompt_sent` was missing from all three runners as first written, and each was fixed separately.
Remembering a shared obligation three times is how the fourth runner forgets it, so the obligation
is asserted here over `runners.available()` — a new backend fails this file until it is listed and
until it reports what it sent.
"""

import json
import subprocess

import pytest

from claimstone import model_call, runners
from tests.test_runner_ollama import FakePost

REQUEST = {
    "call_id": "abc", "lane": "extract", "system": "the registry", "user": "a chunk",
    "max_output_tokens": 800, "response_schema": {"type": "array", "items": {"type": "object"}},
}


@pytest.fixture
def no_subprocess(monkeypatch):
    def fake_run(argv, **kwargs):
        if argv[1:2] == ["--version"]:
            return subprocess.CompletedProcess(argv, 0, stdout="1.0\n", stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"result": "[]"}), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)


def _build(name):
    """One built runner per registered name, with its transport replaced."""
    if name.endswith("-cli"):
        return runners.build(name, model="m")
    if name == "ollama-cloud":
        post = FakePost({"message": {"content": "[]"}})
        return runners.build(name, model="m", api_key="sk-test", post=post)
    if name == "llamacpp":
        post = FakePost({"choices": [{"message": {"content": "[]"}, "finish_reason": "stop"}]})
        return runners.build(name, post=post)
    raise AssertionError(f"no test harness for registered backend {name!r}: add one")


def test_every_registered_backend_has_a_harness_here():
    """So a new runner cannot be added without this file being told about it."""
    for name in runners.available():
        assert _build(name) is not None


@pytest.mark.parametrize("name", sorted(runners.available()))
def test_every_runner_reports_the_prompt_it_sent(name, no_subprocess):
    answer = _build(name).run(dict(REQUEST))
    assert answer.prompt_sent == model_call.rendered_prompt(REQUEST["system"], REQUEST["user"]), (
        f"{name} reports no prompt_sent, so the echo check cannot run on it"
    )


@pytest.mark.parametrize("name", sorted(runners.available()))
def test_every_runner_names_itself_and_declares_its_pacing(name, no_subprocess):
    runner = _build(name)
    assert runner.name == name
    assert runner.max_concurrency >= 1
    assert runner.min_interval_s >= 0.0
    assert runner.harness_version()


@pytest.mark.parametrize("name", sorted(runners.available()))
def test_no_runner_judges_its_own_answer(name, no_subprocess):
    """A runner returns bytes. If it parsed them, two backends' results would not be comparable."""
    answer = _build(name).run(dict(REQUEST))
    assert isinstance(answer.body, bytes)
    assert answer.failure_class is None
