"""The notification outbox: events worth telling a person about, and every attempt to tell them.

An event is derived from the ledgers by `claimstone.notify`, never written by a stage. It is
identified by `event_key`, a hash of the occurrence it describes, and `record()` appends it at
most once. That is what makes a restart safe: a second drain derives the same key, finds the
event already in the outbox, and sends nothing.

**No source content ever enters this ledger.** An event is a fixed shape — an event name, a
reason from a closed set, a project, a subject id, a list of ids and a count. There is no
free-text field, on purpose: a title, a quote or an abstract has nowhere to go. `detail` on an
attempt is the channel's short cause, cleaned and length-bounded; a channel that handles a
secret is responsible for redacting it before returning it.

Attempts are facts too. A send that failed is an `attempt` row with an outcome and a cause, not
a missing message; a failure is never dropped to make a drain look clean.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .store import Store

LEDGER = "notifications.jsonl"
OUTBOX_VERSION = 1

EVENT = "event"
ATTEMPT = "attempt"
START = "started"

MAX_ATTEMPTS = 3
RETRY_AFTER_SECONDS = 15 * 60
RATE_LIMIT = 20
DETAIL_LIMIT = 300
ID_LIMIT = 200
IDS_SHOWN = 10

# event name -> the reasons it may carry. Closed on purpose: a new reason is a code change
# with a sentence here, not a string a caller invents.
REASONS: dict[str, frozenset[str]] = {
    "needs_person": frozenset({
        "plan_awaiting_authorization", "signature_required", "integrity_error"}),
    "retry": frozenset({
        "copy_obtained_after_retry", "candidate_given_up", "retry_ceiling_used",
        "retry_window_expired", "host_breaker_open"}),
    "finished": frozenset({"batch_completed", "round_below_floor"}),
    "failure": frozenset({"operation_failed"}),
}

OUTCOMES = frozenset({"SENT", "FAILED", "REFUSED", "RATE_LIMITED", "TIMEOUT", "CONNECTION"})

# The only input keys an event may have. event_key, record and outbox_version are computed.
EVENT_FIELDS = frozenset({
    "event", "reason", "project", "subject", "ids", "count", "occurrence", "occurred_at",
    "code"})
_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,60}$")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _clean(value: Any, *, limit: int = ID_LIMIT) -> str:
    """One line, printable, bounded. A newline in a ledger value would forge a row."""
    text = " ".join(str(value).split())
    text = "".join(character if character.isprintable() else " " for character in text)
    return text[:limit]


def _timestamp(value: str | None) -> str:
    text = value or _now()
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"occurred_at is not an ISO timestamp: {text!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError("occurred_at needs a timezone: a naive timestamp is ambiguous")
    return parsed.isoformat(timespec="seconds")


def _identity(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": row["event"], "reason": row["reason"], "project": row["project"],
        "subject": row["subject"], "ids": row["ids"], "count": row["count"],
        "occurrence": row["occurrence"], "code": row["code"],
    }


def event_key(identity: dict[str, Any]) -> str:
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True)
    return "n1-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_event(row: dict[str, Any]) -> dict[str, Any]:
    unknown = set(row) - EVENT_FIELDS
    if unknown:
        raise ValueError(f"{sorted(unknown)[0]!r} is not an event field")
    event = row.get("event")
    if event not in REASONS:
        raise ValueError(f"unknown event: {event!r}")
    reason = row.get("reason")
    if reason not in REASONS[event]:
        raise ValueError(f"reason {reason!r} does not belong to event {event!r}")
    project = _clean(row.get("project"))
    if not project:
        raise ValueError("an event needs a project")
    subject = _clean(row.get("subject"))
    if not subject:
        raise ValueError("an event needs a subject")
    ids = row.get("ids", [])
    if not isinstance(ids, (list, tuple)) or not ids:
        raise ValueError("an event needs at least one id")
    cleaned_ids = sorted({_clean(item) for item in ids if _clean(item)})
    if not cleaned_ids:
        raise ValueError("an event needs at least one non-empty id")
    count = row.get("count", 1)
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("an event's count is a positive integer")
    code = row.get("code")
    if code is not None and (not isinstance(code, str) or not _CODE.match(code)):
        raise ValueError(f"a code is an identifier, not prose: {code!r}")
    return {
        "event": event,
        "reason": reason,
        "project": project,
        "subject": subject,
        "ids": cleaned_ids,
        "count": count,
        "occurrence": _clean(row.get("occurrence", "")),
        "occurred_at": _timestamp(row.get("occurred_at")),
        "code": code,
    }


def key(event: dict[str, Any]) -> str:
    """The idempotency key of an event, computed without writing it."""
    return event_key(_identity(_validate_event(event)))


def record(store: Store, event: dict[str, Any]) -> dict[str, Any]:
    """Append an event unless its occurrence is already in the outbox; return the row."""
    validated = _validate_event(event)
    event_id = event_key(_identity(validated))
    with store.writer_lock():
        for existing in events(store):
            if existing["event_key"] == event_id:
                return existing
        row = {"record": EVENT, "outbox_version": OUTBOX_VERSION,
               "event_key": event_id, **validated}
        store.append(LEDGER, row)
    return row


def start(store: Store, *, now: str | None = None) -> dict[str, Any]:
    """Mark the outbox's first drain. One-shot history before this is not replayed.

    Idempotent: a second call returns the first row. State-derived events are unaffected —
    what still needs a person is sent on the first drain whatever its age."""
    moment = _timestamp(now)
    with store.writer_lock():
        for row in store.read(LEDGER):
            if row.get("record") == START:
                return row
        row = {"record": START, "outbox_version": OUTBOX_VERSION, "at": moment}
        store.append(LEDGER, row)
    return row


def watermark(store: Store) -> str | None:
    """When one-shot events begin to count, or None before the outbox was started."""
    for row in store.read(LEDGER):
        if row.get("record") == START:
            return row["at"]
    return None


def _attempts(store: Store) -> list[dict[str, Any]]:
    return [row for row in store.read(LEDGER) if row.get("record") == ATTEMPT]


def events(store: Store) -> list[dict[str, Any]]:
    return [row for row in store.read(LEDGER) if row.get("record") == EVENT]


def attempt(store: Store, key: str, channel: str, outcome: str, *,
            http_status: int | None = None, failure_class: str | None = None,
            detail: str | None = None, now: str | None = None) -> dict[str, Any]:
    """Append one delivery attempt. Refuses a key the outbox never recorded."""
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown outcome: {outcome!r}")
    channel = _clean(channel)
    if not channel:
        raise ValueError("an attempt needs a channel")
    with store.writer_lock():
        known = {row["event_key"] for row in events(store)}
        if key not in known:
            raise ValueError(f"unknown event: {key!r}")
        number = 1 + sum(1 for row in _attempts(store)
                         if row["event_key"] == key and row["channel"] == channel)
        row = {
            "record": ATTEMPT, "outbox_version": OUTBOX_VERSION, "event_key": key,
            "channel": channel, "attempt": number, "outcome": outcome,
            "http_status": http_status, "failure_class": failure_class,
            "detail": _clean(detail, limit=DETAIL_LIMIT) if detail else None,
            "at": _timestamp(now),
        }
        store.append(LEDGER, row)
    return row


@dataclass(frozen=True)
class SendResult:
    outcome: str
    http_status: int | None = None
    failure_class: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise ValueError(f"unknown outcome: {self.outcome!r}")


def _parse(value: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(value)


def pending(store: Store, channel: str, *, now: str | None = None,
            max_attempts: int = MAX_ATTEMPTS,
            retry_after_seconds: int = RETRY_AFTER_SECONDS) -> list[dict[str, Any]]:
    """Events with no successful attempt on this channel, and not currently backing off.

    An event whose attempts are used up is not pending: it stays in the ledger with its
    recorded failures rather than being retried forever or silently forgotten."""
    moment = _parse(_timestamp(now))
    sent: set[str] = set()
    history: dict[str, list[dict[str, Any]]] = {}
    for row in _attempts(store):
        if row.get("channel") != channel:
            continue
        history.setdefault(row["event_key"], []).append(row)
        if row.get("outcome") == "SENT":
            sent.add(row["event_key"])
    waiting = []
    for row in events(store):
        key = row["event_key"]
        if key in sent:
            continue
        tries = history.get(key, [])
        if len(tries) >= max_attempts:
            continue
        if tries:
            last = max(_parse(item["at"]) for item in tries)
            if (moment - last).total_seconds() < retry_after_seconds:
                continue
        waiting.append(row)
    return sorted(waiting, key=lambda row: (row["occurred_at"], row["event_key"]))


def deliver(store: Store, channel, *, limit: int = RATE_LIMIT,
            now: str | None = None, max_attempts: int = MAX_ATTEMPTS,
            retry_after_seconds: int = RETRY_AFTER_SECONDS) -> dict[str, int]:
    """Send pending events, one message each, up to the per-channel rate limit.

    The rate limit is per drain, not per event: a hundred events do not become a hundred
    messages in one burst, and the rest stay pending."""
    name = getattr(channel, "name", "")
    if not name:
        raise ValueError("a channel needs a name")
    moment = _timestamp(now)
    summary = {"sent": 0, "failed": 0, "refused": 0, "rate_limited": 0,
               "timed_out": 0, "connection": 0, "attempted": 0}
    for event in pending(store, name, now=moment, max_attempts=max_attempts,
                         retry_after_seconds=retry_after_seconds)[:max(0, limit)]:
        try:
            result = channel.send(event)
            if not isinstance(result, SendResult):
                raise TypeError("a channel returns a SendResult")
        except TimeoutError as exc:
            result = SendResult("TIMEOUT", failure_class="TIMEOUT", detail=str(exc))
        except Exception as exc:  # noqa: BLE001 - recorded, never swallowed
            result = SendResult("FAILED", failure_class="EXCEPTION",
                                detail=f"{type(exc).__name__}: {exc}")
        attempt(store, event["event_key"], name, result.outcome,
                http_status=result.http_status, failure_class=result.failure_class,
                detail=result.detail, now=moment)
        summary["attempted"] += 1
        summary[{"SENT": "sent", "FAILED": "failed", "REFUSED": "refused",
                 "RATE_LIMITED": "rate_limited", "TIMEOUT": "timed_out",
                 "CONNECTION": "connection"}[result.outcome]] += 1
    summary["pending_after"] = len(pending(store, name, now=moment,
                                           max_attempts=max_attempts,
                                           retry_after_seconds=retry_after_seconds))
    return summary


class ChannelNotConfigured(RuntimeError):
    """The channel's switch is off: no credentials in the environment."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would carry the token in the URL to a host nobody chose. Refuse it."""

    def redirect_request(self, *_args, **_kwargs):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _user_agent() -> str:
    contact = (os.environ.get("CLAIMSTONE_CONTACT_EMAIL") or "").strip()
    suffix = f"; contact: {contact}" if contact else ""
    return f"Claimstone/0.1 (notifications; +https://github.com/Jonbj/claimstone{suffix})"


