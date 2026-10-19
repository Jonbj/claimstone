"""The e-mail channel on the notification outbox (issue #6).

E-mail is information only, and its content rule is stricter than Telegram's: mail is stored
in clear by third parties, so the subject and body carry ids, a count and a portal link —
never a title, quote, claim or source content. Credentials, the recipient and the SMTP host
live in the environment and never enter a ledger, a detail or a message.

The channel is exercised against a fake SMTP object for the failure classes, and against a
real local SMTP stub for one delivered message. Plaintext exists only in that last test: the
environment switch cannot select it.
"""

from __future__ import annotations

import smtplib
import socketserver
import threading
from email import message_from_bytes, policy

import pytest

from claimstone import notifications

EVENT = {
    "event": "needs_person", "reason": "signature_required", "code": "ADJUDICATION",
    "project": "example-news-and-returns", "subject": "Q03", "ids": ["Q03", "Q07"],
    "count": 2, "occurrence": "occ", "occurred_at": "2026-10-18T10:00:00+00:00",
}

SMTP_VARIABLES = {
    "CLAIMSTONE_SMTP_HOST": "smtp.example.org",
    "CLAIMSTONE_SMTP_FROM": "claimstone@example.org",
    "CLAIMSTONE_SMTP_TO": "operator@example.org",
}


def _configure(monkeypatch, **overrides):
    for name in list(SMTP_VARIABLES) + [
            "CLAIMSTONE_SMTP_PORT", "CLAIMSTONE_SMTP_SECURITY",
            "CLAIMSTONE_SMTP_USERNAME", "CLAIMSTONE_SMTP_PASSWORD",
            "CLAIMSTONE_PORTAL_URL"]:
        monkeypatch.delenv(name, raising=False)
    values = SMTP_VARIABLES | overrides
    for name, value in values.items():
        monkeypatch.setenv(name, value)


class FakeSMTP:
    """Records the conversation; every method can be overridden by the class attribute."""

    instances: list["FakeSMTP"] = []
    fail_with: Exception | None = None

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.calls: list[object] = []
        self.message = None
        FakeSMTP.instances.append(self)

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self, *, context=None):
        self.calls.append("starttls")
        self.context = context

    def login(self, username, password):
        if FakeSMTP.fail_with is not None:
            raise FakeSMTP.fail_with
        self.calls.append(("login", username, password))

    def send_message(self, message):
        if FakeSMTP.fail_with is not None:
            raise FakeSMTP.fail_with
        self.calls.append("send_message")
        self.message = message

    def close(self):
        self.calls.append("close")


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances = []
    FakeSMTP.fail_with = None
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


def test_the_switch_needs_host_sender_and_recipient(monkeypatch):
    for name in SMTP_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(notifications.ChannelNotConfigured) as caught:
        notifications.EmailChannel.from_environment()
    message = str(caught.value)
    for name in SMTP_VARIABLES:
        assert name in message
    assert "smtp.example.org" not in message


def test_half_a_credential_pair_is_a_configuration_error(monkeypatch):
    _configure(monkeypatch, CLAIMSTONE_SMTP_USERNAME="claimstone")
    with pytest.raises(notifications.ChannelNotConfigured) as caught:
        notifications.EmailChannel.from_environment()
    assert "CLAIMSTONE_SMTP_PASSWORD" in str(caught.value)


def test_the_environment_cannot_select_plaintext(monkeypatch):
    _configure(monkeypatch, CLAIMSTONE_SMTP_SECURITY="none")
    with pytest.raises(notifications.ChannelNotConfigured) as caught:
        notifications.EmailChannel.from_environment()
    assert "starttls" in str(caught.value) and "tls" in str(caught.value)


def test_an_invalid_port_is_a_sentence_not_a_traceback(monkeypatch):
    _configure(monkeypatch, CLAIMSTONE_SMTP_PORT="not-a-port")
    with pytest.raises(notifications.ChannelNotConfigured):
        notifications.EmailChannel.from_environment()


def test_one_recipient_per_channel_in_this_version(monkeypatch):
    _configure(monkeypatch, CLAIMSTONE_SMTP_TO="one@example.org, two@example.org")
    with pytest.raises(notifications.ChannelNotConfigured) as caught:
        notifications.EmailChannel.from_environment()
    assert "CLAIMSTONE_SMTP_TO" in str(caught.value)


def test_the_default_port_follows_the_security_mode(monkeypatch):
    _configure(monkeypatch)
    assert notifications.EmailChannel.from_environment().port == 587
    _configure(monkeypatch, CLAIMSTONE_SMTP_SECURITY="tls")
    assert notifications.EmailChannel.from_environment().port == 465
    _configure(monkeypatch, CLAIMSTONE_SMTP_PORT="2525")
    assert notifications.EmailChannel.from_environment().port == 2525


def test_the_message_carries_ids_a_count_and_a_way_in_only(monkeypatch):
    _configure(monkeypatch, CLAIMSTONE_PORTAL_URL="http://127.0.0.1:8788")
    channel = notifications.EmailChannel.from_environment()
    message = channel.compose(EVENT)
    subject = str(message["Subject"])
    body = message.get_body(preferencelist=("plain",)).get_content()

    assert "signature required" in subject and "2" in subject
    assert "Q03" in body and "Q07" in body and "ADJUDICATION" in body
    assert "http://127.0.0.1:8788/" in body
    assert message.get_body(preferencelist=("html",)) is None
    assert message["From"] == "claimstone@example.org"
    assert message["To"] == "operator@example.org"
    assert "Claimstone" in str(message["X-Mailer"])
    assert message.get_content_type() == "text/plain"


