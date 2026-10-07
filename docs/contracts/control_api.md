# The control API — the contract

**Status:** contract for `claimstone control` (`claimstone/control.py`), specified in
`docs/superpowers/specs/2026-10-07-portal-backend-spec.md` (steps B4–B12) and decided by
D87. The server is a separate process from the read API: it mounts the store read-write,
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
| identity | none | operator session |
| network egress | none | only the explicit admin checks (B11) and the operator URL fetch of intake (B7a) |

`claimstone control [--projects DIR] [--store DIR] [--bind 127.0.0.1] [--port 8790]
[--allow-host H]` refuses a non-loopback bind unless `--allow-host` names the proxy
authority, as `api` does.

## What the control server never does

- It never signs for anyone. A signature carries the authenticated operator, never a typed
  name.
- It never preselects, suggests or defaults a verdict.
- It never starts network or paid model work except the two explicit actions named in the
  table above.
- It never decides scientific policy. Policies are declared in the project's input files
  or recorded by the operator, and the server enforces them.
- It never ranks access, intake or purchase items by anything derived from claims, reviews
  or stances (F13).
- It never runs stage commands: discover, acquire, normalize, extract, review, synthesize.
  Executing work is the scheduler's job (B12).

## Sessions (B4)

Operators are declared on the CLI, not the web. `claimstone operator add ID --name
"Display name"` prompts for a password twice (`getpass`) and appends to `operators.jsonl`
(in `CLAIMSTONE_STATE_DIR`, default `.claimstone/`, gitignored):
`{operator_version, id, name, scrypt params, salt, hash, created_at}`, `hashlib.scrypt`
with n=2^15, r=8, p=1. `operator disable ID` appends a disabling row; the latest row per
id is the id's state, and an id with any row at all is refused by `add` — re-enabling is
a deliberate act this ledger does not silently perform. No password ever appears in
arguments, logs or responses.

- `POST /control/v1/session` with `{id, password}`: constant-time comparison; 5 failures
  per id per 15 minutes → 429 (a success does not clear the window — the count is of
  failures); an unknown id and a wrong password answer the same 401 sentence. On success
  a 32-byte random token in the `claimstone_control` cookie — HttpOnly, SameSite=Strict,
  Path=/, `Secure` on TLS or behind `X-Forwarded-Proto: https` — and the response body
  `{"operator": {"id", "name"}, "csrf_token"}`.
- Sessions live in server memory and expire after 12 hours of inactivity; a restart logs
  everyone out.
- `DELETE` is not used: logout is `POST /control/v1/session/end`, which requires the
  session and the CSRF header, accepts an empty body, and expires the cookie.
- `GET /control/v1/session` returns `{operator: {id, name}, csrf_token}` or 401.
- Every POST — the login included — requires a present, same-origin `Origin` header.
- Credential writes (B11) require the password again in the request.

The envelope codes B4 answers: `UNAUTHORIZED` (401), `NO_ORIGIN`/`CROSS_ORIGIN`/`CSRF`
(403), `NOT_FOUND` (404), `METHOD_NOT_ALLOWED` (405), `BAD_REQUEST` (400), `TOO_LARGE`
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
4. **Lock.** The project writer lock (`claimstone/locks.py`, B1) is held while re-reading
   the ledgers the decision depends on and appending. Network calls happen outside the
   lock; their outcomes re-enter under it.
5. **Freshness.** The live project is reloaded and registry drift is checked on every
   request, with `check_registry_drift(..., record=False)` (F9). Any drift → 409, nothing
   written.
6. **Ledger rows.** Every row carries `actor` (operator id), `signer_auth:
   "portal-session"`, a UTC `recorded_at`, the code revision, and a `*_version` integer of
   its record type.
7. **Idempotency.** A request may carry `Idempotency-Key`; a repeated key with the same
   body returns the first result. A repeated key with a different body → 409.
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
  rationale, profile_sha256, attest: true}`: resolves the flow to its selector; calls
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

### B9 — today

- `POST /control/v1/seen` with `{project?, until}` appends to `seen.jsonl`.
- `GET /control/v1/today` returns, for the operator: `changed` since their last marker,
  from ledger `recorded_at` values only (F17: no mtimes); `needs_you`, split into required
  and optional; and `continues_without_you`, flows with work authorized and not blocked —
  empty until B12 exists, said so in a field rather than shown as an empty list that means
  "nothing".

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