# The control API — the contract

**Status:** contract for `claimstone control` (`claimstone/control.py`), decided by D87
(steps B4–B12 of the portal backend). The server is a separate process from the read API: it mounts the store read-write,
holds an operator session, and is the only process through the web that writes.

The read API (`claimstone api`, prefix `/api/v1`) stays read-only. Nothing in this
document adds a route to `api.py` or `transport.BaseHandler`. The control server reuses
`transport.py`'s Host and Origin checks and response headers; it does **not** inherit
"GET only".

## Two servers

| | read API | control API |
|---|---|---|
| prefix | `/api/v1` | `/control/v1` |
| verbs | GET | GET (authenticated reads) and POST |
| store mount | `:ro` | read-write |
| identity | operator session, validated by this server (D152); `--open-reads` only for a loopback single-user server | operator session |
| network egress | only the session probe to `control` | only the explicit admin checks (B11) and the operator URL fetch of intake (B7a) |

`claimstone control [--projects DIR] [--store DIR] [--bind 127.0.0.1] [--port 8790]
[--allow-host H]` refuses a non-loopback bind unless `--allow-host` names the proxy
authority, as `api` does.

## The read API's gate (D152, issue #7)

`claimstone api --session-authority URL` requires a valid session on every route in
`api_schema.ROUTES` except `GET /api/v1/meta`, the compose healthcheck's probe. The read
server holds no sessions: it sends the one `claimstone_control` cookie it received to
`GET {URL}/control/v1/session` and accepts a 200. The probe carries no other cookie, is
given an explicit timeout and does not follow redirects. Its answer is:

| answer | read API |
|---|---|
| 200 | the read is computed |
| 401 | `401 UNAUTHORIZED`, the §3.3 envelope |
| 500, 3xx, time-out, unreachable | `503 SESSION_AUTHORITY_UNAVAILABLE` — an outage is not a refusal |

The gate runs after the Host and Origin defences and before routing: a stranger's request
for an unknown path is 401, not a 404 that maps the API. A request with no cookie is 401
without asking the authority. Authentication only: any operator who can sign in may read
every project; per-project grants are not part of this contract.

Exactly one mode is required. `--open-reads` serves every read without a session, is off by
default, refuses a non-loopback bind, and prints a loud start-up warning. The compose `api`
service passes `--session-authority http://control:8790`; `/api/v1/meta` stays anonymous so
its healthcheck (`200`) does not depend on `control` being up. Exports and downloads are
`control` routes and already require a session; the read API only lists export metadata.

## What the control server never does

- It never signs for anyone. A signature carries the authenticated operator, never a typed
  name.
- It never preselects, suggests or defaults a verdict.
- It never starts network or paid model work except the two explicit actions named in the
  table above.
- It never decides scientific policy. Policies are declared in the project's input files
  or recorded by the operator, and the server enforces them.
  The new-project wizard records the policy the operator declares; the server checks it against the
  engine's loaders and decides none of it.
- It never ranks access, intake or purchase items by anything derived from claims, reviews
  or stances (F13).
- It never runs stage commands: discover, acquire, normalize, extract, review, synthesize.
  Executing work is the scheduler's job (B12).

## Sessions (B4)

Who may hold a session is the operators ledger (`operators.jsonl`) and its rules: row kinds, roles,
passwords, ids, revocation, the CLI that edits it and what to know before the portal is opened are in
`docs/contracts/operators.md`. The portal and the CLI write the same rows through the same functions. No
password ever appears in arguments, logs or responses.

- `POST /control/v1/session` with `{id, password}`: constant-time comparison; an unknown id, a disabled
  id and a wrong password answer the same 401 sentence. Two failure budgets, both 15-minute windows and
  both answering 429: **5 failures per id** and **20 per remote address** (a success does not clear the
  window — the count is of failures). On success a 32-byte random token (new at every sign-in) in the
  `claimstone_control` cookie — HttpOnly, SameSite=Strict, Path=/, `Secure` on TLS or behind
  `X-Forwarded-Proto: https` — and the response body
  `{"operator": {"id", "name", "role", "must_change_password"}, "csrf_token"}`.
- Sessions live in server memory. They expire after **12 hours of inactivity and, activity or not,
  7 days after sign-in**; a restart logs everyone out. Every request also re-checks the ledger (the
  person is enabled and the credential stamp is unchanged), so a disable or a password change made by any
  process ends the session on its next request.
- `DELETE` is not used: logout is `POST /control/v1/session/end`, which requires the
  session and the CSRF header, accepts an empty body, and expires the cookie.
