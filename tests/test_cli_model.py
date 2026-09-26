"""model-run and model-report at the command line."""

import pytest

from claimstone.cli import build_parser, main


def test_a_backend_must_be_named():
    # D13 defers lane assignment to measurement, so there is no default to fall back on.
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["model-run", "projects/example-news-and-returns", "extract", "--batch", "b1"])


def test_a_backend_that_needs_a_model_says_so_rather_than_crashing(capsys):
    code = main(["model-run", "projects/example-news-and-returns", "extract",
                 "--batch", "b1", "--backend", "claude-cli"])
    assert code == 2
    error = capsys.readouterr().err
    assert "--model" in error


def test_a_backend_with_a_default_model_needs_no_flag():
    from claimstone import runners

    # llamacpp serves whatever the local server has loaded; naming it is not the caller's job.
    assert runners.build("llamacpp").model == "local"


def test_an_unknown_backend_is_refused_by_name(capsys):
    code = main(["model-run", "projects/example-news-and-returns", "extract",
                 "--batch", "b1", "--backend", "nonesuch"])
    assert code == 2
    assert "nonesuch" in capsys.readouterr().err


def test_an_unknown_lane_is_refused(capsys):
    code = main(["model-run", "projects/example-news-and-returns", "synthesis",
                 "--batch", "b1", "--backend", "llamacpp"])
    assert code == 2


def test_model_report_on_an_empty_batch_says_so(tmp_path, capsys):
    code = main(["model-report", "projects/example-news-and-returns", "extract",
                 "--batch", "b1", "--store", str(tmp_path)])
    assert code == 0
    assert "no calls" in capsys.readouterr().out


def test_the_backend_list_in_help_matches_the_registry():
    # Two lists that must agree, so a runner added without updating the help is a failing test
    # rather than a backend nobody can select.
    from claimstone import runners
    from claimstone.cli import BACKENDS

    assert set(BACKENDS) == set(runners.available())


def test_model_run_actually_drains_a_queue(tmp_path, capsys, monkeypatch):
    """Every other test in this file fails before the drain, so none of them touched it.

    The plan's handler called queue.pending() with no backend, and pending is keyword-only on it —
    a TypeError on the one path the command exists for.
    """
    import json as _json

    from claimstone import model_call, runners
    from claimstone.runners.base import RawAnswer
    from claimstone.store import Store
    from tests.fakes import FakeRunner

    schema = {"type": "array", "items": {"type": "object",
                                         "properties": {"question_id": {"type": "string"}},
                                         "required": ["question_id"]}}
    store = Store("example-news-and-returns", base=tmp_path)
    queue = model_call.Queue(store, lane="extract", batch="b1")
    queue.write([model_call.work_unit(
        lane="extract", system="the registry", user="a chunk", response_schema=schema,
        max_output_tokens=800, registry_version=2, source_id="S01", chunk_id="S01#c1")])

    answered = RawAnswer(body=_json.dumps([{"question_id": "H02"}]).encode(), model="m",
                         prompt_sent=model_call.rendered_prompt("the registry", "a chunk"))
    monkeypatch.setattr(runners, "build", lambda name, **kw: FakeRunner(default=answered))

    code = main(["model-run", "projects/example-news-and-returns", "extract",
                 "--batch", "b1", "--backend", "llamacpp", "--store", str(tmp_path)])
    assert code == 0
    out = capsys.readouterr()
    assert "1 answered, 1 valid" in out.out
    assert [row["ok"] for row in queue.results(backend="fake").values()] == [True]
