# Scheduler operations — append-only contract

**Status:** `operations_version 2` implements one scoped normalize,
extract-build, review-build, harvest or synthesize stage per operation, a
bounded local `llamacpp` or explicitly budgeted `ollama-cloud` drain, a
bounded one-candidate acquisition from an existing URL, or one bounded
scholarly-API query. `claimstone scheduler-preview` remains read-only. Batch
plans cover multiple frozen queries or candidates; lease heartbeats, portal
control routes and automatic paid-lane planning remain design requirements.

`claimstone scheduler batch-plan` groups at most `--max-units` one-query or
one-candidate plans in `operation_batches.jsonl`. Its batch ID hashes the
exact operation IDs, scope, skipped items and summed physical request ceiling.
`authorize-batch` is one local operator action that records authorization on
each unchanged plan. `scheduler tick` runs already authorized work; `scheduler
worker` polls for it. It never invents permission for a later candidate or
API call. A failed offline operation needs a new named attempt; an unsettled
physical request blocks automatic retry.

`scheduler drive` is a single operator-invoked pass. It first runs only the
flow's external operations already authorized at invocation, then chains the
scoped local stages with at most the specified total number of local model
calls. It records each local plan and authorization. It stops at any network
work lacking approval, the floor or human-reading boundary. It is not a standing daemon
policy and cannot reset a persistent paid budget by restarting a worker.

The scheduler executes a bounded plan for one existing flow. It does not create a
scientific verdict, close a source-selection cohort from provisional AI labels,
or infer that a previously refused host is now available. The live project and
ledgers remain authoritative; a stored snapshot is checked at execution, never
substituted for the current protocol.

## Identity and frozen plan

An operation belongs to `(project, flow_id, selector, protocol_sha256)`.
Its `plan_id` is the SHA-256 of canonical JSON of the immutable plan. The plan
in version 1 contains the stage, selector, protocol digest, whole input-ledger
hashes, a hash of all Python package files, exact hosts and schemes where a
network request is allowed, a physical request ceiling, and backend/model/
harness/call IDs for a drain. Network plans require a positive ceiling. A paid
plan also freezes a budget ID and total ceiling in cents, per-call reservation,
declared input/output price ceilings, prompt-queue hash and exact call IDs.
The runner's timeout and endpoint are represented by the hashed code and
harness. The local estimate uses UTF-8 prompt bytes plus 8192 tokens of chat
overhead and each request's output limit. Provider-side token additions,
pricing changes and incomplete usage can exceed this estimate; the reservation
is **not** a provider-enforced spending cap.

Version 1 has one stage per operation, or a frozen list of local `call_id`s.
The plan hash identifies the stage unit and each local model result is tied to
its `call_id`. A changed input creates a new plan; it never changes an old row.
The current one-stage operation can be retried after a terminal offline
failure only with a new `--run-label`. An unsettled physical request without
its acquisition/query outcome blocks even a newly labelled plan until it is
inspected; a name alone cannot justify another network transfer.

The existing `flow_id` binds a selector and protocol. A flow whose binding has
drifted, whose registry drifted, or whose pre-binding rows lack verified
provenance cannot start work through this contract. The first preview names
these conditions rather than guessing an applicable protocol.

## Event ledger

File: `store/<project>/operations.jsonl`; append-only, one event per
line. Every event carries `operation_version`, `operation_id`, `plan_id`,
`flow_id`, `event_id`, UTC timestamp, actor kind and code SHA-256. `event_id`
hashes the canonical event body excluding its timestamp, so a repeated append
of the same state transition is detected under the project writer lock.

| Event | Required meaning |
|---|---|
| `planned` | Stores the full immutable plan and previewed preconditions; permits no execution. |
| `authorized` | Names the local OS operator, exact plan and approved limits; cannot enlarge the plan. |
| `started` | Names worker PID and records that frozen preconditions were rechecked. |
| `call_started` | For a paid model call, records its exact call ID and reserved cents before transport. A missing result after this event blocks automatic retry. |
| `unit_completed` | Binds the stage result or local `call_id` to an already recorded outcome. |
| `completed` | All planned units have a recorded disposition; does not mean the scientific cohort is complete. |
| `failed` | A named invariant or integrity problem prevented safe continuation. |

There is one current state derived by replaying valid events; no row is edited.
Duplicate events with the same id and payload are idempotent. The same id
with a different payload is corruption and blocks continuation. Version 1
holds the project writer lock for the entire unit; `status` reports
`RUNNING_OR_LOCK_HELD` while a writer holds it and `INTERRUPTED` if an
unfinished unit has released it. The busy lock may belong to another writer,
so the status does not claim a specific operation is running. The
worker reconciles model results and acquisition/query rows before
resuming. `heartbeat`, `stopping`, `stopped` and leases across unlocked calls
remain the target design for a parallel executor.

## Preconditions and coordination

Before `started`, the worker checks the flow binding, frozen input hashes,
current package identity and the approved limits. A changed prerequisite
refuses the old plan. The existing authorization does not silently cover a
new proposal.

All CLI, portal and worker writers for one project must use one project-wide
writer lock. Under it, re-read the operation and stage ledgers, verify
idempotency and remaining limits, then append the transition. Version 1 keeps
the lock through its bounded network or local model call. This serializes
other project writers during a slow call but prevents duplicate work without
an unlocked claim/lease protocol. A future parallel executor must release the
lock around calls and add durable reservations and heartbeats. Multi-ledger
work is resumable, never an assumed atomic transaction.

The per-host failure budget is reconstructed from recorded requests and
applies across restarts. A 403 is an access refusal, not a purchase offer.
Every redirect hop must obey the allowed host and non-global-address guard.
No terminal retry occurs without a named, authorized campaign.

The full amount of every authorized paid plan remains reserved in its named
budget, including failed and unused calls. Under the project lock, a second
authorization with the same budget ID must have the same ceiling and cannot
bring cumulative reservations over it. Actual cost is recorded from the model
result, with the plan's declared prices; an unknown or over-reservation result
stops further calls. A crash after `call_started` with no result refuses retry
until billing is inspected. This is deliberately conservative: no release or
recycling of budget occurs automatically. Operator authorization of a frozen
plan remains required even when account credits are available.

## Human boundary

An operation may prepare a plan, perform authorized collection, normalization,
extraction, review and profile building once their scoped stage APIs are
ready. It may prepare a source, offer, identity or verdict packet for a person.
Only authenticated people authorize new network/spending scope, decide a
verified purchase offer, resolve contested scientific selection when policy
requires it, and sign a verdict. An `AI_PROVISIONAL` assessment never becomes
admission merely because a worker finished its queue.

## Remaining implementation gate

Before an unlocked parallel executor is enabled, add durable unit
claims/leases, stop requests, authenticated portal control routes and stronger
integration tests around a killed worker.
The current single-writer executor has tests for scope isolation, crash
reconciliation, host ceilings across restarts, idempotent replay and changed
input refusal. It does not authorize an actual campaign; the operator must
approve its exact plan or batch.
