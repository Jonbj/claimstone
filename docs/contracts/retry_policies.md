# Retry policies (`retry_policies.jsonl`)

`store/<project>/retry_policies.jsonl` is append-only, one ledger per project, with the same event
discipline as [copy policies](copy_policies.md): `planned` (immutable, `policy_id` = digest of the
policy), then `authorized` (a person, exactly once), then optionally `revoked`. Each row also carries
`version`, `event_id` (digest of the row without `event_id` and `at`) and `at`.

A retry policy is a **finite, revocable, flow-scoped permission to try again, on its own, the
acquisitions that failed for a reason that can pass** (D134). It never retries a terminal failure: those
need a named campaign by a person, as before. It never widens hosts, never touches `excluded_hosts`, never
calls a model and never signs anything.

## The frozen policy

`{version, project, flow_id, selector, allowed_hosts, max_retries, max_attempts_each,
max_requests_each, max_total_requests, use_apis, retry_after_hours, not_before, expires_at,
code_sha256, protocol_sha256}`

- `allowed_hosts`: exact lowercase hosts (no wildcard, none in the project's `excluded_hosts`). With
  `use_apis: true` the two resolver hosts `api.unpaywall.org` and `api.openalex.org` must be listed.
- `max_retries`: lifetime ceiling on retry operations (1–200). `max_attempts_each`: ceiling per candidate
  (1–5), counted over operations authorized by this policy. `max_requests_each`: 1–20.
  `max_total_requests = max_retries * max_requests_each`.
- `retry_after_hours`: 6–168; a candidate is not retried before its last attempt is that old.
- `not_before` is the planning instant; `expires_at` is a future UTC instant within 366 days.
- `code_sha256` and `protocol_sha256` freeze the code and the protocol: a policy planned under other code
  or another protocol starts nothing (the person plans a new one).

## What it may start

Each time the executor ticks (`operations.tick`, `autopilot`), `retry_policy.materialize_due` plans and
authorizes — under the project writer lock, the policy's lifetime ceilings and the window — one ordinary
`acquire` operation (`operations.plan` with the policy's hosts, `max_requests_each` and `use_apis`, no
`retry_classes`) for every candidate of the flow such that **all** hold:

1. its latest acquisition row is not acquired and is *transient-unfinished* (below);
2. that row is at least `retry_after_hours` old;
3. its URL host is in `allowed_hosts`;
4. no operation for the candidate is active, and the policy has authorized fewer than `max_attempts_each`
   operations for it;
5. the policy has authorized fewer than `max_retries` operations and the sum of their request ceilings
   plus this one stays within `max_total_requests`.

The operation's `authorized` event carries `identity.retry_policy_id`. The executor refuses to start such
an operation unless `retry_policy.due` (policy authorized, not revoked, inside its window) still holds.
Everything the ordinary executor enforces stays: `robots.txt`, redirect and host gates, the per-domain
failure budget, exact hosts, the request ceiling.

## Transient-unfinished

`acquire.should_attempt` (routine runs and this policy alike) treats a not-acquired row as retryable
without a named campaign when its `failure_class` is in `net.TRANSIENT` **or** when any recorded attempt of
that row has a class in `net.TRANSIENT` — the headline class is the last attempt's, and a row whose last
attempt was a refusal can still hold a location that failed only because the server was down (measured:
`doi:10.1016/j.mhpa.2015.12.004`, 2026-10-17, `SERVER_ERROR_5XX` then `CONNECTION_ERROR`, headline
`EXCLUDED_HOST`). The headline class recorded in the ledger does not change. `REQUEST_LIMIT_REACHED`,
paywalls, robots refusals, redirects to non-HTTP destinations and excluded hosts stay terminal.

## Status (`retry_policy.status`)

`{policy_id, state: PLANNED|AUTHORIZED|REVOKED, policy, reserved_retries, remaining_retries,
reserved_requests, events}`; it raises when reservations exceed a ceiling.
