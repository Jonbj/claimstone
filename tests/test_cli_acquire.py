"""The CLI is where the floor becomes enforceable by a script."""

from claimstone.cli import build_parser, main


def test_acquire_is_no_longer_a_placeholder():
    args = build_parser().parse_args(["acquire", "projects/example-news-and-returns"])
    assert args.func.__name__ != "_not_implemented"


def test_retrying_a_terminal_class_requires_a_named_campaign(capsys):
    code = main(["acquire", "projects/example-news-and-returns", "--retry-class", "PAYWALL_403"])
    assert code == 2
    assert "--campaign" in capsys.readouterr().err


def test_report_gate_exits_three_below_the_floor(tmp_path, capsys):
    from claimstone.store import Store

    store = Store("example-news-and-returns", base=tmp_path)
    store.append("acquisitions.jsonl", {"candidate_key": "a", "source_class": "ACA",
                                        "acquired": False, "failure_class": "PAYWALL_403",
                                        "url": "https://x.example/a"})
    code = main(["report", "projects/example-news-and-returns", "--store", str(tmp_path), "--gate"])
    assert code == 3
    out = capsys.readouterr().out
    assert "INSUFFICIENT_ACQUISITION" in out
    # The floor travels with its version, or two rounds are not comparable.
    assert "v1" in out


def test_report_without_gate_exits_zero_below_the_floor(tmp_path):
    from claimstone.store import Store

    store = Store("example-news-and-returns", base=tmp_path)
    store.append("acquisitions.jsonl", {"candidate_key": "a", "source_class": "ACA",
                                        "acquired": False, "failure_class": "PAYWALL_403",
                                        "url": "https://x.example/a"})
    # Measuring is not failing: only --gate turns an inadmissible round into an exit code.
    assert main(["report", "projects/example-news-and-returns", "--store", str(tmp_path)]) == 0


def test_progress_goes_to_stderr_and_the_summary_to_stdout(tmp_path, capsys, monkeypatch):
    from claimstone import acquire, cli

    monkeypatch.setattr(
        acquire, "run",
        lambda *a, **k: iter([
            {"candidate_key": "a", "source_id": "S01", "acquired": True,
             "provenance": "unpaywall", "licence": "cc-by", "bytes": 412839,
             "failure_class": None},
            {"candidate_key": "b", "source_id": "S02", "acquired": False,
             "failure_class": "ABSTRACT_ONLY", "bytes": 0},
        ]),
    )
    cli.main(["acquire", "projects/example-news-and-returns", "--store", str(tmp_path)])
    captured = capsys.readouterr()
    assert "S01" in captured.err and "S02" in captured.err
    assert "0.50" in captured.err           # the running rate is visible while it runs
    assert "S01" not in captured.out        # stdout carries the summary only
    assert "2 attempted" in captured.out
