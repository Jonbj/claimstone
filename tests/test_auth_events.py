import json
import os
import stat

import pytest

from claimstone import auth_events


def test_records_are_owner_only_single_lines_without_control_characters(tmp_path):
    auth_events.record(tmp_path, "login_failed", id="a\nb" + "x" * 300, method="password",
                       remote="127.0.0.1", detail="bad_password", now="2026-10-12T00:00:00+00:00")
    path = tmp_path / "auth_events.jsonl"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    (line,) = path.read_text().splitlines()
    row = json.loads(line)
    assert row["event"] == "login_failed" and "\n" not in row["id"] and len(row["id"]) <= 200
    assert row["at"] == "2026-10-12T00:00:00+00:00"


def test_an_unknown_event_name_is_refused(tmp_path):
    with pytest.raises(ValueError):
        auth_events.record(tmp_path, "something_else")
    assert not (tmp_path / "auth_events.jsonl").exists()


def test_a_hostile_id_cannot_forge_a_second_line(tmp_path):
    forged = '"}\n{"event": "login_ok", "id": "admin"}\t\r '
    auth_events.record(tmp_path, "login_failed", id=forged, now="2026-10-12T00:00:00+00:00")
    auth_events.record(tmp_path, "logout", id="b", now="2026-10-12T00:00:01+00:00")
    lines = (tmp_path / "auth_events.jsonl").read_text().splitlines()
    assert len(lines) == 2
    rows = [json.loads(line) for line in lines]
    assert [r["event"] for r in rows] == ["login_failed", "logout"]
    assert not any(c in rows[0]["id"] for c in "\n\t\r ")


def test_the_directory_is_created_owner_only(tmp_path):
    target = tmp_path / "state"
    auth_events.record(target, "logout", id="a")
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o700
