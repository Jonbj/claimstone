You are implementing one step of a multi-step feature in the Claimstone repository. **Perform
exactly one step, the next one not yet done, then stop and report.** Do not ask me questions. When
something is unspecified, make the smallest decision that keeps every existing test passing and the
seven invariants in `CLAUDE.md` intact, record it in the progress log, and continue.

## The work

The specification is `docs/superpowers/specs/2026-10-06-portal-frontend-docker-design.md`. It is the
authority; read it in full every time. The framework decision is made: **TypeScript + SvelteKit with
`adapter-static`**.

## Read first, every time

1. `CLAUDE.md` (invariants: non-negotiable) and `AGENTS.md`
2. the spec above, in full
3. `docs/superpowers/specs/2026-10-06-research-portal-implementation-review.md`, which records what
   the current portal does and why
4. the progress log `docs/superpowers/plans/2026-10-06-portal-frontend-progress.md`. If it does not
   exist, create it: run the three checks below and record their output as the baseline.
5. `claimstone/portal.py`, `claimstone/portal_state.py`, `claimstone/cli.py`, `compose.yaml`,
   `Dockerfile`, `claimstone.sh`, and the tests `tests/test_portal.py` and
   `tests/test_portal_state.py`. `build_workspace` is the fixture to reuse.

## Steps. Do the first one the log does not mark DONE.

| step | content (spec section) | done when |
|---|---|---|
| **S1** | Factor the shared transport out of `portal.py` into a base class used by both: GET-only, Host/Origin with `--allow-host`, headers, lookup-never-path. Add `claimstone/api.py` with every `/api/v1` route (§3.2), the error envelope (§3.3) and `API_VERSION = 1`. Add the `claimstone api` CLI command. Add tests A1–A7 (§3.5) in `tests/test_api.py`. `portal.py` behaviour stays identical: its tests must pass unchanged. Do **not** register `API_VERSION` in `tools/check_instrument_versions.py` yet (that happens in S6). | the three checks pass; `claimstone api` answers every route on a tmp workspace |
| **S2** | Add `claimstone/api_schema.py`, `tools/build_portal_api_schema.py`, the committed `docs/contracts/portal-api.schema.json`, the minimal stdlib validator and contract test A2 (§3.4). Add `tools/build_portal_fixtures.py` and the committed `web/tests/fixtures/*.json`, plus a currency test for both. | the three checks pass |
| **S3** | Scaffold `web/` per §4.1, with exact pinned versions in `package.json` and a committed `package-lock.json`. Add: `svelte.config.js`, `vite.config.ts` (dev proxy), strict `tsconfig.json`, the `gen:types` script and generated `api-types.ts`, `api.ts`, `vocabulary.ts`, the base components (`Chip`, `Fraction`, `Pending`, `ErrorState`, `CommandBlock`), `+layout.ts` / `+layout.svelte` with header and theme, and vitest tests F1, F4, F5, F6 and F8 (§4.4). | `cd web && npm ci && npm run check && npm test && npm run build` succeed; the three checks pass |
| **S4** | Every route and remaining component of §4.1: index with lazy per-selector summaries, project, overview, question, lineage, dossier, inbox, admin, and 3 s polling. Follow every rule in §4.2. Add vitest F2, F3 and F7. | the S3 web commands succeed; the three checks pass |
| **S5** | `web/Dockerfile` and `web/nginx.conf` (§4.3); the `api` and `web` services and the `portal` network in `compose.yaml` (§5), keeping every existing comment and service; `Dockerfile` args and env; `portal.sh`; `.dockerignore`. Pin both base images by digest (`docker pull`, then `docker image inspect --format '{{index .RepoDigests 0}}'`). | every acceptance command in §7 step 4, with its output recorded; `./portal.sh down` afterwards |
| **S6** | Parity check (§7 step 5) between `claimstone portal` and the SPA on a **tmp copy** of a store built from test fixtures, never the real store. Write D83 (§6) in `docs/DESIGN_DECISIONS.md`, register `("claimstone/api.py", "API_VERSION", "portal_api_version")`, and update `docs/README.md`, `AGENTS.md` (Node is needed only to build the frontend) and a dated `HANDOFF.md` paragraph. | the three checks pass; `check_instrument_versions.py` counts one more instrument |

## The three checks, after every step

```bash
.venv/bin/pytest -q
.venv/bin/claimstone validate --all-projects
.venv/bin/python tools/check_instrument_versions.py
```

From S3 on, also run: `cd web && npm run check && npm test && npm run build`.

## Hard constraints. These override any instinct to be helpful.

- **No git commits, branches, stashes, resets or checkouts.** The working tree holds uncommitted work
  by others. Leave all changes uncommitted.
- **Never write to, repair or delete anything under `store/`, and never modify `projects/`.** Tests
  use `tmp_path`. Any server or container you start for a check must use a tmp store built from
  `tests.test_portal_state.build_workspace`. One exception: S5's acceptance may bring the compose
  `portal` profile up against the real `store/`, because it is mounted **read-only** (`:ro`). Before
  that, verify the `:ro` flags in `compose.yaml`. Afterwards, run `./portal.sh down`.
- **Network:** only the npm registry (for `npm ci` / `npm install`) and Docker Hub (for base images).
  No scholarly API, no publisher, no model backend. Never run `acquire`, `discover`, `normalize`,
  `extract`, `review`, `synthesize`, `adjudicate`, `model-run` or `./claimstone.sh`.
- **No new Python dependency.** The API stays stdlib. Node and npm exist only under `web/` and in the
  frontend image.
- **The frontend writes nothing.** No form, no non-GET `fetch`, no verdict input. Display texts from
  the API are rendered verbatim (§4.2).
- Never weaken, skip, delete or rewrite an existing test to make it pass. If an existing test fails
  because of your change, the change is wrong.
- Never invent figures. Every number written in docs or in the log is copied from output you ran.
- If the same failure survives three distinct fix attempts, re-read the spec section, choose the
  simplest design that satisfies its stated purpose, and record the deviation. If something is truly
  impossible, mark it **NOT DONE** with the reason and finish the rest of the step.

## Progress log: `docs/superpowers/plans/2026-10-06-portal-frontend-progress.md`

Append one section per step, in this format:

```
### S<n> — DONE | PARTIAL
Files added/changed: …
Tests added: …
Checks: <exact final lines of each command>
Decisions (spec silent): …
Deviations: …
NOT DONE: …
```

Mark a step DONE only when its "done when" column holds. If you run out of budget mid-step, mark it
PARTIAL and list exactly what remains, so the next run resumes there.

## Final message

Reply with:
- which step you did and whether it is DONE or PARTIAL;
- the final lines of each check;
- the files you created or changed;
- the decisions and deviations;
- which step is next.

Keep it under half a page. Do not claim anything you did not verify by running it.
