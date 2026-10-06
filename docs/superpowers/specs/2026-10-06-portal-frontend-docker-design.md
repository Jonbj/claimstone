# Research portal: separate frontend and container packaging

**Status:** evaluation plus implementation spec. Nothing in this document is implemented.
**Decision (2026-10-06):** option E, TypeScript + SvelteKit static. The operator delegated the choice;
it is reversible because §3 and §5 do not depend on it. Implementation is delegated step by step
through `2026-10-06-portal-frontend-glm-prompt.md`, one step per session, with a commit per sub-task.
**Date:** 2026-10-06.
**Asked by the operator:** stop generating the portal's HTML from Python, choose a real frontend
language, and package everything in Docker Compose: a backend API container, a frontend container,
GROBID, and whatever else is needed.
**Builds on:** `2026-10-06-research-portal-implementation-review.md` (I1–I15, now fixed) and D82.

---

## 1. Evaluation

### 1.1 What the stdlib HTML portal costs today (measured)

- `claimstone/portal.py` is about 950 lines of HTML assembled in f-strings, with escaping done by
  hand at every interpolation. It works and is tested (H-T5), but every new view is HTML written
  in Python with no components, no types and no client-side state.
- `/` and `/inbox` take about 29 s on the real store (implementation review I4). The page cannot
  render anything until the whole server computation is done. A client that loads each project and
  selector **lazily, in parallel** solves this without a cache.
- P3/P4 bring forms: intake, offer decisions, the signing workbench. Hand-written HTML forms with
  CSRF tokens in f-strings would multiply the surface I13-style mistakes come from.

### 1.2 Options

| option | for | against | verdict |
|---|---|---|---|
| **A. Keep server-rendered Python HTML** | no Node toolchain; one process | the costs in §1.1; the operator explicitly does not want it | rejected |
| **B. Python templates + HTMX** | small; little JS | still HTML from Python; needs a template engine (a new Python dependency, against CLAUDE.md "no framework"); weak typing between API and view | rejected |
| **C. TypeScript + React (Vite)** | largest ecosystem | largest dependency tree and runtime; more code per view | viable |
| **D. TypeScript + Vue 3 (Vite)** | mature, readable templates | middle-sized tree | viable |
| **E. TypeScript + Svelte 5 / SvelteKit with `adapter-static`** | compiles to small static files with no runtime server; components with typed props; fewest dependencies of C–E; static output works with a strict CSP (`script-src 'self'`) | younger ecosystem than React | **recommended** |

**Recommendation: E, TypeScript + SvelteKit, built as a static single-page app** (`adapter-static`,
`ssr = false`, `prerender = false`, fallback `index.html`). Three reasons:

1. **There is no Node server in production.** nginx serves files, so the only running code that
   reads the store is the Python API. That keeps the trust boundary where it is today.
2. **The dependency tree is smaller than with React.** This matters because the repository is public
   and the data is not. A smaller tree is less supply-chain surface. The lockfile is committed and
   the install is `npm ci --ignore-scripts`.
3. **Types end to end.** TypeScript types are generated from the API's JSON Schema, and the schema is
   generated from the Python side (§3.4).

The choice of framework is reversible: everything in §3 (API, schema, compose) is
framework-independent. If the operator prefers Vue or React, only §4 changes.

### 1.3 Constraints this must respect (from CLAUDE.md, compose.yaml and D7)

- **The engine stays stdlib.** The API is the existing `http.server` code with JSON only:
  - no FastAPI or Flask;
  - no new Python dependency.

  D7's "dependencies behind a process boundary" is exactly what a separate frontend container is.
  Node and npm never enter the Python image.
- **The API is not "a service per stage".** `compose.yaml` refuses an HTTP boundary between stages.
  The API is a **read model over the ledgers**, like `serve` today. Stages still run as the
  `claimstone` CLI job and still write through files. This is recorded in D83 (§6).
