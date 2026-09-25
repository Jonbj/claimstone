"""The subprocess runner. No process is started: subprocess.run is replaced."""

import json
import subprocess

import pytest

from claimstone.runners import cli as cli_runner


def request(**overrides):
    base = {"call_id": "abc", "lane": "extract", "system": "the registry", "user": "a chunk",
            "max_output_tokens": 800, "response_schema": {"type": "array"}}
    return {**base, **overrides}


@pytest.fixture
def recorder(monkeypatch):
    seen: dict[str, list] = {"argv": [], "input": []}

    def fake_run(argv, **kwargs):
        seen["argv"].append(argv)
        seen["input"].append(kwargs.get("input"))
        if argv[1:2] == ["--version"]:
            return subprocess.CompletedProcess(argv, 0, stdout="2.1.280 (Claude Code)\n",
                                               stderr="")
        payload = json.dumps({"result": '[{"question_id": "Q07"}]'})
        return subprocess.CompletedProcess(argv, 0, stdout=payload, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return seen


def test_claude_is_invoked_in_print_mode_with_json_output(recorder):
    runner = cli_runner.CliRunner(tool="claude", model="claude-opus-5")
    runner.run(request())
    argv = recorder["argv"][-1]
    assert argv[0] == "claude"
    assert "--print" in argv or "-p" in argv
    assert "--output-format" in argv and "json" in argv
    assert "--model" in argv and "claude-opus-5" in argv


def test_the_prompt_goes_in_on_stdin_not_on_the_command_line(recorder):
    # A chunk is thousands of characters and may contain anything; an argv full of it is a
    # length limit and a quoting bug waiting to happen.
    runner = cli_runner.CliRunner(tool="claude", model="m")
    runner.run(request(user="a chunk with 'quotes' and $dollars"))
    assert "a chunk with 'quotes' and $dollars" in recorder["input"][-1]
    assert not any("dollars" in part for part in recorder["argv"][-1])


def test_the_harness_version_comes_from_the_tool_itself(recorder):
    runner = cli_runner.CliRunner(tool="claude", model="m")
    assert runner.harness_version() == "claude 2.1.280 (Claude Code)"


def test_a_non_zero_exit_is_a_backend_error(monkeypatch):
    def failing(argv, **kwargs):
        if argv[1:2] == ["--version"]:
            return subprocess.CompletedProcess(argv, 0, stdout="1.0\n", stderr="")
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", failing)
    answer = cli_runner.CliRunner(tool="claude", model="m").run(request())
    assert answer.failure_class == "BACKEND_ERROR"
    assert "boom" in answer.detail


def test_a_timeout_is_a_timeout(monkeypatch):
    def timing_out(argv, **kwargs):
        if argv[1:2] == ["--version"]:
            return subprocess.CompletedProcess(argv, 0, stdout="1.0\n", stderr="")
        raise subprocess.TimeoutExpired(argv, 60)

    monkeypatch.setattr(subprocess, "run", timing_out)
    answer = cli_runner.CliRunner(tool="claude", model="m").run(request())
    assert answer.failure_class == "TIMEOUT"


def test_the_envelope_is_unwrapped_but_its_payload_is_not_parsed(recorder):
    # The CLI answers with its own JSON envelope; the model's answer is a string inside it.
    # model_call parses that, so the runner hands the bytes over untouched.
    answer = cli_runner.CliRunner(tool="claude", model="m").run(request())
    assert answer.body == b'[{"question_id": "Q07"}]'


def test_a_subscription_backed_call_is_unpriced(recorder):
    answer = cli_runner.CliRunner(tool="claude", model="m").run(request())
    assert answer.cost_usd is None


def test_the_cli_runner_is_serial_and_paced():
    runner = cli_runner.CliRunner(tool="claude", model="m")
    assert runner.max_concurrency == 1
    assert runner.min_interval_s >= 1.0


def test_the_prompt_sent_is_reported_so_the_echo_check_actually_runs(recorder):
    """It costs nothing here, and without it every row from this backend is unverified.

    The runner also must not rebuild the joining of system and user by hand: model_call owns that
    string, and a second copy of the separator would silently diverge from the hash it is compared
    against.
    """
    from claimstone import model_call

    req = request()
    answer = cli_runner.CliRunner(tool="claude", model="m").run(req)
    assert answer.prompt_sent == model_call.rendered_prompt(req["system"], req["user"])
    assert answer.prompt_sent == recorder["input"][-1]


def test_the_harness_version_is_asked_for_once(monkeypatch):
    """The drain reads it per call. A subprocess per call just to print a version number is a
    fifteenth of the corpus spent on nothing."""
    versions = []

    def counting(argv, **kwargs):
        if argv[1:2] == ["--version"]:
            versions.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout="2.1.280 (Claude Code)\n", stderr="")
        return subprocess.CompletedProcess(
            argv, 0, stdout=json.dumps({"result": "[]"}), stderr="")

    monkeypatch.setattr(subprocess, "run", counting)
    runner = cli_runner.CliRunner(tool="claude", model="m")
    assert runner.harness_version() == runner.harness_version() == "claude 2.1.280 (Claude Code)"
    assert len(versions) == 1