class TelegramChannel:
    """One chat on `api.telegram.org`. Information only: it never reads replies."""

    name = "telegram"
    DEFAULT_ENDPOINT = "https://api.telegram.org"
    DEFAULT_PORTAL_URL = "http://127.0.0.1:8788"

    def __init__(self, token: str, chat_id: str, *, portal_url: str = DEFAULT_PORTAL_URL,
                 endpoint: str = DEFAULT_ENDPOINT, timeout: float = 10.0,
                 opener=None) -> None:
        if not token or not chat_id:
            raise ValueError("a Telegram channel needs a token and a chat id")
        parsed = urllib.parse.urlparse(endpoint)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"the endpoint must be an http(s) base URL: {endpoint!r}")
        if parsed.path or parsed.query or parsed.fragment:
            raise ValueError(f"the endpoint must be a base URL without a path: {endpoint!r}")
        self.token = token
        self.chat_id = chat_id
        self.portal_url = portal_url
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self._opener = opener or _OPENER

    @classmethod
    def from_environment(cls) -> "TelegramChannel":
        token = (os.environ.get("CLAIMSTONE_TELEGRAM_BOT_TOKEN") or "").strip()
        chat_id = (os.environ.get("CLAIMSTONE_TELEGRAM_CHAT_ID") or "").strip()
        missing = [name for name, value in (
            ("CLAIMSTONE_TELEGRAM_BOT_TOKEN", token),
            ("CLAIMSTONE_TELEGRAM_CHAT_ID", chat_id)) if not value]
        if missing:
            raise ChannelNotConfigured(
                "Telegram is off: set "
                + " and ".join(missing)
                + " in the environment file outside this repository")
        portal_url = (os.environ.get("CLAIMSTONE_PORTAL_URL") or "").strip() \
            or cls.DEFAULT_PORTAL_URL
        return cls(token, chat_id, portal_url=portal_url)

    def _redact(self, text: Any) -> str:
        """Neither credential may survive in a cause, even one echoed by the API."""
        cleaned = "" if text is None else str(text)
        for secret in (self.token, self.chat_id):
            cleaned = cleaned.replace(secret, "<redacted>")
        return cleaned

    def send(self, event: dict[str, Any]) -> SendResult:
        url = f"{self.endpoint}/bot{self.token}/sendMessage"
        body = {"chat_id": self.chat_id, "text": message(event, portal_url=self.portal_url),
                "disable_web_page_preview": True}
        request = urllib.request.Request(
            url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     "User-Agent": _user_agent()})
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8") or "{}")
                if not isinstance(payload, dict):
                    payload = {}
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
            try:
                payload = json.loads(exc.read().decode("utf-8") or "{}")
                if not isinstance(payload, dict):
                    payload = {}
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                payload = {}
            description = self._redact(payload.get("description") or "")
            if 300 <= status < 400:
                return SendResult("FAILED", status, "REDIRECT_REFUSED",
                                  f"telegram answered {status}: redirect not followed")
            if status == 429:
                wait = (payload.get("parameters") or {}).get("retry_after")
                detail = f"telegram answered 429{': ' + description if description else ''}"
                return SendResult("RATE_LIMITED", status, "RATE_LIMITED",
                                  detail + (f"; retry_after={wait}" if wait is not None else ""))
            return SendResult("FAILED", status, f"HTTP_{status}",
                              f"telegram answered {status}"
                              + (f": {description}" if description else ""))
        except TimeoutError as exc:
            return SendResult("TIMEOUT", None, "TIMEOUT", self._redact(exc) or "timed out")
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                return SendResult("TIMEOUT", None, "TIMEOUT", self._redact(exc.reason))
            return SendResult("CONNECTION", None, "CONNECTION", self._redact(exc.reason))
        except OSError as exc:
            return SendResult("CONNECTION", None, "CONNECTION", self._redact(exc))
        if payload.get("ok") is True:
            return SendResult("SENT", status)
        description = self._redact(payload.get("description") or "the API did not answer ok")
        return SendResult("FAILED", status, "TELEGRAM_REFUSED", description)