- **Read-only is structural.** The API container mounts `store/` and `projects/` **read-only**
  (`:ro`). A code path that tried to write would fail with `EROFS`, not succeed silently. This is
  stronger than the in-process guarantee and costs nothing.
- **One code identity (D42).** The API runs from the **same image** as the CLI job, built from the
  same `Dockerfile`, so the portal and the stages cannot run different code. The image carries
  `CLAIMSTONE_CODE_REVISION` as a build argument because `.git` is not in the image.
- **No secrets in the frontend.** The admin view receives booleans only (A-T1). The frontend image
  contains no environment values. `.env` is read only by the API and the CLI containers.
- **The privacy rule.** No image contains `store/` or `projects/` (`.dockerignore` already excludes
  `store/`). The frontend build must not embed project names or data. It is generic and fetches
  everything at runtime.

---

## 2. Target architecture

```
                 host 127.0.0.1:8788
                        │
                 ┌──────▼──────┐   static SPA (built TS/Svelte)
                 │    web      │   nginx-unprivileged, CSP, no data
                 │  (nginx)    │── /api/* ──┐
                 └─────────────┘            │  network: portal (internal)
                                     ┌──────▼──────┐
                                     │    api      │  claimstone api (stdlib, JSON only)
                                     │ same image  │  store:ro  projects:ro
                                     └─────────────┘
   ┌─────────────┐                   ┌─────────────┐
   │ claimstone  │  CLI job (cli)    │   grobid    │  network: claimstone (internal)
   │ store:rw    │──────────────────▶│  pinned     │
   └─────────────┘                   └─────────────┘
```

- `web` is the only service with a published port, bound to **127.0.0.1** on the host.
- `api` has no published port. It is reachable only from `web` on the `portal` network.
- `claimstone` (the CLI job) and `grobid` are unchanged. The portal does not depend on GROBID.

---

## 3. Backend: `claimstone api` (Python, stdlib)

### 3.1 New module `claimstone/api.py`

- Reuses `portal_state` for every computation. It must contain **no HTML**.
- Reuses the transport rules from `portal._Handler`, by factoring them into a shared base class:
  - GET only, `405` otherwise;
  - the Host/Origin checks, including `--allow-host`;
  - the security headers;
  - lookup-never-path parameters.

  `portal.py` and `api.py` share that base. Do not copy the code.
- CLI: `claimstone api [--projects-dir projects] [--store store] [--host 127.0.0.1] [--port 8788]
  [--allow-host NAME[:PORT] ...]`. A non-loopback `--host` prints `dashboard.host_warning`, as
  `portal` does.
- Every response is `application/json; charset=utf-8` with `Cache-Control: no-store`,
  `X-Content-Type-Options: nosniff` and `Content-Security-Policy: default-src 'none'; frame-ancestors
  'none'`.
- Every response body carries `"api_version": 1`.

### 3.2 Routes (all GET, prefix `/api/v1`)

Selector paths: `flows/{flow_id}` for a bound flow, `unbound/{slug}` for an unbound selector. The slug
grammar is from `portal_state.selector_slug`: `-` is the whole store, and a `~manifest` suffix marks
`manifest_only`.

| route | source | cost |
|---|---|---|
| `/meta` | code revision, `instrument_versions()`, `api_version`, server start time | cheap |
| `/projects` | per project: name, config state/error, registry version + short sha, registry drift text, flows (`flow_id`, title, selector, `selector_label`, `binding_state`, `bound_after_data`), unbound selectors (`slug`, `label`, selector) | **cheap**: no `compute()` |
| `/projects/{p}/integrity` | `portal_state.integrity` | medium |
| `/projects/{p}/activity?limit=` | `round_state.activity(store, limit)` | medium |
| `/projects/{p}/poll` | `round_state.cheap_state` | cheap |
| `/projects/{p}/{sel}/summary` | floor status, verdict counts, inbox counts by category. One `compute()` | expensive |
| `/projects/{p}/{sel}/overview` | `portal_state.flow_overview` | expensive |
| `/projects/{p}/{sel}/inbox` | `inbox_cards` as dicts | expensive |
| `/projects/{p}/{sel}/questions/{qid}` | `question_detail` | expensive |
| `/projects/{p}/{sel}/claims/{claim_id}` | `lineage` | medium |
| `/projects/{p}/{sel}/sources/{candidate_key}` | `source_dossier` | medium |
| `/admin` | `admin_state` (booleans only) | cheap |