- `GET /control/v1/session` returns `{operator: {id, name, role, must_change_password}, csrf_token}` or 401.
- `GET /control/v1/session/options` (anonymous) returns `{"google": false}`; Google sign-in is not built.
- Every POST — the login included — requires a present, same-origin `Origin` header.
- Credential writes (B11) and every admin action on people require the password again in the request.

Accounts and people, all under `/control/v1`. Every route is in `ROUTES` and passes the anonymous-access
sweep. A request body with an unknown key is a 400.

| Method and path | Who | Body → answer |
|---|---|---|
| `GET /account` | session | `{operator: {id, name, role, email, google_linked, must_change_password}}` |
| `POST /account/password` | session | `{current, new}` → `{changed: true}`; ends every other session of the id |
| `GET /account/sessions` | session | `{sessions: [{session_id, created_at, last_seen, method, current}]}`; never a token |
| `POST /account/sessions/end-others` | session | `{}` → `{ended: n}` |
| `GET /people` | admin | `{people: [{id, name, role, email, enabled, google_linked}]}` |
| `POST /people` | admin | `{password, id, name, email, role, temporary_password}` → 201 `{person}`; the person must change the temporary password at first sign-in |
| `POST /people/{id}/password` | admin | `{password, new_password}` → `{changed: true}`; marks the password as one to change; ends that person's sessions |
| `POST /people/{id}/disable`, `/enable` | admin | `{password}` → `{person}`; disabling ends that person's sessions |
| `POST /people/{id}/email` | admin | `{password, email}` → `{person}` |
| `POST /people/{id}/role` | admin | `{password, role}` → `{person}` |

In an admin body, `password` is the **acting admin's own** password (re-authentication). A wrong one is
403 `REAUTH` and counts against the same per-id budget as a failed login, so the fifth gives 429. A
non-admin gets 403 `FORBIDDEN` before any re-authentication, so cannot burn the admin's budget; the role is
read from the ledger at each request. The B11 administration routes (`/admin`, `/admin/check`,
`/admin/credential`, `/admin/paid-test`) are open to every operator: an admin differs from an operator
only in managing people. While a session's `must_change_password` is
true, every route except `GET`/`POST /session…`, `GET /account` and `POST /account/password` answers 403
`PASSWORD_CHANGE_REQUIRED`. Routes that carry a password (`/account/password`, `/people` and its
`password`, `disable`, `enable`, `email`, `role` actions, `/admin/credential`) **ignore
`Idempotency-Key`**: an answer to a password is never kept in memory or replayed.

The envelope codes B4 answers: `UNAUTHORIZED` (401), `NO_ORIGIN`/`CROSS_ORIGIN`/`CSRF`/
`FORBIDDEN`/`REAUTH`/`PASSWORD_CHANGE_REQUIRED` (403), `NOT_FOUND` (404), `METHOD_NOT_ALLOWED` (405), `BAD_REQUEST` (400), `TOO_LARGE`
(413), `VALIDATION` (422), `RATE_LIMITED` (429), `MISDIRECTED` (421). Every POST route
the server will ever answer is registered in `control.py`'s `ROUTES`, and the
anonymous-access test enumerates that registry, so a route added by a later step is
covered the moment it is registered.

## Rules for every mutating route

1. **Session.** A valid session cookie is required.
2. **CSRF.** A header `X-CSRF-Token` must equal the session's token. The `Origin` header
   must be present and allowed.
3. **Body.** `Content-Type: application/json`, at most 64 KiB, except the file upload of
   B7b. Unknown keys → 400.
4. **Lock.** The project writer lock (`Store.writer_lock`, B1) is held while re-reading
   the ledgers the decision depends on and appending. Network calls happen outside the
   lock; their outcomes re-enter under it.
5. **Freshness.** The live project is reloaded and registry drift is checked on every
   request, with `check_registry_drift(..., record=False)` (F9). Any drift → 409, nothing
   written.
6. **Ledger rows.** Every row carries `actor` (operator id), `signer_auth:
   "portal-session"`, a UTC `recorded_at`, the code revision, and a `*_version` integer of
   its record type.
7. **Idempotency.** A request may carry `Idempotency-Key` (1–200 characters). Keys are
   per operator and held in server memory for 24 hours; a restart forgets them, as it ends
   every session. A repeated key with the same route and body replays the first successful
   answer; with a different body → 409 `IDEMPOTENCY_CONFLICT`; while the first request still
   runs → 409 `IDEMPOTENCY_IN_PROGRESS`. A refused request keeps nothing, so its key stays
   free for the corrected request. (Implemented in B5.)
