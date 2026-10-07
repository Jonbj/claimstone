# Portal backend — the write boundary for design v2.1

**Date:** 2026-10-07. **Status:** implementation specification, to be built in steps B0–B13.
**Branch:** `research-portal`.
**Design it serves:** `docs/design/portal/v2/README.md` (v2.1, fifteen boards). Its §7 table says which
controls need backend work; this document specifies that work.
**Findings it closes:** F5, F6, F13, F14, F15 and F16 of
`docs/superpowers/specs/2026-10-06-research-portal-review.md`, and the "first implementation gate" of
`docs/contracts/scheduler_operations.md`.

`CLAUDE.md` overrides this document wherever they differ. When this document is silent, choose the smallest
behaviour that keeps every existing test passing and every invariant intact, and record the choice.

## 1. Shape

### 1.1 Two servers, not one

The read API (`claimstone api`, D84) **stays read-only**: GET only, store mounted `:ro`, no secret, no
authentication. Nothing in this specification adds a write path to `api.py` or `transport.BaseHandler`.

Writes go through a **new, separate process**: `claimstone control` (`claimstone/control.py`).

| | read API | control API |
|---|---|---|
| prefix | `/api/v1` | `/control/v1` |
| verbs | GET | GET (authenticated reads) and POST |
| store mount | `:ro` | read-write |
| identity | none | operator session |
| network egress | none | only the explicit admin checks of B11 and the operator URL fetch of B7 |

Why two processes: D84 records "the API holds no secret and mounts the store read-only" as a security
property. Keeping it means a defect in a read route can never write. The control server reuses the Host/Origin
checks and response headers of `transport.py`, by composition or a sibling base class. It does **not**
inherit "GET only".

### 1.2 What the control server never does

- It never signs for anyone. A signature carries the authenticated operator, never a typed name.
- It never preselects, suggests or defaults a verdict.
- It never starts network or paid model work except the two explicit actions named in 1.1.
- It never decides scientific policy. Policies are declared in the project's input files or recorded by the
  operator, and the server enforces them.
- It never ranks access, intake or purchase items by anything derived from claims, reviews or stances (F13).
- It never runs stage commands: discover, acquire, normalize, extract, review, synthesize.
  Executing work is the scheduler's job (B12).

### 1.3 Common rules for every mutating route

1. **Session.** A valid session cookie is required (B4).
2. **CSRF.** A header `X-CSRF-Token` must equal the session's token. The `Origin` header must be present
   and allowed.
3. **Body.** `Content-Type: application/json`, at most 64 KiB, except the file upload of B7b. Unknown keys
   → 400.
4. **Lock.** The project writer lock (B1) is held while re-reading the ledgers the decision depends on and
   appending. Network calls happen outside the lock; their outcomes re-enter under it.
5. **Freshness.** The live project is reloaded and registry drift is checked on every request, with
   `check_registry_drift(..., record=False)` (F9). Any drift → 409, nothing written.
6. **Ledger rows.** Every row carries `actor` (operator id), `signer_auth: "portal-session"`, a UTC
   `recorded_at`, the code revision, and a `*_version` integer of its record type.
7. **Idempotency.** A request may carry `Idempotency-Key`; a repeated key with the same body returns the
   first result. A repeated key with a different body → 409.
8. **Errors.** The read API's envelope (`{"error": {"code", "message"}}`) is used.
   - 401: no session.
   - 403: CSRF, Origin or permission failure.
   - 404: unknown id. Ids are looked up in ledgers, never used as paths.
   - 409: stale, drift, conflict or policy refusal.
   - 413: body too large.
   - 422: validation.

   The message is the engine's own sentence when there is one, for example `StaleProfile`'s.

### 1.4 New ledgers (all append-only JSONL, `store/<project>/`)

| file | step | contains |
|---|---|---|
| `adjudications.jsonl` (existing) | B3 | gains `adjudication_version: 2`, `signer_auth`, `actor` |
| `drafts.jsonl` | B5 | operator reasoning drafts; never read by the engine |
| `intake.jsonl` | B7 | one row per material event: received, checked, outcome |
| `quarantine/<sha256>.<ext>` | B7b | uploaded bytes before they pass |
| `decisions.jsonl` | B8 | operator decisions: retry campaigns, purchase offers, defer/decline, obsolete |
| `seen.jsonl` | B9 | per-operator "seen up to" markers |
| `exports.jsonl` (existing) | B10 | unchanged format; rows also carry `actor` when made from the portal |

