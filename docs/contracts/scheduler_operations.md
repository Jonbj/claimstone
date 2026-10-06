# Scheduler operations — proposed append-only contract

**Status:** design contract for the next implementation slice. No `operations.jsonl`
writer or worker exists yet. `claimstone scheduler-preview` is read-only and produces
neither an operation nor an authorization.

The scheduler executes a bounded plan for one existing flow. It does not create a
scientific verdict, close a source-selection cohort from provisional AI labels,
or infer that a previously refused host is now available. The live project and
ledgers remain authoritative; a stored snapshot is checked at execution, never
substituted for the current protocol.

## Identity and frozen plan

An operation belongs to `(project, flow_id, selector, protocol_sha256)`.
Its `plan_id` is the SHA-256 of canonical JSON of the immutable plan. The plan
contains: operation kind, dated campaign, sorted work units, input ledger-prefix
hashes, input bytes needed for reproducibility, instrument and code identity,
permitted destinations and redirect policy, physical request and robots limits,
model/backend/harness and prompt identities where applicable, spending ceiling,
unknown-cost reservation policy, and timeout. A null limit is **not** unlimited;
the planner refuses an unbounded network or paid plan.

A `unit_id` hashes the plan id, stage, candidate or document identity, and
the exact input identity. An unchanged unit reuses its recorded outcome. A
changed input creates a new unit; it never changes the meaning of the old row.

The existing `flow_id` binds a selector and protocol. A flow whose binding has
drifted, whose registry drifted, or whose pre-binding rows lack verified
provenance cannot start work through this contract. The first preview names
these conditions rather than guessing an applicable protocol.

## Event ledger

Future file: `store/<project>/operations.jsonl`; append-only, one event per
line. Every event carries `operation_version`, `operation_id`, `plan_id`,
`flow_id`, `event_id`, UTC timestamp, actor kind and code revision. `event_id`
hashes the canonical event body excluding its timestamp, so a repeated append
of the same state transition is detected under the project writer lock.

| Event | Required meaning |
|---|---|
| `planned` | Stores the full immutable plan and previewed preconditions; permits no execution. |
| `authorized` | Names an authenticated operator, the exact `plan_id`, approved limits and time interval. An authorization cannot enlarge the plan. |
| `started` | Names worker identity and lease; records that frozen preconditions were rechecked. |
| `heartbeat` | Advances the lease for that worker only. A past event cannot imply a live worker. |
| `unit_completed` | Binds a `unit_id` to the already recorded stage/request/model outcome and actual consumption. This is the resume cursor, not a replacement for the stage ledger. |
| `unit_failed` | Names a terminal or retryable recorded outcome and its class. |
| `stopping` | Records a cooperative stop request; no new units start. In-flight outcomes are still recorded. |
| `stopped` | Names completed and remaining units and actual consumption. |
| `completed` | All planned units have a recorded disposition; does not mean the scientific cohort is complete. |
| `failed` | A named invariant or integrity problem prevented safe continuation. |

There is one current state derived by replaying valid events; no row is edited.
Duplicate events with the same id and payload are idempotent. The same id
with a different payload is corruption and blocks continuation. An expired
lease becomes `INTERRUPTED`, not success or permission to start a duplicate
worker. A new worker reconciles request and stage ledgers before resuming.

## Preconditions and coordination

Before `started` and each unit, the worker checks the flow binding, live
registry, frozen input hashes, current code/instrument identity, remaining
host budget and remaining spending reservation. A changed prerequisite
produces a new proposal. The existing authorization does not silently cover
the new proposal.

All CLI, portal and worker writers for one project must use one project-wide
writer lock. Under the lock, re-read the operation ledger and authoritative
stage ledgers, verify idempotency and remaining limits, then append the
transition. Network and model calls occur outside the lock; their outcomes
re-enter under it. Multi-ledger work is a sequence of resumable units, not an
assumed atomic transaction. This shared lock is a prerequisite for an
executor; the existing flow/source-selection locks are insufficient.

The per-host failure budget is reconstructed from recorded requests and
applies across restarts. A 403 is an access refusal, not a purchase offer.
Every redirect hop must obey the allowed host and non-global-address guard.
No terminal retry occurs without a named, authorized campaign.

Spending is reserved before a paid call. Actual usage releases or consumes
the reservation in a recorded outcome. Calls of unknown cost require a
bounded reservation. A restart uses the cumulative approved ceiling rather
than resetting it. A cancelled or failed call remains accounted as an
attempt with its known or unknown cost.

## Human boundary

An operation may prepare a plan, perform authorized collection, normalization,
extraction, review and profile building once their scoped stage APIs are
ready. It may prepare a source, offer, identity or verdict packet for a person.
Only authenticated people authorize new network/spending scope, decide a
verified purchase offer, resolve contested scientific selection when policy
requires it, and sign a verdict. An `AI_PROVISIONAL` assessment never becomes
admission merely because a worker finished its queue.

## First implementation gate

Before any executor is enabled: adopt the shared writer lock in every stage
writer; make the failure budget and redirect guard persistent; make stage
builders respect the selected round; implement the ledger validator and
idempotent event append; prove preview/execute scope parity, crash recovery,
concurrent writer safety, budget exhaustion and a changed-input refusal in
temporary stores. Read-only scheduler previews may run before these gates.
