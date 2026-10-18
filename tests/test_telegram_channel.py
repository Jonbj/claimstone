"""Telegram is a delivery channel on the notification outbox, information only.

It sends one message per event, to one chat, through one host. The bot token is part of the
request URL by Telegram's design; that is exactly why it must never reach a ledger, a log or
a message. These tests plant a recognisable token and grep for it in everything that survives
the send.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from claimstone import notifications
from claimstone.store import Store

TOKEN = "123456:AAH-secret-token-that-must-never-be-written"
CHAT = "424242"


class _Telegram:
    """The one endpoint this channel is allowed to call, reduced to a recorded request."""

    def __init__(self, status: int = 200, body: dict | None = None,
                 headers: dict[str, str] | None = None, delay: float = 0.0):
        self.requests: list[dict] = []
        self.status = status
        self.body = body if body is not None else {"ok": True, "result": {"message_id": 1}}
        self.headers = headers or {}
        self.delay = delay
        telegram = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - http.server's naming
                length = int(self.headers.get("Content-Length") or 0)
                telegram.requests.append({
                    "method": "POST", "path": self.path,
                    "body": json.loads(self.rfile.read(length) or b"{}"),
                    "user_agent": self.headers.get("User-Agent"),
                    "content_type": self.headers.get("Content-Type"),
                })
                if telegram.delay:
                    time.sleep(telegram.delay)
                data = json.dumps(telegram.body).encode("utf-8")
                self.send_response(telegram.status)
                for name, value in telegram.headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):  # noqa: N802
                telegram.requests.append({"method": "GET", "path": self.path})
                self.send_response(404)
                self.end_headers()

            def log_message(self, *_args):  # noqa: D401 - silence the stub
                return

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        return self

    def __exit__(self, *_exc):
        self.httpd.shutdown()
        self.thread.join(timeout=5)


def _event(store: Store) -> dict:
    return notifications.record(store, {
        "event": "needs_person", "reason": "signature_required", "project": "example",
        "subject": "flow:abc/Q02", "ids": ["Q02"], "count": 1, "occurrence": "profile-1",
        "occurred_at": "2026-10-18T10:00:00+00:00"})


def _channel(telegram: _Telegram, **changes) -> notifications.TelegramChannel:
    options = {"endpoint": telegram.url, "portal_url": "http://127.0.0.1:8788"}
    options.update(changes)
    return notifications.TelegramChannel(TOKEN, CHAT, **options)


def test_the_switch_is_the_presence_of_both_credentials(monkeypatch):
    monkeypatch.delenv("CLAIMSTONE_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("CLAIMSTONE_TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(notifications.ChannelNotConfigured, match="CLAIMSTONE_TELEGRAM"):
        notifications.TelegramChannel.from_environment()
    monkeypatch.setenv("CLAIMSTONE_TELEGRAM_BOT_TOKEN", TOKEN)
    with pytest.raises(notifications.ChannelNotConfigured, match="CLAIMSTONE_TELEGRAM_CHAT_ID"):
        notifications.TelegramChannel.from_environment()
    monkeypatch.setenv("CLAIMSTONE_TELEGRAM_CHAT_ID", CHAT)
    channel = notifications.TelegramChannel.from_environment()
    assert channel.name == "telegram"
    assert channel.chat_id == CHAT


def test_one_message_per_event_with_ids_and_counts_only(tmp_path):
    store = Store("example", tmp_path)
    event = _event(store)
    with _Telegram() as telegram:
        result = _channel(telegram).send(event)
    assert result.outcome == "SENT"
    (request,) = telegram.requests
    assert request["method"] == "POST"
    assert request["path"] == f"/bot{TOKEN}/sendMessage"
    assert request["content_type"] == "application/json"
    assert "Claimstone" in request["user_agent"]
    assert request["body"]["chat_id"] == CHAT
    text = request["body"]["text"]
    assert "example" in text and "Q02" in text and "signature required" in text
    assert "http://127.0.0.1:8788/" in text
    assert request["body"]["disable_web_page_preview"] is True


def test_the_channel_never_asks_for_updates(tmp_path):
    """No reply handling, no commands: the only request is the send."""
    store = Store("example", tmp_path)
    with _Telegram() as telegram:
        _channel(telegram).send(_event(store))
    assert [request["path"] for request in telegram.requests] == [
        f"/bot{TOKEN}/sendMessage"]


def test_a_telegram_refusal_with_http_200_is_not_a_success(tmp_path):
    with _Telegram(body={"ok": False, "description": "chat not found"}) as telegram:
        result = _channel(telegram).send(_event(Store("example", tmp_path)))
    assert result.outcome == "FAILED"
    assert result.http_status == 200
    assert "chat not found" in result.detail


def test_a_429_records_the_rate_limit_and_the_wait(tmp_path):
    body = {"ok": False, "description": "Too Many Requests",
            "parameters": {"retry_after": 7}}
    with _Telegram(status=429, body=body) as telegram:
        result = _channel(telegram).send(_event(Store("example", tmp_path)))
    assert result.outcome == "RATE_LIMITED"
    assert result.failure_class == "RATE_LIMITED"
    assert result.http_status == 429
    assert "7" in result.detail


def test_a_transport_error_is_a_connection_failure_not_a_silence(tmp_path):
    closed = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = closed.server_address[1]
    closed.server_close()
    channel = notifications.TelegramChannel(TOKEN, CHAT, endpoint=f"http://127.0.0.1:{port}")
    result = channel.send(_event(Store("example", tmp_path)))
    assert result.outcome == "CONNECTION"
    assert result.failure_class == "CONNECTION"


def test_a_timeout_is_explicit(tmp_path):
    with _Telegram(delay=0.3) as telegram:
        result = _channel(telegram, timeout=0.05).send(_event(Store("example", tmp_path)))
    assert result.outcome == "TIMEOUT"


def test_a_redirect_is_refused_and_the_token_is_not_carried_to_another_host(tmp_path):
    """Following a redirect would carry the token in the URL to a host the operator did not
    choose. The only host this channel contacts is the API endpoint it was built with."""
    with _Telegram(status=302, body={}, headers={"Location": "http://127.0.0.1:1/steal"}) as telegram:
        result = _channel(telegram).send(_event(Store("example", tmp_path)))
    assert result.outcome == "FAILED"
    assert result.failure_class == "REDIRECT_REFUSED"
    assert len(telegram.requests) == 1


def test_the_token_never_reaches_the_outbox(tmp_path):
    store = Store("example", tmp_path)
    _event(store)
    with _Telegram(status=500, body={"ok": False, "description": f"bad {TOKEN}"}) as telegram:
        summary = notifications.deliver(store, _channel(telegram))
    assert summary["failed"] == 1
    ledger = store.path(notifications.LEDGER).read_text()
    assert TOKEN not in ledger
    assert "123456" not in ledger
    assert "AAH-secret" not in ledger


def test_the_endpoint_must_be_a_base_url():
    with pytest.raises(ValueError, match="base URL"):
        notifications.TelegramChannel(TOKEN, CHAT, endpoint="https://api.telegram.org/bot")
    with pytest.raises(ValueError, match="http"):
        notifications.TelegramChannel(TOKEN, CHAT, endpoint="api.telegram.org")