Installation-level files live in `CLAIMSTONE_STATE_DIR`, default `.claimstone/`, which must be gitignored:
`operators.jsonl` (B4) and `admin_checks.jsonl` (B11).

Each new record type gets a contract file under `docs/contracts/` and a version constant registered in
`tools/check_instrument_versions.py`.

## 2. Steps

### B0 — Decision entry and contracts (documentation only)

- Write the next free `D` number in `docs/DESIGN_DECISIONS.md`: "A separate authenticated control service for
  portal writes". Record:
  - which clauses of D82/D84 stay unchanged: the read API stays read-only;
  - the two-process reason (1.1);
  - the rules of 1.2 and 1.3;
  - the operator policies this work enforces but does not choose (§3).
- Write `docs/contracts/control_api.md`: routes, envelope, auth and CSRF, and the ledger table of 1.4.

**Done when:** the files exist and the checks pass. No code.

### B1 — One project writer lock (F5)

- `claimstone/locks.py`: `project_lock(store)`, a context manager taking an exclusive `fcntl.flock` on
  `store/<project>/.project.lock`.
  - Re-entrant within one process: a thread-local depth counter.
  - Documented order: **project lock first**, then the existing `.flows.lock` and source-selection lock.
    Never the reverse.
- Adopt it in every writer that appends to a project ledger: every stage command in `cli.py`, `flows`,
  `source_selection`, `export`, `synthesize.adjudicate`. Under it, re-read the state the write depends on:
  - `acquire`: re-read the candidate's latest attempt immediately before appending, and refuse a duplicate
    `attempt_no`;
  - `adjudicate`: the profile check and the append happen under one hold.
- Network and model calls must not run while the lock is held. Where a stage currently fetches and appends in
  one loop, take the lock per append and re-check before it.

**Tests:**
- two processes (`multiprocessing`) appending through the same writer → no duplicate ids;
- adjudicate racing a synthesize that changes the profile → exactly one of "signed" or `StaleProfile`,
  never a signature on the old hash;
- lock order: acquiring flows-lock-then-project-lock raises in debug mode, or is proven impossible by
  construction.

### B2 — Persistent host budget and URL guard (F6, F15)

- **Host budget.** `net.Fetcher`'s failure budget is reconstructed from `requests.jsonl`, using the recorded
  `failure_class` and `recorded_at`, when the fetcher is created. A new process cannot reset it. Keep the
  window and limit already in `net.py`. A host with a recorded 403 stays refused outside a named campaign,
  as today.
- **URL guard.** `claimstone/urlguard.py`: `check(url, resolver=socket.getaddrinfo)`.
  - http/https only.
  - Resolve the host, and refuse unless **every** resolved address is global. Use `ipaddress`: no
    loopback, private, link-local, multicast, reserved, unspecified, or the metadata address 169.254.169.254.
  - Excluded hosts are refused.

  `Fetcher` follows redirects manually and calls `check` on **every hop**, recording each hop as today.

**Tests:** a fake resolver for each refused class; a redirect from a public to a private address is refused
at the hop; a budget exhausted in one `Fetcher` holds in a fresh `Fetcher` over the same store. Nothing real
is contacted.

### B3 — Signature authentication field (F16)

- `adjudications.jsonl` rows written from now on carry:
  - `adjudication_version: 2`;
  - `signer_auth`: `"cli-declared"` from the CLI, `"portal-session"` from the control server;
  - `actor`: the operator id from the portal; `null` from the CLI.

  `adjudicated_by` keeps its meaning: the CLI's free text, or the operator's display name from the portal.
- Old rows have no `adjudication_version`. They are read as version 1, `signer_auth: "cli-declared"`.
  Never rewrite them.
- `synthesize.adjudicate` gains keyword parameters `signer_auth` and `actor`, both required with no default,
  so no caller can omit them silently. Update the CLI call.
- The read API's adjudication card exposes `signer_auth`. Update `api_schema.py`, the schema and the
  fixtures.

**Tests:** old rows read as v1; CLI rows say `cli-declared`; the field is required.

### B4 — Control server, operators, sessions

- `claimstone control [--projects DIR] [--store DIR] [--bind 127.0.0.1] [--port 8790] [--allow-host H]`.
  Refuse a non-loopback bind unless `--allow-host` names the proxy authority, as `api` does.
- **Operators.** `claimstone operator add ID --name "Display name"` prompts for a password twice
  (`getpass`) and appends to `operators.jsonl`:
  - `{operator_version, id, name, scrypt params, salt, hash, created_at}`, using `hashlib.scrypt` with
    n=2^15, r=8, p=1;
  - `operator disable ID` appends a disabling row.

  No password ever appears in arguments, logs or responses.
