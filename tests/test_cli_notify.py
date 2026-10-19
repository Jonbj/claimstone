"""`claimstone notify`: derive the outbox, and optionally drain it (issue #5).

The command is information only. It never authorizes anything, and a dry run writes nothing:
the point of a preview is that it leaves no trace to be mistaken for a sent message.
"""

from __future__ import annotations

from claimstone import cli, notifications, operations
from claimstone.config import load_project
from claimstone.store import Store


def _project(tmp_path):
    project = load_project("projects/example-news-and-returns")
    return project, Store(project.name, base=tmp_path)


def _planned(store: Store) -> str:
    plan = {"flow_id": "flow-1", "project": "example-news-and-returns",
            "stage": "acquire", "candidate_key": "c1"}
    operation_id = operations._digest(plan)
    body = {"operation_version": operations.OPERATIONS_VERSION,
            "operation_id": operation_id, "plan_id": operation_id,
            "flow_id": "flow-1", "actor": "test", "code_sha256": "sha",
            "event": "planned", "plan": plan}
    store.append(operations.LEDGER,
                 body | {"event_id": operations._digest(body),
                         "at": "2026-10-18T10:00:00+00:00"})
    return operation_id


def test_notify_records_the_outbox_and_sends_nothing_without_a_channel(tmp_path, capsys):
    project, store = _project(tmp_path)
    operation_id = _planned(store)
    status = cli.main(["notify", str(project.root), "--store", str(tmp_path)])
    assert status == 0
    out = capsys.readouterr().out
    assert "1 new event" in out and "no channel" in out
    rows = list(store.read(notifications.LEDGER))
    assert [row["record"] for row in rows] == ["started", "event"]
    assert rows[1]["ids"] == [operation_id]


def test_a_second_run_does_not_repeat_an_event(tmp_path, capsys):
    project, store = _project(tmp_path)
    _planned(store)
    assert cli.main(["notify", str(project.root), "--store", str(tmp_path)]) == 0
    capsys.readouterr()
    assert cli.main(["notify", str(project.root), "--store", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "0 new event" in out
    assert len([row for row in store.read(notifications.LEDGER)
                if row["record"] == "event"]) == 1


def test_a_dry_run_writes_nothing(tmp_path, capsys):
    project, store = _project(tmp_path)
    _planned(store)
    status = cli.main(["notify", str(project.root), "--store", str(tmp_path), "--dry-run"])
    assert status == 0
    out = capsys.readouterr().out
    assert "plan_awaiting_authorization" in out
    assert list(store.read(notifications.LEDGER)) == []


def test_the_telegram_switch_refuses_to_run_without_credentials(tmp_path, capsys, monkeypatch):
    project, store = _project(tmp_path)
    _planned(store)
    monkeypatch.delenv("CLAIMSTONE_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("CLAIMSTONE_TELEGRAM_CHAT_ID", raising=False)
    status = cli.main(["notify", str(project.root), "--store", str(tmp_path),
                       "--channel", "telegram"])
    assert status == 2
    assert "CLAIMSTONE_TELEGRAM" in capsys.readouterr().err


def test_a_drain_records_a_sent_attempt(tmp_path, capsys, monkeypatch):
    project, store = _project(tmp_path)
    _planned(store)

    class Channel:
        name = "telegram"

        def send(self, event):
            return notifications.SendResult("SENT", http_status=200)

    monkeypatch.setattr(notifications.TelegramChannel, "from_environment",
                        classmethod(lambda cls: Channel()))
    status = cli.main(["notify", str(project.root), "--store", str(tmp_path),
                       "--channel", "telegram"])
    assert status == 0
    out = capsys.readouterr().out
    assert "1 sent" in out
    attempts = [row for row in store.read(notifications.LEDGER)
                if row["record"] == "attempt"]
    assert len(attempts) == 1 and attempts[0]["outcome"] == "SENT"


def test_an_unknown_channel_is_a_usage_error(tmp_path, capsys):
    project, _store = _project(tmp_path)
    assert cli.main(["notify", str(project.root), "--store", str(tmp_path),
                     "--channel", "carrier-pigeon"]) == 2
    assert "telegram" in capsys.readouterr().err


def test_an_invalid_since_is_a_usage_error(tmp_path, capsys):
    project, _store = _project(tmp_path)
    assert cli.main(["notify", str(project.root), "--store", str(tmp_path),
                     "--since", "yesterday"]) == 2
    assert "since" in capsys.readouterr().err


def test_a_damaged_operation_ledger_is_a_sentence_not_a_traceback(tmp_path, capsys):
    project, store = _project(tmp_path)
    store.root.mkdir(parents=True)
    store.path(operations.LEDGER).write_text('{"not": "an operation"}\n')
    status = cli.main(["notify", str(project.root), "--store", str(tmp_path)])
    assert status == 1
    assert "error:" in capsys.readouterr().err
