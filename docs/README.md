# Documentation map

Which file answers which question. *In italiano: [README.it.md](README.it.md).*

## Start here

| I want to… | read |
|---|---|
| know what this project is, in two minutes | [`../README.md`](../README.md) |
| run a round and understand what comes out | [`GUIDE.md`](GUIDE.md) |
| know what is running and what is pending right now | [`HANDOFF.md`](HANDOFF.md) |
| find implemented scheduler limits and remaining automation work | [`SCHEDULER_BACKLOG.md`](SCHEDULER_BACKLOG.md) |
| run the local Docker Compose trial (portal, control, GROBID, scheduler worker) | [`LOCAL_COMPOSE_TRIAL.md`](LOCAL_COMPOSE_TRIAL.md) |
| adapt the frontend to the scheduler | [`design/portal/SCHEDULER_FRONTEND_HANDOFF.md`](design/portal/SCHEDULER_FRONTEND_HANDOFF.md) — UI states, available APIs, missing controls and acceptance walkthrough |
| serve the read-only portal over every project | `claimstone portal` — the dashboard's multi-project successor (D82); read-only, GET only, loopback by default |
| run the portal in containers (React frontend + read-only API) | `./portal.sh` (`./portal.sh down` to stop) — D84; API contract [`contracts/portal-api.schema.json`](contracts/portal-api.schema.json) |
| develop the frontend | `.venv/bin/claimstone control --allow-host localhost:5173` and `.venv/bin/claimstone api --session-authority http://127.0.0.1:8790` (two terminals; D152), then `cd web && npm run dev` (http://localhost:5173); checks: `npm run typecheck && npm test && npm run build` |
| work on the code as an agent | [`../CLAUDE.md`](../CLAUDE.md), then [`../AGENTS.md`](../AGENTS.md) |
| argue with an architectural choice | [`DESIGN_DECISIONS.md`](DESIGN_DECISIONS.md) — find its entry first |
| write to a ledger, or read one | [`contracts/`](contracts/) — one file per ledger |

## The design record

[`DESIGN_DECISIONS.md`](DESIGN_DECISIONS.md) holds every numbered decision — 132 as of 2026-10-16, in ~5,000
lines (`grep -c '^## D' docs/DESIGN_DECISIONS.md` for the current count) — each carrying **the
measurement that decided it**. It is not meant to be read front to back.

Its purpose is narrow and worth stating: **so that a choice is not relitigated from first principles.** Most
entries exist because something plausible was tried, measured, and found wrong. Several record a prediction
of mine that the measurement falsified — those are the most useful ones, because they say which instincts
this corpus punishes.

To argue with a decision, find its entry and argue with its measurement. If the measurement no longer holds,
that is a new dated entry, not an edit to the old one: two figures produced under different instruments are
not comparable, and erasing the first hides that.

## The data contracts

One file per ledger, describing every field and why it exists. Read the one for the ledger you are about to
write to — several fields exist to prevent a specific defect and look optional until you know which.

| file | ledger |
|---|---|
| [`contracts/candidates.md`](contracts/candidates.md) | what discovery found, and through which channel |
| [`contracts/query_hits.md`](contracts/query_hits.md) | every keyword result position, including duplicate and out-of-population hits |
| [`contracts/search_page_probe.md`](contracts/search_page_probe.md) | isolated, bounded OpenAlex page inspections |
| [`contracts/requests.md`](contracts/requests.md) | scholarly request events and completed/failed queries |
| [`contracts/acquisitions.md`](contracts/acquisitions.md) | every fetch attempt, its licence, and why it failed |
| [`contracts/normalize.md`](contracts/normalize.md) | documents and chunks |
| [`contracts/source_selection.md`](contracts/source_selection.md) | preparatory audits and append-only advisory screening/identity ledgers; production admission unchanged |
| [`contracts/claims.md`](contracts/claims.md) | a claim, its quote, and the engine's converted values |
| [`contracts/reviews.md`](contracts/reviews.md) | a second reader's verdict on one claim |
| [`contracts/profiles.md`](contracts/profiles.md) | stage-6 profiles and the adjudications a person signs |
| [`contracts/model_calls.md`](contracts/model_calls.md) | the file boundary every model-using stage crosses |
| [`contracts/flows.md`](contracts/flows.md) | a round selector bound to the protocol digests it ran under |
| [`contracts/scheduler_operations.md`](contracts/scheduler_operations.md) | scoped single-stage and network operations, with their exact plans and outcomes |
| [`contracts/network_schedules.md`](contracts/network_schedules.md) | finite UTC windows placed around already frozen network batches |
| [`contracts/copy_policies.md`](contracts/copy_policies.md) | a bounded, revocable allowance for acquiring matching future candidates |
| [`contracts/local_mandates.md`](contracts/local_mandates.md) | bounded recurring local work for one flow |
| [`contracts/worker_runtime.md`](contracts/worker_runtime.md) | expiring local worker heartbeat and its limits |
| [`contracts/periodic_dossiers.md`](contracts/periodic_dossiers.md) | whole-corpus periodic evidence handoff and its finalization gates |
| [`contracts/periodic_exports.md`](contracts/periodic_exports.md) | packaged cumulative dossier and verification |
| [`contracts/exports.md`](contracts/exports.md) | a verifiable snapshot of one flow, and how it is checked |
| [`contracts/control_api.md`](contracts/control_api.md) | the authenticated write boundary behind the portal |
| [`contracts/operators.md`](contracts/operators.md) | who may hold a control-API session, and the auth event log |
| [`contracts/decisions.md`](contracts/decisions.md) | operator decisions taken through the control API |
| [`contracts/drafts.md`](contracts/drafts.md) | operator reasoning drafts — never read by a stage or export |
| [`contracts/intake.md`](contracts/intake.md) | material an operator proposes, before any admission |
| [`contracts/journey.md`](contracts/journey.md) | the guided research page the server computes for the portal |
| [`contracts/new_project.md`](contracts/new_project.md) | the new-project wizard's drafts and routes |
| [`contracts/notifications.md`](contracts/notifications.md) | the outbox of events that need a person, and the Telegram and e-mail channels (D153, D154) |

## Removed material

The per-stage specs and plans, the replay and review reports and the provider integration guides were
removed from the tree on 2026-10-16 as superseded. They remain in git history: `git show 23a0a44:<path>`.
Where `DESIGN_DECISIONS.md` or `HANDOFF.md` cites one, the decision entry carries the measurement.

## Language

The reader-facing documents are in **English and Italian**: this map, the top-level README, and the guide.

Everything else is **English only**: the design record, the data contracts, the working documents
(`HANDOFF.md`, `SCHEDULER_BACKLOG.md`, the compose trial, the frontend handoffs) and the code
comments. That is a deliberate choice, not an omission. Those files change on almost every commit, and two
copies of a rule drift — the copy that drifts is the one that misleads someone. This repository already pins
`cli.BACKENDS` against `runners.available()` with a test for exactly that reason, and three tests written in
one day had to be fixed because they matched the *prose of a comment* rather than the code it described.

So: bilingual where it is stable and read occasionally, one language where it is worked on.