The cheap `/projects` route is what fixes I4. The frontend renders the list at once, then requests
each `summary` in parallel and fills the cards as they arrive. It shows a "computing…" state, never
a zero.

### 3.3 Error envelope

`{"api_version": 1, "error": {"code": CODE, "message": TEXT}}`:

| code | HTTP | when |
|---|---|---|
| `BAD_REQUEST` | 400 | a malformed query parameter (e.g. a non-integer `limit`) |
| `NOT_FOUND` | 404 | unknown project, flow, slug, question, claim or source |
| `CONFIG_ERROR` | 409 | `ConfigError` (message = the error text) |
| `REGISTRY_DRIFT` | 409 | `RegistryDrift` (message = the error text) |
| `LEDGER_CORRUPT` | 500 | `LedgerCorrupt` (message = the error text: it names the ledger and line) |
| `MISDIRECTED` | 421 | Host check failed |
| `CROSS_ORIGIN` | 403 | Origin check failed |
| `INTERNAL` | 500 | anything else; the message is the exception **class name only** |

A 500 never carries a body that could be read as data. The frontend renders every error code as a
named state, never as an empty table.

### 3.4 Contract: JSON Schema generated from Python

- New `tools/build_portal_api_schema.py` writes `docs/contracts/portal-api.schema.json`. It writes
  one JSON Schema (draft 2020-12) per route payload, built from hand-declared Python dicts in a new
  `claimstone/api_schema.py`. A Python test checks the committed file is current, by regenerating it
  in memory and comparing.
- New `tests/test_api_contract.py` validates every route's response against the schema using a
  **minimal stdlib validator** in the test file. It covers `type`, `required`, `properties`, `enum`,
  `items` and `additionalProperties: false` on the top level of each payload. No `jsonschema`
  dependency.
- The frontend generates `web/src/lib/api-types.ts` from the schema with
  `json-schema-to-typescript` (devDependency) in `npm run gen:types`. CI and `npm run check` fail if
  the generated file differs from the committed one.
- **Meaning stays on the server.** The API sends display-ready semantic fields. The frontend must
  render them verbatim and never re-derive them:
  - `failure_display` (F19);
  - `selector_label`;
  - card `cause` and `note`;
  - the floor panel `sentences` and `disclosure`;
  - `direction_count_note`;
  - the verdict vocabulary as an enum.

### 3.5 Tests (Python)

| id | asserts |
|---|---|
| A1 | every route in §3.2 answers 200 on the `build_workspace` fixture, and the store is byte-identical afterwards |
| A2 | each payload validates against `portal-api.schema.json`; the committed schema equals the regenerated one |
| A3 | error envelope and status for each code in §3.3 (unknown flow → 404 `NOT_FOUND`; edited question under the same version → 409 `REGISTRY_DRIFT`; interior-corrupt ledger → 500 `LEDGER_CORRUPT`) |
| A4 | `/projects` performs no `compute()` (monkeypatch counter = 0) |
| A5 | `/admin` contains no credential value (same assertions as A-T1) |
| A6 | non-GET → 405; foreign Host → 421; foreign Origin → 403; `--allow-host api:8788` admits exactly that |
| A7 | **read-only under a read-only mount**: run every route against a fixture store with all files and directories `chmod`ed read-only (restore in `finally`); everything answers 200 |