def message(event: dict[str, Any], *, portal_url: str = "http://127.0.0.1:8788") -> str:
    """The text of one message: ids, a count and a way in. Nothing else."""
    phrases = {
        "signature_required": "signature required on {count} question(s)",
        "plan_awaiting_authorization": "{count} plan(s) awaiting authorization",
        "integrity_error": "{count} integrity error(s)",
        "copy_obtained_after_retry": "{count} copy/copies obtained after a retry",
        "candidate_given_up": "{count} candidate(s) given up",
        "retry_ceiling_used": "retry ceiling reached on {count} item(s)",
        "retry_window_expired": "retry window expired on {count} item(s)",
        "host_breaker_open": "host breaker opened for {count} host(s)",
        "batch_completed": "batch completed ({count} unit(s))",
        "round_below_floor": "round below the acquisition floor: {count} admission(s)",
        "operation_failed": "{count} operation(s) failed",
    }
    shown = ", ".join(event["ids"][:IDS_SHOWN])
    if len(event["ids"]) > IDS_SHOWN:
        shown += f", +{len(event['ids']) - IDS_SHOWN} more"
    code = f" ({event['code']})" if event.get("code") else ""
    return (f"claimstone · {event['project']}\n"
            f"{phrases[event['reason']].format(count=event['count'])}{code}: {shown}\n"
            f"open the portal: {portal_url.rstrip('/')}/")
