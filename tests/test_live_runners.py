"""One real call per backend. Skipped everywhere by default, including CI.

Its job is to catch a backend rotting — an envelope key renamed, a flag removed, an endpoint
moved — which no fake can detect, because a fake is written from the same assumption the code is.
"""

import os

import pytest

from claimstone import model_call

pytestmark = pytest.mark.skipif(
    os.environ.get("CLAIMSTONE_LIVE") != "1", reason="set CLAIMSTONE_LIVE=1 to run"
)

SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["answer"], "properties": {"answer": {"type": "string"}}}

UNIT = dict(
    lane="extract", registry_version=1, max_output_tokens=200, response_schema=SCHEMA,
    system='Answer only with JSON of the form {"answer": "..."}. No prose.',
    user="What is the capital of France?",
)


@pytest.mark.network
@pytest.mark.parametrize("backend,model", [
    ("claude-cli", "claude-opus-5"),
    ("ollama-cloud", "deepseek-v4.1-flash"),
    ("llamacpp", "local"),
])
def test_a_backend_returns_something_the_validator_accepts(backend, model):
    from claimstone import runners

    runner = runners.build(backend, model=model)
    request = model_call.work_unit(**UNIT)
    answer = runner.run(dict(request))
    if answer.failure_class:
        pytest.skip(f"{backend} unavailable: {answer.failure_class} {answer.detail}")

    row = model_call.build_result(
        request, answer, backend=runner.name, harness_version=runner.harness_version(),
        raw_sha256=None, raw_path=None, started_at="", finished_at="", latency_s=0.0)
    assert row["ok"], f"{backend}: {row['failure_class']} {row['schema_errors']} {row['detail']}"
    assert "paris" in row["output"]["answer"].lower()