- **Sessions.**
  - `POST /control/v1/session` with `{id, password}`:
    - constant-time comparison;
    - 5 failures per id per 15 minutes → 429;
    - on success, a 32-byte random token in an HttpOnly, SameSite=Strict, Path=/ cookie (`Secure` when
      behind HTTPS), and a separate CSRF token in the JSON body.
  - Sessions live in server memory and expire after 12 hours of inactivity; a restart logs everyone out.
  - `DELETE` is not used: logout is `POST /control/v1/session/end`.
  - `GET /control/v1/session` returns `{operator: {id, name}, csrf_token}` or 401.
- **Re-authentication.** Credential writes (B11) require the password again in the request.

**Tests:** login and logout; a wrong password; rate limit; CSRF missing or wrong; Origin missing or foreign;
cookie flags; non-loopback refused; every POST route listed by the server refuses an anonymous request.
The last test must cover routes added by later steps automatically.

### B5 — Signing from the web, with drafts

- `POST /control/v1/p/{project}/flows/{flow_id}/q/{question_id}/adjudicate` with
  `{verdict, rationale, profile_sha256, attest: true}`:
  - resolves the flow to its selector;
  - calls `synthesize.adjudicate` under the project lock with `by` = operator display name,
    `signer_auth="portal-session"` and `actor` = operator id;
  - `attest` must be the literal `true`;
  - `verdict` must be one of `cli.VERDICT_NAMES`, and an operational question → 409 with the engine's
    sentence;
  - returns the stored row.

  There is no "opened N of M" check; the design keeps it a reading aid.
- **Drafts.**
  - `PUT` is not used: `POST …/q/{question_id}/draft` with `{rationale, profile_sha256}` appends to
    `drafts.jsonl`.
  - `GET …/q/{question_id}/draft` returns the operator's latest draft and whether its `profile_sha256` is
    still current.
  - Drafts are never read by the engine, never exported and never count as a signature.

**Tests:** happy path in a tmp store; stale profile → 409; provisional → 409; rationale under 120 trimmed
characters → 422; no session → 401; a draft survives a profile change and reports `current: false`.

### B6 — Profile difference (read API)

`GET /api/v1/p/{project}/flows/{flow_id}/q/{question_id}/profile-diff?from={sha}&to={sha}`, read-only, in
`api.py`.
- Both hashes are looked up in `profiles.jsonl`.
- The response lists results added, removed and changed, keyed by their stable result id (annotation id, or
  claim id plus review id), with the reason for each change when the rows record one, e.g. a gate version.
- It also gives per-relation counts before and after, and per-class counts.

A hash not in the ledger → 404. Update the schema and fixtures.

**Tests:** identical hashes → empty diff; one result losing its review → removed with its reason.

### B7a — Material intake: references, DOIs, links

- `POST /control/v1/p/{project}/flows/{flow_id}/intake` with `{kind: "doi"|"url"|"reference", value,
  note?}`.
  - DOI: normalise (`ids.py`).
  - URL: `urlguard.check` before anything else.
  - Reference: stored as text, flagged for identity resolution.
- **Cohort routing**, decided by the server and returned before anything counts:
  - if the flow's round is frozen (a closed manifest or cohort), a new work cannot join it. The item either
    matches an existing candidate, in which case it is a copy or version and goes to identity resolution,
    or it is recorded as `NEEDS_NEW_ROUND` with the open flows it could go to;
  - if the round is open, the item becomes an intake candidate for that round's next discover. **Do not run
    discover.**
- A URL item may be fetched **once**, by the explicit route `POST …/intake/{intake_id}/fetch`. It goes
  through `Fetcher` (robots, budget, guard on every hop) and is recorded in `requests.jsonl`. A fetched PDF
  continues as in B7b.
- `intake.jsonl` rows: `{intake_version, intake_id, flow_id, kind, value, state, stage, reason, links,
  actor, recorded_at}`.
  - `state` ∈ RECEIVED, CHECKING, DUPLICATE, POSSIBLE_VERSION, NEEDS_NEW_ROUND, REJECTED, READY,
    COUNTED, REPORTED_SEPARATELY.
  - A state change is a new row, never an edit.
- `GET /control/v1/p/{project}/flows/{flow_id}/intake` lists items with their latest state.

**Tests:** a DOI matching a candidate → POSSIBLE_VERSION or a copy link; a new work into a frozen round →
NEEDS_NEW_ROUND and no candidate row; a private URL → 422 with no request made; the same DOI twice →
DUPLICATE.

