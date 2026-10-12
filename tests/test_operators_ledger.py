"""The operators ledger's identity rules (design 2026-10-12). No socket, no server."""

from __future__ import annotations

import json

import pytest

from claimstone import operators
from claimstone.operators import OperatorError

PW = "correct horse battery"


@pytest.fixture()
def d(tmp_path):
    return tmp_path / "state"


def test_first_person_is_admin_later_ones_operators(d):
    assert operators.add_operator(d, "a", "Alpha", PW)["role"] == "admin"
    assert operators.add_operator(d, "b", "Beta", PW)["role"] == "operator"
    assert operators.people(d)["b"]["role"] == "operator"


def test_legacy_rows_read_as_admin_and_still_verify(d):
    d.mkdir()
    legacy = {"operator_version": 1, "id": "old", "name": "Old", "scrypt": operators.SCRYPT,
              "salt": "00" * 16, "hash": operators._hash("legacy password!", bytes(16), operators.SCRYPT),
              "created_at": "2026-10-01T00:00:00+00:00"}
    (d / "operators.jsonl").write_text(json.dumps(legacy) + "\n" + json.dumps(
        {"operator_version": 1, "id": "old", "disabled": True, "disabled_at": "x"}) + "\n")
    assert operators.people(d)["old"]["role"] == "admin"
    assert operators.load(d) == {}                       # disabled
    operators.enable_operator(d, "old", by="cli")
    assert operators.verify(operators.load(d)["old"], "legacy password!")


@pytest.mark.parametrize("password", ["short", "x" * 257, "alpha-user-id"])
def test_password_rule(d, password):
    with pytest.raises(OperatorError):
        operators.add_operator(d, "alpha-user-id", "Alpha", password)


def test_an_id_is_never_reused(d):
    operators.add_operator(d, "keeper", "Keeper", PW)      # the admin who stays
    operators.add_operator(d, "a", "Alpha", PW)
    operators.disable_operator(d, "a", by="cli")
    with pytest.raises(OperatorError, match="already recorded"):
        operators.add_operator(d, "a", "Again", PW)


def test_email_is_unique_among_enabled_people_and_case_folded(d):
    operators.add_operator(d, "a", "Alpha", PW, email="Ann@Example.org")
    with pytest.raises(OperatorError, match="email"):
        operators.add_operator(d, "b", "Beta", PW, email="ann@example.org")
    operators.add_operator(d, "b", "Beta", PW, email="bob@example.org")
    with pytest.raises(OperatorError, match="email"):
        operators.set_email(d, "b", "ANN@example.org", by="a")


def test_last_admin_cannot_be_disabled_or_demoted(d):
    operators.add_operator(d, "a", "Alpha", PW)
    with pytest.raises(OperatorError, match="last admin"):
        operators.disable_operator(d, "a", by="a")
    with pytest.raises(OperatorError, match="last admin"):
        operators.set_role(d, "a", "operator", by="a")
    operators.add_operator(d, "b", "Beta", PW, role="admin")
    operators.set_role(d, "a", "operator", by="b")        # now allowed
    with pytest.raises(OperatorError, match="last admin"):
        operators.disable_operator(d, "b", by="b")


def test_password_change_replaces_the_hash_and_can_demand_a_change(d):
    operators.add_operator(d, "a", "Alpha", PW)
    operators.set_password(d, "a", "a brand new password", by="a", must_change=True)
    person = operators.load(d)["a"]
    assert operators.verify(person, "a brand new password") and not operators.verify(person, PW)
    assert person["must_change_password"] is True
    operators.set_password(d, "a", "yet another password", by="a")
    assert operators.load(d)["a"]["must_change_password"] is False


def test_google_link_rules(d):
    operators.add_operator(d, "a", "Alpha", PW, email="a@example.org")
    operators.add_operator(d, "b", "Beta", PW, email="b@example.org")
    operators.link_google(d, "a", sub="sub-1", email="A@example.org", by="a")
    assert operators.find_by_sub(d, "sub-1")["id"] == "a"
    with pytest.raises(OperatorError, match="already linked"):
        operators.link_google(d, "b", sub="sub-1", email="b@example.org", by="b")
    with pytest.raises(OperatorError, match="already has"):
        operators.link_google(d, "a", sub="sub-2", email="a@example.org", by="a")
    with pytest.raises(OperatorError, match="email"):
        operators.link_google(d, "b", sub="sub-3", email="other@example.org", by="b")
    operators.unlink_google(d, "a", by="a")
    assert operators.find_by_sub(d, "sub-1") is None
    operators.link_google(d, "b", sub="sub-1", email="b@example.org", by="b")   # free again


