# `intake.jsonl` — material an operator proposes

**Written by:** the control server, `POST /control/v1/p/{p}/flows/{flow_id}/intake` (B7a), and the
file intake of B7b. **Read by:** the same server's `GET …/intake`. No stage reads it yet. Nothing in it
counts toward a denominator, creates a candidate or runs a stage.

One row per state of one item. A state change is a new row with the same `intake_id`; the latest row
is the item's state. A second submission of the same item gets its own `intake_id` and the state
`DUPLICATE`, linking the first. It never changes the first.

| field | meaning |
|---|---|
| `intake_version` | `1` (`claimstone/intake.py:INTAKE_VERSION`, registered as an instrument) |
| `intake_id` | 24 random hex characters; looked up, never used as a path |
| `flow_id` | the flow the operator proposed it for |
| `kind` | `doi`, `url` or `reference` (B7b adds `file`) |
| `value` | the comparison form: bare lowercase DOI, normalised URL, or the reference as written |
| `submitted` | what the operator typed, trimmed |
| `note` | the operator's note, or `null` |
| `state` | see below |
| `stage` | which step wrote the row: `routing` in B7a |
| `reason` | one sentence saying why this state |
| `links` | `candidate_key`, `intake_id` or `open_flows`, depending on the state |
| `actor`, `signer_auth` | the operator id, and `"portal-session"` |
| `code_revision` | the control server's code revision, or `null` |
| `recorded_at` | UTC, seconds |

## States set by routing (B7a)

The routing follows what the engine treats as frozen (review F10). A round freezes its population
**predicate**, not its set. Only a `manifest_only` selector has a fixed candidate set.

| state | when | links |
|---|---|---|
| `DUPLICATE` | the same `kind`/`value` was already proposed for this flow, or a DOI/URL equals a scoped candidate's | `intake_id` or `candidate_key` |
| `POSSIBLE_VERSION` | a reference whose folded text equals a scoped candidate's folded title, or contains one longer than 20 characters | `candidate_key` |
| `NEEDS_NEW_ROUND` | no match, and the flow is `manifest_only` or names no round | `open_flows`: bound, `CURRENT`, single-round flows |
| `READY` | no match, in an open round: routed to that round's next discover | — |

**Before anything is recorded**, a URL must be http(s), must not be an excluded host, and must
resolve only to global addresses (`net.global_addresses`, the same rule `Fetcher` applies per hop).
Resolving a name is not a request to the host; nothing is fetched in B7a.

`READY` is "recorded and routed". Discover does not read `intake.jsonl` yet, so a `READY` item enters
no candidate set until it does. When it does, discover applies the round's population predicate:
the intake never decides admission. `REJECTED`, `READY` after file checks, `COUNTED` and
`REPORTED_SEPARATELY` are set by B7b.
