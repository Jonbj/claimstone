"""The operator CLI beyond add/disable: every subcommand prints one line and writes the same rows
the control server would (design 2026-10-12). Passwords come in through a monkeypatched getpass."""

import getpass

import pytest

from claimstone import cli, operators

PW = "long-enough-pass-1"
ENDS = "sessions of a running control server end on their next request"


@pytest.fixture()
def st(tmp_path, monkeypatch):
    directory = tmp_path / "st"
    monkeypatch.setenv("CLAIMSTONE_STATE_DIR", str(directory))
    operators.add_operator(directory, "adm", "Admin", PW, email="adm@example.org")
    return directory


def _answers(monkeypatch, *typed):
    answers = iter(typed)
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": next(answers))


def test_add_takes_a_role_and_an_email(st, monkeypatch, capsys):
    _answers(monkeypatch, "another-long-pass", "another-long-pass")
    assert cli.main(["operator", "add", "ann", "--name", "Ann", "--role", "operator",
                     "--email", "Ann@Example.org"]) == 0
    assert "(Ann, operator)" in capsys.readouterr().out
    person = operators.people(st)["ann"]
    assert (person["role"], person["email"]) == ("operator", "ann@example.org")
    assert [r["by"] for r in operators._rows(st) if r["id"] == "ann"] == ["cli"]


def test_enable_restores_a_disabled_person(st, capsys):
    operators.add_operator(st, "ann", "Ann", PW)
    assert cli.main(["operator", "disable", "ann"]) == 0
    out = capsys.readouterr().out
    assert "operator disabled: ann" in out and ENDS in out
    assert "ann" not in operators.load(st)
    assert cli.main(["operator", "enable", "ann"]) == 0
    assert capsys.readouterr().out.strip() == "operator enabled: ann"
    assert "ann" in operators.load(st)
    assert cli.main(["operator", "enable", "ann"]) == 2  # already enabled
    assert "already enabled" in capsys.readouterr().err


def test_set_password_replaces_it_and_can_demand_a_change(st, monkeypatch, capsys):
    _answers(monkeypatch, "brand new password", "brand new password")
    assert cli.main(["operator", "set-password", "adm", "--must-change"]) == 0
    out = capsys.readouterr().out
    assert "password replaced: adm" in out and ENDS in out
    loaded = operators.load(st)
    assert loaded["adm"]["must_change_password"] is True
    assert operators.verify(loaded["adm"], "brand new password")
    assert not operators.verify(loaded["adm"], PW)
    _answers(monkeypatch, "yet another password", "yet another password")
    assert cli.main(["operator", "set-password", "adm"]) == 0
    assert operators.load(st)["adm"]["must_change_password"] is False


def test_set_password_refuses_a_short_one_and_writes_nothing(st, monkeypatch, capsys):
    before = (st / operators.LEDGER).read_text()
    _answers(monkeypatch, "short", "short")
    assert cli.main(["operator", "set-password", "adm"]) == 2
    err = capsys.readouterr().err
    assert "at least 12 characters" in err and "short" not in err.replace("at least", "")
    _answers(monkeypatch, "one long password", "another long password")
    assert cli.main(["operator", "set-password", "adm"]) == 2
    assert "do not match" in capsys.readouterr().err
    assert (st / operators.LEDGER).read_text() == before


def test_set_email_and_set_role(st, capsys):
    operators.add_operator(st, "ann", "Ann", PW)
    assert cli.main(["operator", "set-email", "ann", "ann@example.org"]) == 0
    assert capsys.readouterr().out.strip() == "email set: ann"
    assert operators.people(st)["ann"]["email"] == "ann@example.org"
    assert cli.main(["operator", "set-email", "ann", "adm@example.org"]) == 2  # taken
    assert "already belongs" in capsys.readouterr().err
    assert cli.main(["operator", "set-role", "ann", "admin"]) == 0
    assert capsys.readouterr().out.strip() == "role set: ann admin"
    assert operators.people(st)["ann"]["role"] == "admin"
    assert cli.main(["operator", "set-role", "nobody", "admin"]) == 2


def test_the_last_admin_cannot_be_demoted_or_disabled_from_the_shell(st, capsys):
    assert cli.main(["operator", "set-role", "adm", "operator"]) == 2
    assert cli.main(["operator", "disable", "adm"]) == 2
    assert "last admin" in capsys.readouterr().err


def test_list_shows_roles_email_and_disabled_people(st, capsys):
    operators.add_operator(st, "ann", "Ann", PW, role="operator", email="ann@example.org")
    operators.add_operator(st, "bob", "Bob Builder", PW, role="operator")
    operators.disable_operator(st, "bob")
    capsys.readouterr()
    assert cli.main(["operator", "list"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines == ["adm\tAdmin\tadmin\tenabled\tadm@example.org",
                     "ann\tAnn\toperator\tenabled\tann@example.org",
                     "bob\tBob Builder\toperator\tdisabled\t-"]