def test_find_by_email_returns_enabled_people_only(d):
    operators.add_operator(d, "a", "Alpha", PW, email="a@example.org")
    operators.add_operator(d, "b", "Beta", PW, email="b@example.org")
    operators.disable_operator(d, "b", by="a")
    assert operators.find_by_email(d, "A@example.org")["id"] == "a"
    assert operators.find_by_email(d, "b@example.org") is None


def test_new_rows_say_who_and_when_and_hold_no_plaintext(d):
    operators.add_operator(d, "a", "Alpha", PW, by="cli")
    operators.set_password(d, "a", "a brand new password", by="a")
    text = (d / "operators.jsonl").read_text()
    assert "correct horse" not in text and "brand new" not in text
    rows = [json.loads(line) for line in text.splitlines()]
    assert [r["kind"] for r in rows] == ["created", "password_set"]
    assert all(r["operator_version"] == 2 and r["by"] and r["at"] for r in rows)


def test_a_v1_reader_still_sees_a_disabled_person_as_disabled(d):
    operators.add_operator(d, "a", "Alpha", PW)
    operators.add_operator(d, "b", "Beta", PW)
    operators.disable_operator(d, "b", by="a")
    active = {}
    for row in operators._rows(d):                      # version-1 fold, after a rollback
        if row.get("disabled"):
            active.pop(str(row["id"]), None)
        elif "hash" in row:
            active[str(row["id"])] = row
    assert set(active) == {"a"}


def test_a_malformed_or_repeated_row_does_not_break_load(d):
    operators.add_operator(d, "a", "Alpha", PW)
    with open(d / "operators.jsonl", "a") as handle:
        handle.write(json.dumps({"operator_version": 2, "id": "x", "at": "t"}) + "\n")
        handle.write(json.dumps({"operator_version": 2, "kind": "created", "id": "a", "name": "Evil",
                                 "salt": "00" * 16, "hash": "00" * 32}) + "\n")
    assert set(operators.load(d)) == {"a"}
    assert operators.load(d)["a"]["name"] == "Alpha"      # first created row wins


def test_lock_file_is_owner_only(d):
    import os
    import stat
    operators.add_operator(d, "a", "Alpha", PW)
    assert stat.S_IMODE(os.stat(d / ".operators.lock").st_mode) == 0o600
    assert stat.S_IMODE(os.stat(d).st_mode) == 0o700


def test_ids_with_padding_or_control_characters_are_refused(d):
    operators.add_operator(d, "a", "Alpha", PW)
    for bad in ("a ", " a", "b\tc", "b\x00c"):
        with pytest.raises(OperatorError):
            operators.add_operator(d, bad, "Bad", PW)


def test_an_email_with_inner_whitespace_is_refused(d):
    with pytest.raises(OperatorError, match="email"):
        operators.add_operator(d, "a", "Alpha", PW, email="a\t@example.org")


def test_enable_refuses_when_the_email_was_taken_meanwhile(d):
    operators.add_operator(d, "a", "Alpha", PW, email="a@example.org")
    operators.add_operator(d, "b", "Beta", PW, email="b@example.org")
    operators.disable_operator(d, "b", by="a")
    operators.add_operator(d, "c", "Gamma", PW, email="b@example.org")     # a disabled address is free
    with pytest.raises(OperatorError, match="email"):
        operators.enable_operator(d, "b", by="a")


def test_link_google_refuses_a_disabled_person(d):
    operators.add_operator(d, "a", "Alpha", PW)
    operators.add_operator(d, "b", "Beta", PW, email="b@example.org")
    operators.disable_operator(d, "b", by="a")
    with pytest.raises(OperatorError, match="disabled"):
        operators.link_google(d, "b", sub="s", email="b@example.org", by="b")


def _race(directory, ident):
    try:
        operators.add_operator(directory, ident, ident, PW, email="same@example.org")
        return True
    except OperatorError:
        return False


def test_two_processes_cannot_both_claim_one_email(d):
    import multiprocessing
    with multiprocessing.get_context("fork").Pool(2) as pool:
        results = pool.starmap(_race, [(d, "p1"), (d, "p2")])
    assert sorted(results) == [False, True]