---

## 4. Frontend: `web/` (TypeScript + SvelteKit static)

### 4.1 Layout

```
web/
  package.json            pinned versions; scripts: dev, build, check, test, gen:types
  package-lock.json       committed
  svelte.config.js        adapter-static, fallback "index.html"
  vite.config.ts          dev proxy /api → http://127.0.0.1:8788
  tsconfig.json           strict
  src/
    app.html
    lib/
      api.ts              typed fetch wrapper; maps the error envelope to ApiError(code, message)
      api-types.ts        GENERATED from docs/contracts/portal-api.schema.json — do not edit
      vocabulary.ts       verdict and state words → CSS class; never a new word
      components/
        StageStrip.svelte  FloorPanel.svelte  QuestionMatrix.svelte  InboxCards.svelte
        Lineage.svelte     SourceDossier.svelte  IntegrityPanel.svelte  ErrorState.svelte
        CommandBlock.svelte   (shows a CLI command + "copy" button; never executes)
        Chip.svelte  Fraction.svelte  Pending.svelte
    routes/
      +layout.ts            export const ssr = false; export const prerender = false;
      +layout.svelte        header: breadcrumb, "read-only derived view", code revision, theme toggle
      +page.svelte          index: /projects at once, then /summary per selector in parallel
      inbox/+page.svelte    per project, lazily, grouped by project then category
      admin/+page.svelte
      p/[project]/+page.svelte                         integrity, flows, unbound selectors, activity
      p/[project]/[kind=selkind]/[sel]/+page.svelte    overview (kind = "f" | "u")
      p/[project]/[kind=selkind]/[sel]/q/[qid]/+page.svelte
      p/[project]/[kind=selkind]/[sel]/claim/[claim]/+page.svelte
      p/[project]/[kind=selkind]/[sel]/source/[key]/+page.svelte
    params/selkind.ts       matches "f" | "u"
  tests/                    vitest unit tests (§4.4)
  Dockerfile                multi-stage: node build → nginx-unprivileged
  nginx.conf
```

### 4.2 Rules the UI must keep. These are the invariants as they appear on a screen.

1. **No zero for an unknown.** `null` renders as "—" with the "not knowable" title. A pending fetch
   renders `Pending`. An error renders `ErrorState` with the code. Never `0`.
2. **Per class before pooled.** `QuestionMatrix` renders `claims_by_class`, then the total.
3. **Five verdicts, plus the engine outcome kept apart.** `vocabulary.ts` maps exactly
   `SUPPORTED`, `CONTRADICTED`, `CONTESTED_IN_LITERATURE`, `UNANSWERED_IN_LITERATURE` and
   `NEVER_ASKED`. `NO_VERIFIED_CLAIM` and `LITERATURE_VERDICT_NOT_APPLICABLE` are rendered dashed, as
   engine states. An unknown string renders as itself, in a neutral chip. It is **never** mapped to
   a verdict.
4. **No verdict input of any kind.** No form, select or button sets a verdict. `CommandBlock` shows
   the adjudicate command with its placeholders and a copy button. There is no `fetch` with a method
   other than GET anywhere in `src/` (test F3).
5. **Display text verbatim.** `failure_display`, `cause`, `note`, `sentences`, `disclosure` and
   `selector_label` are rendered exactly as received.
6. **Cards in server order.** The UI does not sort, rank or filter inbox cards except by an
   explicit operator-chosen category filter. Server order is the F13 rule.
7. **Colour never carries meaning alone.** Every chip has its word. Light and dark themes are both
   legible.
8. **Live updates:** poll `/projects/{p}/poll` every 3 s on project-scoped pages. When the ledgers
   signature changes and the tab is visible, re-fetch the current view's data (not a full reload).
9. **No external origin.** No CDN, no web font and no analytics. Everything is bundled.

### 4.3 Dockerfile and nginx