8. **Errors.** The read API's envelope (`{"error": {"code", "message"}}`):
   - 401: no session.
   - 403: CSRF, Origin or permission failure.
   - 404: unknown id. Ids are looked up in ledgers, never used as paths.
   - 409: stale, drift, conflict or policy refusal.
   - 413: body too large.
   - 422: validation.

   The message is the engine's own sentence when there is one, for example
   `StaleProfile`'s.

## Routes

`{p}` is a project name, `{flow_id}` a flow id (sha256 of the binding), `{question_id}` a
question id from the registry. Every id is looked up in ledgers, never used as a path.

### B5 — signing and drafts

- `POST /control/v1/p/{p}/flows/{flow_id}/q/{question_id}/adjudicate` with `{verdict,
  rationale, profile_sha256, attest: true, never_asked_basis?}`: resolves the flow to its selector; calls
  `synthesize.adjudicate` under the project lock with `by` = operator display name,
  `signer_auth="portal-session"` and `actor` = operator id. `attest` must be the literal
  `true`; `verdict` must be one of `cli.VERDICT_NAMES`, and an operational question → 409
  with the engine's sentence. Returns the stored row. There is no "opened N of M" check:
  the design keeps it a reading aid.
- `POST …/q/{question_id}/draft` with `{rationale, profile_sha256}` appends to
  `drafts.jsonl`. `PUT` is not used.
- `GET …/q/{question_id}/draft` returns the operator's latest draft and whether its
  `profile_sha256` is still current.

Drafts are never read by the engine, never exported and never count as a signature.

As built (B5):
- Signing also requires the flow's binding to be `CURRENT` (`flows.binding_state`). A
  drifted flow → 409 `FLOW_DRIFTED`, naming the state and the differing digests: the flow no
  longer names the protocol the engine judges with. Drafts do not require it.
- `adjudicate` answers 201 `{"adjudication": <the stored row>}`. Request-rule refusals are
  422 `VALIDATION` before the engine runs: verdict not one of the five (nothing is
  preselected or defaulted), `attest` not the literal `true`, rationale under 120 trimmed
  characters, `profile_sha256` not 64 hex. A `NEVER_ASKED` verdict must name
  `never_asked_basis` (currently only `SIGNER_ATTESTATION`); the key on any other verdict is
  refused, both 422. Engine refusals are 409: `NO_PROFILE`, `PROVISIONAL`,
  `STALE_PROFILE`, and `REFUSED` (an operational question), each with the
  engine's sentence. Unknown project, flow or question → 404.
- `POST …/draft` answers 201 `{"draft", "current", "current_profile_sha256"}`; `GET …/draft`
  answers the operator's own latest draft or `null`, with `current` null when there is no
  draft. Another operator's drafts are never returned. Row format: `docs/contracts/drafts.md`.

### B7a — intake: references, DOIs, links

- `POST /control/v1/p/{p}/flows/{flow_id}/intake` with `{kind: "doi"|"url"|"reference",
  value, note?}`. DOI: normalise (`ids.py`). URL: `urlguard.check` before anything else.
  Reference: stored as text, flagged for identity resolution.
- **Cohort routing**, decided by the server and returned before anything counts: a new
  work cannot join a frozen round (closed manifest or cohort). It either matches an
  existing candidate — a copy or version, going to identity resolution — or is recorded
  as `NEEDS_NEW_ROUND` with the open flows it could go to. If the round is open, the item
  becomes an intake candidate for that round's next discover. **Do not run discover.**
- `POST …/intake/{intake_id}/fetch`: a URL item may be fetched **once**, through
  `Fetcher` (robots, budget, guard on every hop), recorded in `requests.jsonl`. A fetched
  PDF continues as in B7b.
- `GET /control/v1/p/{p}/flows/{flow_id}/intake` lists items with their latest state.

As built (B7a):
- The routes are `POST` and `GET /control/v1/p/{p}/flows/{flow_id}/intake`. `POST` answers 201
  `{"intake": <row>}`. A malformed item or a forbidden destination is 422 and is not recorded.
- `GET` answers `{"flow_id", "items"}`: the latest state per item, newest first.
- Routing and the row format: `docs/contracts/intake.md`.
- **The single explicit fetch moved to B7b.** Its only purpose is to put bytes into the
  quarantine that B7b builds, so B7a makes no request of any kind.