### B7b — Material intake: files, quarantine, and the floor policy (F14)

- `POST /control/v1/p/{project}/flows/{flow_id}/intake/file?target={candidate_id}`:
  - the body is the file bytes, `Content-Type: application/pdf` (or the supplement types the normalize stage
    accepts), at most 50 MiB;
  - bytes are hashed while streamed and written to `quarantine/<sha256>.<ext>`;
  - identical bytes already held (`raw/` or `quarantine/`) → DUPLICATE, "same file, nothing added", and
    nothing new is stored.
- **Checks** reuse the engine's own gates; no new heuristics:
  - magic bytes;
  - the existing "is this a document" content gate used for downloads;
  - identity against the target candidate's metadata (title, DOI, authors), using the same comparison
    `source_selection` uses for identity counterparts.

  A mismatch → POSSIBLE_VERSION, which opens an identity decision via `source_selection`'s identity API,
  never a merge, or REJECTED with the reason.
- **On pass:**
  - bytes move to `raw/<sha256>.<ext>`;
  - one `acquisitions.jsonl` row is appended with `provenance: "operator-supplied"`, an empty `attempts`
    list and an unknown licence kept unknown, following the `store-reuse` precedent in
    `docs/contracts/acquisitions.md`. Document that value there.
- **Floor policy**, declared by the project and never decided per card. `sources.yaml` may declare
  `supplied_copies: count | separate`; the default is `separate`.
  - Add it to `config.py` validation and to the protocol digest, so changing it is drift.
  - `separate`: admissibility excludes `operator-supplied` rows from the floor numerator and reports them on
    their own line.
  - `count`: they count like any confirmed copy.
  - The denominator never changes. **Do not edit any file under `projects/`**: tests build their own
    project.
- **Not done here:** normalising the new copy. It is listed as ready for the next scoped normalize run.

**Tests:**
- duplicate bytes;
- wrong-identity file → POSSIBLE_VERSION and an identity observation, with no acquisition row;
- passing file under `separate` → floor rate unchanged and a separate line;
- under `count` → numerator +1;
- the policy is in the digest;
- a 51 MiB body → 413 with nothing written.

### B8 — Operator decisions: identity, retry campaigns, purchase offers

- **Identity.** `POST …/identity/{observation_id}/resolve` with
  `{answer: "same_work"|"version_of"|"different"|"not_sure", reason}`.
  - The reason is required, ≥ 20 trimmed characters, except `not_sure`.
  - It appends through `source_selection`'s identity API, which already refuses silent merges.
  - Both records are kept; the count of independent studies is unchanged by `version_of`.
- **Retry campaign.** `POST …/decisions/retry-campaign` with `{candidate_ids, campaign_name, max_requests,
  hosts}`.
  - Server-side validation: the hosts are those recorded for those candidates, `max_requests` is bounded,
    excluded hosts are refused.
  - `GET …/decisions/retry-campaign/preview?candidate_ids=…` returns the exact plan, built by the same code.
  - The decision is recorded only. Execution is B12 or the CLI.
- **Purchase offer.**
  - `POST …/offers` with `{candidate_id, work_version, vendor, price, currency, tax_status?, terms_url,
    verified_at, resolves}` records an offer as *verified by the operator*.
  - `POST …/offers/{offer_id}/stage` with `{stage: "approved"|"bought_externally"|"declined"}` moves it.
    `copy_provided` and `copy_verified` are **set only by intake**, B7b linking an intake to the offer;
    never by hand.
  - A changed price, vendor or terms is a new offer; the old one becomes `obsolete`, linked.
  - A 403 is never an offer. Never infer one from an HTTP status.
- **Defer, decline, obsolete.** `POST …/decisions/{decision_id}/state` with `{state: "deferred"|"declined",
  until?, reason}`.
  - The row records what the decision blocked and what continues; the server computes both from the inbox
    model, not the client.
  - Declined work is never executed by anything.
- **Ordering (F13).** The decisions list is ordered by required/optional, then by acquisition metadata and
  frozen denominators, then by age. A test asserts that changing claims, reviews or stances does not change
  the order.

**Tests:** each route's validation; offer stages cannot skip to `copy_verified`; an offer change creates a
new offer; the ordering test; identity `version_of` leaves the study count unchanged.

### B9 — Today: seen markers and changes