- Build stage: `node:22-alpine@sha256:<digest>`, running `npm ci --ignore-scripts`,
  `npm run gen:types` with a check that the output is unchanged, then `npm run check`, `npm test`
  and `npm run build`.
- Runtime stage: `nginxinc/nginx-unprivileged:1.27-alpine@sha256:<digest>`, listening on 8080 as a
  non-root user. Copy `build/` to `/usr/share/nginx/html`.
- `nginx.conf`:
  - `try_files $uri /index.html;`
  - `location /api/ { proxy_pass http://api:8788; proxy_set_header Host api:8788;
    proxy_set_header Origin ""; proxy_read_timeout 120s; }`
  - headers on every response:
    - `Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self';
      img-src 'self' data:; connect-src 'self'; font-src 'self'; base-uri 'none';
      form-action 'none'; frame-ancestors 'none'`
    - `X-Content-Type-Options nosniff`
    - `Referrer-Policy no-referrer`
    - `Cache-Control no-store` for `index.html` only (hashed assets may be cached)
  - no `server_tokens`.
- The `Origin` header is blanked when proxying because the browser's origin is `web`, which the API
  does not need to know. The DNS-rebinding defence moves to nginx: `server_name localhost 127.0.0.1;`
  plus a default server returning 421 for any other Host.

### 4.4 Frontend tests (vitest)

