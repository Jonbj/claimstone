# `flows.jsonl` — the contract

Written by `claimstone flow create` and `claimstone flow title`. Append-only. A flow is a round
selector bound to the digests of the protocol as it stood at binding time, so "these figures were
produced under this protocol" becomes a checkable statement instead of a memory.

**A flow never supplies a value to a computation.** Floors, registry and population are always read
from the live project, and the binding is only compared against them (review F4). A snapshot that
drove computation would make the portal disagree with the CLI on the same round.

## Identity

`flow_id` is the sha256 of the canonical JSON (`sort_keys`, `ensure_ascii=False`,
separators `(",", ":")`, `default=str`) of the **binding alone**. Titles, timestamps, creators and
code revisions are metadata and never change who a flow is, so creating the same binding twice
yields the same id — the ledger keeps one `created` row and the second call reports `exists`.

A round with candidates but no flow is **legacy: protocol not verified**. `flow list` prints those
rounds after the flows; the portal shows them under `/p/<project>/legacy/<round>/`.

## Events

`created`:

| field | meaning |
|---|---|
| `event` | `created` |
| `flow_version` | ledger shape version; currently 1 |
| `flow_id` | sha256 of the canonical JSON of `binding` |
| `binding` | the identity: see below |
| `input_files` | sha256 per input file (`topics.yaml`, `questions.yaml`, `sources.yaml`, `manifest.tsv`), or null where absent. **Information only** — a whitespace edit is not drift |
| `bound_after_data` | true when the selector already had candidates at binding time |
| `candidates_at_binding` | that count |
| `title` | display name; changed by `title` events, never part of identity |
| `created_at` | UTC, ISO 8601, seconds |
| `created_by` | `getpass.getuser()` |
| `code_revision` | `git rev-parse HEAD`, or null when git cannot answer |
| `code_dirty` | true when `git status --porcelain` is non-empty; null when git cannot answer |

`binding`:

| field | meaning |
|---|---|
| `project` | the project directory's name |
| `selector` | `{"round": …, "manifest_only": …}` — the canonical selector of `claimstone/scope.py` |
| `registry_version`, `registry_sha256` | the registry the flow runs under |
| `protocol_sha256` | the semantic protocol digest (below) |
| `population_sha256` | the round's `populations.jsonl` `policy_sha256`, or null |
| `derived_from` | a flow id this one replaces or extends, or null |
| `relation` | `null`, `supersedes` or `derived_from`; required non-null when `derived_from` is set, and the referenced id must already exist in this ledger |

`title`: `{"event": "title", "flow_id", "title", "at", "by"}`. Display metadata only.

## The protocol digest

`protocol_sha256` hashes the canonical JSON of the loaded project's semantic protocol: classes
(with their own floors and policies), the project floor and its provenance, excluded hosts,
topics, registry version and digest, the manifest, gate thresholds and policy, normalize
thresholds, the extraction vocabulary, the citation channel rule, and the population policy.
File bytes are hashed separately in `input_files` precisely so that a comment or a re-indent does
not read as drift — the reasoning of `config.registry_digest`'s docstring, applied to the whole
protocol.

## Binding states

`flows.binding_state(project, store, flow)` compares the binding against the live project and
returns one of:

| state | meaning |
|---|---|
| `CURRENT` | registry, protocol and population all equal the live values |
| `REGISTRY_DRIFTED` | `registry_sha256` or `registry_version` differs — checked first, because it invalidates the meaning of the others |
| `PROTOCOL_DRIFTED` | `protocol_sha256` differs |
| `POPULATION_DRIFTED` | `population_sha256` differs from the round's recorded `populations.jsonl` row |

`differences` names every differing component regardless of which state won the priority order.
A protocol change is a **new flow**: `claimstone flow create … --derived-from <id> --relation
supersedes`. `flow check` exits 0 on `CURRENT`, 4 otherwise, 2 on an unknown id.

When `bound_after_data` is true, every UI that shows the flow must also say: "bound after data
existed: rows written before binding are not verified against this protocol." Freezing inputs
after the fact verifies nothing (review F10); the field records that honestly instead of
pretending.

## Writes and the lock

The only writer commands are `flow create` and `flow title`. Each takes an exclusive `fcntl.flock`
on `store/<project>/.flows.lock`, rereads the ledger under the lock, and only then appends — the
pattern of `source_selection._writer_lock` — so two concurrent creates cannot both decide they
were first. `flow list` and `flow check` take no lock and record nothing: they open the store with
`check_registry_drift(..., record=False)` and report `RegistryDrift` as a state, not a crash.

The lock serializes flow writers against each other and nothing else. It does not stop a stage
writer appending to another ledger mid-read — which is why `claimstone export` (see
`docs/contracts/exports.md`) cuts its snapshot at the last newline and verifies prefixes instead
of trusting a file to be quiescent.

## Row validity

A `created` row counts as a flow only if its `flow_id` equals the sha256 of its `binding`.
Rows where it does not are excluded from `flows()`, listed by `flows.invalid_flows(store)`, and shown
on the portal's integrity panel. They are never repaired. Without this rule, a hand-edited binding
would keep the id of a protocol it no longer describes.

## Selectors without a flow

`flows.legacy_selectors` lists the candidate rounds that no flow binds. The portal shows a wider
set, `portal_state.unbound_selectors`, which adds:

- the whole-store selector, whenever any candidate exists;
- every `(round, manifest_only)` pair under which a profile or an adjudication was recorded.

`pmc-screen-time` is why this matters: its eight current profiles, Q04 included, carry
`round: null`. A list of rounds alone would have hidden the one decision the project is waiting on.
In URLs, `-` is the whole store and a `~manifest` suffix marks `manifest_only`. A slug is only ever
looked up among the unbound selectors that exist. An invented slug is a 404.