### B7b — intake: files and quarantine

- `POST /control/v1/p/{p}/flows/{flow_id}/intake/file?target={candidate_id}`: the body is
  the file bytes, `Content-Type: application/pdf` (or the supplement types the normalize
  stage accepts), at most 50 MiB. Bytes are hashed while streamed and written to
  `quarantine/<sha256>.<ext>`. Identical bytes already held (`raw/` or `quarantine/`) →
  DUPLICATE, "same file, nothing added", nothing new stored.
- **Checks** reuse the engine's own gates; no new heuristics: magic bytes; the existing
  "is this a document" content gate used for downloads; identity against the target
  candidate's metadata (title, DOI, authors), using the same comparison `source_selection`
  uses for identity counterparts. A mismatch → POSSIBLE_VERSION, which opens an identity
  decision via `source_selection`'s identity API, never a merge, or REJECTED with the
  reason.
- **On pass:** bytes move to `raw/<sha256>.<ext>`; one `acquisitions.jsonl` row is
  appended with `provenance: "operator-supplied"`, an empty `attempts` list and an
  unknown licence kept unknown, following the `store-reuse` precedent in
  `docs/contracts/acquisitions.md`.
- **Floor policy.** `sources.yaml` may declare `supplied_copies: count | separate`; the
  default is `separate`. `separate`: admissibility excludes `operator-supplied` rows from
  the floor numerator and reports them on their own line. `count`: they count like any
  confirmed copy. The denominator never changes. The policy is in the protocol digest, so
  changing it is drift.
- **Not done here:** normalising the new copy. It is listed as ready for the next scoped
  normalize run.

As built (B7b):
- `POST /control/v1/p/{p}/flows/{flow_id}/intake/file?target={candidate_key}` answers 201
  `{"intake": <row>}`.
- Refusals before any byte is read:
  - 411: no `Content-Length`;
  - 413: over 50 MiB;
  - 415: not `application/pdf`;
  - 422: no target;
  - 404: a target that is not in the flow.
- Outcomes and states: `docs/contracts/intake.md`; the acquisition row:
  `docs/contracts/acquisitions.md`.
- The policy key is in the protocol digest only when declared, so flows bound before this step
  stay `CURRENT`.
- The single explicit fetch of an intake URL is **not built**. B7b needs no fetch: an operator who
  holds a copy uploads it. Fetching an operator-supplied URL is a network campaign, so it waits for
  the scheduler's authorized operations (B12) rather than becoming a side door around them.
- The control container needs `pdftotext` (poppler-utils): B13.

### B8 — operator decisions

- `POST …/identity/{observation_id}/resolve` with `{answer:
  "same_work"|"version_of"|"different"|"not_sure", reason}`. The reason is required,
  ≥ 20 trimmed characters, except `not_sure`. Appends through `source_selection`'s
  identity API, which refuses silent merges. Both records are kept; the count of
  independent studies is unchanged by `version_of`.
- `POST …/decisions/retry-campaign` with `{candidate_ids, campaign_name, max_requests,
  hosts}`. Server-side validation: the hosts are those recorded for those candidates,
  `max_requests` is bounded, excluded hosts are refused. The decision is recorded only;
  execution is B12 or the CLI.
- `GET …/decisions/retry-campaign/preview?candidate_ids=…` returns the exact plan, built
  by the same code.
- `POST …/offers` with `{candidate_id, work_version, vendor, price, currency, tax_status?,
  terms_url, verified_at, resolves}` records an offer as *verified by the operator*.
- `POST …/offers/{offer_id}/stage` with `{stage: "approved"|"bought_externally"|"declined"}`.
  `copy_provided` and `copy_verified` are **set only by intake**, B7b linking an intake to
  the offer; never by hand. A changed price, vendor or terms is a new offer; the old one
  becomes `obsolete`, linked. A 403 is never an offer.
- `POST …/decisions/{decision_id}/state` with `{state: "deferred"|"declined", until?,
  reason}`. The row records what the decision blocked and what continues; the server
  computes both from the inbox model, not the client. Declined work is never executed by
  anything.
- **Ordering (F13).** The decisions list is ordered by required/optional, then by
  acquisition metadata and frozen denominators, then by age.

