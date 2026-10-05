# Research portal: protocol-bound flows and human intake

**Status:** design proposal for Claude Code review; no portal implementation is claimed.
**Date:** 2026-10-06. **Input:** operator's requested portal, repository contracts, and an independent GPT-6-astra architecture review. No network request or model experiment was part of this design.

## Purpose and boundary

The portal lets an operator start and inspect separate research flows, understand the six-stage evidence path, provide lawful copies and other source information, act on access decisions, inspect model configuration, and export a reproducible research result. A flow is tied to a frozen protocol. The portal must preserve the seven invariants in `CLAUDE.md`; the final verdict remains a person's signed decision. The existing `claimstone/dashboard.py` is a read-only single-round view and remains available during migration.

The portal is an interface and orchestrator over Claimstone's append-only record. Its UI is never the authoritative research record. It does not claim literature completeness from a percentage of discovered records, infer a purchase offer from an HTTP 403, convert AI screening to admission, or sign a verdict.

## Mental model and navigation

| Surface | Operator sees and does |
|---|---|
| Research index | One row/card per flow: title, protocol version and date, current run, execution state, unresolved interventions, question coverage, acquisition floor, profile/verdict availability, last trustworthy event. Filters for active, waiting for input, failed, completed and historical flows. |
| New research | Import or edit protocol, validate topics/questions/sources and registry, inspect frozen digest and planned scope, then create a flow. Start is a separate bounded operation. |
| Flow overview | Protocol and selection section, six stage sections, question matrix, actionable blockers, recent events, export. Each section opens its records and evidence. |
| Intervention inbox | Cross-flow queue for source/copy identity, verified access offers, missing PDFs, screening uncertainty, conflicts and verdict-ready profiles. Every card gives cause, affected question or scope, and the next valid action. |
| Source dossier | Distinct candidate, bibliographic work, version and physical/digital copy records; acquisition attempts, selection observations, identity relations, provenance and access status. |
| Administration | Operator identity, key presence and rotation, configured backends/models and verification status, parser/harness versions, health, limits and budgets. |

The six stages are discovery, acquisition, normalization, extraction, review and synthesis. Protocol/selection precedes these stages. Verdict signing follows synthesis as a separate human action. A stage panel shows input scope, completed work, pending work, rejected work, reason-coded blockers, ledger events and links to affected questions. A question-centric matrix shows which classes and sources support each question, the exact quote lineage, exclusions and gaps. A live event stream reports observed ledger events and job heartbeats; it does not imply a request has succeeded until the outcome has been recorded.

## Flow identity and scientific scope

An opaque, immutable `flow_id` binds a project to a frozen protocol snapshot. The snapshot includes exact contents and digests for topics, numbered questions and their kinds, source configuration, question registry version/digest, candidate population or selection inventory, source classes, acquisition floor and exact selector (`round`, `manifest_only`). It records creation time and schema/instrument versions. A mutable display title is metadata, never the identity.

A material protocol or selection change creates a new flow with `supersedes_flow_id` or `derived_from_flow_id`; it cannot silently retarget an existing flow. A campaign, retry or worker job is a run of a flow. Historical rounds without reconstructible binding display **legacy: protocol not verified**. The UI must not invent an immutable protocol for them.

The selection panel exposes frozen inventory, source-screening and identity observations, including `AI_PROVISIONAL` and supersession. D79–D81 observations are advisory. They do not change admission, the acquisition denominator or a human reference. Controlled admission of a closed cohort needs its own reviewed scientific contract and implementation before the UI can offer that action.

## Honest state model

The index and stage panels show three independent dimensions:

| Dimension | Required behavior |
|---|---|
| Execution | `IDLE`, `QUEUED`, `RUNNING`, `STOP_REQUESTED`, `FAILED`, `INTERRUPTED`, `UNKNOWN`. `RUNNING` requires a live lease/heartbeat; an expired lease is shown as interrupted/unknown until reconciled. |
| Work in frozen scope | Counts for pending, completed, rejected/excluded and unknown, each with a named denominator and links to rows. No single aggregate completion percentage. |
| Scientific usability | Floor sufficient/insufficient/unknown, advisory selection, profile available, human verdict pending/signed, stale signature, or legacy protocol unknown as applicable. These can coexist with execution state. |