| id | asserts |
|---|---|
| F1 | `vocabulary.ts`: `NO_VERIFIED_CLAIM` is not mapped to `UNANSWERED_IN_LITERATURE` or `NEVER_ASKED`; an unknown word stays itself |
| F2 | `QuestionMatrix` renders per-class counts before the total (DOM order) |
| F3 | a source scan of `src/` finds no `method:` other than GET and no `<form>`. Strip comments before matching (HANDOFF's "grep matches the comment" lesson) |
| F4 | `Fraction` with `null` renders "—", never "0"; `Pending` while loading |
| F5 | `ErrorState` renders each §3.3 code with its message; `LEDGER_CORRUPT` is never an empty table |
| F6 | `CommandBlock` copies text and has no execute affordance; the adjudicate placeholder `<ONE_OF_FIVE>` survives rendering |
| F7 | `InboxCards` preserves server order |
| F8 | `api-types.ts` is up to date with the schema (`gen:types` produces no diff) |

Fixtures come from a new `tools/build_portal_fixtures.py`. It builds the `build_workspace` fixture in
a temporary directory, calls each `portal_state` function and writes JSON to `web/tests/fixtures/`.
The fixtures are committed. A Python test checks they are current.

---

## 5. Compose

Changes to `compose.yaml`. Keep every existing comment and service. Add:

```yaml
  api:
    build:
      context: .
      args:
        UID: ${UID:-1000}
        GID: ${GID:-1000}
        CLAIMSTONE_CODE_REVISION: ${CLAIMSTONE_CODE_REVISION:-unknown}
    image: claimstone:local          # the same image the CLI job runs (D42: one code identity)
    profiles: [portal]
    command: ["api", "--host", "0.0.0.0", "--port", "8788", "--allow-host", "api:8788"]
    environment:
      CLAIMSTONE_ROOT: /app
      CLAIMSTONE_CODE_REVISION: ${CLAIMSTONE_CODE_REVISION:-unknown}
    volumes:
      - ./store:/app/store:ro       # read-only is structural: a write would fail with EROFS
      - ./projects:/app/projects:ro
    user: "${UID:-1000}:${GID:-1000}"
    networks: [portal]
    read_only: true
    tmpfs: [/tmp]
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8788/api/v1/meta', headers={'Host':'api:8788'}), timeout=4); sys.exit(0 if r.status==200 else 1)"]
      interval: 15s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  web:
    build: ./web
    profiles: [portal]
    depends_on:
      api:
        condition: service_healthy
    ports:
      - "127.0.0.1:${CLAIMSTONE_PORTAL_PORT:-8788}:8080"   # loopback only; never 0.0.0.0
    networks: [portal]
    read_only: true
    tmpfs: [/tmp, /var/cache/nginx]
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    restart: unless-stopped

networks:
  portal:
    driver: bridge
    internal: false   # web must publish a port; api is reachable only through web
```

Also:

- `claimstone` (CLI) gets `image: claimstone:local`, so `api` and the job share one image.
- `Dockerfile`:
  - add `ARG CLAIMSTONE_CODE_REVISION` and `ENV CLAIMSTONE_CODE_REVISION=...`;
  - set `ENV CLAIMSTONE_ROOT=/app` (`tools/` and `docs/` are already copied).
- A new `portal.sh` mirrors `claimstone.sh`. It refuses without `.env`, exports
  `CLAIMSTONE_CODE_REVISION="$(git rev-parse HEAD)$(git diff --quiet || echo -dirty)"`, then runs
  `docker compose --profile portal up -d --build --wait` and prints the URL. `./portal.sh down` stops
  it.
- `.dockerignore`: add `web/node_modules/` and `web/build/`. `projects/` is already excluded from
  the images by never being copied; add `projects/*/` to the ignore list too, so the build context
  never carries real instances.
- GROBID stays out of the `portal` profile. The portal reads what normalize already wrote.

---

## 6. Decision entry D83 (to write in `DESIGN_DECISIONS.md`)

Title: `## D83 — A typed frontend over a read-only JSON API, packaged as containers (2026-10-06)`.

It must state:

- why server-rendered Python HTML is retired for new views (§1.1, with the 29 s measurement), and
  that `claimstone portal` and `claimstone serve` stay until the SPA reaches parity;
- why the API is a read model and not a stage service. This is consistent with `compose.yaml`'s
  refusal of a service per stage;
- that Node and npm live only in the frontend image, behind a process boundary (D7). The Python
  engine stays stdlib plus its three dependencies;
- the read-only mount as the structural guarantee, and test A7;
- `portal_api_version 1`, registered in `tools/check_instrument_versions.py` as
  `("claimstone/api.py", "API_VERSION", "portal_api_version")`. The API's payload shape is what the
  operator reads, so it is versioned like an instrument.

---

## 7. Implementation order and acceptance

| step | content | acceptance |
|---|---|---|
| 1 | Factor the shared transport base out of `portal.py`; add `claimstone/api.py`, `api_schema.py`, the CLI command and tests A1–A7 | `pytest` green; `claimstone api` answers every route on a tmp workspace |
| 2 | `tools/build_portal_api_schema.py`, the committed schema, `tools/build_portal_fixtures.py` and the committed fixtures | currency tests green |
| 3 | `web/` scaffold, types generation, components, routes, vitest F1–F8 | `npm ci && npm run check && npm test && npm run build` succeed |
| 4 | `web/Dockerfile`, `nginx.conf`, compose services, `portal.sh`, Dockerfile args | `./portal.sh` brings `api` and `web` up healthy; `curl -s 127.0.0.1:8788/` serves the SPA; `curl -s 127.0.0.1:8788/api/v1/projects` returns JSON; `curl -H 'Host: evil' ...` returns 421; `docker compose exec api touch /app/store/x` fails with a read-only error |
| 5 | Manual parity check against `claimstone portal` on a tmp copy of a store: same figures on index, flow, question, lineage and dossier | parity notes in the progress log |
| 6 | D83, `docs/README.md` map, HANDOFF paragraph, `AGENTS.md` "what this machine needs" line for Node (frontend only) | `check_instrument_versions.py` exit 0 |

**Out of scope:** any write route, authentication, intake forms and the signing workbench. These
stay P3/P4 and are blocked by the findings listed in the design review. The frontend architecture is
chosen so that they *can* be added later as POST routes with CSRF tokens behind nginx. None is added
now.