def test_starttls_is_negotiated_before_login(monkeypatch, smtp):
    _configure(monkeypatch, CLAIMSTONE_SMTP_USERNAME="claimstone",
               CLAIMSTONE_SMTP_PASSWORD="hunter2")
    result = notifications.EmailChannel.from_environment().send(EVENT)
    assert result.outcome == "SENT"
    server = smtp.instances[0]
    assert server.calls.index("starttls") < server.calls.index(
        ("login", "claimstone", "hunter2"))
    assert server.context is not None
    assert server.context.check_hostname is True
    assert server.context.verify_mode == 2  # ssl.CERT_REQUIRED
    assert server.message is not None
    assert server.calls[-1] == "close"


def test_implicit_tls_wraps_the_connection_from_the_start(monkeypatch, smtp):
    _configure(monkeypatch, CLAIMSTONE_SMTP_SECURITY="tls")
    result = notifications.EmailChannel.from_environment().send(EVENT)
    assert result.outcome == "SENT"
    assert smtp.instances[0].context is not None
    assert "starttls" not in smtp.instances[0].calls


def test_a_failed_login_is_a_recorded_class_and_the_secret_is_redacted(monkeypatch, smtp):
    _configure(monkeypatch, CLAIMSTONE_SMTP_USERNAME="claimstone",
               CLAIMSTONE_SMTP_PASSWORD="hunter2")
    smtp.fail_with = smtplib.SMTPAuthenticationError(
        535, b"5.7.8 hunter2 rejected for operator@example.org at smtp.example.org")
    result = notifications.EmailChannel.from_environment().send(EVENT)
    assert result.outcome == "FAILED"
    assert result.failure_class == "AUTH_535"
    for secret in ("hunter2", "claimstone", "operator@example.org", "smtp.example.org"):
        assert secret not in (result.detail or "")


def test_refused_recipients_are_their_own_class(monkeypatch, smtp):
    _configure(monkeypatch)
    smtp.fail_with = smtplib.SMTPRecipientsRefused(
        {"operator@example.org": (550, b"no such user")})
    result = notifications.EmailChannel.from_environment().send(EVENT)
    assert result.outcome == "FAILED" and result.failure_class == "RECIPIENTS_REFUSED"
    assert "operator@example.org" not in (result.detail or "")


def test_an_smtp_error_carries_its_code(monkeypatch, smtp):
    _configure(monkeypatch)
    smtp.fail_with = smtplib.SMTPResponseException(451, b"try later")
    result = notifications.EmailChannel.from_environment().send(EVENT)
    assert result.outcome == "FAILED" and result.failure_class == "SMTP_451"


def test_a_timeout_is_a_timeout(monkeypatch, smtp):
    _configure(monkeypatch)
    smtp.fail_with = TimeoutError("timed out")
    result = notifications.EmailChannel.from_environment().send(EVENT)
    assert result.outcome == "TIMEOUT"


def test_an_unreachable_server_is_a_connection_error(monkeypatch):
    class Refused:
        def __init__(self, *args, **kwargs):
            raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(smtplib, "SMTP", Refused)
    _configure(monkeypatch)
    result = notifications.EmailChannel.from_environment().send(EVENT)
    assert result.outcome == "CONNECTION" and result.failure_class == "CONNECTION"


class _StubSMTPHandler(socketserver.StreamRequestHandler):
    """The smallest SMTP conversation that accepts one message."""

    def handle(self):
        self.wfile.write(b"220 localhost ESMTP stub\r\n")
        in_data = False
        data = bytearray()
        for raw in self.rfile:
            line = raw.rstrip(b"\r\n")
            if in_data:
                if line == b".":
                    in_data = False
                    self.server.messages.append(bytes(data))
                    self.wfile.write(b"250 queued\r\n")
                    data = bytearray()
                else:
                    data.extend(raw)
                continue
            command = line.split(b" ", 1)[0].upper()
            if command == b"EHLO":
                self.wfile.write(b"250-localhost\r\n250 HELP\r\n")
            elif command in (b"MAIL", b"RCPT"):
                self.wfile.write(b"250 ok\r\n")
            elif command == b"DATA":
                in_data = True
                self.wfile.write(b"354 send it\r\n")
            elif command == b"QUIT":
                self.wfile.write(b"221 bye\r\n")
                return
            else:
                self.wfile.write(b"250 ok\r\n")


class _StubSMTP(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    messages: list[bytes]


def test_a_real_smtp_conversation_delivers_one_plain_text_message(monkeypatch):
    with _StubSMTP(("127.0.0.1", 0), _StubSMTPHandler) as server:
        server.messages = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            channel = notifications.EmailChannel(
                "127.0.0.1", "claimstone@example.org", "operator@example.org",
                port=server.server_address[1], security="none", timeout=5.0,
                portal_url="http://127.0.0.1:8788")
            result = channel.send(EVENT)
        finally:
            server.shutdown()
            thread.join(timeout=5)
    assert result.outcome == "SENT"
    assert len(server.messages) == 1
    parsed = message_from_bytes(server.messages[0], policy=policy.default)
    assert "signature required" in str(parsed["Subject"])
    assert parsed["To"] == "operator@example.org"
    body = parsed.get_body(preferencelist=("plain",)).get_content()
    assert "Q03" in body and "Q07" in body