Stages can overlap in time. An HTTP 403 is an access-blocked attempt, not proof that a paid copy exists. A question with no extracted claim is not a finding of no effect. `NEVER_ASKED` and `UNANSWERED_IN_LITERATURE` remain distinct. Question and source-class counts are visible before any pooled presentation. Every displayed number names its scope and derivation; CLI and portal must agree for the same frozen flow.

`claimstone/round_state.py` currently has project-wide reads in `_stage_normalize`, `activity` and `_last_write`. A common scoped read adapter is prerequisite to a multi-flow UI. Validate it using two rounds in one project, including different manifests, so another round's document, activity or timestamp never appears in this flow. The existing single-round dashboard cannot simply be wrapped as the multi-flow source.

## Acquisition, offers and human-supplied copies

Access, offer, decision and copy are independent records. A useful UI state vocabulary is:

| Axis | States |
|---|---|
| Access | `NOT_CHECKED`, `OA_SEARCH_PENDING`, `OA_COPY_FOUND`, `NO_OA_FOUND_IN_CHECKED_ROUTES`, `ACCESS_BLOCKED` |
| Offer | `NONE`, `UNVERIFIED`, `VERIFIED`, `STALE`, `WITHDRAWN` |
| Human decision | `NONE`, `APPROVED`, `DECLINED`, `DEFERRED`, `REVOKED` |
| Copy | `NONE`, `UPLOADED`, `IDENTITY_PENDING`, `IDENTITY_CONFLICT`, `VALIDATION_FAILED`, `READY_FOR_IMPORT`, `IMPORTED` |

A verified offer requires a matched work/version, vendor and URL, observed price/currency, tax status (known or unknown), access duration/terms, observation time and retained proof. Its hash fixes what the operator approved. A changed price, terms or target creates a new offer and decision. Purchase happens outside the portal in the first release. An approved offer is permission to buy that exact offer, not evidence that a purchase occurred. Uploading a PDF or invoice does not establish bibliographic identity, readable content, licence or redistribution rights.

The intervention inbox accepts bibliographic leads, publisher/access links and locally held PDFs. Upload computes a byte hash, records actor, time, origin and declared relationship, stores bytes in a quarantine/content-addressed area, and runs type, identity, corruption and existing-copy checks before import. A mismatch becomes an identity conflict and stays inspectable; it never silently changes a candidate key or substitutes another work. Existing acquisition conduct still governs network checks: robots.txt, per-domain failure budget, named campaign for terminal retry, explicit bounded operator authorization for sweeps.

## Persistent contracts and concurrency

Add only minimal append-only contracts; define every field, schema version, idempotency key, supersession rule, provenance and failure state in `docs/contracts/` before writing. Proposed ledgers:

| Ledger | Purpose |
|---|---|
| `flows.jsonl` | Immutable flow/protocol binding and explicit derivation; display-title revisions as events. |
| `intake.jsonl` | Submitted leads, copied byte hashes, actor, identity and import states. |
| `access_offers.jsonl` | Time-bound vendor observations with evidence and offer hash. |
| `access_decisions.jsonl` | Authenticated operator decisions tied to the exact offer hash. |
| `operations.jsonl` | Preview/execute intent, frozen preconditions, authorization, job reference, result and resume state. |

Existing D79–D81 screening and identity ledgers retain their meaning. No secret goes into a ledger. The backend stores secrets locally with restrictive permissions and exposes only presence and health. A typed API/adapter invokes the existing stage logic; UI code does not write stage ledgers directly.

All CLI, worker and portal writers for one project share one effective lock. Under the lock, reread authoritative ledgers, recheck frozen preconditions and idempotency, append, and release. Reusing an idempotency key with a different payload is a conflict. A multi-ledger operation has an operation ID and resumable steps because appends across files are not atomic. Network and model calls occur outside the lock; their recorded outcomes re-enter under it. A crash after byte storage but before ledger append must be recoverable by hash without creating an untracked accepted copy. A damaged ledger is surfaced; GET never repairs it or treats it as empty.

## Operations and security