As built (B8): row format and rules in `docs/contracts/decisions.md`.
- `POST …/intake/{intake_id}/resolve` `{answer, reason}` → 201 `{decision, intake}`.
- `GET …/decisions` → `{open, decided_recently}`.
- `GET …/decisions/retry-campaign/preview?candidate_ids=a,b` → the plan.
- `POST …/decisions/retry-campaign` `{candidate_ids, campaign, max_requests}` → 201.
- `POST …/decisions/{decision_id}/state` `{state, until?, reason}` → 201.
- `POST …/offers` → 201.
- `POST …/offers/{offer_id}/stage` `{stage}` → 201.

Error mapping: a refused rule is 422, a state conflict 409, an unknown id 404.
`source_identity.jsonl` observations (D79–D81 screening scopes) are not written from here. The
portal resolves intake items; screening identity keeps its own tools.

### B9 — today

- `POST /control/v1/seen` with `{project?, until}` appends to `seen.jsonl`.
- `GET /control/v1/today` returns, for the operator: `changed` since their last marker,
  from ledger `recorded_at` values only (F17: no mtimes); `needs_you`, split into required
  and optional; and `continues_without_you`, flows with work authorized and not blocked —
  empty until B12 exists, said so in a field rather than shown as an empty list that means
  "nothing".

As built (B9):
- **`seen.jsonl` is installation state**, in the state directory beside `operators.jsonl`, not per
  project. A marker without a project covers every project, and an operator's markers are theirs
  alone. The file is owner-only (`0600`).
- Rows: `{seen_version: 1, actor, project|null, until, recorded_at}`. `until` defaults to now and
  must carry a zone and not be in the future.
- `POST /control/v1/seen` `{project?, until?}` → 201. An unknown project → 404.
- `GET /control/v1/today` → per project:
  - `since` and `first_visit`;
  - `changed`: per-stage counts and the 20 newest rows after the marker, from the rows' own
    timestamps only, with the count of undated rows reported rather than guessed;
  - `needs_you`, with `required` (inbox `ADJUDICATION`, `INTEGRITY`, `PROTOCOL` cards and identity
    questions) and `optional` (offers, deferred items now due).

  A project that cannot be read carries `error` instead of being left out.
  `continues_without_you` is `null` with a note until B12 reports the scheduler's queue.

### B10 — exports

- `POST /control/v1/p/{p}/flows/{flow_id}/exports` with `{include_pdfs: false}` calls
  `export.export` under the lock and returns `{export_id, created_now}`.
- `include_pdfs: true` adds only files whose recorded licence permits redistribution. An
  unknown licence is **excluded and listed**. The manifest records the rule and the
  excluded ids.
- `POST …/exports/{export_id}/verify` runs `export.verify` and returns its problems list.
  It is never run as a side effect of a GET.
- Read API: `GET /api/v1/p/{p}/flows/{flow_id}/exports` lists `exports.jsonl` rows
  (read-only; the only read-API route in this contract). Implemented 2026-10-07 (BR), on
  the read API with the house spelling `GET /api/v1/projects/{p}/flows/{flow_id}/exports`:
  entries carry `export_id`, `created_at` and `actor` when the row records one, never the
  server-side `path`.

As built (B10):
- `POST …/exports` `{include_copies?: bool}` → 201 on creation, or 200 with `created_now: false`
  for an identical snapshot. Answers `{export_id, created_now, copies}`.
- `POST …/exports/{export_id}/verify` `{}` → 200 `{export_id, holds, problems}`. An export id not
  in this flow's ledger → 404.
- The spec's `include_pdfs` is named `include_copies`, because held copies are not only PDFs (HTML
  and JATS too). Rules in `docs/contracts/exports.md`.

### B11 — administration

- `POST /control/v1/admin/check` with `{target: "llamacpp"|"ollama-cloud"|"grobid"}`: a
  single unpaid reachability request — llamacpp `/health`, ollama-cloud model list, GROBID
  `/api/isalive`; timeout 5 s, descriptive User-Agent with contact; appends to
  `admin_checks.jsonl` with `{target, ok, status, latency_ms, checked_at, actor}`.
- `GET /control/v1/admin` returns `admin_state` plus the latest check per target.
- `POST /control/v1/admin/credential` with `{name, value, password}`: `name` must be one of
  the names in `admin_state`; re-authentication is required; writes `.env` atomically
  (temp file plus `os.replace`), mode 0600, preserving other lines. The response and every
  log line contain the name only. There is no GET that returns a value.
- The paid test call is **not built**: it needs the model-call boundary and a cost
  reservation, so it belongs to the scheduler (B12). The route returns 501 with that
  sentence.

As built (B11):
- **No route contacts a service to answer a read.** `GET /control/v1/admin` returns:
  - `admin_state` (credential presence, configured backends, instruments);
  - `checks`, the last recorded check per service;
  - `check_targets`, the configured address of each service.
