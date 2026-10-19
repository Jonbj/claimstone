# Notifications — the outbox of events that need a person

Status: built 2026-10-18 (issue #5). Design: **D153**. Code:
`claimstone/notifications.py` (the ledger and the channel), `claimstone/notify.py` (the
derivation from the other ledgers), `claimstone/cli.py` (`notify`).

The outbox is information only. It never authorizes, signs, retries or changes anything; a
message is a signal that something is waiting, with a way into the portal. Authorizations stay
in the control API, behind a session, a confirmation and exact limits.

## Files

One file per project: `store/<project>/notifications.jsonl`, append-only, written only by
`claimstone notify` (and by `notifications.record` / `notifications.attempt`). A half-written
last line is skipped exactly as `Store.read` skips one; damage elsewhere raises.

| kind | written by | contains |
|---|---|---|
| `started` | the first non-dry `notify` run | the watermark one-shot occurrences are compared against |
| `event` | `notify` through `record()` | an occurrence that needs a person, once per identity |
| `attempt` | `deliver()` | one send attempt per event and channel, successful or not |

All rows carry `outbox_version: 1`. There is no other version yet; a change to the event shape
is a new version, because the key and the deduplication depend on it.

## `event` rows

```json
{"record": "event", "outbox_version": 1, "event_key": "n1-…",
 "event": "needs_person", "reason": "signature_required", "code": "ADJUDICATION",
 "project": "example-news-and-returns", "subject": "Q03", "ids": ["Q03"], "count": 1,
 "occurrence": "…", "occurred_at": "2026-10-18T10:00:00+00:00"}
```

| field | why it exists |
|---|---|
| `event_key` | `n1-` + SHA-256 of the canonical identity: event, reason, code, project, subject, ids, count, occurrence. `record()` appends at most once per key; a restart, a re-derivation or a second process cannot send the same occurrence twice |
| `event` | `needs_person`, `retry`, `finished` or `failure`; a closed set |
| `reason` | one of the eleven reasons below; a closed set per event |
| `code` | an **identifier** (`OperationError`, `DOMAIN_BUDGET_EXHAUSTED`, `INTEGRITY`), validated against `^[A-Za-z][A-Za-z0-9_.-]{0,60}$`. It is the recorded cause at the class level; prose cannot travel here |
| `project` | the project the message is about |
| `subject` | the one entity: an operation id, a batch id, a question id, a candidate key, a host, a retry policy id, a round selector, or an inbox card's subject |
| `ids` | sorted, unique, cleaned short ids shown in the message |
| `count` | a positive integer; how many rows the event stands for |
| `occurrence` | the part of the identity that distinguishes this occurrence from the next: an `event_id`, an attempt number, a profile-bearing card's hashed text, an expiry. It is hashed into the key, never shown |
| `occurred_at` | the source row's own time, UTC with an offset; not the drain's time, except for a live state whose source has no time (`needs_person` cards) |

**There is no free-text field, on purpose.** A title, a quote, an abstract or a claim cannot
enter this ledger because there is nowhere to put it. `notify` enforces the field set, not a
convention. A `code` is not an escape hatch: it must parse as an identifier.

`subject` and `ids` are cleaned of control characters and length-bounded, so a hostile id
cannot forge a second ledger line.

## The eleven reasons

States are derived on every drain and deduplicated by identity. Occurrences are derived only
from source rows at or after the watermark (`started.at`), or `--since` when given.

| event | reason | kind | source |
|---|---|---|---|
| `needs_person` | `plan_awaiting_authorization` | state | `operations.jsonl`: last event `planned`; `operation_batches.jsonl`: every operation still `planned` |
| `needs_person` | `signature_required` | state | `portal_state.inbox_cards`, category `ADJUDICATION` |
| `needs_person` | `integrity_error` | state | `inbox_cards`, categories `INTEGRITY` and `PROTOCOL`; `code` names which |
| `retry` | `copy_obtained_after_retry` | occurrence | latest `acquisitions.jsonl` row per candidate: `acquired`, `attempt_no > 1`, not a store reuse or an operator intake |
| `retry` | `candidate_given_up` | occurrence | latest acquisition: not acquired, `net.is_terminal(failure_class)` |
| `retry` | `retry_ceiling_used` | occurrence | an authorized `retry_policies.jsonl` policy whose `remaining_retries` is 0; time of its last reservation |
| `retry` | `retry_window_expired` | occurrence | an authorized retry policy whose `expires_at` has passed |
| `retry` | `host_breaker_open` | occurrence | `requests.jsonl` rows `event: blocked`, `failure_class: DOMAIN_BUDGET_EXHAUSTED`, grouped per host into one episode |
| `finished` | `batch_completed` | occurrence | every operation of an `operation_batches.jsonl` batch has last event `completed`; time of the latest |
| `finished` | `round_below_floor` | state | `admissibility.admit` returns `INSUFFICIENT_ACQUISITION` with `found > 0`; count is `found` |
| `failure` | `operation_failed` | occurrence | `operations.jsonl`: last event `failed`; `code` is its `failure_class` |

`needs_person`, `round_below_floor` and the state form of `plan_awaiting_authorization` are
always derived: the first drain tells the operator what is waiting, however old it is.
Everything else is history and is not replayed.

The portal's `today` page calls `ADJUDICATION`, `INTEGRITY` and `PROTOCOL` the required
categories; notifications reads the same `portal_state.inbox_cards` computation, so a new
integrity check reaches the outbox by existing rather than by being remembered here. Cards
that only name a command (`ACQUISITION`, `CLASSIFICATION`, `NORMALIZE`, `EXTRACT`, `REVIEW`,
`ADVISORY`) do not notify.

## `attempt` rows

```json
{"record": "attempt", "outbox_version": 1, "event_key": "n1-…", "channel": "telegram",
 "attempt": 1, "outcome": "FAILED", "http_status": 500, "failure_class": "HTTP_500",
 "detail": "telegram answered 500: Internal Server Error", "at": "…"}
```

`outcome` is one of `SENT`, `FAILED`, `REFUSED`, `RATE_LIMITED`, `TIMEOUT`, `CONNECTION`. A
channel exception is caught and recorded as an attempt with `failure_class: EXCEPTION`; it is
never swallowed to make the drain look clean. `detail` is cleaned, bounded to 300 characters
and redacted by the channel of any credential it handles.

`pending()` considers an event on a channel until a `SENT` attempt exists. A failed attempt is
retried only after 15 minutes; an event has at most 3 attempts per channel, after which it stays
in the ledger with its failures and is no longer pending. A different channel does not consume
it: issue #6 will add e-mail on this same outbox.

`deliver()` sends at most `--limit` messages per drain (default 20). That is the per-channel
rate limit: a hundred events do not become a hundred messages in one burst, and the rest remain
pending.

## Telegram

The switch is the presence of both environment variables, in an environment file outside this
public repository:

| variable | meaning |
|---|---|
| `CLAIMSTONE_TELEGRAM_BOT_TOKEN` | BotFather's token |
| `CLAIMSTONE_TELEGRAM_CHAT_ID` | the one chat that receives messages |
| `CLAIMSTONE_PORTAL_URL` | optional; the link in the message, default `http://127.0.0.1:8788` |

The only host contacted is `api.telegram.org` (a test may pass another endpoint; the CLI cannot).
The request is one `POST /bot<token>/sendMessage` with an explicit 10-second timeout, a
descriptive `User-Agent`, `disable_web_page_preview: true`, and no `getUpdates`: there is no
reply handling and no command surface.

A redirect is refused (`REDIRECT_REFUSED`), because following one would carry the token in the
URL to a host nobody chose. The token and the chat id never enter a ledger, a log or a message;
an API error description that echoes them is redacted before it becomes `detail`.

### Message

```
claimstone · example-news-and-returns
signature required on 1 question(s) (ADJUDICATION): Q03
open the portal: http://127.0.0.1:8788/
```

Ids, a count and a way in. No claim text, quote, title or source content.

## Running

```
claimstone notify projects/<name> --store store                 # record the outbox only
claimstone notify projects/<name> --store store --dry-run       # print; write nothing
claimstone notify projects/<name> --store store --channel telegram
```

A dry run writes neither a `started` row nor an event, so it cannot leave a trace that later
looks like a sent message. It does not start the outbox: the next real run sets the watermark.

## Not built

- No digest mode. The issue left the default open; immediate, one message per event, is the
  conservative choice, and the rate limit bounds a burst. A digest would be a new decision.
- No per-event opt-out in the portal, and no recipient other than the one chat id.
- Notifications for authorization windows in `network_schedules.jsonl`, `copy_policies.jsonl`
  and `local_mandates.jsonl`, and for model-call batches, are not derived yet. The reasons
  exist for the operation plans; these four ledgers have their own `planned` states and need
  their own occurrence identity.
- No e-mail. That is issue #6, on the same outbox.