Starting discovery/acquisition is a two-step workflow: preview exact flow scope, query domains, job count, request ceilings, estimated and unknown model cost, failure budget and planned writes; then execute the frozen plan with preconditions rechecked. Unknown cost requires a ceiling or explicit reservation. Jobs have durable states, leases and cooperative stop/resume. A stopped job records completed requests and remaining units; restart uses the same frozen plan and content-hash idempotency. New network sweeps still require the operator's explicit authorization under `AGENTS.md`.

The first deployment targets a trusted local operator. Human-signature actions require an authenticated operator identity; a free-text `actor` field is insufficient. Mutating endpoints use loopback binding, Host/Origin checks and CSRF protection; no permissive CORS. Escape all displayed metadata and quotes. Downloads of untrusted PDF bytes are isolated and use safe content disposition. URLs submitted by users are data for validated acquisition routes, not arbitrary fetch targets. Admin health probes and paid model calls are explicit operations, never side effects of GET.

## Export and provenance

Export creates a consistent snapshot by capturing complete ledger prefix offsets and hashes under the coordinated writer, then deriving a manifest from those prefixes. Export packages the protocol snapshot, scope, instrument and model/harness versions, stage outcomes, question evidence profiles, human verdicts and signature freshness, exclusions/rejections, acquisition coverage, and traceable quote → chunk → document → copy/attempt lineage. Machine-readable JSON plus a reader-oriented report and CSV tables are reasonable initial formats. A PDF copy, purchase receipt or vendor licence is included only when the applicable rights and operator choice permit it. Export during concurrent append must represent one consistent prefix; later events require a new export ID. An unverifiable prefix or stale signature is visible in the artifact.

## New product ideas from the architecture review

1. **Intervention inbox:** one place to see the small set of decisions a person can actually unblock, ranked by urgency and affected flow/question. This directly reduces operator time.
2. **Question matrix and provenance explorer:** move from stage-oriented status to the evidence path of each research question, with exact quotes and reasons for rejected material.
3. **Explained blockers:** each warning names the underlying rows and next valid action, including floor failures, identity conflicts and stale signatures.
4. **Coverage simulator, later:** show how a hypothetical lawful copy would affect the acquisition floor without treating it as acquired or altering a ledger.
5. **Comparable-flow view, later:** compare only compatible protocol scopes and instrument versions, and expose stale signatures rather than presenting a trend across incompatible rounds.
6. **Saved bounded operation plans, later:** retain a reviewed preview for repeatable campaigns while rechecking its preconditions at execution.

The UI should avoid a single quality score, a claimed literature-completeness percentage, purchase prioritization by favorable result direction, and a free-form chat agent with write authority.

## Build order and review gates

1. Define flow/protocol and new ledger contracts; fix scoped read primitives and test two rounds in one project. Decide how legacy rounds display when binding cannot be proven.
2. Build read-only research index, flow overview, intervention inbox, question matrix, provenance view and snapshot export using scoped adapters. Preserve the current dashboard during rollout.
3. Add controlled intake, verified offers and exact-offer decisions, then copy validation/import. Keep selection advisory until a separate controlled-admission design is approved and implemented.
4. Add authenticated admin, shared writer discipline and durable job operations; wire bounded preview/start/stop/resume after their contracts and security gates pass.
5. Add optional simulator and compatible-flow comparisons after the core measurements are trustworthy.

Acceptance requires tests for: two rounds of the same project without data leakage; protocol drift and stale signature; a failed candidate remaining in the acquisition denominator; 403 without purchase offer; wrong PDF and same bytes submitted under two IDs; CLI/portal concurrent writes; crash between bytes and ledger; export during append; expired heartbeat; no secret disclosure; Host/Origin/CSRF checks; exact preview/execute match; corrupted ledger surfaced instead of zero counts. Tests must preserve all seven `CLAUDE.md` invariants and existing stage behavior.

## Questions for Claude Code review

Check this proposal against `CLAUDE.md`, D42, D79–D81, current contracts and code. Identify incorrect assumptions, missing trust or provenance boundaries, scope leaks, simpler designs and conflicts with existing measured decisions. Evaluate the six new product ideas for practical value and suggest further ideas that make human intervention shorter without degrading scientific validity. Rank findings by severity, cite repository locations, distinguish verified code facts from design inferences, and propose exact wording changes. Do not implement or run network operations during this review.