- `POST /control/v1/admin/check` `{target}` → 201.
  - `target` is a name (`llamacpp`, `ollama-cloud`, `grobid`), never an address. The addresses come
    from configuration: llama.cpp's `/health`, Ollama Cloud's unpaid model list `/api/tags`, and
    GROBID's `/api/isalive` at `CLAIMSTONE_GROBID_URL`.
  - The check is one request, with a 5 s timeout, no redirects, and the descriptive agent with
    contact. Without `CLAIMSTONE_CONTACT_EMAIL` → 422.
  - Outcome recorded in `admin_checks.jsonl` (state dir, `0600`, `admin_check_version 1`):
    `{kind: "reachability", target, url, ok, status, detail, latency_ms, actor, recorded_at}`.
- `POST /control/v1/admin/credential` `{name, value, password}` → 201.
  - The password is asked again. A wrong one → 403 `REAUTH`, counted against the login budget, so
    the fifth failure gives 429.
  - `name` is one of `portal_state.CREDENTIAL_NAMES`; `value` is one line of at most 4096
    characters.
  - `.env` is rewritten atomically with every other line kept, mode `0600`.
  - The response and the ledger row (`kind: "credential"`, `name`, `actor`) never contain the
    value.
- `POST /control/v1/admin/paid-test` → 501 with the reason.

### B12 — scheduler-facing routes (conditional)

Precondition: the scheduler track has committed an operations ledger module implementing
`docs/contracts/scheduler_operations.md`. If it does not exist, these routes are absent.

- `POST …/operations/{plan_id}/authorize` appends `authorized` with the operator, the exact
  `plan_id` and the limits it shows. An authorization cannot enlarge the plan.
- `POST …/operations/{operation_id}/pause` appends `stopping`.
- `POST …/operations/{operation_id}/resume` appends a new authorization over the remaining
  units only, with the cumulative ceiling.
- `GET …/operations` returns state, worker last heartbeat, last completed unit, and spent,
  reserved and remaining per authorization. An expired lease is `INTERRUPTED`, shown as
  "Status being checked".

### New project — drafts and creation

See `docs/contracts/new_project.md`. These routes keep a private draft ledger and, on confirmation, create
one new directory under `projects/` through `project_builder.create_project`, the only code that writes
there. The `control` service therefore mounts `projects/` read-write; it still never runs a stage and never
starts network or paid work.

## New ledgers (all append-only JSONL, `store/<project>/`)

| file | step | contains |
|---|---|---|
| `adjudications.jsonl` (existing) | B3 | gains `adjudication_version: 2`, `signer_auth`, `actor` |
| `drafts.jsonl` | B5 | operator reasoning drafts; never read by the engine |
| `intake.jsonl` | B7 | one row per material event: received, checked, outcome |
| `quarantine/<sha256>.<ext>` | B7b | uploaded bytes before they pass |
| `decisions.jsonl` | B8 | operator decisions: retry campaigns, purchase offers, defer/decline, obsolete |
| `seen.jsonl` | B9 | per-operator "seen up to" markers |
| `exports.jsonl` (existing) | B10 | unchanged format; rows also carry `actor` when made from the portal |

Installation-level files live in `CLAIMSTONE_STATE_DIR`, default `.claimstone/`, which
must be gitignored: `operators.jsonl` (B4) and `admin_checks.jsonl` (B11).

Each new record type gets a contract file under `docs/contracts/` and a version constant
registered in `tools/check_instrument_versions.py`.

## Operator policies this contract enforces but does not choose

