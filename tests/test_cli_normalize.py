"""normalize and --confirm-audit at the command line."""

from claimstone.cli import build_parser, main


def test_normalize_is_no_longer_a_placeholder():
    args = build_parser().parse_args(["normalize", "projects/example-news-and-returns"])
    assert args.func.__name__ != "_not_implemented"


def test_a_dead_grobid_is_reported_with_the_workaround(tmp_path, capsys, monkeypatch):
    """Reported when it is needed. A PDF with no TEI on disk is what needs it."""
    from claimstone import grobid
    from claimstone.store import Store
    from tests.test_normalize import acquired

    store = Store("example-news-and-returns", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store))
    monkeypatch.setattr(grobid.Grobid, "is_alive", lambda self: False)

    code = main(["normalize", "projects/example-news-and-returns", "--store", str(tmp_path)])
    assert code == 2
    error = capsys.readouterr().err
    assert "JAVA_TOOL_OPTIONS=-XX:-UseContainerSupport" in error
    assert "cgroup v2" in error


def test_a_dead_grobid_does_not_block_a_corpus_already_parsed(tmp_path, capsys, monkeypatch):
    """The TEI is on disk under its hash, so re-chunking the whole corpus needs nothing running.

    Demanding a container that will never be contacted is a wall in front of an offline operation.
    """
    from claimstone import grobid, normalize
    from claimstone.store import Store
    from tests.test_normalize import FakeGrobid, acquired

    store = Store("example-news-and-returns", base=tmp_path)
    store.append("acquisitions.jsonl", acquired("S01", store))
    list(normalize.run(store, FakeGrobid()))          # writes the TEI under the PDF's hash

    monkeypatch.setattr(grobid.Grobid, "is_alive", lambda self: False)
    code = main(["normalize", "projects/example-news-and-returns", "--store", str(tmp_path),
                 "--force"])
    assert code == 0
    assert "1 confirmed" in capsys.readouterr().out


def test_progress_goes_to_stderr_and_the_summary_to_stdout(tmp_path, capsys, monkeypatch):
    from claimstone import cli, normalize

    monkeypatch.setattr(
        normalize, "run",
        lambda *a, **k: iter([
            {"source_id": "S01", "fulltext_confirmed": True, "chunks": 5, "references": 41,
             "tables": 8, "body_chars": 36137, "reason": "41 references"},
            {"source_id": "IND008", "fulltext_confirmed": False, "chunks": 0, "references": 1,
             "tables": 1, "body_chars": 4377, "failure_class": "NOT_A_DOCUMENT",
             "reason": "1 references and body_chars 4377"},
        ]),
    )
    monkeypatch.setattr("claimstone.grobid.Grobid.is_alive", lambda self: True)
    cli.main(["normalize", "projects/example-news-and-returns", "--store", str(tmp_path)])
    captured = capsys.readouterr()
    assert "S01" in captured.err and "IND008" in captured.err
    assert "S01" not in captured.out
    assert "1 confirmed" in captured.out


def test_an_unreadable_artifact_is_neither_ok_nor_fail_on_the_progress_line(tmp_path, capsys, monkeypatch):
    """It establishes nothing, so printing it as a failure would read as a rejected source."""
    from claimstone import cli, normalize

    monkeypatch.setattr(
        normalize, "run",
        lambda *a, **k: iter([{"source_id": "S01", "fulltext_confirmed": None, "chunks": 0,
                               "failure_class": normalize.ARTIFACT_UNREADABLE,
                               "reason": "FileNotFoundError: gone"}]),
    )
    monkeypatch.setattr("claimstone.grobid.Grobid.is_alive", lambda self: True)
    cli.main(["normalize", "projects/example-news-and-returns", "--store", str(tmp_path)])
    captured = capsys.readouterr()
    assert "ARTIFACT_UNREADABLE" in captured.err
    assert "1 unreadable" in captured.out
    assert "0 confirmed" in captured.out


def test_confirm_audit_does_not_need_grobid(tmp_path, capsys, monkeypatch):
    from claimstone import grobid

    monkeypatch.setattr(grobid.Grobid, "is_alive", lambda self: False)
    code = main(["normalize", "projects/example-news-and-returns", "--confirm-audit",
                 "--store", str(tmp_path)])
    assert code == 0
    assert "no documents" in capsys.readouterr().out
