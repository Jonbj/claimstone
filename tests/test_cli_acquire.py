"""The CLI is where the floor becomes enforceable by a script."""

from claimstone.cli import build_parser, main
import datetime as dt
import pytest


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


@pytest.mark.parametrize('retry_terminal', [False, True])
def test_dry_run_matches_execution_scope_retry_and_limit(tmp_path, capsys, monkeypatch, retry_terminal):
    from claimstone import acquire, net
    from claimstone.config import load_project, check_registry_drift
    from claimstone.store import Store
    from tests.fakes import FakeFetcher, ok
    from tests.test_fulltext import pdf
    from tools.replay_answers import files_snapshot

    project = load_project('projects/example-news-and-returns')
    store = Store(project.name, base=tmp_path)
    check_registry_drift(project, store)
    candidates = [dict(candidate_key=key, source_id=key, source_class='ACA', title=key,
                       round='chosen', is_oa=True, url=f'https://repo.example/{key}.pdf')
                  for key in ['other', 'done', 'recent', 'blocked', 'unknown', 'a', 'b']]
    candidates[0]['round'] = 'other-round'
    candidates[4].update(source_id=None, is_oa=None)
    for row in candidates:
        store.append('candidates.jsonl', row)
    store.append('acquisitions.jsonl', {'candidate_key': 'done', 'acquired': True})
    for key, failure in [('recent', 'TIMEOUT'), ('blocked', 'PAYWALL_403')]:
        store.append('acquisitions.jsonl', {'candidate_key': key, 'acquired': False,
            'failure_class': failure, 'fetched_at': dt.datetime.now(dt.timezone.utc).isoformat()})
    fetcher = FakeFetcher(pages={c['url']: ok(c['url'], pdf()) for c in candidates})
    fetcher_class = net.Fetcher
    monkeypatch.setattr(net, 'Fetcher', lambda **kwargs: fetcher)
    before = files_snapshot(store)
    command = ['acquire', str(project.root), '--store', str(tmp_path), '--round', 'chosen',
               '--manifest', '--only-oa', '--limit', '1', '--no-apis', '--dry-run']
    retry_classes = frozenset({'PAYWALL_403'}) if retry_terminal else frozenset()
    if retry_terminal:
        command += ['--campaign', 'explicit-retry', '--retry-class', 'PAYWALL_403']
    assert main(command) == 0
    output = capsys.readouterr().out
    expected = 'blocked' if retry_terminal else 'a'
    assert output.splitlines()[0] == expected
    assert len(output.splitlines()) == 2
    assert files_snapshot(store) == before
    monkeypatch.setattr(net, 'Fetcher', fetcher_class)
    rows = list(acquire.run(candidates, store, fetcher, use_apis=False, round_name='chosen',
        manifest_only=True, only_oa=True, limit=1, retry_classes=retry_classes,
        campaign='explicit-retry' if retry_terminal else 'routine'))
    assert [r['candidate_key'] for r in rows] == [expected]