| policy | where it is declared | default until declared |
|---|---|---|
| supplied copies count toward the floor | `sources.yaml: supplied_copies` | `separate` |
| who records "bought externally" | any authenticated operator, recorded with `actor` | — |
| evidence of possession | only an intake that passes B7b sets `copy_verified` | — |
| PDFs with unknown licence in exports | excluded and listed | excluded |
As built (B12):
- `GET …/operations` → `{flow_id, operations}`. Each operation is read through the scheduler's own
  replay (`operations._events`), so a damaged ledger is a 409 here as it is a refusal for the worker.
  Each carries:
  - `stage`, `state` (the scheduler's words) and `state_note`;
  - `limits`, `spent_usd`, `units_with_unknown_cost` and `remaining_usd`;
  - `units_completed`, `last_event_at`, `authorized_by`;
  - `worker_last_seen: null`: the ledger has no heartbeat, and the last event is not proof of
    running.
- `POST …/operations/{operation_id}/authorize` `{limits}` → 201, or 200 if it was already
  authorized.
  - `limits` must equal the plan's `{network_requests, model_calls, spend_usd}`, otherwise 409
    `PLAN_DIFFERS`: an authorization never covers more than what was read.
  - The `authorized` event records `identity: {signer_auth: "portal-session", operator, name}`
    through a new optional `identity` argument of `operations.authorize`. The CLI still records
    the OS login.
- `POST …/operations/{operation_id}/pause` and `…/resume` → 501. The operation ledger's transition
  table has no `stopping` event yet, and appending one would make the whole ledger invalid. **Not
  built**: it belongs to the scheduler track.
- Single operations are still planned by the scheduler and the CLI; a discovery or acquisition **batch** is planned from the portal (D132, below).
- `GET …/batches` → `{flow_id, batches}` for frozen operation batches in this
  flow. Each batch includes its ID, exact units and hosts, skipped subjects,
  summed physical-request ceiling, current operation states and the number
  awaiting approval. A changed batch hash or mismatched operation is a 409.
- `POST …/batches/{batch_id}/authorize` with the displayed
  `{operation_ids, max_total_requests}` → 201 when it authorizes new units, 200
  on an idempotent repeat. A mismatch is 409 `PLAN_DIFFERS`; the event names
  the authenticated portal operator on every newly authorized operation.
- `POST /control/v1/p/{p}` `/flows` with `{title, round}` → 201 `{flow_id, created: true, title, round}`, or 200
  `created: false` for the same binding. It binds the named round to the protocol as it stands (for a
  project that declares a population, it freezes that population for the round) and sends no request. `title` is 1 to
  120 characters; `round` matches `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`; both are required and nothing else is accepted
  (422 `VALIDATION`). A drifted registry or a changed population is 409 `REFUSED`.
- `POST …/flows/{flow_id}/batches` with `{stage: "discover"|"acquire", apis, allowed_hosts, max_units,
  max_requests_each, per_query}` → 201 with the frozen batch (`batch_id`, `operation_ids`, `units`,
  `max_total_requests`). It writes `planned` rows only and contacts no host. Exact hosts are required
  (`apis` only for `discover`); a flow with no candidates cannot plan `acquire` (409 `REFUSED`).
  An optional `use_apis: true` (acquire only; default false, 422 otherwise) lets each unit also ask the
  Unpaywall and OpenAlex APIs for open-access locations: those two hosts, and every host a location may
  point to, must then be in `allowed_hosts`, or the request is refused as outside the plan.
  Optional `retry_classes` (acquire only; terminal network classes) with a mandatory `retry_reason`
  (1–400 characters) re-plans candidates whose last attempt ended in one of those classes: a named
  campaign, as on the CLI. `retry_reason` without `retry_classes`, or either on `discover`, is 422.
  Authorizing stays the separate exact act above.
- `GET …/flows/{flow_id}/acquire-hosts` (session required, read-only) → `{pending_candidates,
  candidate_hosts: [{host, candidates}], refused_hosts: [{host, candidates}],
  retryable_classes: [{failure_class, candidates}], plain_http_candidates,
  suggested_max_requests_each}` (5 when a pending URL is plain `http` or a candidate already hit the
  request ceiling, otherwise 3; a plain-`http` URL spends one request on the redirect to `https`): the hosts an `acquire` plan
  would need, read from the record: the hosts of the URLs of candidates with no attempt yet, and the hosts
  earlier attempts were refused at as "outside this plan". Hosts in the project's `excluded_hosts` are never
  suggested. A suggestion, not a grant: the portal pre-fills the plan form with it, the person edits the list
  and plans, and the plan still needs its own authorization.
- Today (B9) now reports `continues_without_you` per project: the authorized, running or
  interrupted operations.

### Finite periodic scheduler controls (D128)

All routes below have prefix `/control/v1/p/{p}` and use the ordinary session,
Origin and CSRF checks. Planning appends frozen local plans only. Authorizing
records the authenticated operator; the control server never executes a stage.

| Route | Request body | Response |
|---|---|---|
| `GET /scheduler` | — | `{project, schedules, copy_policies, local_mandates, workers, archive}` |
| `POST /periodic-plans` | `{source_flow_id, rounds, apis, allowed_hosts, max_units_each, max_requests_each, per_query}` | 201; dated child flows and frozen schedule plan |
| `GET /schedules/{schedule_id}` | — | Frozen plan, state and events |
| `POST /schedules/{schedule_id}/authorize` | `{plan_sha256, max_total_requests}` | 201/200; finite schedule authorization |
| `POST /schedules/{schedule_id}/revoke` | `{plan_sha256}` | 200; stops later starts |
| `POST /copy-policies` | `{schedule_id, allowed_hosts, source_classes, max_candidates, max_requests_each, not_before, expires_at}` | 201; frozen future-copy policy |
| `GET /copy-policies/{policy_id}` | — | Policy, reservations, state and events |
| `POST /copy-policies/{policy_id}/authorize` | `{policy_sha256, max_candidates, max_requests_each, max_total_requests}` | 201/200; contingent copy permission |
| `POST /copy-policies/{policy_id}/revoke` | `{policy_sha256}` | 200; stops later copy starts |
| `POST /flows/{flow_id}/retry-policies` | `{allowed_hosts, max_retries, max_attempts_each, max_requests_each, use_apis, base_delay_hours, max_delay_hours, expires_at}` | 201; frozen retry policy ([retry_policies](retry_policies.md)), `PLANNED` |
| `GET /flows/{flow_id}/retry-policies` | — | `{policies: [status]}` newest first |
| `GET /retry-policies/{policy_id}` | — | Policy, reservations, state and events |
| `POST /retry-policies/{policy_id}/authorize` | `{policy_sha256, max_retries, max_requests_each, max_total_requests}` | 201/200; permission to retry transient failures |
| `POST /retry-policies/{policy_id}/revoke` | `{policy_sha256}` | 200; stops later retry starts |
| `GET /local-mandates/{mandate_id}` | — | Mandate, child IDs, reservations and state; `model_backend` and `paid_budget` (`budget_cents`, `reserved_cents`, `max_call_cents`, prices) or `null` |
| `POST /local-mandates/series` | `{schedule_id, flow_ids, extract_model, review_model, max_total_local_calls}` | 201; one shared lifetime cap over the exact child flows |
| `POST /flows/{flow_id}/local-mandates` | `{flow_id, extract_model, review_model, max_total_local_calls}`, optionally `backend: "ollama-cloud"` with all of `budget_cents, max_call_cents, price_in_cents, price_out_cents` (D135) | 201; one-flow local mandate; the paid fields are 422 unless `backend` is `ollama-cloud`, which needs all four |
| `POST /local-mandates/{mandate_id}/disable` | `{mandate_id}` | 200; stops later local passes |

All request bodies require exactly the shown keys. The client must repeat the
hash and limits from GET before authorization; mismatch is 409 `PLAN_DIFFERS`.
Unknown IDs are 404. The engine's policy refusal is 409 `REFUSED`. Schedule
approval alone covers only its frozen discovery operations. Future copies
require the separate policy and local extraction/review requires the separate
mandate. The worker still uses the same ledger gates as CLI authorizations.

### Worker observation, archive paging and cumulative download (D129)

`GET /control/v1/p/{p}/scheduler` now returns at most 25 of **each** schedule,
copy policy and local mandate by default. `?limit=N` accepts 1–100;
`archive.total` has the three total counts, `archive.next_cursor` advances
each collection by one page, and `archive.revision` names the ID inventory.
Pass the opaque cursor back as `?limit=N&cursor=...`. If an item is added,
409 `ARCHIVE_CHANGED` requires restarting at page one. An invalid cursor is
400 `BAD_REQUEST`. The index also returns `workers.supervisor` (the
installation-wide D130 coordinator), `workers.operations` and
`workers.mandates[mandate_id]` for the mandates on that page. Worker status is
ephemeral process liveness, never evidence that an operation completed; see
`worker_runtime.md`.

The following authenticated routes package a current finalized cumulative
dossier (see `periodic_exports.md`):

| Route | Body or result |
|---|---|
| `POST /schedules/{schedule_id}/export` | `{dossier_id}`; echo the current final dossier ID from the read API. 201 on creation, 200 on an identical repeat, 409 for stale or unfinished evidence. |
| `GET /periodic-exports/{export_id}` | Export ledger row and manifest. |
| `GET /periodic-exports/{export_id}/download` | `application/zip` attachment containing four report files, no copies. |
| `POST /periodic-exports/{export_id}/verify` | `{}`; returns `{holds, problems}` after recomputation. |

These four paths are under `/control/v1/p/{p}`. A valid session is required
for reads and downloads; POST also requires Origin and CSRF. Export IDs are
looked up in the ledger and may not be arbitrary filesystem paths.