- `POST /control/v1/seen` with `{project?, until}` appends to `seen.jsonl`.
- `GET /control/v1/today` returns, for the operator:
  - `changed` since their last marker, from ledger `recorded_at` values only (F17: no mtimes);
  - `needs_you`, split into required and optional, from the B8 model and the inbox;
  - `continues_without_you`: flows with work authorized and not blocked, empty until B12 exists, said so in a
    field rather than shown as an empty list that means "nothing".

**Tests:** a marker excludes older events; no marker → everything since the project began, with a
`first_visit: true` flag.

### B10 — Export from the web

- `POST /control/v1/p/{project}/flows/{flow_id}/exports` with `{include_pdfs: false}` calls `export.export`
  under the lock and returns `{export_id, created_now}`.
- `include_pdfs: true` adds only files whose recorded licence permits redistribution. An unknown licence is
  **excluded and listed**. The manifest records the rule and the excluded ids. This bumps `EXPORT_VERSION`
  only if the manifest shape changes.
- `POST …/exports/{export_id}/verify` runs `export.verify` and returns its problems list. It is never run as
  a side effect of a GET.
- Read API: `GET /api/v1/p/{project}/flows/{flow_id}/exports` lists `exports.jsonl` rows (read-only).

**Tests:** create twice → `created_now: false`; verify after an append → no problems; verify after a
tampered output → a problem; unknown licence excluded and listed.

### B11 — Administration actions

- `POST /control/v1/admin/check` with `{target: "llamacpp"|"ollama-cloud"|"grobid"}`:
  - a single unpaid reachability request: llamacpp `/health`, ollama-cloud model list, GROBID
    `/api/isalive`;
  - timeout 5 s, descriptive User-Agent with contact;
  - appends to `admin_checks.jsonl` with `{target, ok, status, latency_ms, checked_at, actor}`.

  `GET /control/v1/admin` returns `admin_state` plus the latest check per target.
- **Credentials.** `POST /control/v1/admin/credential` with `{name, value, password}`:
  - `name` must be one of the names in `admin_state`; re-authentication is required;
  - writes `.env` atomically (temp file plus `os.replace`), mode 0600, preserving other lines;
  - the response and every log line contain the name only.

  There is no GET that returns a value.
- **Not built:** the paid test call. It needs the model-call boundary and a cost reservation, so it belongs to
  the scheduler (B12). The route returns 501 with that sentence.

**Tests:**
- a check against a local stub server (tmp port, loopback is allowed **only** here and only via an explicit
  test hook);
- a credential write keeps the other lines and sets mode 0600;
- the value never appears in any response;
- a wrong password → 403.

### B12 — Scheduler-facing routes (conditional)

**Precondition:** the scheduler track has committed an operations ledger module implementing
`docs/contracts/scheduler_operations.md`: replay, idempotent append, `authorized`, `stopping` events.

**If it does not exist when this step starts, mark B12 `BLOCKED`, write why, and end the session.** Do not
implement the operations ledger here: it belongs to the scheduler track.

If it exists:
- `POST …/operations/{plan_id}/authorize` appends `authorized` with the operator, the exact `plan_id` and the
  limits it shows. An authorization cannot enlarge the plan.
- `POST …/operations/{operation_id}/pause` appends `stopping`.
- `POST …/operations/{operation_id}/resume` appends a new authorization over the remaining units only, with
  the cumulative ceiling.
- `GET …/operations` returns state, worker last heartbeat, last completed unit, and spent, reserved and
  remaining per authorization.

An expired lease is `INTERRUPTED`, shown as "Status being checked".

### B13 — Containers and records

- `compose.yaml`: a `control` service.
  - Same image; command `claimstone control`.
  - Store and the state dir mounted read-write; `projects` mounted `:ro`.
  - Loopback-published only, on the `portal_internal` network plus egress for B7a/B11.
  - nginx in `web` proxies `/control/` to it with the same security headers.

  The `api` service is unchanged and still `:ro`.
- Register the new version constants; regenerate schema and fixtures; finish the decision entry of B0 with
  the measured test counts; add a dated `HANDOFF.md` paragraph.

## 3. Operator policies this work enforces and does not choose

| policy | where it is declared | default until declared |
|---|---|---|
| supplied copies count toward the floor | `sources.yaml: supplied_copies` | `separate` |
| who records "bought externally" | any authenticated operator, recorded with `actor` | — |
| evidence of possession | only an intake that passes B7b sets `copy_verified` | — |
| PDFs with unknown licence in exports | excluded and listed | excluded |

## 4. Out of scope

- Project creation and protocol revision from the web. They write `projects/`, which needs its own decision.
- The scheduler executor.
- The paid test call.
- Any frontend change. The React pages that use these routes come after this backend, in a separate prompt.
