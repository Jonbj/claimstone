"""discover and discover-report at the command line."""

from claimstone.cli import build_parser, main


def test_discover_is_a_real_command():
    args = build_parser().parse_args(["discover", "projects/example-news-and-returns"])
    assert args.func.__name__ == "_discover"
    assert args.channel == "both"
    assert args.round == "routine"


def test_the_citation_channel_alone_needs_no_contact_address(tmp_path, capsys, monkeypatch):
    # It reads a ledger. Requiring a crawler identity for that would be theatre.
    monkeypatch.delenv("CLAIMSTONE_CONTACT_EMAIL", raising=False)
    code = main(["discover", "projects/example-news-and-returns", "--channel", "citation",
                 "--store", str(tmp_path)])
    assert code == 0
    assert "nothing to read" in capsys.readouterr().out


def test_an_unknown_api_is_refused_by_name(capsys):
    code = main(["discover", "projects/example-news-and-returns", "--api", "scholar"])
    assert code == 2
    assert "scholar" in capsys.readouterr().err


def test_discover_report_on_an_empty_store_says_so(tmp_path, capsys):
    code = main(["discover-report", "projects/example-news-and-returns",
                 "--store", str(tmp_path)])
    assert code == 0
    assert "no candidates" in capsys.readouterr().out


def test_the_report_prints_the_caveat_not_an_estimate(tmp_path, capsys):
    from claimstone.store import Store

    store = Store("example-news-and-returns", base=tmp_path)
    store.append("candidates.jsonl", {"candidate_key": "a", "channel": "keyword",
                                      "source_class": "ACA", "round": "routine"})
    main(["discover-report", "projects/example-news-and-returns", "--store", str(tmp_path)])
    out = capsys.readouterr().out
    assert "deliberately not combined" in out
    assert "2962" not in out
    assert "coverage" not in out.lower()


def test_the_citation_channel_without_resolve_still_opens_no_socket(tmp_path, monkeypatch):
    """The promise that makes resolution opt-in. Without --resolve it reads a ledger and nothing else."""
    import socket

    from claimstone.store import Store

    store = Store("example-news-and-returns", base=tmp_path)
    store.append("references.jsonl", {"key": "title:a perfectly good long title here",
                                      "title": "A perfectly good long title here",
                                      "citations_in_corpus": 3, "year": 2010, "authors": []})

    def refuse(*args, **kwargs):
        raise AssertionError("--channel citation without --resolve must open no socket")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    assert main(["discover", "projects/example-news-and-returns", "--channel", "citation",
                 "--store", str(tmp_path)]) == 0


def test_resolve_needs_a_contact_address_because_it_makes_requests(tmp_path, capsys, monkeypatch):
    """Identifying the crawler is a condition of using these APIs politely, and net.contact_email
    refuses to guess. Failing with that sentence beats failing inside the first request."""
    monkeypatch.delenv("CLAIMSTONE_CONTACT_EMAIL", raising=False)
    code = main(["discover", "projects/example-news-and-returns", "--channel", "citation",
                 "--resolve", "--store", str(tmp_path)])
    assert code == 2
    assert "CLAIMSTONE_CONTACT_EMAIL" in capsys.readouterr().err


def test_the_resolution_outcomes_are_printed_per_class(tmp_path, capsys):
    from claimstone.store import Store

    store = Store("example-news-and-returns", base=tmp_path)
    store.append("references.jsonl", {"key": "title:a perfectly good long title here",
                                      "title": "A perfectly good long title here",
                                      "citations_in_corpus": 3, "year": 2010, "authors": []})
    main(["discover", "projects/example-news-and-returns", "--channel", "citation",
          "--store", str(tmp_path)])
    out = capsys.readouterr().out
    assert "NOT_ATTEMPTED" in out
    assert "--resolve" in out
